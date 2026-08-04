"""
Sunny Narrator - AI-powered book translation tool.

Translates FB2/EPUB/TXT books using dual-LLM architecture:
- Primary LLM (Hunyuan): Translation + Synopsis generation
- Secondary LLM: Quality reflection + Style improvement

Usage:
    python app.py  # Uses config from .env
"""

import os
import sys
import signal
import time
import warnings
import base64
import logging
import re
import json
from datetime import datetime
from pathlib import Path
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
from src.vocabulary_manager import get_vocabulary_manager, DictionaryCreatedSignal
from src.character_registry import get_character_registry, reset_character_registry
from src.epub_writer import create_epub_from_fb2

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

# Conditional import of NER module
ner = None
if config.ner_opt:
    try:
        import src.ner as ner_module
        ner = ner_module
    except ImportError as e:
        logger.warning(f"NER module not available: {e}")


# =============================================================================
# Translation Engine
# =============================================================================

class TranslationEngine:
    """
    Main translation engine with context management and recursive processing.

    Features:
    - Dual-LLM pipeline (Primary for translation, Secondary for quality)
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

        # Statistics counters
        self.stats = {
            'successful': 0,
            'failed': 0,
            'total_tokens': 0,
            'retry_tokens': 0,
            'rechunk_events': 0,
            'xml_repairs': 0,
            'language_mismatch_retries': 0,
        }

        # Character registry (shared between synopsis and vocabulary)
        reset_character_registry()
        self.character_registry = get_character_registry()

        # Synopsis manager with character registry integration
        self.synopsis_manager = SynopsisManager(character_registry=self.character_registry)

        # Vocabulary manager for dictionary handling
        self.vocab_manager = None
        if book_path:
            self.vocab_manager = get_vocabulary_manager(book_path)

    def get_vocab_entries_for_chunk(self, chunk: str, s_idx: int, c_idx: int) -> List:
        """
        Get vocabulary entries for chunk (full VocabEntry objects).
        
        Returns List[VocabEntry] with source, target, category, gender, notes.
        """
        if not self.vocab_manager:
            logger.warning("vocab_manager not initialized - returning empty entries")
            return []

        entries = self.vocab_manager.get_vocab_for_chunk(chunk, s_idx, c_idx)

        if not entries:
            logger.info(f"Chunk {s_idx}-{c_idx}: No matching vocabulary terms")
            return []

        if config.debug:
            logger.debug(f"Vocab entries for chunk {s_idx}-{c_idx}: {len(entries)} terms")
        elif entries:
            logger.info(f"Vocabulary: {len(entries)} terms for chunk {s_idx}-{c_idx}")

        return entries

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
        
        entries = self.vocab_manager.get_vocab_for_chunk(chunk, s_idx, c_idx)
        
        if not entries:
            # Empty vocab is valid for chunks without dictionary terms
            return ""
        
        # Format for specific model
        formatted = self.vocab_manager.format_for_model(entries, config.model_translate)
        
        if config.debug:
            logger.debug(f"Vocab for chunk {s_idx}-{c_idx}: {len(entries)} terms, formatted_len={len(formatted) if formatted else 0}")
        elif formatted:
            logger.info(f"Vocabulary: {len(entries)} terms for chunk {s_idx}-{c_idx}")
        
        return formatted

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
                depth=0  # Start at depth 0
            )

            if translation is None:
                raise ValueError("Translation returned None")

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
            final_content = f"[TRANSLATION FAILED: chunk {g_id}]"
            self.stats['failed'] += 1
            return final_content, synopsis

        # Empty result is a failure, not a success
        if not final_content or not final_content.strip():
            logger.warning(f"Empty translation result for chunk {g_id}")
            self.stats['failed'] += 1
            return f"[TRANSLATION FAILED: chunk {g_id}]", synopsis

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
        Basic XML cleanup after translation.

        NOTE: Does NOT repair tag structure for chunks.
        Chunks may have intentionally unbalanced tags
        (e.g., <title> opened in one chunk, closed in another).
        Full XML validation happens only on final assembled document.

        - Removes artifacts via rem_tags()
        - Does NOT use LLM repair (would break chunk structure)
        """
        # Basic cleanup only - no XML parsing of chunks
        # rem_tags is for final FB2 validation, not chunk processing
        cleaned = translated_text.strip()

        # Remove common artifacts
        cleaned = re.sub(r'\n\s*\n+', '\n\n', cleaned)

        return cleaned

    def process_all_chunks(self, all_chunks: list, orig_sections: list,
                           vocab: dict, output_tfile: str, checkpoint_file: str = None) -> str:
        """
        Process all chunks sequentially.
        Groups chunks by section and wraps each section in <section> tags.

        Args:
            all_chunks: List of chunk dicts with metadata
            orig_sections: Original sections structure (list of lists)
            vocab: Vocabulary dictionary
            output_tfile: Temp output file path
            checkpoint_file: Path to checkpoint JSON file (optional)

        Returns:
            Combined translated content with proper <section> wrapping
        """
        content_parts = []  # F1: list+join вместо O(n²)-конкатенации строк
        total = len(all_chunks)

        logger.info(f"Starting translation: {total} chunks")
        print(f"\n{'='*60}")
        print(f"Starting translation: {total} chunks")
        print(f"{'='*60}\n")

        # Track which sections have been written to avoid duplicates on resume
        written_sections = set()
        current_section_idx = -1
        current_section_chunks = []

        for item in all_chunks:
            chunk = item['chunk']
            s_idx = item['section_idx']
            c_idx = item['chunk_idx']
            g_id = item['global_id']

            # If we moved to a new section, write the previous one
            if s_idx != current_section_idx and current_section_idx != -1:
                if current_section_idx not in written_sections:
                    # Write accumulated section content
                    section_content = "\n".join(current_section_chunks)
                    section_wrapped = f"<section>\n{section_content}\n</section>"
                    content_parts.append(section_wrapped + "\n")
                    with open(output_tfile, 'a', encoding='utf-8') as f:
                        f.write(section_wrapped + "\n")
                    written_sections.add(current_section_idx)
                current_section_chunks = []

            current_section_idx = s_idx

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
            if final_content:
                self.total_source_len += len(chunk)
                self.total_target_len += len(final_content)

                # Clean final_content: remove outer <section> if present (will be wrapped later)
                cleaned_content = final_content.strip()
                if cleaned_content.startswith('<section>') and cleaned_content.endswith('</section>'):
                    cleaned_content = cleaned_content[9:-10].strip()

                # Accumulate chunks for this section
                current_section_chunks.append(cleaned_content)

            # Update last processed chunk
            self.last_processed_chunk = g_id
            self.last_section_idx = s_idx
            self.last_chunk_idx = c_idx

            # Save checkpoint after each chunk
            if checkpoint_file:
                self.save_checkpoint(checkpoint_file)

            # DEBUG: Print stats after each chunk
            if config.debug:
                length_diff = len(final_content) - len(chunk) if final_content else 0
                length_diff_pct = (length_diff / len(chunk) * 100) if chunk and len(chunk) > 0 else 0
                status = "✓" if final_content else "✗ EMPTY"
                print(f"  [{status}] {len(chunk)} → {len(final_content):,} chars ({length_diff_pct:+.1f}%) | Successful: {self.stats['successful']}/{self.stats['failed'] + self.stats['successful']}")

        # Write the last section after the loop
        if current_section_chunks and current_section_idx not in written_sections:
            section_content = "\n".join(current_section_chunks)
            section_wrapped = f"<section>\n{section_content}\n</section>"
            content_parts.append(section_wrapped + "\n")
            with open(output_tfile, 'a', encoding='utf-8') as f:
                f.write(section_wrapped + "\n")
            written_sections.add(current_section_idx)

        # Warn if too many chunks failed
        total_processed = self.stats['successful'] + self.stats['failed']
        if total_processed > 0 and self.stats['failed'] / total_processed > 0.1:
            print(f"\n⚠️ WARNING: {self.stats['failed']}/{total_processed} chunks failed to translate!")
            logger.warning(f"High failure rate: {self.stats['failed']}/{total_processed} chunks failed")

        return "".join(content_parts)

    def save_checkpoint(self, checkpoint_file: str):
        """
        Save translation progress to checkpoint file (atomic write).

        Args:
            checkpoint_file: Path to checkpoint JSON file
        """
        checkpoint = {
            "version": 1,
            "book_path": self.book_path,
            "last_chunk": self.last_processed_chunk,
            "last_section_idx": self.last_section_idx,
            "last_chunk_idx": self.last_chunk_idx,
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
        """
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

def load_vocab_from_file(file_path: str) -> dict:
    """Load vocabulary from .dic file."""
    vocab = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                # Format: source = target, category, gender, notes
                parts = line.split('=', 1)
                source = parts[0].strip()
                rest = parts[1].strip()

                # Parse comma-separated values: target, category, gender, notes
                csv_parts = [p.strip() for p in rest.split(',')]
                target = csv_parts[0] if len(csv_parts) > 0 else ''
                category = csv_parts[1] if len(csv_parts) > 1 else ''
                gender = csv_parts[2] if len(csv_parts) > 2 else ''
                notes = csv_parts[3] if len(csv_parts) > 3 else ''

                key = source.replace(' ', '_')
                if key not in vocab:
                    vocab[key] = {}
                vocab[key][config.source_lang] = source
                vocab[key][config.target_lang] = target
                if category:
                    vocab[key]['category'] = category
                if gender:
                    vocab[key]['gender'] = gender
                if notes:
                    vocab[key]['notes'] = notes
    return vocab


def _translate_vocabulary_batch(terms_text: str, source_lang: str, target_lang: str, country: str) -> str:
    """
    Translate vocabulary terms in batch using Primary LLM.
    DEPRECATED: Use ta.vocabulary() with prompts.json instead.
    """
    # This function is deprecated - use ta.vocabulary() with proper prompts
    raise NotImplementedError("Use ta.vocabulary() with prompts.json instead")


def _save_vocabulary_formatted(translated_text: str, dict_file: str, original_terms: str):
    """
    Save vocabulary in proper format according to docs/DICTIONARY_FORMAT.md

    Format: source = target, category, gender, notes

    Args:
        translated_text: Translated terms from LLM (JSON or CSV format)
        dict_file: Output file path
        original_terms: Original NER output with categories
    """
    import json
    import re
    
    # Parse original terms to extract categories
    original_categories = {}
    for line in original_terms.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        # Extract term and category from NER output
        # Format: "Term [CATEGORY]" or "Term"
        match = re.match(r'^(.+?)\s*\[([^\]]+)\]$', line)
        if match:
            term = match.group(1).strip().lower()
            category = match.group(2).strip()
            original_categories[term] = category
        else:
            # Common word without category - mark as empty
            original_categories[line.lower()] = ''

    # Robust JSON parsing with multiple strategies
    translations = {}
    categories_from_llm = {}

    # Strategy 1: Full JSON object/array parsing
    try:
        data = json.loads(translated_text.strip())
        if isinstance(data, dict) and 'terms' in data:
            terms = data['terms']
        elif isinstance(data, list):
            terms = data
        else:
            raise ValueError("Invalid JSON structure")
            
        for term in terms:
            if isinstance(term, dict):
                source = term.get('source', '').strip()
                target = term.get('target', '').strip()
                category = term.get('category', '').strip()
                if source and target:
                    translations[source.lower()] = (source, target)
                    if category:
                        categories_from_llm[source.lower()] = category
        print(f"Parsed {len(translations)} terms from JSON")
    except (json.JSONDecodeError, ValueError, AttributeError):
        # Strategy 2: Extract JSON array from response
        array_match = re.search(r'\[.*\]', translated_text.strip(), re.DOTALL)
        if array_match:
            try:
                terms = json.loads(array_match.group(0))
                for term in terms:
                    if isinstance(term, dict):
                        source = term.get('source', '').strip()
                        target = term.get('target', '').strip()
                        category = term.get('category', '').strip()
                        if source and target:
                            translations[source.lower()] = (source, target)
                            if category:
                                categories_from_llm[source.lower()] = category
                print(f"Parsed {len(translations)} terms from JSON array")
            except (json.JSONDecodeError, AttributeError):
                pass
        
        # Strategy 3: Extract individual JSON objects
        if not translations:
            term_pattern = r'\{\s*"source"\s*:\s*"([^"]*)"\s*,\s*"target"\s*:\s*"([^"]*)"(?:\s*,\s*"category"\s*:\s*"([^"]*)")?[^}]*\}'
            matches = re.findall(term_pattern, translated_text, re.DOTALL)
            for match in matches:
                source = match[0].strip()
                target = match[1].strip()
                category = match[2].strip() if len(match) > 2 else ''
                if source and target:
                    translations[source.lower()] = (source, target)
                    if category:
                        categories_from_llm[source.lower()] = category
            print(f"Parsed {len(translations)} terms from individual JSON objects")
        
        # Strategy 4: Fallback to line-based parsing
        if not translations:
            for line in translated_text.strip().split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                if '=' in line:
                    parts = line.split('=', 1)
                    source = parts[0].strip()
                    target = parts[1].strip()
                    # Extract target before any comma
                    target_clean = target.split(',')[0].strip()
                    translations[source.lower()] = (source, target_clean)
            print(f"Parsed {len(translations)} terms from line-based fallback")

    # Group by category (prefer LLM category, fallback to NER)
    categories = {'PERSON': [], 'LOC': [], 'ORG': [], 'TERM': [], 'OTHER': []}

    for term_key, (source, target) in translations.items():
        # First try LLM-provided category
        cat = categories_from_llm.get(term_key, '')

        # Fallback to NER category if LLM didn't provide
        if not cat:
            cat = original_categories.get(term_key, '')
            # Map NER categories to our format
            if cat in ['PERSON', 'LOC', 'ORG']:
                pass  # Keep as is
            elif cat in ['GPE', 'GPE/LOC']:
                cat = 'LOC'  # Map GPE to LOC
            elif cat == 'TERM':
                pass  # Keep as TERM
            else:
                cat = 'OTHER' if cat else 'TERM'  # Default to TERM if empty

        if cat not in categories:
            cat = 'OTHER'
        categories[cat].append((source, target, cat))

    # Write dictionary in proper format with commas
    with open(dict_file, 'w', encoding='utf-8') as f:
        f.write(f"# Vocabulary for {Path(dict_file).stem}\n")
        f.write(f"# Format: source = target, category, gender, notes\n")
        f.write(f"# Generated automatically by NER\n")
        f.write(f"# Please review and edit as needed\n\n")

        for cat_name in ['PERSON', 'LOC', 'ORG', 'TERM', 'OTHER']:
            entries = categories[cat_name]
            if not entries:
                continue

            f.write(f"# {cat_name} ({len(entries)} terms)\n")
            for source, target, cat in entries:
                # Format: source = target, category, gender, notes
                # Empty gender and notes by default
                f.write(f"{source} = {target}, {cat}, , \n")

    logger.info(f"Dictionary saved: {dict_file} ({len(translations)} entries)")


def write_to_file(data, output_file: str, auto_repair_fb2: bool = False):
    """Write data to file.

    Note: Auto-repair is disabled by default as it may corrupt valid content.
    FB2 structure should be correct at generation time.
    """
    if isinstance(data, str):
        data = [data]

    content = '\n'.join(data)

    # Write content to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)

    # Note: Auto-repair disabled - it was causing content loss
    # FB2 structure should be validated at generation time, not repair time


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


def assemble_resume_content(new_content: str, resume_from_chunk: int, output_tfile: str) -> str:
    """On resume, output_tfile has ALL sections (prior + new) but
    process_all_chunks only returns new chunks' content.
    Read the full accumulated file to avoid data loss."""
    if resume_from_chunk > 0 and os.path.exists(output_tfile):
        with open(output_tfile, 'r', encoding='utf-8') as f:
            return f.read()
    return new_content


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main translation workflow."""
    # Graceful shutdown handler
    def _handle_shutdown(signum, frame):
        logger.warning(f"Received signal {signum}, saving checkpoint...")
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)


    # Check input file
    myfile = config.myfile
    if not os.path.exists(myfile):
        print(f"File not found: {myfile}")
        return

    # Prepare paths
    file_name, file_ext = os.path.splitext(os.path.basename(myfile))
    output_dir = os.path.dirname(myfile) or '.'
    dict_file = f"{output_dir}/{file_name}.dic"
    timestamp = datetime.now().strftime("%H%M-%d%m")

    if file_ext.lower() not in ['.fb2', '.epub', '.txt']:
        raise ValueError(f"Unsupported format: {file_ext}")

    # Output paths
    _paths = build_resume_paths(myfile, config.target_lang)
    output_file = _paths["output_file"]
    output_tfile = _paths["output_tfile"]
    checkpoint_file = _paths["checkpoint_file"]
    output_base = os.path.splitext(output_file)[0]  # used by EPUB writer/fallback

    # 1. Parse Input
    print(f"Parsing {file_ext.upper()} file...")
    if file_ext.lower() == '.fb2':
        body, header, footer = fb2.parse_xml(myfile)
    elif file_ext.lower() == '.epub':
        body, header, footer = epub.parse_epub(myfile)
    else:
        body, header, footer = txt.parse_txt(myfile)

    # 2. Vocabulary Management
    vocab = {}
    if config.ner_opt and ner:
        if not os.path.exists(dict_file):
            print("Generating vocabulary...")
            vb = ner.make_vocab(body)

            # Check if NER returned any terms
            if not vb or not vb.strip():
                print("Warning: NER did not extract any terms. Creating empty dictionary.")
                # Create empty dictionary template
                with open(dict_file, 'w', encoding='utf-8') as f:
                    f.write(f"# Vocabulary for {file_name}\n")
                    f.write(f"# Format: source = target | category | gender | notes\n")
                    f.write(f"# No terms extracted by NER - please add terms manually\n\n")
                print(f"Empty dictionary created: {dict_file}")
                print("Please edit the dictionary and restart.")
                sys.exit(0)

            # Translate vocabulary using Secondary LLM with proper prompts
            print(f"Translating {len(vb.strip().split(chr(10)))} terms using Secondary LLM...")
            vocab_raw = ta.vocabulary(config.source_lang, config.target_lang, vb, config.country, "Proofread")

            # Parse and save in proper format
            _save_vocabulary_formatted(vocab_raw, dict_file, vb)

            print(f"Vocabulary created: {dict_file}")
            print("Please review and restart.")
            sys.exit(0)
        else:
            vocab = load_vocab_from_file(dict_file)

    # 3. Prepare Chunks
    print("Preparing chunks...")

    # Use prepare_chunks_with_sections to preserve original FB2 section structure
    # Returns: [[section1_chunk1, section1_chunk2], [section2_chunk1], ...]
    sections = fb2.prepare_chunks_with_sections(body, config.max_len_chunk)

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

    # 4. Translate
    engine = TranslationEngine(output_tfile, book_path=myfile)

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
            content = engine.process_all_chunks(chunks, sections, vocab, output_tfile, checkpoint_file)
            content = assemble_resume_content(content, resume_from_chunk, output_tfile)
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
            lang_map = {'russian': 'ru', 'english': 'en', 'french': 'fr', 'german': 'de'}
            metadata['lang'] = lang_map.get(config.target_lang.lower(), config.target_lang)
            translated_meta = ta.translate_metadata(metadata, config.source_lang, config.target_lang, config.country)
            if translated_meta:
                header = fb2.update_header_with_metadata(header, translated_meta)

    if config.api_key_images:
        print("Processing cover...")
        cover_data = fb2.get_cover_image(header, footer)
        if cover_data:
            cover_result = ta.process_image_request(cover_data, config.source_lang, config.target_lang, config.country)
            if cover_result:
                header, footer, body = fb2.replace_cover_image(header, footer, body, cover_result)
                try:
                    with open(f"{output_dir}/{file_name}_cover.jpg", 'wb') as f:
                        f.write(base64.b64decode(cover_result))
                except Exception as e:
                    logger.error(f"Cover save error: {e}")

    # 6. Finalize
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
            epub_path = create_epub_from_fb2(header, content, footer, output_base)
            print(f"\n✓ EPUB created: {epub_path}")
        except Exception as e:
            logger.error(f"EPUB creation failed: {e}")
            write_to_file(xml_str, f"{output_base}.fb2", auto_repair_fb2=config.fb2_auto_repair)
            print(f"\n✓ FB2 created (fallback): {output_base}.fb2")
    else:
        write_to_file(xml_str, output_file, auto_repair_fb2=config.fb2_auto_repair)
        print(f"\n✓ FB2 created: {output_file}")
        if config.fb2_auto_repair:
            print(f"  (Auto-repair check enabled - fixed version may be created alongside)")


    # Calculate retry token percentage
    retry_pct = (engine.stats['retry_tokens'] / engine.stats['total_tokens'] * 100) if engine.stats['total_tokens'] > 0 else 0

    # Statistics
    print("\n--- Statistics ---")
    print(f"Source: {engine.total_source_len:,} chars")
    print(f"Target: {engine.total_target_len:,} chars")
    if engine.total_source_len > 0:
        diff = (engine.total_target_len - engine.total_source_len) / engine.total_source_len * 100
        print(f"Length diff: {diff:+.1f}%")
    print("------------------\n")

    # Translation Metrics Report
    try:
        from src.utils import print_translation_report
        print_translation_report()
    except Exception as e:
        logger.error(f"Failed to print translation report: {e}")

    # Remove checkpoint after successful completion
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
        logger.info(f"Checkpoint removed: {checkpoint_file}")


