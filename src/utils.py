import logging
import functools
from typing import Union
import openai
import tiktoken
import re
import json
import time
import io
import base64
from PIL import Image
from src.config import Config

# Initialize global config (can be overridden or passed if needed, but for now this replaces the 'from app import ...')
config = Config()

# Setup logging
logger = logging.getLogger(__name__)
if config.debug:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def log_entry(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"Entering function: {func.__name__}")
        return func(*args, **kwargs)
    return wrapper

# Discrete chunks to translate one chunk at a time
MAX_TOKENS_PER_CHUNK = config.max_len_chunk * 4  # if text is more than this many tokens, we'll break it up into bytes x2 to tokens

# Language mapping for models requiring ISO codes (like TranslateGemma)
LANG_MAP = {
    "english": "en",
    "russian": "ru",
    "chinese": "zh",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "italian": "it",
    "japanese": "ja",
    "korean": "ko",
    "portuguese": "pt",
    "czech": "cs",
    "polish": "pl",
    "ukrainian": "uk",
    "turkish": "tr",
    "dutch": "nl",
}

class LLMService:
    @log_entry
    def __init__(self):
        self.clientTranslate = openai.OpenAI(
            api_key=config.api_key_translate,
            base_url=config.base_url_translate,
            timeout=config.timeout_translate
        )
        self.clientProofread = openai.OpenAI(
            api_key=config.api_key_proofread,
            base_url=config.base_url_proofread,
            timeout=config.timeout_proofread
        )
        self.clientImages = openai.OpenAI(
            api_key=config.api_key_images,
            base_url=config.base_url_images,
            timeout=config.timeout_images
        )

    @log_entry
    def get_completion(self, role="Translate", prompt_category=None, prompt_key="user", json_mode=False, max_tokens=MAX_TOKENS_PER_CHUNK, **kwargs):
        if role == "Translate":
            client, model, temp, sys_off, nothink, label = (
                self.clientTranslate, config.model_translate, config.temp_translate, config.sys_not_promt_translate, config.nothink_translate, "Translate"
            )
        else:
            client, model, temp, sys_off, nothink, label = (
                self.clientProofread, config.model_proofread, config.temp_proofread, config.sys_not_promt_proofread, config.nothink_proofread, "Proofread"
            )

        system_message = config.get_prompt(prompt_category, "system", **kwargs)
        user_message = config.get_prompt(prompt_category, prompt_key, **kwargs)

        if sys_off:
            user_message = f"{system_message}.{user_message}"
            if config.debug:
                print(f"DEBUG: Selected system off message")
            system_message = None

        if nothink:
            if config.debug:
                print(f"DEBUG: Selected nothink message")
            if system_message:
                system_message = f"{system_message} /no_think"
            else:
                user_message = f"{user_message}  /no_think"

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})

        if model == "TranslateGemma":
            src = kwargs.get("source_lang", config.source_lang)
            tgt = kwargs.get("target_lang", config.target_lang)
            src_code = LANG_MAP.get(src.lower(), src)
            tgt_code = LANG_MAP.get(tgt.lower(), tgt)
            if config.debug:
                print(f"DEBUG: Selected TranslateGemma message")
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "source_lang_code": src_code,
                        "target_lang_code": tgt_code,
                        "text": user_message
                    }
                ]
            })
        else:
            messages.append({"role": "user", "content": user_message})

        if config.debug:
            print(f"DEBUG: Input length: {num_tokens_in_string(user_message)} tokens, Action: {label}")

        comp_kwargs = {
            "model": model,
            "temperature": kwargs.get("temperature", temp),
            "max_tokens": max_tokens,
            "messages": messages
        }
        if json_mode:
            comp_kwargs["response_format"] = {"type": "json_object"}

        # Raw prompt logging
        logger.debug(f"OpenAI API Request ({label}): {json.dumps(comp_kwargs, ensure_ascii=False, indent=2)}")

        response = client.chat.completions.create(**comp_kwargs)
        result = response.choices[0].message.content

        # Raw response logging
        logger.debug(f"OpenAI API Response ({label}): {result}")

        return result

llm_service = LLMService()

