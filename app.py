from icecream import ic
import os
import re
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
import src.utils as ta
import src.xmlcheck as xc

config_dir = Path(__file__).parent.resolve()

# load .env config
load_dotenv(config_dir / ".env")

api_key = os.getenv('API_KEY', '')  # Default value is an empty string
base_url = os.getenv('API_BASE', 'https://api.openai.com/v1')  # Default API base URL
sys_off = bool(os.getenv('S_PROMT'))  # Disable system prompt if set
model = os.getenv('MODEL', 'gpt-4-turbo')  # Default model is 'gpt-4-turbo'
temp = float(os.getenv('TEMP'))  # Temperature setting for the model
temp2 = float(os.getenv('TEMP2'))  # Secondary temperature setting
api_key2 = os.getenv('API_KEY2', '')  # Default value is an empty string for secondary API key
base_url2 = os.getenv('API_BASE2', 'https://api.openai.com/v1')  # Default secondary API base URL
sys_off2 = bool(os.getenv('S_PROMT2'))  # Disable secondary system prompt if set
model2 = os.getenv('MODEL2', 'gpt-4-turbo')  # Default secondary model is 'gpt-4-turbo'
api_timeout = int(os.getenv('TIMEOUT', 6000))  # Default API timeout is 6000 milliseconds
api_timeout2 = int(os.getenv('TIMEOUT2', 6000))  # Default secondary API timeout is 6000 milliseconds
#vocab = os.getenv('VOCAB', 'config/dict.txt')  # Vocabulary file path (commented out)
example = os.getenv('EXAMPLE', '')  # Example for TXT mode , add it to prompt  (default is an empty string)
source_lang = os.getenv('SOURCE_LANG')  # Source language
target_lang = os.getenv('TARGET_LANG')  # Target language
nothink = bool(os.getenv('NOTHINK'))  # Add /nothink for llama.cpp in prompt if set (1 - add, 0 - no add)
ner_opt = bool(os.getenv('NER',False))  # Enable Named Entity Recognition if set
country = os.getenv('COUNTRY')  # Country setting
nermodel = os.getenv('NERMODEL')  # Named Entity Recognition model
short = os.getenv('SHORT')  # Short setting
nothink2 = bool(os.getenv('NOTHINK2'))  # Add /nothink for llama.cpp in prompt if set for secondary
max_len_chunk = int(os.getenv('MAX_LEN_CHUNK'))  # Maximum length of chunks
myfile = Path(__file__).parent.resolve() / os.getenv('FILE', 'books/ExampleBook.fb2')  # File path (default is 'books/ExampleBook.fb2')
debug = os.getenv('DEBUG', 'False').lower() in ['true', '1', 't']  # Enable debug mode if set (values: 'true', '1', 't')
vocab = ""

if ner_opt:
    try:
        import src.ner as ner
    except ImportError as e:
        print(f"Ошибка импорта: {e}")
        # Обработка ошибки импорта

#sunny-narrator code by neowisard

def load_vocab_from_file(file_path, source_lang, target_lang):
    vocab = {}
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if line and '=' in line:
                source_word, target_word = line.split('=', 1)
                # Удаляем лишние пробелы с краев слов
                source_word = source_word.strip()
                target_word = target_word.strip()
                # Разделяем исходное слово на ключ и добавляем перевод
                key = source_word.replace(' ', '_')  # Используем нижнее подчеркивание вместо пробела в ключе
                if key not in vocab:
                    vocab[key] = {}
                vocab[key][source_lang] = source_word
                vocab[key][target_lang] = target_word
    ic(vocab)
    return vocab


