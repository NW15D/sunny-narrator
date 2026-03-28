import os
import sys
import warnings
import base64
from datetime import datetime
from pathlib import Path

# Suppress FutureWarning from transformers/torch interaction
warnings.filterwarnings("ignore", category=FutureWarning, message=".*torch.utils._pytree._register_pytree_node.*")

# Import local modules
import src.utils as ta
import src.xmlcheck as xc
import src.fb2_handler as fb2
import src.epub_handler as epub
import src.txt_handler as txt
from src.config import Config
from src.synopsis_manager import SynopsisManager
from src.vocabulary_manager import VocabularyManager, get_vocabulary_manager

# Initialize configuration
config = Config()

# Global statistics (kept for simplicity, though could be moved to class)
rechunk_stats = {
    'runs': 0,
    'fixed': 0,
    'not_fixed': 0,
    'failures': [] # list of percentage failures
}

# Conditional import of NER module
ner = None
if config.ner_opt:
    try:
        import src.ner as ner_module
        ner = ner_module
    except ImportError as e:
        if config.debug:
            print("DEBUG:", f"Import Error: {e}")
        pass

class TranslationEngine:
    """
    Encapsulates the translation logic, context management, and recursive processing.
    """
    def __init__(self, output_tfile, book_path=None):
        self.output_tfile = output_tfile
        self.vocab_dict_map = {}
        self.shared_outline = {'text': ''}
        self.total_source_len = 0
        self.total_target_len = 0
        # NEW: Synopsis manager for proper context handling per section
        self.synopsis_manager = SynopsisManager()
        # NEW: Vocabulary manager for dictionary handling
        self.vocab_manager = None
        if book_path:
            self.vocab_manager = get_vocabulary_manager(book_path)

    def load_vocab_for_chunk(self, chunk, s_idx, c_idx, vocab):
        """
        Prepares the vocabulary dictionary for a specific chunk using NER.
        
        LEGACY: Kept for backward compatibility.
        NEW: Use VocabularyManager via get_formatted_vocab_for_chunk()
        """
        if not (config.ner_opt and ner and vocab):
            return

        key = (s_idx, c_idx)
        if key not in self.vocab_dict_map:
            self.vocab_dict_map[key] = []
        
        # chunk is now a plain string
        chunk_text = chunk if isinstance(chunk, str) else chunk
        found_strings = ner.find_matching_words_with_cosine_similarity(chunk_text, vocab, config.source_lang)
        
        for string in found_strings:
            normalized_string = string.replace(' ', '_')
            if normalized_string in vocab:
                source_lang_word = vocab[normalized_string][config.source_lang]
                target_lang_word = vocab[normalized_string][config.target_lang]
                entry = f"{source_lang_word}={target_lang_word}"
                if entry not in self.vocab_dict_map[key]:
                    self.vocab_dict_map[key].append(entry)
        
        if config.debug and self.vocab_dict_map[key]:
             print(f"DEBUG: Vocab for chunk {s_idx}-{c_idx}: {self.vocab_dict_map[key]}")

    def get_formatted_vocab_for_chunk(self, chunk, s_idx, c_idx) -> str:
        """
        NEW: Get formatted vocabulary for chunk using VocabularyManager.
        
        Returns vocabulary formatted for the current model (Hunyuan, Gemma, etc.)
        """
        if not self.vocab_manager:
            return ""
        
        chunk_text = chunk if isinstance(chunk, str) else str(chunk)
        
        # Get relevant entries for this chunk
        entries = self.vocab_manager.get_vocab_for_chunk(chunk_text, s_idx, c_idx)
        
        if not entries:
            return ""
        
        # Format for current model
        formatted = self.vocab_manager.format_for_model(entries, config.model_translate)
        
        if config.debug and formatted:
            print(f"DEBUG: Formatted vocab for chunk {s_idx}-{c_idx}: {len(entries)} terms")
        
        return formatted

    def translate_chunk_wrapper(self, source_text, source_lang, target_lang, outline_text, country, vocab_list, temperature):
        """
        Synchronous wrapper around ta.translate generator to get the final result.
        """
        current_translation = None
        new_outline = ""
        
        try:
            current_translation, new_outline = ta.translate(
                source_lang, target_lang, source_text, 'xml', outline_text,
                country, vocab_list, temperature=temperature
            )
            
            if current_translation is None:
                raise ValueError("Translation returned None")
                
            return current_translation, new_outline
            
        except Exception as e:
            raise ValueError(f"Error during translation wrapper: {e}")

    def process_chunk_recursive(self, chunk, s_idx, c_idx, g_id, vocab_dict_key, current_context, depth=0):
        """
        Recursively translates a chunk (no masking).
        - Translates plain text with XML tags
        - Post-processes XML via xc.rem_tags()
        - Splits chunk if length mismatch is high
        """
        final_content = None
        new_outline_val = ""
        validation_failed = False
        current_temp = config.temp_translate
        
        # chunk is now a plain string (no masking)
        source_text = chunk if isinstance(chunk, str) else chunk.text
        source_len = len(source_text)

        # --- Retry Loop ---
        for attempt in range(3):
            temp_content = None
            try:
                # Call Translation
                temp_content, new_outline_val = self.translate_chunk_wrapper(
                    source_text, config.source_lang, config.target_lang, current_context,
                    config.country, self.vocab_dict_map.get(vocab_dict_key, []),
                    current_temp
                )

                if temp_content is not None:
                    # Post-process XML (validate + repair)
                    final_content = post_process_xml(source_text, temp_content)
                    validation_failed = False
                    if config.debug and attempt > 0:
                         print(f"DEBUG: XML validation passed on attempt {attempt+1}")
                    break

            except Exception as e:
                if config.debug:
                    print(f"DEBUG: Translation/Validation failed (attempt {attempt+1}): {e}")
                current_temp += 0.05
                validation_failed = True
        
        # Handling Failure
        if final_content is None:
             if config.debug:
                  print(f"DEBUG: All validation attempts failed for chunk {g_id}. Proceeding with potentially broken XML.")
             final_content = temp_content if temp_content else ""
             # Still post-process even on failure
             final_content = post_process_xml(source_text, final_content)

        # -- Splitting Logic --
        target_len = len(final_content)
        percent_diff = abs(target_len - source_len) / source_len * 100 if source_len > 0 else 0
        
        if config.debug:
             print(f"DEBUG: Chunk {g_id} (depth {depth}): Source {source_len}, Target {target_len}, Ratio {percent_diff:.2f}%")

        should_split = False
        split_reason = ""
        
        # Skip length check for small chunks (< 1000 chars) to avoid over-splitting micro-chunks
        MIN_CHUNK_SIZE_FOR_LENGTH_CHECK = 1000
        
        if percent_diff > config.length_check_threshold and source_len >= MIN_CHUNK_SIZE_FOR_LENGTH_CHECK:
            should_split = True
            split_reason = f"length diff {percent_diff:.2f}% > {config.length_check_threshold}%"
        elif validation_failed and source_len >= MIN_CHUNK_SIZE_FOR_LENGTH_CHECK:
            should_split = True
            split_reason = "persistent validation failure"

        if should_split and depth < 3:
            if config.debug:
                print(f"DEBUG: Chunk {g_id} split triggered: {split_reason}. Splitting...")
            
            # Split original source
            part1, part2 = ta.split_text_smartly(source_text)
            
            # Recursive calls (plain strings, no masking)
            res1_content, res1_outline = self.process_chunk_recursive(part1, s_idx, c_idx, g_id, vocab_dict_key, current_context, depth + 1)
            res2_content, res2_outline = self.process_chunk_recursive(part2, s_idx, c_idx, g_id, vocab_dict_key, current_context, depth + 1)
            
            # Combine
            combined_content = (res1_content or "") + (res2_content or "")
            combined_outline = (res1_outline or "") + " " + (res2_outline or "")
            
            return combined_content, combined_outline
        
        return final_content, new_outline_val


    def process_all_chunks(self, all_chunks, orig_sections, vocab, output_tfile):
        """
        Main loop to process all chunks sequentially.
        """
        all_content = ""
        total_chunks = len(all_chunks)
        
        print(f"\n{'='*60}")
        print(f"Starting translation: {total_chunks} chunks")
        print(f"{'='*60}\n")
        
        for item in all_chunks:
            chunk = item['chunk']
            s_idx = item['section_idx']
            c_idx = item['chunk_idx']
            g_id = item['global_id']
            section_chunks = len(orig_sections[s_idx])
            
            # Prepare Vocab
            key = (s_idx, c_idx)
            self.load_vocab_for_chunk(chunk, s_idx, c_idx, vocab)
            
            # NEW: Get formatted vocab for current model
            formatted_vocab = self.get_formatted_vocab_for_chunk(chunk, s_idx, c_idx)
            
            # Log chunk info
            chunk_preview = chunk[:80] if isinstance(chunk, str) else str(chunk)[:80]
            vocab_count = len(self.vocab_dict_map.get(key, []))
            new_vocab_count = len(formatted_vocab.split('\n')) if formatted_vocab else 0
            print(f"\n[Chunk {g_id+1}/{total_chunks}] Section {s_idx+1}.{c_idx+1} | {len(chunk)} chars | Vocab: {vocab_count} terms (formatted: {new_vocab_count})")
            print(f"  Source: {chunk_preview}{'...' if len(chunk) > 80 else ''}")

            # Get Context from SynopsisManager (NEW: proper per-section, per-chunk synopsis)
            current_context = self.synopsis_manager.get_synopsis(s_idx, c_idx)
            
            # Execute Translation
            final_content, new_outline_val = self.process_chunk_recursive(chunk, s_idx, c_idx, g_id, key, current_context)
            
            # Save result to SynopsisManager for future chunks in this section
            self.synopsis_manager.add_chunk_result(s_idx, c_idx, final_content)
            
            # Legacy: also update shared_outline for backward compatibility
            self.shared_outline['text'] = new_outline_val
            
            # Log result
            result_preview = final_content[:80] if final_content else "(empty)"
            print(f"  Result: {result_preview}{'...' if len(final_content) > 80 else ''}")
            
            # Statistics & Output
            if final_content:
                chunk_text = chunk if isinstance(chunk, str) else chunk
                self.total_source_len += len(chunk_text)
                self.total_target_len += len(final_content)
                
                # Strip internal tags for final output flow if needed, 
                # but fb2 unmasked content usually still needs 'rem_tags' to be safe from hallucinations?
                # xc.rem_tags removes <initial_translation> artifacts etc.
                section_content = xc.rem_tags(final_content)
                all_content += section_content + "\n"
                
                with open(output_tfile, 'a', encoding='utf-8') as f:
                    f.write(section_content + "\n")
        
        return all_content