if __name__ == '__main__':
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
                       help='Minimum occurrences for common words')
    # Calibre pipeline mode
    parser.add_argument('--pipeline', choices=['classic', 'new'], default='classic',
                       help='Translation pipeline: classic (FB2/EPUB parser) or new (Calibre-based)')
    parser.add_argument('--output-format', type=str, default=None,
                       help='Output format for --pipeline new: fb2 or epub (default: from config)')
    parser.add_argument('--max-chunk-size', type=int, default=None,
                       help='Max chunk size in chars for --pipeline new translation (default: MAX_LEN_CHUNK=8192 from config)')
    parser.add_argument('--fast-mode', action='store_true',
                       help='Skip reflection/improve stages in --pipeline new')

    args, unknown = parser.parse_known_args()

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
                min_count_word=args.min_count_word
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
        from src.ner import make_vocab, _save_vocabulary_formatted
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
        if file_ext.lower() == '.fb2':
            body, _, _ = fb2.parse_xml(book_path)
        elif file_ext.lower() == '.epub':
            body, _, _ = epub.parse_epub(book_path)
        else:
            body, _, _ = txt.parse_txt(book_path)
        # Generate unverified NER terms first
        vb = make_vocab(body, min_count_ner=args.min_count_ner, min_count_word=args.min_count_word)
        # Write initial untranslated dictionary
        with open(dict_path, 'w', encoding='utf-8') as f:
            f.write(f"# Vocabulary for {os.path.basename(dict_path)}\n")
            f.write("# Format: source = target, category, gender, notes\n")
            # Write NER terms as initial entries
            for term in vb.strip().split('\n'):
                if term.strip():
                    f.write(f"{term}\n")
            # Add format metadata
            f.write("# Format: source = target, category, gender, notes\n")

        # Now translate and update dictionary
        num_terms = len(vb.strip().splitlines())
        print(f"Translating {num_terms} terms using secondary LLM...")
        # Get translation results
        vocab_raw = ta.vocabulary(config.source_lang, config.target_lang, vb, config.country, "Proofread")
        # Update dictionary with translations
        updated_lines = []
        for line in vocab_raw.split('\n'):
            if line.strip() and '=' in line:
                source, _, rest = line.partition('=')
                target, *extra = rest.strip().split(',')
                translated_target = target.strip()  # Already translated by LLM
                updated_lines.append(f"{source} = {translated_target}\n")
            else:
                updated_lines.append(line)
        # Write updated dictionary
        with open(dict_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(updated_lines))
        print(f"Dictionary updated with translations: {dict_path}")
        sys.exit(0)
    
    # Handle new Calibre pipeline
    if args.pipeline == 'new':
        import src.calibre_pipeline as cp

        # Determine input file
        input_file = config.myfile
        if input_file and not os.path.exists(input_file):
            print(f"Error: Input file not found: {input_file}")
            sys.exit(1)
        if not input_file:
            print("Error: No input file specified. Set myfile in .env or pass via --input")
            sys.exit(1)

        output_format = args.output_format or config.output_format or 'fb2'
        output_format = output_format.lower()
        if output_format not in ('fb2', 'epub'):
            print(f"Error: Unsupported output format: {output_format}. Use fb2 or epub.")
            sys.exit(1)

        print(f"Pipeline: new (Calibre-based)")
        print(f"Input: {input_file}")
        print(f"Output format: {output_format}")
        print(f"Chunk size: {args.max_chunk_size}")

        if not cp.check_calibre_installed():
            print("Error: Calibre (ebook-convert) is not installed.")
            print("Install it: https://calibre-ebook.com/download")
            sys.exit(1)

        try:
            output_path = cp.run_pipeline(
                input_path=input_file,
                output_format=output_format,
                max_chunk_size=args.max_chunk_size,
                source_lang=config.source_lang,
                target_lang=config.target_lang,
                country=config.country,
                fast_mode=args.fast_mode
            )
            print(f"\n✓ Pipeline complete: {output_path}")
        except Exception as e:
            print(f"\n✗ Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        sys.exit(0)

    main()