@log_entry
def remove_tags(text):
    """
    Removes various XML/HTML tags and specific artifacts from the text.
    """
    #pattern = r'<SOURCE_TEXT>.*?</SOURCE_TEXT>|<INITIAL_TRANSLATION>.*?</INITIAL_TRANSLATION>|<DICTIONARY>.*?</DICTIONARY>|<FIRST_TRANSLATION>.*?</FIRST_TRANSLATION>|<EXPERT_SUGGESTIONS>.*?</EXPERT_SUGGESTIONS>|<TRANSLATION>|</TRANSLATION>|<SOURCE>|</SOURCE>|<SYNOPSIS>.*?</SYNOPSIS>|<think>.*?</think>|<myheader>.*?</myheader>|<myfooter>.*?</myfooter>|</section>|<section>|<IMPROVED_TRANSLATION>|</IMPROVED_TRANSLATION>|```xml|```|OceanofPDF.com|</target>|<target>|<a l:href="https://oceanofpdf.com">|<\|channel\|>.*?<\|end\|>|<TTEXT>|</TTEXT>|<SYNOPSIS>|<\|im_end\|>|<\|file_separator\|>|</think>'
    #cleaned_text = re.sub(pattern, '', text, flags=re.DOTALL)
    pattern = r'''<SOURCE_TEXT>[\s\S]*?</SOURCE_TEXT>|<DICTIONARY>[\s\S]*?</DICTIONARY>|<EXPERT_SUGGESTIONS>[\s\S]*?</EXPERT_SUGGESTIONS>|<SYNOPSIS>[\s\S]*?</SYNOPSIS>|<think>[\s\S]*?</think>|<myheader>[\s\S]*?</myheader>|<myfooter>[\s\S]*?</myfooter>|<\|channel\|>[\s\S]*?<\|end\|>|```xml|```|OceanofPDF\.com|<a l:href="https://oceanofpdf.com">|</?(?:INITIAL_TRANSLATION|FIRST_TRANSLATION|TRANSLATION|SOURCE|section|IMPROVED_TRANSLATION|target|TTEXT|SYNOPSIS|TRANS)>|<\|im_end\|>|<\|file_separator\|>'''
    cleaned = re.sub(pattern, '', text, flags=re.IGNORECASE | re.VERBOSE)
    return cleaned

@log_entry
def check_and_print_tags(text):
    """
    Finds and returns a list of specific tags present in the text.
    """
    pattern = r'<SOURCE_TEXT>.*?</SOURCE_TEXT>|<INITIAL_TRANSLATION>.*?</INITIAL_TRANSLATION>|<EXPERT_SUGGESTIONS>.*?</EXPERT_SUGGESTIONS>|<TRANSLATION>.*?</TRANSLATION>|<SOURCE>|</SOURCE>|<SYNOPSIS>.*?</SYNOPSIS>|<think>.*?</think>|<myheader>.*?</myheader>|<myfooter>.*?</myfooter>|```xml.*?```'
    matches = re.findall(pattern, text)
    return matches

@log_entry
def remove_markers(text: str) -> str:
    """
    Removes @@@TAG_000n@@@ markers and any leftover bracket artifacts from text
    to prepare clean input for synopsis/outline generation.
    """
    # Remove standard markers @@@TAG_0001@@@
    text = re.sub(r'@@@TAG_\d+@@@', '', text)
    # Remove any other content in triple at-signs just in case @@@...@@@
    text = re.sub(r'@@@.*?@@@', '', text)
    # Remove orphan triple at-signs
    text = re.sub(r'@@@', '', text)
    # Clean up multiple spaces resulting from removals
    text = re.sub(r'\s+', ' ', text).strip()
    return text