def load_vocab_from_file(file_path):
    vocab = {}
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if line and '=' in line:
                source_word, target_word = line.split('=', 1)
                key = source_word.strip().replace(' ', '_')
                if key not in vocab:
                    vocab[key] = {}
                vocab[key][config.source_lang] = source_word.strip()
                vocab[key][config.target_lang] = target_word.strip()
    return vocab

def main():
    myfile = config.myfile
    if not os.path.exists(myfile):
        print(f"File not found: {myfile}")
        return

    file_name, file_extension = os.path.splitext(os.path.basename(myfile))
    output_dir = os.path.dirname(myfile)
    dict_file = f"{output_dir}/{file_name}.dic"
    formatted_time = datetime.now().strftime("%H%M-%d%m")
    
    if file_extension.lower() not in ['.fb2', '.epub', '.txt']:
        raise ValueError(f"Unsupported file extension: {file_extension}")

    output_file = f"{output_dir}/{file_name}_{config.target_lang}_{formatted_time}.fb2"
    output_tfile = f"{output_dir}/{file_name}_{config.target_lang}_tmp_{formatted_time}.fb2"

    # 1. Parse Input
    if file_extension.lower() == '.fb2':
        body, header, footer = fb2.parse_xml(myfile)
    elif file_extension.lower() == '.epub':
        body, header, footer = epub.parse_epub(myfile)
    else:
        body, header, footer = txt.parse_txt(myfile)

    # 2. Vocabulary Management
    vocab = {}
    if config.ner_opt and ner:
        if not os.path.exists(dict_file):
            print("NER: Generating vocabulary...")
            vb = ner.make_vocab(body)
            vocab_dict_initial = ta.vocabulary(config.source_lang, config.target_lang, vb, config.country, "Proofread")
            write_to_file(ta.remove_tags(vocab_dict_initial), dict_file)
            print(f"Vocabulary generated. Please check {dict_file} and restart.")
            sys.exit(0)
        else:
            vocab = load_vocab_from_file(dict_file)

    # 3. Prepare Chunks
    orig_sections = fb2.prepare_chunks(body, config.max_len_chunk)
    all_chunks = []
    for s_idx, section in enumerate(orig_sections):
        for c_idx, chunk in enumerate(section):
            all_chunks.append({
                'chunk': chunk,
                'section_idx': s_idx,
                'chunk_idx': c_idx,
                'global_id': len(all_chunks)
            })

    # 4. Initialize Engine & Translate
    # NEW: Pass book_path to enable VocabularyManager
    engine = TranslationEngine(output_tfile, book_path=myfile)
    
    # NEW: Initialize vocabulary via VocabularyManager if available
    if engine.vocab_manager:
        try:
            vocab = engine.vocab_manager.initialize()
            print(f"Vocabulary loaded: {len(vocab)} entries")
        except SystemExit:
            # Dictionary was created, user needs to edit
            return
    
    all_content = engine.process_all_chunks(all_chunks, orig_sections, vocab, output_tfile)

    # 5. Metadata & Cover
    translated_metadata = None
    if header:
        print("Translating metadata...")
        metadata = fb2.extract_metadata(header)
        if metadata:
            lang_map = {'russian': 'ru', 'english': 'en', 'french': 'fr', 'german': 'de'}
            metadata['lang'] = lang_map.get(config.target_lang.lower(), config.target_lang)
            translated_metadata = ta.translate_metadata(metadata, config.source_lang, config.target_lang, config.country)
            if translated_metadata:
                header = fb2.update_header_with_metadata(header, translated_metadata)

    if config.api_key_images:
        print("Processing cover image...")
        cover_data = fb2.get_cover_image(header, footer)
        if cover_data:
            cover_result = ta.process_image_request(
                cover_data, config.source_lang, config.target_lang, config.country, translated_metadata or metadata
            )
            if cover_result:
                header, footer, body = fb2.replace_cover_image(header, footer, body, cover_result)
                try:
                    with open(f"{output_dir}/{file_name}_cover.jpg", 'wb') as f:
                        f.write(base64.b64decode(cover_result))
                except Exception as e:
                    print(f"Cover save error: {e}")

    # 6. Finalize
    xml_str = f"{header}<body>\n{all_content}</body>\n{footer}"
    
    # Validation
    validation_errors = xc.validate_fb2(xml_str)
    if validation_errors:
        print("WARNING: Final FB2 validation errors:")
        for err in validation_errors:
            print(f"  {err}")
    
    write_to_file(xml_str, output_file)

    # Stats
    print("\n--- Translation Statistics ---")
    print(f"Total Source Length: {engine.total_source_len}")
    print(f"Total Target Length: {engine.total_target_len}")
    if engine.total_source_len > 0:
        diff = ((engine.total_target_len - engine.total_source_len) / engine.total_source_len) * 100
        print(f"Global Length Difference: {diff:.2f}%")
    print("----------------------------\n")


