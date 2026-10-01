"""
Sunny Narrator - AI-powered book translation tool.

Translates books with a dual-LLM architecture (translate LLM + proofread LLM).
FB2/TXT go through the classic pipeline in this module; DOCX/EPUB/PDF are
routed to src/calibre_pipeline.py.

Usage:
    python app.py [--output-format ...]   # config from .env, see cli()
"""

import os
import sys
import signal
import time
import warnings
import base64
import logging
import json
from datetime import datetime
from typing import Dict, List

# Suppress FutureWarning from transformers/torch interaction.
# This warning is triggered by torch.utils._pytree._register_pytree_node
# during import of transformers. It's harmless but noisy in logs.
# Kept targeted to this specific message to avoid hiding other warnings.
warnings.filterwarnings("ignore", category=FutureWarning,
                       message=".*torch.utils._pytree._register_pytree_node.*")

# Import local modules
import src.utils as ta
import src.xmlcheck as xc
import src.fb2_handler as fb2
import src.epub_handler as epub
import src.txt_handler as txt
from src.config import Config
from src.synopsis_manager import SynopsisManager
from src.llm_logger import init_llm_logger
from src.vocabulary_manager import get_vocabulary_manager, DictionaryCreatedSignal, VocabularyManager
from src.character_registry import get_character_registry, reset_character_registry
from src.epub_writer import create_epub_from_fb2
from src.xml_utils import IMAGE_EXTENSIONS, sniff_image_type
from src.checkpoint_manager import CHECKPOINT_VERSION, compute_fingerprint
from src.fb2_structure import (
    close_dangling_sections,
    sanitize_translated_chunk,
    section_transition,
)

# Initialize configuration
config = Config()

# Setup logging
logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize LLM logger if enabled
if config.llm_logging_enabled:
    init_llm_logger(log_dir=config.llm_logging_dir, enabled=True)
    logger.info(f"LLM logging enabled. Logs will be written to: {config.llm_logging_dir}/")

# =============================================================================
# Translation Engine
# =============================================================================

class _StaleCheckpoint(Exception):
    """A checkpoint that does not describe the chunk list about to be translated.

    Raised and handled entirely within main()'s resume block: it exists only
    to skip the restore without indenting the whole success path, and it is
    reported to the user before it is raised.
    """