@log_entry
def split_text_smartly(text: str) -> tuple[str, str]:
    """
    Splits text roughly in half, trying to respect paragraph boundaries (</p>).
    """
    if not text:
        return "", ""
        
    length = len(text)
    mx = int((length // 2) * 1.1)
    
    # Try to find closing p tag
    split_pos = text.rfind('</p>', 0, mx)
    
    if split_pos == -1:
        # Fallback to simple middle split if no tag found
        split_pos = mx if mx < length else length // 2
    else:
        split_pos += 4 # Include the </p>
        
    return text[:split_pos], text[split_pos:]

@log_entry
def process_with_retries_and_rechunking(
    func, 
    source_text: str, 
    validation_func=None,
    initial_temp: float = 0.1,
    role: str = "Translate"
) -> str:
    """
    Executes a generation function with retries on validation failure, 
    and falls back to recursive rechunking if all retries fail.
    
    Args:
        func: Async callable taking (text, temperature) -> result str
        source_text: The input text
        validation_func: Callable(source, target) -> bool
        initial_temp: Starting temperature
        role: Logging role
    """
    current_temp = initial_temp
    
    # 1. Attempt with retries
    for attempt in range(3):
        try:
            result = func(source_text, temperature=current_temp)
            #cleaned_result =  remove_tags(result)
            
            if not validation_func:
                return result
                
            if validation_func(source_text, result):
                if config.debug and attempt > 0:
                     print(f"DEBUG: {role} successful on attempt {attempt + 1} with temp {current_temp:.2f}")
                return result
                
            if config.debug:
                source_len = len(source_text)
                target_len = len(result)
                diff = abs(target_len - source_len) / source_len if source_len > 0 else 0
                print(f"DEBUG: {role} attempt {attempt + 1} failed validation: diff {diff:.2%}. Retrying...")
                print(f"DEBUG: Source len: {source_len}, Target len: {target_len}")
                print(f"DEBUG: Source: {source_text}")
                print(f"DEBUG: Target: {cleaned_result}")
                
            current_temp += 0.1
            
        except Exception as e:
            if config.debug:
                 print(f"DEBUG: {role} attempt {attempt + 1} raised error: {e}")
            current_temp += 0.1

    # 2. Rechunking Fallback
    if len(source_text) > 500: # Only split if text is reasonably long
        if config.debug:
            print(f"DEBUG: {role} failed all retry attempts. Splitting text...")
            
        part1, part2 = split_text_smartly(source_text)
        
        # Recursively process parts
        # We need validation logic for parts too
        res1 = process_with_retries_and_rechunking(
            func, part1, validation_func, initial_temp, role
        )
        res2 = process_with_retries_and_rechunking(
            func, part2, validation_func, initial_temp, role
        )
        
        return res1 + res2
    else:
        if config.debug:
            print(f"DEBUG: {role} failed and text too short to split. Returning last result.")
        return cleaned_result  # Return whatever we got last

@log_entry
def process_with_retries_only(
    func, 
    source_text: str, # Not really used for splitting, just for logging length
    validation_func=None,
    initial_temp: float = 0.1,
    role: str = "Translate"
) -> str:
    """
    Executes a generation function with retries on validation failure.
    Does NOT attempt to split text.
    """
    current_temp = initial_temp
    
    # Attempt with retries
    for attempt in range(3):
        try:
            result = func(temperature=current_temp)
            cleaned_result = remove_tags(result)
            
            if not validation_func:
                return cleaned_result
                
            if validation_func(source_text, cleaned_result):
                if config.debug and attempt > 0:
                     print(f"DEBUG: {role} successful on attempt {attempt + 1} with temp {current_temp:.2f}")
                return cleaned_result
                
            if config.debug:
                # Basic diff logging
                print(f"DEBUG: {role} attempt {attempt + 1} failed validation. Retrying...")
                
            current_temp += 0.1
            
        except Exception as e:
            if config.debug:
                  print(f"DEBUG: {role} attempt {attempt + 1} raised error: {e}")
            current_temp += 0.1
            
    # Return last result even if failed
    if config.debug:
        print(f"DEBUG: {role} failed all retry attempts. Returning last result.")
    return cleaned_result



@log_entry
def one_chunk_initial_translation(
        source_lang: str, target_lang: str, source_text: str, style: str, outline_text: str, vocab_dict, role: str, **kwargs
) -> str:
    """
    Translate the entire text as one chunk using an LLM.
    Includes length control: if the result differs by more than 15%, retries with higher temperature.
    """
    def length_validator(source, target):
        if not source: return True
        s_len = len(source)
        t_len = len(target)
        diff = abs(t_len - s_len) / s_len
        return diff <= 0.22

    if config.example:
        outline_text = f"{outline_text}.{config.example}"

    prompt_key = "user_xml" if style == 'xml' else "user_text"
    if role == "Translate" and config.model_translate == "Hunyuan":
        prompt_key = "user_hunyuan"
        
    def generation_func(text, temperature):
        return llm_service.get_completion(
            role=role, 
            prompt_category="initial_translation", 
            prompt_key=prompt_key,
            source_lang=source_lang,
            target_lang=target_lang,
            outline_text=outline_text,
            vocab_dict=vocab_dict,
            source_text=text,
            temperature=temperature
        )

    def combined_validator(source, target):
        # Length check only (markers removed)
        if not source: return True
        s_len = len(source)
        t_len = len(target)
        diff = abs(t_len - s_len) / s_len
        if diff > 0.22:
             if config.debug:
                 print(f"DEBUG: Initial Translation length mismatch {diff:.2%}")
             return False
        return True

    return process_with_retries_and_rechunking(
        generation_func,
        source_text,
        combined_validator,
        float(kwargs.get('temperature', config.temp_translate)),
        role="Initial Translation"
    )

@log_entry
def one_chunk_referat(
         target_lang: str, final_translation: str,  role: str
) -> str:
    """
    Make the synopsis (referat) for chunk using an LLM.
    """
    translation = llm_service.get_completion(
        role=role,
        prompt_category="synopsis",
        target_lang=target_lang,
        final_translation=final_translation,
        max_tokens=160
    )
    return remove_tags(translation)

@log_entry
def one_chunk_editor(source_lang: str, source_text: str, translation_1: str, style: str, lang: str, country: str, role: str, **kwargs
) -> str:
    """
    Edits and proofreads the text. Compares original + translation to restore XML tags.
    """
    prompt_key = "user_xml" if style == 'xml' else "user_text"
    
    # Same validator as translation 
    def length_validator(source, target):
        if not source: return True
        s_len = len(source)
        t_len = len(target)
        diff = abs(t_len - s_len) / s_len
        return diff <= 0.25

    def generation_func(text, temperature):
         return llm_service.get_completion(
            role=role,
            prompt_category="editor",
            prompt_key=prompt_key,
            source_lang=source_lang,
            source_text=source_text,  # Original for comparison
            translation_1=translation_1,  # Translation to edit
            target_lang=lang,
            country=country,
            temperature=temperature
        )

    # Editor uses length_validator only
    return process_with_retries_and_rechunking(
        generation_func,
        translation_1,  # Process the translation, not the source
        length_validator,
        config.temp_proofread,
        role="Editor"
    )

@log_entry
def vocabulary(
        source_lang: str,
        target_lang: str,
        source_text: str,
        country: str,
        role: str,
) -> str:
    """
    Use an LLM to generate vocabulary for proper nouns.
    """
    translation = llm_service.get_completion(
        role=role,
        prompt_category="vocabulary",
        source_lang=source_lang,
        target_lang=target_lang,
        country=country,
        source_text=source_text
    )
    if config.debug:
        print(f"DEBUG: Vocabulary: {translation}")
    return translation

@log_entry
def one_chunk_reflect_on_translation(
        source_lang: str,
        target_lang: str,
        source_text: str,
        translation_1: str,
        country: str ,
        vocab_dict,
        role: str,
) -> str:
    """
    Reflect on the initial translation and provide suggestions for improvement.
    """
    translation = llm_service.get_completion(
        role=role,
        prompt_category="reflect_on_translation",
        source_lang=source_lang,
        target_lang=target_lang,
        source_text=source_text,
        translation_1=translation_1,
        country=country,
        vocab_dict=vocab_dict,
        max_tokens=int(MAX_TOKENS_PER_CHUNK / 4)
    )
    return remove_tags(translation)

@log_entry
def one_chunk_improve_translation(
        source_lang: str,
        target_lang: str,
        source_text: str,
        translation_1: str,
        reflection: str,
        style: str,
        role: str,
) -> str:
    """
    Use the reflection to improve the translation.
    """
    prompt_key = "user_xml" if style == 'xml' else "user_text"
    
    def generation_func(temperature=0.1):
        return llm_service.get_completion(
            role=role,
            prompt_category="improve_translation",
            prompt_key=prompt_key,
            source_lang=source_lang,
            target_lang=target_lang,
            source_text="  " + source_text,
            translation_1=translation_1,
            reflection=reflection,
            temperature=temperature
        )

    def marker_validator(source, target):
        # We don't have explicit markers passed here yet.
        # Logic: If translation_1 had markers, improved should have them.
        # Check source_text for markers?
        # Extract markers from source_text
        markers = re.findall(r'@@@TAG_\d+@@@', source_text)
        missing = [m for m in markers if m not in target]
        if missing:
            if config.debug:
                 print(f"DEBUG: Improve Translation missing markers: {missing}")
            return False
        return True

    return process_with_retries_only(
        generation_func,
        source_text,
        marker_validator,
        initial_temp=config.temp_proofread,
        role="Improve Translation"
    )

@log_entry
def num_tokens_in_string(
        input_str: str, encoding_name: str = "cl100k_base"
) -> int:
    """
    Calculate the number of tokens in a given string using a specified encoding.
    """
    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception:
        # Fallback if encoding name is not found, though cl100k_base should be standard
        encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(input_str))
    return num_tokens

@log_entry
def calculate_chunk_size(token_count: int, token_limit: int) -> int:
    """
    Calculate the chunk size based on the token count and token limit.
    """
    if token_count <= token_limit:
        return token_count

    num_chunks = (token_count + token_limit - 1) // token_limit
    chunk_size = token_count // num_chunks

    remaining_tokens = token_count % token_limit
    if remaining_tokens > 0:
        chunk_size += remaining_tokens // num_chunks

    return chunk_size

@log_entry
def translate(
        source_lang,
        target_lang,
        source_text,
        style,
        outline_text,
        country,
        vocab_dict,
        max_tokens=MAX_TOKENS_PER_CHUNK,
        temperature=None
):
    """Translate the source_text from source_lang to target_lang."""

    num_tokens_in_text = num_tokens_in_string(source_text)

    if config.debug:
        print(f"DEBUG: num_tokens_in_text: {num_tokens_in_text}")

    # Simplified check, original logic raise error if oversized but here we trust the chunker upstream for now or just process it.
    # The original code raised ValueError("Chunks is oversized!!!") if > max_tokens. 
    # We will keep that behavior but perhaps it should be handled more gracefully in production.
    if num_tokens_in_text <= max_tokens:
        if config.debug:
            print("DEBUG: Translating text as a single chunk")

        # Step 1: Initial translation
        start_time = time.time()
        role = "Translate"

        translation_1 = one_chunk_initial_translation(
            source_lang, target_lang, source_text, style, outline_text, vocab_dict, role, temperature=temperature
        )
        translation_1_time = time.time() - start_time
        if config.debug:
            print(f"DEBUG: Translation 1 time: {translation_1_time:.2f}s, tokens: {num_tokens_in_string(translation_1)}, translation: {translation_1}")
            #print(f"DEBUG: Style: {style}, Outline: {outline_text}, role: {role}")

        # Step 2: Outline
        start_time = time.time()
        role = "Proofread"
        outline_text = one_chunk_referat(target_lang, translation_1, role)
        outline_time = time.time() - start_time
        if config.debug:
            print(f"DEBUG: Outline time: {outline_time:.2f}s, tokens: {num_tokens_in_string(outline_text)}, outline: {outline_text} role: {role}")
                
        # YIELD OUTLINE EARLY - REPLACED WITH RETURN AT END
        # yield ("outline", outline_text)

        if config.fast_trans:
            if config.debug:
               print("DEBUG: Fast translation mode: Skipping Reflection and Improvement steps")
            
            # Step 5: Final translation (using translation_1)
            start_time = time.time()
            role = "Proofread"
            final_translation = one_chunk_editor(source_lang, source_text, translation_1, style, target_lang, country, role)
            final_translation_time = time.time() - start_time
            #if config.debug:
            #     print(f"DEBUG: Final translation time: {final_translation_time:.2f}s, tokens: {num_tokens_in_string(final_translation)}")

        else:
            # Step 3: Reflection on the initial translation
            start_time = time.time()
            role = "Proofread"
            reflection = one_chunk_reflect_on_translation(
                source_lang, target_lang, source_text, translation_1, country, vocab_dict, role
            )
            reflection_time = time.time() - start_time
            if config.debug:
                print(f"DEBUG: Reflection time: {reflection_time:.2f}s, tokens: {num_tokens_in_string(reflection)}, reflection: {reflection}")
                print(f"DEBUG: Style: {style}, role: {role}")

            # Step 4: Improved translation
            start_time = time.time()
            role = "Proofread"
            translation_2 = one_chunk_improve_translation(
                source_lang, target_lang, source_text, translation_1, reflection, style, role
            )
            translation_2_time = time.time() - start_time
            if config.debug:
                print(f"DEBUG: Improved translation,  Translation 2 time: {translation_2_time:.2f}s, tokens: {num_tokens_in_string(translation_2)}")
                print(f"DEBUG: Style: {style}, role: {role}")

            # Step 5: Final translation
            start_time = time.time()
            role = "Proofread"
            final_translation = translation_2 
            # #one_chunk_editor(target_lang, translation_2, style, target_lang, country, role, validation_markers=validation_markers)
            final_translation_time = time.time() - start_time
            if config.debug:
                print(f"DEBUG: Final translation time: {final_translation_time:.2f}s, tokens: {num_tokens_in_string(final_translation)}")


        return final_translation, outline_text
    else:
        raise ValueError(f"Chunk of size {num_tokens_in_text} tokens exceeds limit of {max_tokens} tokens.")

import httpx

# ...

@log_entry
def process_image_request(image_data: str, source_lang: str, target_lang: str, country: str, metadata: dict = None) -> str:
    """
    Sends an image to the OpenAI API (client3) for image variation generation,
    then resizes and compresses the result.
    """
    if metadata:
        title = metadata.get('book-title', '')
        authors_list = metadata.get('author', [])
        authors_str = ", ".join([f"{a.get('first-name', '')} {a.get('last-name', '')}".strip() for a in authors_list if isinstance(a, dict)])
        genres = ", ".join(metadata.get('genre', []))
        annotation = " ".join(metadata.get('annotation', []))[:300]
        
        prompt = config.get_prompt("image_generation", "generation", target_lang=target_lang, title=title, authors_str=authors_str, genres=genres, annotation=annotation)
    else:
        prompt = config.get_prompt("image_generation", "variation", source_lang=source_lang, target_lang=target_lang)

    try:
        if metadata:
            if config.debug:
                print(f"DEBUG: Image prompt: {prompt}")
            
            # Raw prompt logging
            logger.debug(f"OpenAI Image API Request (generate): prompt='{prompt}', model='{config.model_images}'")
            
            response = llm_service.clientImages.images.generate(
                model=config.model_images,
                prompt=prompt,
                n=1,
                size="1024x1024",
                # response_format="b64_json" # Removed as it causes unknown parameter error
            )
        else:
            image_bytes = base64.b64decode(image_data)
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            width, height = img.size
            size = min(width, height)
            left = (width - size) / 2
            top = (height - size) / 2
            right = (width + size) / 2
            bottom = (height + size) / 2
            img = img.crop((left, top, right, bottom))
            img = img.resize((1024, 1024), Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            if config.debug:
                print(f"DEBUG: Image variation prompt: {prompt}")
                
            # Raw prompt logging
            logger.debug(f"OpenAI Image API Request (create_variation): prompt='{prompt}', model='{config.model_images}'")

            response = llm_service.clientImages.images.create_variation(
                image=buffer,
                n=1,
                size="1024x1024",
                # response_format="b64_json", # Removed
                model=config.model_images
            )
        
        # Determine if response has b64_json (unlikely per error) or url
        # Just handle URL as default fallback if b64_json is missing or explicitly not asked
        generated_data = response.data[0]
        
        # Raw response logging (log metadata of response)
        logger.debug(f"OpenAI Image API Response: {generated_data}")

        img_bytes = None
        if hasattr(generated_data, 'b64_json') and generated_data.b64_json:
             img_bytes = base64.b64decode(generated_data.b64_json)
        elif hasattr(generated_data, 'url') and generated_data.url:
             if config.debug:
                 print(f"DEBUG: Downloading image from URL: {generated_data.url}")
             with httpx.Client() as client:
                 r = client.get(generated_data.url)
                 if r.status_code == 200:
                     img_bytes = r.content
                 else:
                     if config.debug:
                        print(f"DEBUG: Failed to download image from URL. Status: {r.status_code}")
                     return None
        
        if not img_bytes:
             if config.debug:
                print("DEBUG: No image data found in response")
             return None

        img = Image.open(io.BytesIO(img_bytes))
        img = img.resize((1024, 1536), Image.Resampling.LANCZOS)
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="JPEG", quality=70)
        return base64.b64encode(output_buffer.getvalue()).decode('utf-8')

    except Exception as e:
        if config.debug:
            print(f"DEBUG: Error processing image request: {e}")
        return None

@log_entry
def translate_metadata(metadata: dict, source_lang: str, target_lang: str, country: str) -> dict:
    """
    Translates a metadata dictionary using the LLM in JSON mode.
    """
    try:
        response_text = llm_service.get_completion(
            role="Proofread", # Use secondary for metadata usually
            prompt_category="metadata_translation",
            json_mode=True,
            source_lang=source_lang,
            target_lang=target_lang,
            country=country,
            metadata_json=json.dumps(metadata, ensure_ascii=False)
        )
        if not response_text:
            return metadata
            
        match = re.search(r'(\{.*\})', response_text, re.DOTALL)
        clean_json = match.group(1) if match else response_text.strip()
        return json.loads(clean_json)
    except Exception as e:
        if config.debug:
            print(f"DEBUG: Error translating metadata: {e}")
        return metadata