# ============================================================================
# XML Post-Processing Functions (outside class)
# ============================================================================

def post_process_xml(source_text, translated_text):
    """
    Валидация и восстановление XML структуры после перевода.
    
    Args:
        source_text: Оригинальный текст с тэгами
        translated_text: Переведённый текст (может терять тэги)
    
    Returns:
        Исправленный translated_text с валидной XML структурой
    """
    # 1. XML валидация через xc.rem_tags()
    cleaned = xc.rem_tags(translated_text)
    
    # 2. Подсчёт тэгов (source vs translated)
    source_tags = count_tags(source_text)
    translated_tags = count_tags(cleaned)
    
    # 3. Если расхождение > 10% → LLM repair
    diff = tag_difference(source_tags, translated_tags)
    if diff > 0.1:
        if config.debug:
            print(f"DEBUG: XML repair needed (diff={diff:.2%})")
        cleaned = llm_repair_xml(source_text, cleaned)
    
    return cleaned


import re

def count_tags(text):
    """Подсчитать XML тэги в тексте."""
    tags = re.findall(r'</?[a-zA-Z][^>]*>', text)
    tag_counts = {}
    for tag in tags:
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return tag_counts

def tag_difference(source_tags, translated_tags):
    """Вычислить разницу в тэгах (0.0-1.0)."""
    all_tags = set(source_tags.keys()) | set(translated_tags.keys())
    if not all_tags:
        return 0.0
    
    diffs = []
    for tag in all_tags:
        src_count = source_tags.get(tag, 0)
        trans_count = translated_tags.get(tag, 0)
        if src_count > 0:
            diff = abs(src_count - trans_count) / src_count
            diffs.append(diff)
    
    return sum(diffs) / len(diffs) if diffs else 0.0


