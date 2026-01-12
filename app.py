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
from src.config import Config

# Initialize configuration
config = Config()

# Conditional import of NER module
ner = None
if config.ner_opt:
    try:
        import src.ner as ner_module
        ner = ner_module
    except ImportError as e:
        print(f"Import Error: {e}")
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
        ic(percentage, "% percent")
        
        if abs(percentage) == 100:
            translated_chunk, outline = ta.translate(
                source_lang, target_lang, source_text, style, outline_text,
                country, vocab_dict)
                
        if abs(percentage) > 7 and len(source_text) > 500:
            ic("Rechunking !!! ", percentage, "% percent")
            mx = int((len(source_text) // 2) * 1.1)
            split_pos = source_text.rfind('</p>', 0, mx) + 4
            if split_pos == -1:
                split_pos = mx
            splitchunks = source_text[:split_pos], source_text[split_pos:]
            translated_chunk = ""
            outline = ""

            for chunk in splitchunks:
                ch, outline_chunk = ta.translate(
                    source_lang, target_lang, chunk, style, outline_text,
                    country, vocab_dict)
                translated_chunk += ch
                outline += outline_chunk

            percentage = ((len(translated_chunk) - len(source_text)) / len(source_text)) * 100
            if abs(percentage) < 7:
                if config.debug:
                    ic("Fixed after rechunk, mx", mx, percentage, "% percent")
            else:
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
        print(f"File not found: {myfile}")
        return

    file_name, file_extension = os.path.splitext(os.path.basename(myfile))
    file_name_without_ext = file_name
    output_dir = os.path.dirname(myfile)
    dict_file = f"{output_dir}/{file_name_without_ext}.dic"
    now = datetime.now()

    formatted_time = now.strftime("%H%M-%d%m")

    if file_extension.lower() == '.fb2':
        output_file = f"{output_dir}/{file_name_without_ext}_{config.target_lang}_{config.short}_{formatted_time}.fb2"
        output_tfile = f"{output_dir}/{file_name_without_ext}_{config.target_lang}_tmp_{formatted_time}.fb2"
        synopsis_file = f"{output_dir}/{file_name_without_ext}_{config.target_lang}_{formatted_time}_synopsis.txt"
        
        # Parse FB2 file
        body, header, footer = fb2.parse_xml(myfile)

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
                print(f"Vocabulary is ready. Please correct it manually: {dict_file} and restart the program.")
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
        with open(output_tfile, 'a', encoding='utf-8') as f:
            for section_index, section in enumerate(orig_sections):
                section_chunks = len(section)
                section_translation = ''

                for chunk_index, chunk in enumerate(section):
                    # Find matching words for dictionary injection
                    found_strings = []
                    if config.ner_opt and ner and vocab:
                        found_strings = ner.find_matching_words_with_cosine_similarity(chunk, vocab, config.source_lang)
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
                    section_content = '<section>\n' + section_translation + '\n</section>\n'
                    ic(section_content)
                    f.write(section_content)
                    all_content += section_content

        # Final validation and saving
        xml_str = "<body>" + all_content + "</body>"
        parsed_html = xc.rem_tags(xml_str)
        xml_str = header + parsed_html + footer

        write_to_file(xml_str, output_file)
        write_to_file(synopsis, synopsis_file)

    elif file_extension.lower() == '.txt':
        # TODO: Update TXT handling to match FB2 improvements
        output_file = f"{output_dir}/{file_name_without_ext}_{config.target_lang}.txt"
        text = read_txt_file(myfile)
        
        if config.ner_opt and ner:
            if not os.path.exists(dict_file):
                vb = ner.make_vocab(text)
                vocab_dict_initial = ta.vocabulary(config.source_lang, config.target_lang, vb, config.country, False)
                write_to_file(vocab_dict_initial, dict_file)
                print(f"Vocabulary is ready. Please correct it manually: {dict_file} and restart the program.")
                sys.exit(0)
            else:
                 pass
        
        # logic for splitting text and translating would go here
        print("TXT translation not fully implemented in this refactor version.")
        
    else:
        raise ValueError(f"Unsupported file extension: {file_extension}")

if __name__ == '__main__':
    main()