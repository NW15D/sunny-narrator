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
import warnings
import base64
import logging
import re
from datetime import datetime
from pathlib import Path

# Suppress FutureWarning from transformers/torch interaction
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
from src.vocabulary_manager import get_vocabulary_manager
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
        self.total_source_len = 0
        self.total_target_len = 0
        
        # Character registry (shared between synopsis and vocabulary)
        reset_character_registry()
        self.character_registry = get_character_registry()
        
        # Synopsis manager with character registry integration
        self.synopsis_manager = SynopsisManager(character_registry=self.character_registry)
        
        # Vocabulary manager for dictionary handling
        self.vocab_manager = None
        if book_path:
            self.vocab_manager = get_vocabulary_manager(book_path)

    def get_formatted_vocab_for_chunk(self, chunk: str, s_idx: int, c_idx: int) -> str:
        """
        Get formatted vocabulary for chunk using VocabularyManager.
        
        Returns vocabulary formatted for the current model (Hunyuan, Gemma, etc.)
        """
        if not self.vocab_manager:
            return ""
        
        entries = self.vocab_manager.get_vocab_for_chunk(chunk, s_idx, c_idx)
        
        if not entries:
            return ""
        
        formatted = self.vocab_manager.format_for_model(entries, config.model_translate)
        
        if config.debug and formatted:
            logger.debug(f"Vocab for chunk {s_idx}-{c_idx}: {len(entries)} terms")
        
        return formatted

    def translate_chunk(self, source_text: str, context: str) -> tuple:
        """
        Translate a single chunk using dual-LLM pipeline.
        
        Args:
            source_text: Text to translate (with XML tags)
            context: Synopsis from previous chunks
        
        Returns:
            (translated_text, synopsis)
        """
        try:
            # Note: rechunking is now handled inside ta.translate_chunk()
            # Get vocabulary for this chunk (formatted for model)
            vocab_dict = self.get_context_for_chunk(source_text, 0, 0)
            
            translation, synopsis = ta.translate_chunk(
                source_lang=config.source_lang,
                target_lang=config.target_lang,
                source_text=source_text,
                outline_text=context,
                vocab_dict=vocab_dict,  # Use formatted vocabulary
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
        
        # Retry loop for XML validation
        for attempt in range(3):
            try:
                # Rechunking happens inside translate_chunk automatically
                temp_content, synopsis = self.translate_chunk(source_text, context)
                
                if temp_content:
                    final_content = self._post_process_xml(source_text, temp_content)
                    
                    if config.debug and attempt > 0:
                        logger.debug(f"XML validation passed on attempt {attempt + 1}")
                    
                    break
                    
            except Exception as e:
                logger.warning(f"Translation attempt {attempt + 1} failed: {e}")
        
        else:
            # All retries failed
            logger.warning(f"All validation attempts failed for chunk {g_id}")
            final_content = temp_content if 'temp_content' in locals() else ""
            final_content = self._post_process_xml(source_text, final_content)
        
        # Log length statistics (no rechunking here - done in translate_chunk)
        target_len = len(final_content)
        percent_diff = abs(target_len - source_len) / source_len * 100 if source_len > 0 else 0
        
        if config.debug:
            logger.debug(f"Chunk {g_id} (depth {depth}): {source_len} → {target_len} chars ({percent_diff:.1f}%)")
        
        # Ensure synopsis is set
        if not synopsis:
            synopsis = ""
        
        return final_content, synopsis

    def _post_process_xml(self, source_text: str, translated_text: str) -> str:
        """
        Validate and repair XML structure after translation.
        
        - Removes artifacts
        - Checks tag balance
        - Repairs via LLM if needed
        """
        cleaned = xc.rem_tags(translated_text)
        
        source_tags = self._count_tags(source_text)
        translated_tags = self._count_tags(cleaned)
        
        diff = self._tag_difference(source_tags, translated_tags)
        
        if diff > 0.1:
            logger.debug(f"XML repair needed (diff={diff:.1%})")
            cleaned = self._llm_repair_xml(source_text, cleaned)
        
        return cleaned

    def _count_tags(self, text: str) -> dict:
        """Count XML tags in text."""
        tags = re.findall(r'</?[a-zA-Z][^>]*>', text)
        counts = {}
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1
        return counts

    def _tag_difference(self, source_tags: dict, translated_tags: dict) -> float:
        """Calculate tag difference ratio (0.0-1.0)."""
        all_tags = set(source_tags.keys()) | set(translated_tags.keys())
        if not all_tags:
            return 0.0
        
        diffs = []
        for tag in all_tags:
            src = source_tags.get(tag, 0)
            trans = translated_tags.get(tag, 0)
            if src > 0:
                diffs.append(abs(src - trans) / src)
        
        return sum(diffs) / len(diffs) if diffs else 0.0

    def _llm_repair_xml(self, source_text: str, translated_text: str) -> str:
        """Repair lost XML tags using LLM."""
        prompt = f"""ОРИГИНАЛ ({config.source_lang}):
{source_text[:1000]}

ПЕРЕВОД ({config.target_lang}, могут быть потеряны тэги):
{translated_text[:1000]}

ЗАДАЧА: Восстанови XML-тэги FB2 (<p>, </p>, <strong>, <em>, etc.) в переводе.
Верни ТОЛЬКО исправленный перевод с тэгами."""

        try:
            client = getattr(ta.llm_service, 'clientProofread', ta.llm_service.clientTranslate)
            response = client.chat.completions.create(
                model=config.model_proofread,
                messages=[
                    {"role": "system", "content": "Ты редактор XML. Восстанавливай тэги FB2."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM repair failed: {e}")
            return translated_text

    def process_all_chunks(self, all_chunks: list, orig_sections: list, 
                           vocab: dict, output_tfile: str) -> str:
        """
        Process all chunks sequentially.
        
        Args:
            all_chunks: List of chunk dicts with metadata
            orig_sections: Original sections structure
            vocab: Vocabulary dictionary
            output_tfile: Temp output file path
        
        Returns:
            Combined translated content
        """
        all_content = ""
        total = len(all_chunks)
        
        logger.info(f"Starting translation: {total} chunks")
        print(f"\n{'='*60}")
        print(f"Starting translation: {total} chunks")
        print(f"{'='*60}\n")
        
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
            
            # Statistics
            if final_content:
                self.total_source_len += len(chunk)
                self.total_target_len += len(final_content)
                
                section_content = xc.rem_tags(final_content)
                all_content += section_content + "\n"
                
                with open(output_tfile, 'a', encoding='utf-8') as f:
                    f.write(section_content + "\n")
        
        return all_content


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
                parts = line.split('=', 1)
                source = parts[0].strip().replace(' ', '_')
                target = parts[1].split('|')[0].strip()  # Handle extended format
                
                if source not in vocab:
                    vocab[source] = {}
                vocab[source][config.source_lang] = parts[0].strip()
                vocab[source][config.target_lang] = target
    return vocab


def write_to_file(data, output_file: str):
    """Write data to file."""
    if isinstance(data, str):
        data = [data]
    with open(output_file, 'w', encoding='utf-8') as f:
        for line in data:
            f.write(line + '\n')


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main translation workflow."""
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
    output_base = f"{output_dir}/{file_name}_{config.target_lang}_{timestamp}"
    output_file = f"{output_base}.{config.output_format}"
    output_tfile = f"{output_dir}/{file_name}_{config.target_lang}_tmp_{timestamp}.fb2"

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
            vocab_raw = ta.vocabulary(config.source_lang, config.target_lang, vb, config.country, "Proofread")
            write_to_file(ta.remove_tags(vocab_raw), dict_file)
            print(f"Vocabulary created: {dict_file}")
            print("Please review and restart.")
            sys.exit(0)
        else:
            vocab = load_vocab_from_file(dict_file)

    # 3. Prepare Chunks
    print("Preparing chunks...")
    sections = fb2.prepare_chunks(body, config.max_len_chunk)
    chunks = [
        {'chunk': chunk, 'section_idx': s_idx, 'chunk_idx': c_idx, 'global_id': idx}
        for s_idx, section in enumerate(sections)
        for c_idx, chunk in enumerate(section)
        for idx in [s_idx * 100 + c_idx]  # Unique ID
    ]
    # Fix global_id
    chunks = []
    gid = 0
    for s_idx, section in enumerate(sections):
        for c_idx, chunk in enumerate(section):
            chunks.append({'chunk': chunk, 'section_idx': s_idx, 'chunk_idx': c_idx, 'global_id': gid})
            gid += 1

    # 4. Translate
    engine = TranslationEngine(output_tfile, book_path=myfile)
    
    if engine.vocab_manager:
        try:
            vocab = engine.vocab_manager.initialize()
            print(f"Vocabulary loaded: {len(vocab)} entries")
        except SystemExit:
            return
    
    content = engine.process_all_chunks(chunks, sections, vocab, output_tfile)

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
            write_to_file(xml_str, f"{output_base}.fb2")
            print(f"\n✓ FB2 created (fallback): {output_base}.fb2")
    else:
        write_to_file(xml_str, output_file)
        print(f"\n✓ FB2 created: {output_file}")

    # Statistics
    print("\n--- Statistics ---")
    print(f"Source: {engine.total_source_len:,} chars")
    print(f"Target: {engine.total_target_len:,} chars")
    if engine.total_source_len > 0:
        diff = (engine.total_target_len - engine.total_source_len) / engine.total_source_len * 100
        print(f"Length diff: {diff:+.1f}%")
    print("------------------\n")


if __name__ == '__main__':
    main()