def llm_repair_xml(source_text, translated_text):
    """LLM-based восстановление потерянных тэгов."""
    # Обрезать до 1000 символов чтобы не превысить контекст
    src_trunc = source_text[:1000]
    trans_trunc = translated_text[:1000]
    
    prompt = f"""ОРИГИНАЛ ({config.source_lang}):
{src_trunc}

ПЕРЕВОД ({config.target_lang}, могут быть потеряны тэги):
{trans_trunc}

ЗАДАЧА: Восстанови XML-тэги FB2 (<p>, </p>, <strong>, <em>, etc.) в переводе на тех же позициях, что в оригинале.
Верни ТОЛЬКО исправленный перевод с тэгами, без объяснений."""

    try:
        # Использовать прямой вызов API с кастомным промптом
        # Fallback: если clientProofread недоступен, использовать основной client
        client = getattr(ta.llm_service, 'clientProofread', ta.llm_service.clientTranslate)
        response = client.chat.completions.create(
            model=config.model_proofread,
            messages=[
                {"role": "system", "content": "Ты редактор XML. Восстанавливай тэги FB2 в тексте."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=2000
        )
        repaired = response.choices[0].message.content
        return repaired
    except Exception as e:
        if config.debug:
            print(f"DEBUG: LLM repair failed: {e}")
        return translated_text  # Вернуть как есть


def write_to_file(data, output_file):
    if isinstance(data, str):
        data = [data]
    with open(output_file, 'w', encoding='utf-8') as f:
        for line in data:
            f.write(line + '\n')

if __name__ == '__main__':
    main()