def parse_xml(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        start_body = content.find('<body')
        end_body_tag = content.find('</body>')

        if start_body == -1 or end_body_tag == -1:
            raise ValueError("Body tag not found in the XML file")

        # Находим конец открывающего тега <body>
        end_start_body = content.find('>', start_body) + 1
        end_body = end_body_tag

        header = content[:start_body]
        body = content[end_start_body:end_body]
        footer = content[end_body_tag + len('</body>'):]

        # Удаление пространств имен
        body = re.sub(r'\sxmlns="[^"]+"', '', body, count=1)
        body = re.sub(r'<myheader>.*?</myheader>', '', body, flags=re.DOTALL)
        body = re.sub(r'<myfooter>.*?</myfooter>', '', body, flags=re.DOTALL)
        # Добавляем переводчика в title-info
        header = re.sub(r'</title-info>',
                        '<translator><nickname>Sunny narrator opensource AI translator </nickname> <email>n@uwns.org</email> </translator> </title-info>',
                        header, flags=re.DOTALL)

        # Удаляем <myheader> и <myfooter> из header и footer
        header = re.sub(r'<myheader>.*?</myheader>', '', header, flags=re.DOTALL)
        footer = re.sub(r'<myfooter>.*?</myfooter>', '', footer, flags=re.DOTALL)
        #header = f"{header}<body>"
        #footer = f"</body>/n{footer}"
        # Возвращаем новый body, обработанный header и footer
        ic(len(body))
        return body, header, footer

def read_txt_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return content



def prepare_chunks(body, max_len_chunk):
    body_str = body
    sections = []
    start_tags = {'<section>', '<SECTION>'}
    end_tags = {'</section>', '</SECTION>'}
    start = 0

    while start < len(body_str):
        # Find the start of the next section
        found_start_tag = None
        for tag in start_tags:
            pos = body_str.find(tag, start)
            if pos != -1 and (found_start_tag is None or pos < found_start_tag[1]):
                found_start_tag = (tag, pos)

        if not found_start_tag:
            break

        section_start = found_start_tag[1] + len(found_start_tag[0])
        section_end = body_str.find('</section>', section_start)

        if section_end == -1:
            break

        section = body_str[section_start:section_end]
        chunks = []

        # Split the section into chunks
        chunk_start = 0
        while chunk_start < len(section):
            chunk_end = chunk_start + max_len_chunk
            if chunk_end >= len(section):
                chunk_end = len(section)
            else:
                # Find the nearest </p> tag within the chunk
                pos = section.rfind('</p>', chunk_start, chunk_end)
                if pos != -1:
                    chunk_end = pos + len('</p>')

            chunks.append(section[chunk_start:chunk_end])
            chunk_start = chunk_end

        sections.append(chunks)
        start = section_end + len('</section>')

    return sections

def translatexml(source_text, source_lang, target_lang, outline_text, country, vocab_dict):
    translated_chunk = None
    style = 'xml'
    #source_text = source_text+" <empty-line/>"  #забыл зачем этот костыль
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
        if abs(percentage) > 5 and len(source_text) > 300:
                ic("Rechunking !!! ", percentage, "% percent")
                mx = int((len(source_text) // 2)*1.1)
                split_pos = source_text.rfind('</p>', 0, mx)+4
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
                if abs(percentage) < 5:
                    if debug:
                        ic("Fixed after rechunk, mx", mx, percentage, "% percent")
                else:
                    if debug:
                        ic("fuck !!!", percentage, "% percent chunk used")

        if translated_chunk is None:
            raise ValueError(f"Translation failed for chunk: {source_text}")
    except Exception as e:
        raise ValueError(f"Error during translation: {e}")

    return translated_chunk, outline

def chunkify_text(text, max_len_chunk, source_lang, target_lang, country,vocab_dict):
    chunks = []
    outline_text = ""
    start = 0
    end = 0
    text_len = len(text)
    style = 'txt'
    while start < text_len:
        end = start + max_len_chunk
        if end >= text_len:
            end = text_len
        else:
            # Ищем "\n\n" сначала
            while end > start and text[end-2:end] != '\n\n':
                end -= 1
            if end > start and text[end-2:end] == '\n\n':
                end -= 1  # Корректируем end, чтобы он указывал на символ перед "\n\n"
            else:
                # Если "\n\n" не найдено, ищем "\n"
                while end > start and text[end-1] != '\n':
                    end -= 1
                if end > start and text[end-1] == '\n':
                    end -= 1  # Корректируем end, чтобы он указывал на символ перед "\n"
                else:
                    # Если "\n" не найдено, ищем "."
                    while end > start and text[end-1] != '.':
                        end -= 1
                    if end == start:
                        end = start + max_len_chunk  # Если точка не найдена, разбиваем по max_len_chunk

        source_text = text[start:end]
        try:
            translated_chunk, outline  = ta.translate(source_lang, target_lang, source_text, style, outline_text, country,vocab_dict)
            outline_text = outline
            if translated_chunk is not None:
                chunks.append(translated_chunk)
            else:
                raise ValueError(f"Translation failed for chunk: {source_text}")
        except Exception as e:
            raise ValueError(f"Error during translation: {e}")
        start = end

    return chunks


def write_to_file(data, output_file):
    # Открываем файл в режиме 'w', что приводит к перезаписи файла при его наличии
    if isinstance(data, str):
        data = [data]

    with open(output_file, 'w', encoding='utf-8') as f:
        for line in data:
            f.write(line + '\n')

#/// Написать функцию перевода чанков здесь, перенеся ее из chunkify и вынес из app.translate и добавив словари  логику чтобы сделать синхронную\асинхронную на 2 LLM
#/// Это также поможет создать шкалу обработки
#/// в конец добавить notification

#Это существенно более быстрый поиск по словарю, но не учитывает окончания и схожеть
def find_matching_words_with_substring_search(text, vocab, lng):
    ic("Starting substring search matching")

    if not text or not vocab:
        ic("No text or vocabulary to process.")
        return []

    orig_values = [entry[lng] for entry in vocab.values() if lng in entry]

    # Create a set of all words and sub-words from the vocabulary
    vocab_words_set = set()
    for word in orig_values:
        sub_words = word.split()
        vocab_words_set.update(sub_words)
        vocab_words_set.add(word)

    # Normalize text to lower case for case-insensitive matching
    text_lower = text.lower()

    # Find matches using substring search
    matched_words_set = set()
    for vocab_word in vocab_words_set:
        if vocab_word.replace('_', ' ').lower() in text_lower:
            matched_words_set.add(vocab_word)

    ic(f"Found matching words: {matched_words_set}")
    return list(matched_words_set)

def main():

    file_name, file_extension = os.path.splitext(os.path.basename(myfile))
    file_name_without_ext = file_name
    output_dir = os.path.dirname(myfile)
    dict_file = f"{output_dir}/{file_name_without_ext}.dic"
    now = datetime.now()

    # Форматируем дату и время в строку в виде hhmm-ddmm
    formatted_time = now.strftime("%H%M-%d%m")



    if file_extension.lower() == '.fb2':
        output_file = f"{output_dir}/{file_name_without_ext}_{target_lang}_{short}_{formatted_time}.fb2"
        output_tfile = f"{output_dir}/{file_name_without_ext}_{target_lang}_tmp_{formatted_time}.fb2"
        synopsis_file = f"{output_dir}/{file_name_without_ext}_{target_lang}_{formatted_time}_synopsis.txt"
        # Вызов функции для обработки fb2 файла
        body, header, footer = parse_xml(myfile)



        #else:
        #    vocab_dict=""

            # ta_header = ta.translate(source_lang, target_lang, header, country)
        if ner_opt :
            if not os.path.exists(dict_file):
                # Если файла нет, выполнить его запись
                # Собираем словарик
                if debug:
                    ic("NER : making vocabulary")
                vb = ner.make_vocab(body)
                if debug:
                    ic(vb)
                vocab_dict = ta.vocabulary(source_lang, target_lang, vb, country, True)
                vocab_dict = ta.remove_tags(vocab_dict)
                write_to_file(vocab_dict, dict_file)
                raise ValueError(f"Vocabulary is ready, just correct it manually: {dict_file} and restart program")

            else:
                # Если файл уже существует, продолжить выполнение программы
                vocab = load_vocab_from_file(dict_file, source_lang, target_lang)

        orig_sections = prepare_chunks(body, max_len_chunk)

        translated_chunks = []
        synopsis = []
        outline_text = ''
        total_sections = len(orig_sections)
        vocab_dict = {}  # Initialize dictionary to store value pairs
        all_content = ''  # Initialize variable to store all content written to the file

        # Iterate over all sections
        with open(output_tfile, 'a', encoding='utf-8') as f:
            for section_index, section in enumerate(orig_sections):
                section_chunks = len(section)
                section_translation = ''

                for chunk_index, chunk in enumerate(section):
                    #found_strings = ner.find_matching_words_with_cosine_similarity(chunk, vocab, source_lang)
                    found_strings = find_matching_words_with_substring_search(chunk, vocab, source_lang)
                    ic("found_strings: ", found_strings)
                    if (section_index, chunk_index) not in vocab_dict:
                        vocab_dict[(section_index, chunk_index)] = []  # Initialize list for current iteration
                    for string in found_strings:
                        # Replace spaces with underscores to match keys in vocab dictionary
                        normalized_string = string.replace(' ', '_')
                        # Check if the string is entirely in the vocab dictionary
                        if normalized_string in vocab:
                            source_lang_word = vocab[normalized_string][source_lang]
                            target_lang_word = vocab[normalized_string][target_lang]
                            vocab_dict[(section_index, chunk_index)].append(f"{source_lang_word}={target_lang_word}")
                    if debug:
                        ic("translate: ", section_index + 1, total_sections, chunk_index + 1, section_chunks,
                           vocab_dict[(section_index, chunk_index)])  # Add output of current chunk number and total

                    translated_chunk, outline_text = translatexml(chunk, source_lang, target_lang, outline_text,
                                                                  country, vocab_dict[(section_index, chunk_index)])

                    if translated_chunk is not None:
                        section_translation += translated_chunk + '\n'
                        translated_chunks.append(translated_chunk)
                        synopsis.append(outline_text)

                # Write the translated section to the file with section tags
                if section_translation:
                    section_content = '<section>\n' + section_translation + '\n</section>\n'
                    ic(section_content)
                    f.write(section_content)
                    all_content += section_content

        # Print or use the all_content variable as needed
            # ic(vocab_dict[0])
            # ic(vocab_dict[2])
            # raise ValueError("Ended")

        # Открываем файл в режиме добавления



        #write_to_file(translated_chunks, output_tfile)
        # Валидация итога
        xml_str = "<body>"+all_content+"</body>"
        parsed_html = xc.rem_tags(xml_str)
        xml_str = header + parsed_html + footer

        #chunks,synopsis = chunkify_fb2(body, max_len_chunk, source_lang, target_lang, country, vocab_dict)
        write_to_file(xml_str, output_file)
        write_to_file(synopsis, synopsis_file)

    elif file_extension.lower() == '.txt':
        #Тут код значимо отстал, словаря нет вроде , цикла нет. Надо копировать с fb2
        output_file = f"{output_dir}/{file_name_without_ext}_{target_lang}.txt"
        text = read_txt_file(myfile)
        # Вызов функции для обработки txt файла
        if not os.path.exists(dict_file):
            # Если файла нет, выполнить его запись
            # Собираем словарик
            vb = ner.make_vocab(text)
            vocab_dict = ta.vocabulary(source_lang, target_lang, vb, country, False)
            write_to_file(vocab_dict, dict_file)
            raise ValueError(f"Vocabulary is ready, just correct it manually: {dict_file} and restart program")

        else:
            # Если файл уже существует, продолжить выполнение программы
            #vocab_dict = load_vocab_from_file(vocab, source_lang, target_lang)
            pass
        #chunks = chunkify_text(text, max_len_chunk, source_lang, target_lang, country, vocab_dict)
        header=''
        footer=''
        #write_to_file(chunks, output_file)
    else                                                           :
        raise ValueError(f"Unsupported file extension: {file_extension}")


if __name__ == '__main__':
    main()