class TranslationEngine:
    """
    Main translation engine with context management and recursive processing.

    Features:
    - Dual-LLM pipeline (translate for translation, proofread for quality)
    - Synopsis management for chunk context
    - Vocabulary management for terminology consistency
    - Character tracking for gender-aware translation
    - XML validation and repair
    """

    def __init__(self, output_tfile: str, book_path: str = None):
        self.output_tfile = output_tfile
        self.book_path = book_path
        self.total_source_len = 0
        self.total_target_len = 0
        self.last_processed_chunk = -1
        self.last_section_idx = 0
        self.last_chunk_idx = 0
        self.start_time = datetime.now()
        # Set by main() once the chunk list exists; written into every
        # checkpoint so a resume can prove it refers to the same slicing.
        self.checkpoint_fingerprint = None
        # _tfile_size follows every write to output_tfile; _tfile_committed
        # only moves together with last_processed_chunk and is what the
        # checkpoint stores, so a checkpoint taken between the two (signal
        # handler) never claims a chunk it does not list as processed.
        self._tfile_size = 0
        self._tfile_committed = 0

        # Statistics counters
        self.stats = {
            'successful': 0,
            'failed': 0,
            'total_tokens': 0,
            'retry_tokens': 0,
        }

        # Expected translation length ratio is learned per book
        ta.length_calibration.reset()

        # Character registry (shared between synopsis and vocabulary)
        reset_character_registry()
        self.character_registry = get_character_registry()

        # Synopsis manager with character registry integration
        self.synopsis_manager = SynopsisManager(character_registry=self.character_registry)

        # Vocabulary manager for dictionary handling
        self.vocab_manager = None
        if book_path:
            self.vocab_manager = get_vocabulary_manager(book_path, dict_file=config.dictionary)

        # Per-chunk vocabulary cache: compute once per chunk, reuse for
        # entries/dict/formatted (previously rebuilt 3-4x per chunk)
        self._vocab_cache_key = None
        self._vocab_cache_entries = None
        self._vocab_cache_formatted = None

    def get_vocab_entries_for_chunk(self, chunk: str, s_idx: int, c_idx: int) -> List:
        """
        Get vocabulary entries for chunk (full VocabEntry objects).
        
        Returns List[VocabEntry] with source, target, category, gender, notes.
        The underlying get_vocab_for_chunk() is computed ONCE per chunk and
        cached; dict and formatted variants reuse the same result.
        """
        if not self.vocab_manager:
            logger.warning("vocab_manager not initialized - returning empty entries")
            return []

        return self._load_vocab_for_chunk(chunk, s_idx, c_idx)

    def _load_vocab_for_chunk(self, chunk: str, s_idx: int, c_idx: int) -> List:
        """
        Compute vocabulary for chunk once and cache it.
        
        Key includes chunk text so any chunk changes self-invalidate.
        Logs a single line per chunk (previously one per accessor call).
        """
        key = (s_idx, c_idx, chunk)
        if key != self._vocab_cache_key:
            entries = self.vocab_manager.get_vocab_for_chunk(chunk, s_idx, c_idx)
            self._vocab_cache_key = key
            self._vocab_cache_entries = entries
            self._vocab_cache_formatted = None  # invalidate formatted cache

            # Single log line per chunk
            if not entries:
                logger.info(f"Chunk {s_idx}-{c_idx}: No matching vocabulary terms")
            elif config.debug:
                logger.debug(f"Vocab entries for chunk {s_idx}-{c_idx}: {len(entries)} terms")
            else:
                logger.info(f"Vocabulary: {len(entries)} terms for chunk {s_idx}-{c_idx}")

        return self._vocab_cache_entries

    def get_vocab_dict_for_chunk(self, chunk: str, s_idx: int, c_idx: int) -> Dict[str, str]:
        """
        Get vocabulary dict for chunk (source -> target mapping).
        
        Used for auto-substitution in source_text.
        """
        entries = self.get_vocab_entries_for_chunk(chunk, s_idx, c_idx)
        return {entry.source: entry.target for entry in entries}

    def get_formatted_vocab_for_chunk(self, chunk: str, s_idx: int, c_idx: int) -> str:
        """
        Get vocabulary formatted for specific model.
        
        Returns vocabulary as formatted string (source = target, category, gender, notes)
        for display/presentation purposes.
        
        Args:
            chunk: Text chunk to match vocabulary against
            s_idx: Section index
            c_idx: Chunk index
            
        Returns:
            Formatted vocabulary string
        """
        if not self.vocab_manager:
            logger.warning("vocab_manager not initialized - returning empty vocabulary")
            return ""
        
        entries = self._load_vocab_for_chunk(chunk, s_idx, c_idx)
        
        if not entries:
            # Empty vocab is valid for chunks without dictionary terms
            return ""
        
        # Format once per chunk (cache reuses it across loop + translate_chunk)
        if self._vocab_cache_formatted is None:
            self._vocab_cache_formatted = self.vocab_manager.format_for_model(entries, config.model_translate)
        
        return self._vocab_cache_formatted

    def translate_chunk(self, source_text: str, context: str, s_idx: int = 0, c_idx: int = 0) -> tuple:
        """
        Translate a single chunk using dual-LLM pipeline.

        Args:
            source_text: Text to translate (with XML tags)
            context: Synopsis from previous chunks
            s_idx: Section index (for vocabulary matching)
            c_idx: Chunk index (for vocabulary matching)

        Returns:
            (translated_text, synopsis)
        """
        try:
            # Note: rechunking is now handled inside ta.translate_chunk()
            # Get vocabulary for this chunk (dict for translation)
            vocab_dict = self.get_vocab_dict_for_chunk(source_text, s_idx, c_idx)
            formatted_vocab = self.get_formatted_vocab_for_chunk(source_text, s_idx, c_idx)

            # Get full VocabEntry objects for rich format
            entries = self.get_vocab_entries_for_chunk(source_text, s_idx, c_idx)

            if config.debug:
                logger.debug(f"Vocab dict: {len(vocab_dict)} terms, formatted: {len(formatted_vocab)} chars")
                logger.debug(f"Vocab entries: {len(entries)} full objects")
            
            characters = []
            translation, synopsis = ta.translate_chunk(
                source_lang=config.source_lang,
                target_lang=config.target_lang,
                source_text=source_text,
                outline_text=context,
                vocab_dict=vocab_dict,
                vocab_entries=entries,
                country=config.country,
                style='xml',
                fast_mode=config.fast_trans,
                depth=0,  # Start at depth 0
                character_sink=characters
            )

            if translation is None:
                raise ValueError("Translation returned None")

            if self.vocab_manager:
                self.vocab_manager.record_character_genders(characters)

            return translation, synopsis

        except Exception as e:
            logger.error(f"Translation error: {e}")
            raise

    def process_chunk_recursive(self, chunk: str, s_idx: int, c_idx: int,
                                 g_id: int, context: str, depth: int = 0) -> tuple:
        """
        Translate chunk with XML validation.

        Note: Length-based rechunking is now handled inside ta.translate_chunk()

        - Translates plain text with XML tags
        - Post-processes XML via validation
        - Retries on XML validation failure
        """
        source_text = chunk if isinstance(chunk, str) else str(chunk)
        source_len = len(source_text)

        # Initialize variables
        final_content = ""
        synopsis = ""
        retry_count = 0

        # Count source tokens once (before retry loop)
        source_tokens = ta.num_tokens_in_string(source_text)

        # Retry loop for XML validation
        for attempt in range(3):
            try:
                # Rechunking happens inside translate_chunk automatically
                temp_content, synopsis = self.translate_chunk(source_text, context, s_idx, c_idx)

                if temp_content:
                    final_content = self._post_process_xml(source_text, temp_content)

                    if config.debug and attempt > 0:
                        logger.debug(f"XML validation passed on attempt {attempt + 1}")

                    # Count retry tokens if not first attempt
                    if attempt > 0:
                        retry_tokens = ta.num_tokens_in_string(temp_content)
                        self.stats['retry_tokens'] += retry_tokens

                    break

            except Exception as e:
                logger.warning(f"Translation attempt {attempt + 1} failed: {e}")
                retry_count += 1
                if attempt < 2:  # Don't sleep after last attempt
                    backoff = 2 ** attempt  # 1s, 2s
                    logger.info(f"Retrying chunk {g_id} in {backoff}s...")
                    time.sleep(backoff)

        else:
            # All retries failed — return visible placeholder instead of silent empty string
            logger.warning(f"All validation attempts failed for chunk {g_id}")
            final_content = f"<p>[TRANSLATION FAILED: chunk {g_id}]</p>"
            self.stats['failed'] += 1
            return final_content, synopsis

        # Empty result is a failure, not a success
        if not final_content or not final_content.strip():
            logger.warning(f"Empty translation result for chunk {g_id}")
            self.stats['failed'] += 1
            return f"<p>[TRANSLATION FAILED: chunk {g_id}]</p>", synopsis

        # Count successful translation
        self.stats['successful'] += 1

        # Count total tokens (source + target) after successful translation
        target_tokens = ta.num_tokens_in_string(final_content)
        self.stats['total_tokens'] += source_tokens + target_tokens

        # Log length statistics (no rechunking here - done in translate_chunk)
        target_len = len(final_content)
        percent_diff = abs(target_len - source_len) / source_len * 100 if source_len > 0 else 0

        if config.debug:
            logger.debug(f"Chunk {g_id} (depth {depth}): {source_len} → {target_len} chars ({percent_diff:.1f}%)")

        return final_content, synopsis

    def _post_process_xml(self, source_text: str, translated_text: str) -> str:
        """
        Fix XML structure of one translated chunk, locally.

        Chunks are balanced by construction (see fb2_structure), so anything
        unbalanced in the LLM answer is the LLM's fault and is repaired right
        here, at the spot it broke, instead of being patched at the end of the
        book. Never drops text.
        """
        return sanitize_translated_chunk(translated_text)

    def _append_tfile(self, output_tfile: str, text: str):
        with open(output_tfile, 'a', encoding='utf-8') as f:
            f.write(text)
        self._tfile_size = os.path.getsize(output_tfile)

    def process_all_chunks(self, all_chunks: list, vocab: dict, output_tfile: str,
                           checkpoint_file: str = None, section_meta: list = None) -> str:
        """
        Process all chunks sequentially and write them out as a section tree.

        Every translated chunk is appended to output_tfile right away, so the
        file is always a prefix of the finished body (only the closers of the
        currently open sections are missing) and a crash loses at most the
        chunk in flight. Section tags are produced here from section_meta
        (open tag + depth per unit, see fb2_structure.prepare_body_structure)
        and never by the LLM, so the tree is balanced by construction.
        Without section_meta every unit is a flat top-level <section>.

        Args:
            all_chunks: List of chunk dicts with metadata
            vocab: Vocabulary dictionary
            output_tfile: Temp output file path
            checkpoint_file: Path to checkpoint JSON file (optional)
            section_meta: Per-unit {'open_tag', 'depth', 'chunks'} (optional)

        Returns:
            The whole translated body as written to output_tfile (on a resume
            too: earlier chunks are already in the file)
        """
        total = len(all_chunks)

        logger.info(f"Starting translation: {total} chunks")
        print(f"\n{'='*60}")
        print(f"Starting translation: {total} chunks")
        print(f"{'='*60}\n")

        def unit_meta(s_idx: int) -> dict:
            if section_meta and s_idx < len(section_meta):
                return section_meta[s_idx]
            return {'open_tag': '<section>', 'depth': 1}

        first_gid = all_chunks[0]['global_id'] if all_chunks else 0
        if first_gid > 0 and self.last_processed_chunk >= 0:
            # Resume: output_tfile already holds everything up to the last
            # processed chunk, including the tags of the sections still open.
            emitted_unit = self.last_section_idx
            cur_depth = unit_meta(emitted_unit)['depth']
        else:
            emitted_unit, cur_depth = -1, 0
            if first_gid == 0:
                # A fresh run must not append to a leftover file of an old run.
                open(output_tfile, 'w', encoding='utf-8').close()
                self._tfile_size = self._tfile_committed = 0

        def emit(text: str):
            if text:
                self._append_tfile(output_tfile, text)

        # The last chunk of the book (known from the per-unit chunk counts)
        # is committed together with the tail, so a checkpoint that says
        # "every chunk is done" always describes a finished file.
        book_end = None
        if section_meta and all('chunks' in m for m in section_meta):
            filled = [i for i, m in enumerate(section_meta) if m['chunks']]
            if filled:
                book_end = (filled[-1], section_meta[filled[-1]]['chunks'] - 1)
        tail_written = False

        def emit_tail():
            # Units after the last chunk (sections without text) and the
            # closers of whatever is still open.
            if section_meta:
                enter_units(len(section_meta) - 1)
            emit('</section>\n' * cur_depth)

        def enter_units(upto: int):
            nonlocal emitted_unit, cur_depth
            while emitted_unit < upto:
                emitted_unit += 1
                text, cur_depth = section_transition(unit_meta(emitted_unit), cur_depth)
                emit(text)

        for item in all_chunks:
            chunk = item['chunk']
            s_idx = item['section_idx']
            c_idx = item['chunk_idx']
            g_id = item['global_id']

            # Get formatted vocabulary
            formatted_vocab = self.get_formatted_vocab_for_chunk(chunk, s_idx, c_idx)
            vocab_count = len(formatted_vocab.split('|' if 'hunyuan' in config.model_translate.lower() else '\n')) if formatted_vocab else 0

            # Progress output
            preview = (chunk[:80] + '...') if len(chunk) > 80 else chunk
            print(f"\n[Chunk {g_id+1}/{total}] Section {s_idx+1}.{c_idx+1} | {len(chunk)} chars | Vocab: {vocab_count}")
            print(f"  Source: {preview}")

            # Get synopsis context
            context = self.synopsis_manager.get_synopsis(s_idx, c_idx)

            # Translate
            final_content, synopsis = self.process_chunk_recursive(chunk, s_idx, c_idx, g_id, context)

            # Update synopsis manager
            self.synopsis_manager.add_chunk_result(s_idx, c_idx, final_content, generated_synopsis=synopsis)

            # Progress output
            result_preview = (final_content[:80] + '...') if len(final_content) > 80 else final_content
            print(f"  Result: {result_preview}")

            # Empty result is a failure - fail fast instead of silently dropping the chunk
            if not final_content or not final_content.strip():
                raise RuntimeError(f"Empty translation result for chunk {c_idx} in section {s_idx}")

            # Statistics
            self.total_source_len += len(chunk)
            self.total_target_len += len(final_content)

            enter_units(s_idx)
            emit(final_content.strip() + "\n")
            if (s_idx, c_idx) == book_end:
                emit_tail()
                tail_written = True

            # Update last processed chunk
            self.last_processed_chunk = g_id
            self.last_section_idx = s_idx
            self.last_chunk_idx = c_idx
            self._tfile_committed = self._tfile_size

            # Save checkpoint after each chunk
            if checkpoint_file:
                self.save_checkpoint(checkpoint_file)

            # DEBUG: Print stats after each chunk
            if config.debug:
                length_diff = len(final_content) - len(chunk) if final_content else 0
                length_diff_pct = (length_diff / len(chunk) * 100) if chunk and len(chunk) > 0 else 0
                print(f"  [✓] {len(chunk)} → {len(final_content):,} chars ({length_diff_pct:+.1f}%) | Successful: {self.stats['successful']}/{self.stats['failed'] + self.stats['successful']}")

        if book_end is None and not tail_written:
            # No chunk counts (flat sections) or a book without any text
            emit_tail()
            self._tfile_committed = self._tfile_size

        # Warn if too many chunks failed
        total_processed = self.stats['successful'] + self.stats['failed']
        if total_processed > 0 and self.stats['failed'] / total_processed > 0.1:
            print(f"\n⚠️ WARNING: {self.stats['failed']}/{total_processed} chunks failed to translate!")
            logger.warning(f"High failure rate: {self.stats['failed']}/{total_processed} chunks failed")

        with open(output_tfile, encoding='utf-8') as f:
            return f.read()

    def save_checkpoint(self, checkpoint_file: str):
        """
        Save translation progress to checkpoint file (atomic write).

        Args:
            checkpoint_file: Path to checkpoint JSON file
        """
        checkpoint = {
            "version": CHECKPOINT_VERSION,
            "fingerprint": self.checkpoint_fingerprint,
            "book_path": self.book_path,
            "last_chunk": self.last_processed_chunk,
            "last_section_idx": self.last_section_idx,
            "last_chunk_idx": self.last_chunk_idx,
            "tfile_size": self._tfile_committed,
            "stats": self.stats,
            "lengths": {
                "total_source_len": self.total_source_len,
                "total_target_len": self.total_target_len
            },
            "synopsis_history": self.synopsis_manager.synopsis_cache,
            "created_at": self.start_time.isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        # Atomic write (temp + rename)
        temp_file = checkpoint_file + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, checkpoint_file)
            logger.debug(f"Checkpoint saved: {checkpoint_file}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def restore_from_checkpoint(self, checkpoint: dict):
        """
        Restore translation state from checkpoint.

        Args:
            checkpoint: Checkpoint dict loaded from JSON

        Raises:
            ValueError: the translated-output file no longer matches the
                checkpoint, so resuming would silently lose or duplicate text.
        """
        expected_size = checkpoint.get("tfile_size")
        if expected_size:
            actual_size = os.path.getsize(self.output_tfile) if os.path.exists(self.output_tfile) else 0
            if actual_size < expected_size:
                raise ValueError(
                    f"{self.output_tfile} holds {actual_size} bytes but the checkpoint "
                    f"expects {expected_size}: previously translated text is missing")
            if actual_size > expected_size:
                logger.warning(f"Cutting {actual_size - expected_size} bytes of an unfinished "
                               f"chunk from {self.output_tfile}")
                os.truncate(self.output_tfile, expected_size)
        self._tfile_size = self._tfile_committed = expected_size or 0

        self.stats = checkpoint.get("stats", self.stats)
        self.total_source_len = checkpoint.get("lengths", {}).get("total_source_len", 0)
        self.total_target_len = checkpoint.get("lengths", {}).get("total_target_len", 0)
        self.last_processed_chunk = checkpoint.get("last_chunk", -1)
        self.last_section_idx = checkpoint.get("last_section_idx", 0)
        self.last_chunk_idx = checkpoint.get("last_chunk_idx", 0)

        # Restore synopsis history. synopsis_cache getter stores JSON-safe
        # "section_X" string keys, so the dict can be passed through as-is.
        synopsis_history = checkpoint.get("synopsis_history", {})
        if synopsis_history:
            self.synopsis_manager.synopsis_cache = synopsis_history

        logger.info(f"Restored from checkpoint: chunk {self.last_processed_chunk + 1}, "
                   f"successful: {self.stats['successful']}, failed: {self.stats['failed']}")


# =============================================================================
# Utility Functions
# =============================================================================

def write_to_file(data, output_file: str, auto_repair_fb2: bool = False,
                  known_errors: list = None):
    """Write data to file.

    With auto_repair_fb2 the text goes through fb2_repair.repair_if_needed
    first. That only touches a book which fails schema validation, keeps the
    result only if the text is unchanged and the error count drops, and fixes
    unbalanced tags where they occur instead of at the end of the book.
    known_errors: validate_fb2() result for data, if the caller already has it.
    """
    if isinstance(data, str):
        data = [data]

    content = '\n'.join(data)

    if auto_repair_fb2:
        from src.fb2_repair import repair_if_needed
        content, notes = repair_if_needed(content, errors=known_errors)
        for note in notes:
            logger.info(f"FB2 auto-repair: {note}")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)


