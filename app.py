from icecream import ic
import asyncio
import os
import sys
import base64
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

async def translatexml(source_text, source_lang, target_lang, outline_text, country, vocab_dict):
    translated_chunk = None
    style = 'xml'
    
    try:
        # Wrapper to handle async generator from ta.translate
        # We need to capture the 'final' result for percentage checks
        
        current_outline = ""
        current_translation = ""
        
        async for kind, val in ta.translate(
            source_lang, target_lang, source_text, style, outline_text,
            country, vocab_dict):
            
            if kind == 'outline':
                current_outline = val
                yield kind, val
            elif kind == 'final':
                current_translation = val
        
        translated_chunk = current_translation
        outline = current_outline

        percentage = ((len(translated_chunk) - len(source_text)) / len(source_text)) * 100
        if config.debug:
            ic(percentage, "% percent")
        
        if abs(percentage) == 100:
            # Retry logic
            async for kind, val in ta.translate(
                source_lang, target_lang, source_text, style, outline_text,
                country, vocab_dict):
                if kind == 'outline':
                    # We yield new outline if retry happens
                    current_outline = val
                    yield kind, val 
                elif kind == 'final':
                    current_translation = val
            translated_chunk = current_translation
            outline = current_outline
                
        if abs(percentage) > 7 and len(source_text) > 500:
            
            if config.debug:
                ic("Rechunking !!! ", percentage, "% percent")
            mx = int((len(source_text) // 2) * 1.1)
            split_pos = source_text.rfind('</p>', 0, mx)
            if split_pos == -1:
                split_pos = mx
            else:
                split_pos += 4
            splitchunks = source_text[:split_pos], source_text[split_pos:]
            translated_chunk = ""
            outline = "" # We aggregate outline from chunks? Or just ignore? 
                         # Usually outline is a summary of the whole. 
                         # For rechunking, maybe concatenation is okay-ish or we just keep the previous one.
                         # Let's accumulate for correctness of return type.

            rechunk_stats['runs'] += 1
            for chunk in splitchunks:
                # Sub-chunks
                async for kind, val in ta.translate(
                    source_lang, target_lang, chunk, style, outline_text,
                    country, vocab_dict):
                    
                    if kind == 'final':
                        translated_chunk += val
                    elif kind == 'outline':
                        outline += val # Append outlines? Rough approximation.

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

    yield 'final', translated_chunk

def write_to_file(data, output_file):
    if isinstance(data, str):
        data = [data]

    with open(output_file, 'w', encoding='utf-8') as f:
        for line in data:
            f.write(line + '\n')

async def main():
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
        output_file = f"{output_dir}/{file_name_without_ext}_{config.target_lang}_{formatted_time}.fb2"
        output_tfile = f"{output_dir}/{file_name_without_ext}_{config.target_lang}_tmp_{formatted_time}.fb2"
        #synopsis_file = f"{output_dir}/{file_name_without_ext}_{config.target_lang}_{formatted_time}_synopsis.txt"
        
        # Parse file based on extension
        if file_extension.lower() == '.fb2':
            body, header, footer = fb2.parse_xml(myfile)
        elif file_extension.lower() == '.epub':
            body, header, footer = epub.parse_epub(myfile)
        else:
            body, header, footer = txt.parse_txt(myfile)

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
                    
                vocab_dict_initial = await ta.vocabulary(config.source_lang, config.target_lang, vb, config.country, False)
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


        # --- Async Translation Pipeline ---
        
        # Determine total chunks to help with ordering
        all_chunks = []
        for s_idx, section in enumerate(orig_sections):
            for c_idx, chunk in enumerate(section):
                all_chunks.append({
                    'chunk': chunk,
                    'section_idx': s_idx,
                    'chunk_idx': c_idx,
                    'global_id': len(all_chunks)
                })
        
        total_chunks = len(all_chunks)
        results = {}
        next_to_write = 0
        
        # Shared context for "leaky" sequential dependency
        context_lock = asyncio.Lock()
        shared_outline = {'text': ''}
        
        concurrent_limit = config.concurrent_limit
        sem = asyncio.Semaphore(concurrent_limit)
        
        # Events for staggered start
        # events[i] is set when chunk i has produced its outline
        # Chunk i+1 waits for events[i]
        outline_events = [asyncio.Event() for _ in range(total_chunks)]
        
        # We pre-set the "dummy" event for the very first chunk so it doesn't wait
        # actually we can just handle index 0 separately, but a dummy event -1 is harder with list.
        # We'll just handle logic inside task.

        async def process_chunk_task(item):
            chunk = item['chunk']
            s_idx = item['section_idx']
            c_idx = item['chunk_idx']
            g_id = item['global_id']
            section_chunks = len(orig_sections[s_idx])
            
            # Wait for previous chunk's outline if not the first one
            if g_id > 0:
                 # Logic for staggered start
                 prev_event = outline_events[g_id - 1]
                 await prev_event.wait()
            
            async with sem:
                # Find matching words for dictionary injection
                found_strings = []
                if config.ner_opt and ner and vocab:
                    found_strings = ner.find_matching_words_with_cosine_similarity(chunk, vocab, config.source_lang)
                    # if config.debug:
                    #     ic("found_strings: ", found_strings)

                key = (s_idx, c_idx)
                if key not in vocab_dict_map:
                    vocab_dict_map[key] = []
                
                for string in found_strings:
                    normalized_string = string.replace(' ', '_')
                    if normalized_string in vocab:
                        source_lang_word = vocab[normalized_string][config.source_lang]
                        target_lang_word = vocab[normalized_string][config.target_lang]
                        vocab_dict_map[key].append(f"{source_lang_word}={target_lang_word}")
                
                if config.debug:
                    ic("translate: ", s_idx + 1, len(orig_sections), c_idx + 1, section_chunks,
                       vocab_dict_map[key])

                # Get current outline (context)
                current_context = shared_outline['text']
                
                final_content = None
                new_outline_val = ""

                # Consume generator
                async for kind, val in translatexml(
                    chunk, config.source_lang, config.target_lang, current_context,
                    config.country, vocab_dict_map[key]):
                    
                    if kind == 'outline':
                        new_outline_val = val
                        # Update shared outline
                        async with context_lock:
                            shared_outline['text'] = new_outline_val
                        
                        # Trigger event for next chunk
                        outline_events[g_id].set()
                        
                    elif kind == 'final':
                        final_content = val
                
                # Fallback: ensure event is set if not already (e.g. if generator finished without outline)
                if not outline_events[g_id].is_set():
                    outline_events[g_id].set()

                return {
                    'global_id': g_id,
                    'content': final_content,
                    'synopsis': new_outline_val
                }

        # Create tasks
        tasks = [asyncio.create_task(process_chunk_task(item)) for item in all_chunks]
        
        # Process as they complete
        for future in asyncio.as_completed(tasks):
            res = await future
            g_id = res['global_id']
            results[g_id] = res['content']
            
            # Write available consecutive chunks
            while next_to_write in results:
                content_to_write = results[next_to_write]
                # Synopsis logic not strictly needed for file output, just keeping track of state
                
                section_content = xc.rem_tags(content_to_write)
                all_content += section_content + "\n"
                
                with open(output_tfile, 'a', encoding='utf-8') as f:
                    f.write(section_content + "\n")
                
                # Clean up memory
                del results[next_to_write]
                next_to_write += 1

        ## Extract and translate metadata (for all formats that have a header)
        metadata = None
        translated_metadata = None
        if header:
            if config.debug:
                ic("Extracting and translating metadata...")
            metadata = fb2.extract_metadata(header)
            if metadata:
                # Include target language from config
                lang_map = {'russian': 'ru', 'english': 'en', 'french': 'fr', 'german': 'de'}
                target_code = lang_map.get(config.target_lang.lower(), config.target_code if hasattr(config, 'target_code') else config.target_lang)
                metadata['lang'] = target_code
                
                translated_metadata = await ta.translate_metadata(
                    metadata, config.source_lang, config.target_lang, config.country
                )
                if translated_metadata:
                    header = fb2.update_header_with_metadata(header, translated_metadata)
                    if config.debug:
                        ic("Metadata translated and header updated.")

        # Process Cover Image (for all formats)
        if config.api_key3:
            # Use appropriate handler or just fb2_handler since structure is unified
            # We can use the module corresponding to extension, but functions are wrappers around fb2 anyway mostly
            # Actually easier to just use fb2 or dynamically chosen handler if logic diverged.
            # But currently epub/txt helpers just call fb2.
            # Let's trust fb2 methods work on the XML strings.
            
            cover_data = fb2.get_cover_image(header, footer)
            if cover_data:
                if config.debug:
                    ic("Processing cover image...")
                
                # Use translated_metadata if available, otherwise original metadata
                meta_to_pass = translated_metadata or metadata
                
                # Updated call with new signature
                cover_result = await ta.process_image_request(
                    cover_data, 
                    config.source_lang, 
                    config.target_lang, 
                    config.country,
                    meta_to_pass
                )
                if cover_result:
                    header, footer, body = fb2.replace_cover_image(header, footer, body, cover_result)
                    
                    # Save cover to file
                    cover_file = f"{output_dir}/{file_name_without_ext}_cover.jpg"
                    try:
                        with open(cover_file, 'wb') as f:
                            f.write(base64.b64decode(cover_result))
                        if config.debug:
                            ic(f"Cover image saved to {cover_file}")
                    except Exception as e:
                        if config.debug:
                            ic(f"Error saving cover image: {e}")

                    if config.debug:
                        ic("Cover image processed/replaced.")

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
        #write_to_file(synopsis, synopsis_file)

        # ic rechunking statistics
        if rechunk_stats['runs'] > 0 and config.debug:
            failures_str = ", ".join([f"{f:.1f}%" for f in rechunk_stats['failures']])
            ic(f"Речанкинг: {rechunk_stats['runs']} запусков, из них {rechunk_stats['fixed']} исправлено, {rechunk_stats['not_fixed']} не исправлено" + (f" ({failures_str})" if rechunk_stats['failures'] else ""))

    else:
        raise ValueError(f"Unsupported file extension: {file_extension}")

if __name__ == '__main__':
    asyncio.run(main())