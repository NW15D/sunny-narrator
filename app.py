from icecream import ic
import os
import sys
from datetime import datetime
from pathlib import Path

# Import local modules
import src.utils as ta
import src.xmlcheck as xc
import src.fb2_handler as fb2
import src.epub_handler as epub
import src.txt_handler as txt
from src.config import Config

# Initialize configuration
config = Config()

# Global statistics
rechunk_stats = {
    'runs': 0,
    'fixed': 0,
    'not_fixed': 0,
    'failures': [] # list of percentages
}

# Conditional import of NER module
ner = None
if config.ner_opt:
    try:
        import src.ner as ner_module
        ner = ner_module
    except ImportError as e:
        if config.debug:
            ic(f"Import Error: {e}")
        # Handle import error gracefully or exit
        pass

def load_vocab_from_file(file_path, source_lang, target_lang):
    vocab = {}
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if line and '=' in line:
                source_word, target_word = line.split('=', 1)
                source_word = source_word.strip()
                target_word = target_word.strip()
                
                key = source_word.replace(' ', '_')
                if key not in vocab:
                    vocab[key] = {}
                vocab[key][source_lang] = source_word
                vocab[key][target_lang] = target_word
    if config.debug:
        ic(vocab)
    return vocab

def read_txt_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return content

def translatexml(source_text, source_lang, target_lang, outline_text, country, vocab_dict):
    translated_chunk = None
    style = 'xml'
    
    try:
        translated_chunk, outline = ta.translate(
            source_lang, target_lang, source_text, style, outline_text,
            country, vocab_dict)

        percentage = ((len(translated_chunk) - len(source_text)) / len(source_text)) * 100
        if config.debug:
            ic(percentage, "% percent")
        
        if abs(percentage) == 100:
            translated_chunk, outline = ta.translate(
                source_lang, target_lang, source_text, style, outline_text,
                country, vocab_dict)
                
        if abs(percentage) > 7 and len(source_text) > 500:
            
            if config.debug:
                ic("Rechunking !!! ", percentage, "% percent")
            mx = int((len(source_text) // 2) * 1.1)
            split_pos = source_text.rfind('</p>', 0, mx) + 4
            if split_pos == -1:
                split_pos = mx
            splitchunks = source_text[:split_pos], source_text[split_pos:]
            translated_chunk = ""
            outline = ""

            rechunk_stats['runs'] += 1
            for chunk in splitchunks:
                ch, outline_chunk = ta.translate(
                    source_lang, target_lang, chunk, style, outline_text,
                    country, vocab_dict)
                translated_chunk += ch
                outline += outline_chunk

            percentage = ((len(translated_chunk) - len(source_text)) / len(source_text)) * 100
            if abs(percentage) < 7:
                rechunk_stats['fixed'] += 1
                if config.debug:
                    ic("Fixed after rechunk, mx", mx, percentage, "% percent")
            else:
                rechunk_stats['not_fixed'] += 1
                rechunk_stats['failures'].append(percentage)
                if config.debug:
                    ic("Warning: Large percentage difference after rechunking", percentage, "% percent chunk used")

        if translated_chunk is None:
            raise ValueError(f"Translation failed for chunk: {source_text}")
            
    except Exception as e:
        raise ValueError(f"Error during translation: {e}")

    return translated_chunk, outline

def write_to_file(data, output_file):
    if isinstance(data, str):
        data = [data]

    with open(output_file, 'w', encoding='utf-8') as f:
        for line in data:
            f.write(line + '\n')

def main():
    myfile = config.myfile
    # Ensure file exists
    if not os.path.exists(myfile):
        if config.debug:
            ic(f"File not found: {myfile}")
        return

    file_name, file_extension = os.path.splitext(os.path.basename(myfile))
    file_name_without_ext = file_name
    output_dir = os.path.dirname(myfile)
    dict_file = f"{output_dir}/{file_name_without_ext}.dic"
    now = datetime.now()

    formatted_time = now.strftime("%H%M-%d%m")

    if file_extension.lower() in ['.fb2', '.epub', '.txt']:
        output_file = f"{output_dir}/{file_name_without_ext}_{config.target_lang}_{config.short}_{formatted_time}.fb2"
        output_tfile = f"{output_dir}/{file_name_without_ext}_{config.target_lang}_tmp_{formatted_time}.fb2"
        synopsis_file = f"{output_dir}/{file_name_without_ext}_{config.target_lang}_{formatted_time}_synopsis.txt"
        
        # Parse file based on extension
        if file_extension.lower() == '.fb2':
            body, header, footer = fb2.parse_xml(myfile)
            
            ## Extract and translate metadata
            if config.debug:
                ic("Extracting and translating metadata...")
            metadata = fb2.extract_metadata(header)
            if metadata:
                translated_metadata = ta.translate_metadata(
                    metadata, config.source_lang, config.target_lang, config.country
                )
                if translated_metadata:
                    header = fb2.update_header_with_metadata(header, translated_metadata)
                    if config.debug:
                        ic("Metadata translated and header updated.")

        elif file_extension.lower() == '.epub':
            body, header, footer = epub.parse_epub(myfile)
        else:
            body, header, footer = txt.parse_txt(myfile)

        # Process Cover Image (for all formats)
        if config.api_key3 and config.base_url3:
            # Use appropriate handler or just fb2_handler since structure is unified
            # We can use the module corresponding to extension, but functions are wrappers around fb2 anyway mostly
            # Actually easier to just use fb2 or dynamically chosen handler if logic diverged.
            # But currently epub/txt helpers just call fb2.
            # Let's trust fb2 methods work on the XML strings.
            
            cover_data = fb2.get_cover_image(header, footer)
            if cover_data:
                if config.debug:
                    ic("Processing cover image...")
                # Updated call with new signature
                cover_result = ta.process_image_request(
                    cover_data, 
                    config.source_lang, 
                    config.target_lang, 
                    config.country, 
                    config.cover_prompt
                )
                if cover_result:
                    header, footer, body = fb2.replace_cover_image(header, footer, body, cover_result)
                    if config.debug:
                        ic("Cover image processed/replaced.")

        vocab_dict = {}
        vocab = {}

        if config.ner_opt and ner:
            if not os.path.exists(dict_file):
                # Generate vocabulary if it doesn't exist
                if config.debug:
                    ic("NER : making vocabulary")
                
                vb = ner.make_vocab(body)
                if config.debug:
                    ic(vb)
                    
                vocab_dict_initial = ta.vocabulary(config.source_lang, config.target_lang, vb, config.country, True)
                vocab_dict_clean = ta.remove_tags(vocab_dict_initial)
                write_to_file(vocab_dict_clean, dict_file)
                if config.debug:
                    ic(f"Vocabulary is ready. Please correct it manually: {dict_file} and restart the program.")
                sys.exit(0) # Exit gracefully

            else:
                # Load existing vocabulary
                vocab = load_vocab_from_file(dict_file, config.source_lang, config.target_lang)

        orig_sections = fb2.prepare_chunks(body, config.max_len_chunk)

        translated_chunks = []
        synopsis = []
        outline_text = ''
        total_sections = len(orig_sections)
        vocab_dict_map = {} 
        all_content = ''

        # Iterate over all sections
        for section_index, section in enumerate(orig_sections):
            section_chunks = len(section)
            section_translation = ''

            for chunk_index, chunk in enumerate(section):
                # Find matching words for dictionary injection
                found_strings = []
                if config.ner_opt and ner and vocab:
                    found_strings = ner.find_matching_words_with_cosine_similarity(chunk, vocab, config.source_lang)
                    if config.debug:
                        ic("found_strings: ", found_strings)

                key = (section_index, chunk_index)
                if key not in vocab_dict_map:
                    vocab_dict_map[key] = []
                
                for string in found_strings:
                    normalized_string = string.replace(' ', '_')
                    if normalized_string in vocab:
                        source_lang_word = vocab[normalized_string][config.source_lang]
                        target_lang_word = vocab[normalized_string][config.target_lang]
                        vocab_dict_map[key].append(f"{source_lang_word}={target_lang_word}")
                
                if config.debug:
                    ic("translate: ", section_index + 1, total_sections, chunk_index + 1, section_chunks,
                       vocab_dict_map[key])

                translated_chunk, outline_text = translatexml(
                    chunk, config.source_lang, config.target_lang, outline_text,
                    config.country, vocab_dict_map[key])

                if translated_chunk is not None:
                    section_translation += translated_chunk + '\n'
                    translated_chunks.append(translated_chunk)
                    synopsis.append(outline_text)

            # Write translated section
            if section_translation:
                section_content = f"<section>\n{section_translation}\n</section>\n"
                # Robust tag repair for the section content
                section_content = xc.rem_tags(section_content)
                
                if config.debug:
                    ic(section_content)
                
                with open(output_tfile, 'a', encoding='utf-8') as f:
                    f.write(section_content + "\n")
                    
                all_content += section_content + "\n"

        # Final validation and saving
        xml_str = f"{header}<body>\n{all_content}</body>\n{footer}"
        
        # Validate the entire FB2 file using XSD
        validation_errors = xc.validate_fb2(xml_str)
        if validation_errors:
            if config.debug:
                ic("WARNING: Final FB2 validation failed with errors:")
                for err in validation_errors:
                    ic(f"  {err}")
        elif config.debug:
            ic("Final FB2 validation passed successfully.")

        write_to_file(xml_str, output_file)
        write_to_file(synopsis, synopsis_file)

        # ic rechunking statistics
        if rechunk_stats['runs'] > 0 and config.debug:
            failures_str = ", ".join([f"{f:.1f}%" for f in rechunk_stats['failures']])
            ic(f"Речанкинг: {rechunk_stats['runs']} запусков, из них {rechunk_stats['fixed']} исправлено, {rechunk_stats['not_fixed']} не исправлено" + (f" ({failures_str})" if rechunk_stats['failures'] else ""))

    else:
        raise ValueError(f"Unsupported file extension: {file_extension}")

if __name__ == '__main__':
    main()