def resolve_classic_output_format(cli_value, config_value: str) -> str:
    """Output format for the classic (FB2/TXT) pipeline: fb2 or epub.

    An explicit --output-format that the classic pipeline cannot write is an
    error; a leftover OUTPUT_FORMAT (e.g. docx meant for another book) only
    falls back to fb2 with a warning.
    """
    value = (cli_value or config_value or 'fb2').lower()
    if value in ('fb2', 'epub'):
        return value
    if cli_value:
        raise ValueError(f"FB2/TXT input can only be written as fb2 or epub, not {value}.")
    logger.warning(f"OUTPUT_FORMAT={value} is not available for FB2/TXT input; writing fb2.")
    print(f"Warning: OUTPUT_FORMAT={value} is not available for FB2/TXT input; writing fb2.")
    return 'fb2'


def build_resume_paths(myfile: str, target_lang: str) -> dict:
    """Build output paths for a translation run.

    checkpoint_file and output_tfile are deterministic (no timestamp) so a
    new run can find the previous checkpoint and resume. The final output
    file keeps a timestamp so finished books don't overwrite each other.
    """
    file_name, _ = os.path.splitext(os.path.basename(myfile))
    output_dir = os.path.dirname(myfile) or '.'
    timestamp = datetime.now().strftime("%H%M-%d%m")
    stable_base = f"{output_dir}/{file_name}_{target_lang}"
    output_base = f"{stable_base}_{timestamp}"
    return {
        "output_file": f"{output_base}.{config.output_format}",
        "output_tfile": f"{stable_base}_tmp.fb2",
        "checkpoint_file": f"{stable_base}.checkpoint.json",
    }


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main translation workflow."""
    # Graceful shutdown handler. Engine/checkpoint refs are filled later;
    # if a signal arrives before that, there is nothing to save yet.
    _shutdown_state = {"engine": None, "checkpoint_file": None}

    def _handle_shutdown(signum, frame):
        engine = _shutdown_state.get("engine")
        checkpoint_file = _shutdown_state.get("checkpoint_file")
        if engine is not None and checkpoint_file:
            logger.warning(f"Received signal {signum}, saving checkpoint...")
            try:
                engine.save_checkpoint(checkpoint_file)
            except Exception as e:
                logger.error(f"Failed to save checkpoint on signal {signum}: {e}")
        else:
            logger.warning(f"Received signal {signum}, exiting (checkpoint not available yet)...")
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    # cli() has already done this; main() may also be called on its own and
    # must never write FB2 XML into a file named .pdf/.docx
    config.output_format = resolve_classic_output_format(None, config.output_format)

    # Check input file
    myfile = config.myfile
    if not os.path.exists(myfile):
        print(f"File not found: {myfile}")
        sys.exit(1)  # H8: error path must exit non-zero

    # Prepare paths
    file_name, file_ext = os.path.splitext(os.path.basename(myfile))
    output_dir = os.path.dirname(myfile) or '.'
    if file_ext.lower() not in ['.fb2', '.txt']:
        print(f"Error: Unsupported format: {file_ext}")
        sys.exit(1)  # H8: error path must exit non-zero

    # Output paths
    _paths = build_resume_paths(myfile, config.target_lang)
    output_file = _paths["output_file"]
    output_tfile = _paths["output_tfile"]
    checkpoint_file = _paths["checkpoint_file"]
    _shutdown_state["checkpoint_file"] = checkpoint_file
    output_base = os.path.splitext(output_file)[0]  # used by EPUB writer/fallback

    # 1. Parse Input
    print(f"Parsing {file_ext.upper()} file...")
    if file_ext.lower() == '.fb2':
        body, header, footer = fb2.parse_xml(myfile)
    else:
        body, header, footer = txt.parse_txt(myfile)

    # 2. Vocabulary: created/loaded below by engine.vocab_manager.initialize()
    # (VocabularyManager — the same code path as the Calibre pipeline).
    vocab = {}

    # 3. Prepare Chunks
    print("Preparing chunks...")

    # prepare_body_structure keeps the original (nested) FB2 section tree:
    # sections = [[unit1_chunk1, unit1_chunk2], [unit2_chunk1], ...] and
    # section_meta = [{'open_tag', 'depth'}, ...] to rebuild the tree on output.
    sections, section_meta = fb2.prepare_body_structure(body, config.max_len_chunk)

    chunks = []
    gid = 0
    for s_idx, section in enumerate(sections):
        for c_idx, chunk in enumerate(section):
            chunks.append({
                'chunk': chunk,
                'section_idx': s_idx,
                'chunk_idx': c_idx,
                'global_id': gid
            })
            gid += 1

    print(f"Prepared {len(chunks)} chunks from {len(sections)} sections")

    # Identifies this exact chunk list. Computed before the resume block below,
    # which slices `chunks` down to the unprocessed tail.
    checkpoint_fingerprint = compute_fingerprint(
        (c['chunk'] for c in chunks),
        max_chunk_size=config.max_len_chunk,
        source_lang=config.source_lang,
        target_lang=config.target_lang,
        # The temp file holds the open tags of this exact section tree
        section_tree=json.dumps([[m['open_tag'], m['depth'], m['chunks']] for m in section_meta]),
    )

    # 4. Translate
    engine = TranslationEngine(output_tfile, book_path=myfile)
    engine.checkpoint_fingerprint = checkpoint_fingerprint
    _shutdown_state["engine"] = engine

    # Initialize content variable - will be populated during translation or loaded from temp file
    content = ""

    # Check for existing checkpoint and resume
    resume_from_chunk = 0
    if os.path.exists(checkpoint_file):
        print(f"\n{'='*60}")
        print(f"Checkpoint found: {checkpoint_file}")
        print("Resuming from previous session...")
        print(f"{'='*60}\n")

        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)

            # Progress is stored as "chunk N of the list", so resuming is only
            # safe while the list is unchanged. A checkpoint from a different
            # slicing (or one written before fingerprinting existed) would be
            # spliced onto boundaries it never belonged to and quietly corrupt
            # the book — see compute_fingerprint.
            if checkpoint.get("fingerprint") != checkpoint_fingerprint:
                reason = ("it predates checkpoint fingerprinting"
                          if not checkpoint.get("fingerprint")
                          else "the book no longer splits into the same chunks")
                logger.warning(f"Checkpoint cannot be resumed ({reason}); starting fresh")
                print(f"Checkpoint ignored ({reason}). Starting fresh.")
                os.remove(checkpoint_file)
                raise _StaleCheckpoint

            engine.restore_from_checkpoint(checkpoint)
            resume_from_chunk = checkpoint["last_chunk"] + 1
            chunks = chunks[resume_from_chunk:]

            if not chunks:
                print("All chunks already processed!")
                # Remove checkpoint and proceed to finalize
                os.remove(checkpoint_file)
                chunks = []  # Empty, skip translation loop
                # Load translated content from temp file
                if os.path.exists(output_tfile):
                    print(f"Loading translated content from {output_tfile}")
                    with open(output_tfile, 'r', encoding='utf-8') as f:
                        content = f.read()
            else:
                print(f"Resuming from chunk {resume_from_chunk + 1}/{len(chunks) + resume_from_chunk}")
        except _StaleCheckpoint:
            pass  # already reported above; fall through to a fresh run
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            print("Starting fresh (checkpoint ignored)")
    else:
        print("No checkpoint found, starting fresh.")

    # Vocabulary must be loaded on resume too: without it resumed chunks are
    # translated without dictionary terms (silent quality loss).
    if engine.vocab_manager:
        try:
            vocab = engine.vocab_manager.initialize()
            print(f"Vocabulary loaded: {len(vocab)} entries")
        except DictionaryCreatedSignal as e:
            print(f"\n📖 {e}")
            sys.exit(0)

    # Process chunks if any remain, or content was already loaded from temp file above
    if chunks:
        try:
            content = engine.process_all_chunks(chunks, vocab, output_tfile, checkpoint_file,
                                                section_meta=section_meta)
        finally:
            # Ensure checkpoint is saved on unexpected exit (signal handler triggers SystemExit)
            if checkpoint_file:
                engine.save_checkpoint(checkpoint_file)
                logger.info(f"Checkpoint saved: {checkpoint_file}")

    # 5. Metadata & Cover
    if header:
        print("Translating metadata...")
        metadata = fb2.extract_metadata(header)
        if metadata:
            target_code = config.lang_code_map.get(config.target_lang.lower(), config.target_lang)
            metadata['lang'] = target_code
            vocab_entries = list(engine.vocab_manager.vocab.values()) if engine.vocab_manager else []
            translated_meta = ta.translate_metadata(metadata, config.source_lang, config.target_lang, config.country,
                                                    vocab_entries=vocab_entries)
            if translated_meta:
                # The LLM translates values; the language code is not one of them.
                translated_meta['lang'] = target_code
                header = fb2.update_header_with_metadata(header, translated_meta)

    if config.api_key_images:
        print("Processing cover...")
        _cover_href, cover_data = fb2.get_cover_image(header, footer)
        if cover_data:
            cover_result = ta.process_image_request(cover_data, config.source_lang, config.target_lang, config.country)
            if cover_result:
                header, footer, body = fb2.replace_cover_image(header, footer, body, cover_result)
                try:
                    cover_bytes = base64.b64decode(cover_result)
                    ext = IMAGE_EXTENSIONS.get(sniff_image_type(cover_bytes), '.png')
                    # language marker: translations into other languages keep their own cover
                    with open(f"{output_dir}/{file_name}_{config.target_lang}_cover{ext}", 'wb') as f:
                        f.write(cover_bytes)
                except Exception as e:
                    logger.error(f"Cover save error: {e}")

    # 6. Finalize
    # Sections are emitted by code, so this only ever closes the tail of a
    # run that was cut off right before its closing tags were written.
    content = close_dangling_sections(content)
    xml_str = f"{header}<body>\n{content}</body>\n{footer}"

    # Validation
    errors = xc.validate_fb2(xml_str)
    if errors:
        print("WARNING: Validation errors:")
        for err in errors[:5]:  # Show first 5
            print(f"  {err}")

    # Write output
    if config.output_format == 'epub':
        try:
            final_output_path = create_epub_from_fb2(header, content, footer, output_base)
            print(f"\n✓ EPUB created: {final_output_path}")
        except Exception as e:
            logger.error(f"EPUB creation failed: {e}")
            final_output_path = f"{output_base}.fb2"
            write_to_file(xml_str, final_output_path, auto_repair_fb2=config.fb2_auto_repair,
                      known_errors=errors)
            print(f"\n✓ FB2 created (fallback): {final_output_path}")
    else:
        final_output_path = output_file
        write_to_file(xml_str, final_output_path, auto_repair_fb2=config.fb2_auto_repair,
                      known_errors=errors)
        print(f"\n✓ FB2 created: {final_output_path}")

    # Statistics + translation metrics report (shared with the Calibre
    # pipeline via src.utils.print_translation_report so both branches
    # print the same format instead of drifting apart).
    try:
        elapsed = (datetime.now() - engine.start_time).total_seconds()
        ta.print_translation_report(
            source_len=engine.total_source_len,
            target_len=engine.total_target_len,
            elapsed=elapsed,
            output_path=final_output_path,
        )
    except Exception as e:
        logger.error(f"Failed to print translation report: {e}")

    # Remove checkpoint after successful completion
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
        logger.info(f"Checkpoint removed: {checkpoint_file}")


def cli():
    """Command-line entry point (`python app.py`, `sunny-narrator`): parses
    arguments and routes the input file to the classic or Calibre pipeline."""
    import argparse

    parser = argparse.ArgumentParser(description='Sunny Narrator - AI book translator')
    parser.add_argument('--build-series-dict', type=str,
                       help='Build unified dictionary from books folder')
    parser.add_argument('--series-dict-output', type=str, default='series.dic',
                       help='Output file for series dictionary')
    # New: build dictionary for a single book
    parser.add_argument('--build-dict', type=str,
                       help='Build dictionary for a single book (path to FB2/EPUB/TXT)')
    parser.add_argument('--book-dict-output', type=str,
                       help='Output dictionary file for --build-dict (default: same name with .dic)')
    parser.add_argument('--min-count-ner', type=int, default=2,
                       help='Minimum occurrences for NER entities')
    parser.add_argument('--min-count-word', type=int, default=5,
                       help='Minimum occurrences for common words (only with --frequent-words)')
    parser.add_argument('--frequent-words', action='store_true',
                       help='--build-dict/--build-series-dict: also add frequent ordinary words, '
                            'not only named entities (default: DICT_FREQUENT_WORDS, off)')
    parser.add_argument('--output-format', type=str, default=None,
                       help='Output format. FB2/TXT input: fb2 or epub; DOCX/EPUB/PDF input: '
                            'docx, epub or pdf (default: OUTPUT_FORMAT from config)')
    parser.add_argument('--max-chunk-size', type=int, default=None,
                       help='Max chunk size in chars for DOCX/EPUB/PDF translation (default: MAX_LEN_CHUNK=8192 from config)')
    # Fast mode — shared across both pipelines
    parser.add_argument('--fast-mode', action='store_true',
                        help='Skip reflection/improve stages (both pipelines)')
    # Calibre pipeline resume control (see src/calibre_pipeline.py:run_pipeline)
    parser.add_argument('--fresh', action='store_true',
                        help='DOCX/EPUB/PDF only: ignore any existing translation '
                             'checkpoint/dump and translate from scratch')
    # Explicit vocabulary file — both pipelines
    parser.add_argument('--dictionary', type=str, default=None,
                        help='Explicit path to the .dic vocabulary file to use for '
                             'translation, overriding the automatic <book_name>.dic '
                             'lookup next to the source file (both pipelines). '
                             'Same as setting DICTIONARY in .env')

    args, unknown = parser.parse_known_args()
    if unknown:
        print(f"Warning: ignoring unknown arguments: {' '.join(unknown)}")

    # M12: validate --max-chunk-size (must be positive)
    if args.max_chunk_size is not None and args.max_chunk_size <= 0:
        print("Error: --max-chunk-size must be a positive integer", file=sys.stderr)
        sys.exit(1)

    # --dictionary overrides DICTIONARY from .env (both pipelines)
    if args.dictionary:
        config.dictionary = args.dictionary
    if config.dictionary:
        dict_dir = os.path.dirname(os.path.abspath(config.dictionary))
        if not os.path.isdir(dict_dir):
            print(f"Error: directory for DICTIONARY does not exist: {dict_dir}", file=sys.stderr)
            sys.exit(1)

    # Supported input formats (used by --build-dict validation and pipeline auto-detection)
    CALIBRE_INPUT_FORMATS = {'.docx', '.epub', '.pdf'}
    CLASSIC_INPUT_FORMATS = {'.fb2', '.txt'}

    # Handle series dictionary build
    if args.build_series_dict:
        from src.ner import create_series_vocab
        
        books_folder = args.build_series_dict
        output_file = args.series_dict_output
        
        print(f"Building series dictionary from: {books_folder}")
        print(f"Output: {output_file}")
        print(f"min_count_ner: {args.min_count_ner}, min_count_word: {args.min_count_word}")
        
        try:
            result = create_series_vocab(
                books_folder, 
                output_file,
                min_count_ner=args.min_count_ner,
                min_count_word=args.min_count_word,
                include_words=args.frequent_words or None,
            )
            print(f"Done: {result}")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        sys.exit(0)

    # Handle single book dictionary build
    if args.build_dict:
        book_path = args.build_dict
        if not os.path.exists(book_path):
            print(f"Error: Book file not found: {book_path}")
            sys.exit(1)
        # Determine output dict path
        dict_path = args.book_dict_output or f"{os.path.splitext(book_path)[0]}.dic"
        print(f"Building dictionary for book: {book_path}")
        print(f"Output dictionary: {dict_path}")
        # Parse book body (reuse same logic as main)
        _, file_ext = os.path.splitext(book_path)
        file_ext = file_ext.lower()
        # H1: reject unknown extensions instead of silently falling back to TXT
        if file_ext not in (CALIBRE_INPUT_FORMATS | CLASSIC_INPUT_FORMATS):
            print(f"Error: Unsupported input format: {file_ext}")
            print("Supported formats: FB2, TXT (classic), DOCX, EPUB, PDF (Calibre)")
            sys.exit(1)
        if file_ext == '.fb2':
            body, _, _ = fb2.parse_xml(book_path)
        elif file_ext == '.epub':
            body, _, _ = epub.parse_epub(book_path)
        elif file_ext == '.txt':
            body, _, _ = txt.parse_txt(book_path)
        else:
            # DOCX/PDF are Calibre-pipeline formats with no body parser here
            print(f"Error: --build-dict does not support {file_ext}. Use FB2, EPUB or TXT.")
            sys.exit(1)
        # Same builder as a translation run (NER + LLM, VocabularyManager)
        VocabularyManager(book_path, dict_file=dict_path).build_dictionary(
            body, min_count_ner=args.min_count_ner, min_count_word=args.min_count_word,
            include_words=args.frequent_words or None)
        print(f"Dictionary created: {dict_path}")
        sys.exit(0)
    
    # Auto-detect pipeline by input file extension (format sets defined above)
    import src.calibre_pipeline as cp

    # Determine input file
    input_file = config.myfile
    if input_file and not os.path.exists(input_file):
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)
    if not input_file:
        print("Error: No input file specified. Set FILE in .env")
        sys.exit(1)

    input_ext = os.path.splitext(input_file)[1].lower()

    if input_ext in CALIBRE_INPUT_FORMATS:
        # ---- Calibre-based pipeline ----
        # Default output: same as input (when config has classic-only 'fb2')
        _cfg_fmt = config.output_format
        if _cfg_fmt not in ('docx', 'epub', 'pdf'):
            _cfg_fmt = 'epub'
        output_format = args.output_format or _cfg_fmt
        output_format = output_format.lower()
        if output_format not in ('docx', 'epub', 'pdf'):
            print(f"Error: Unsupported output format: {output_format}. Use docx, epub or pdf.")
            sys.exit(1)

        print(f"Pipeline: Calibre-based (auto-detected)")
        print(f"Input: {input_file}")
        print(f"Output format: {output_format}")
        chunk_label = args.max_chunk_size or 'default'
        print(f"Chunk size: {chunk_label}")

        if not cp.check_calibre_installed():
            print("Error: Calibre (ebook-convert) is not installed.")
            print("Install it: https://calibre-ebook.com/download")
            sys.exit(1)

        run_start = datetime.now()
        stats = cp.TranslationStats()
        try:
            output_path = cp.run_pipeline(
                input_path=input_file,
                output_format=output_format,
                max_chunk_size=args.max_chunk_size,
                source_lang=config.source_lang,
                target_lang=config.target_lang,
                country=config.country,
                fast_mode=args.fast_mode,
                fresh=args.fresh,
                dict_file=config.dictionary,
                stats_out=stats,
            )
            print(f"\n✓ Pipeline complete: {output_path}")

            # Statistics + translation metrics report — same function and
            # format the classic FB2/TXT pipeline prints (src.utils.
            # print_translation_report), so both branches produce a
            # comparable report instead of the Calibre branch staying silent.
            elapsed = (datetime.now() - run_start).total_seconds()
            ta.print_translation_report(
                source_len=stats.total_source_len,
                target_len=stats.total_target_len,
                elapsed=elapsed,
                output_path=output_path,
            )
        except DictionaryCreatedSignal as e:
            # Same as the classic pipeline: stop so the new .dic can be reviewed
            print(f"\n📖 {e}")
            sys.exit(0)
        except Exception as e:
            print(f"\n✗ Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        sys.exit(0)

    elif input_ext in CLASSIC_INPUT_FORMATS:
        # ---- Classic FB2/TXT pipeline ----
        if args.fast_mode:
            config.fast_trans = True
        try:
            config.output_format = resolve_classic_output_format(args.output_format, config.output_format)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        print(f"Output format: {config.output_format}")
        main()
    else:
        print(f"Error: Unsupported input format: {input_ext}")
        print(f"Supported formats: DOCX, EPUB, PDF (Calibre pipeline), FB2, TXT (Classic pipeline)")
        sys.exit(1)



if __name__ == '__main__':
    cli()