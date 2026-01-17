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
    def __init__(self):
        self.clientTranslate = openai.AsyncOpenAI(
            api_key=config.api_key_translate,
            base_url=config.base_url_translate,
            timeout=config.timeout_translate
        )
        self.clientProofread = openai.AsyncOpenAI(
            api_key=config.api_key_proofread,
            base_url=config.base_url_proofread,
            timeout=config.timeout_proofread
        )
        self.clientImages = openai.AsyncOpenAI(
            api_key=config.api_key_images,
            base_url=config.base_url_images,
            timeout=config.timeout_images
        )

    async def get_completion(self, role="Translate", prompt_category=None, prompt_key="user", json_mode=False, max_tokens=MAX_TOKENS_PER_CHUNK, **kwargs):
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
                system_message = f"{system_message}./no_think"
            else:
                user_message = f"{user_message} ./no_think"

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

        response = await client.chat.completions.create(**comp_kwargs)
        return response.choices[0].message.content

llm_service = LLMService()

def remove_tags(text):
    """
    Removes various XML/HTML tags and specific artifacts from the text.
    """
    #pattern = r'<SOURCE_TEXT>.*?</SOURCE_TEXT>|<INITIAL_TRANSLATION>.*?</INITIAL_TRANSLATION>|<DICTIONARY>.*?</DICTIONARY>|<FIRST_TRANSLATION>.*?</FIRST_TRANSLATION>|<EXPERT_SUGGESTIONS>.*?</EXPERT_SUGGESTIONS>|<TRANSLATION>|</TRANSLATION>|<SOURCE>|</SOURCE>|<SYNOPSIS>.*?</SYNOPSIS>|<think>.*?</think>|<myheader>.*?</myheader>|<myfooter>.*?</myfooter>|</section>|<section>|<IMPROVED_TRANSLATION>|</IMPROVED_TRANSLATION>|```xml|```|OceanofPDF.com|</target>|<target>|<a l:href="https://oceanofpdf.com">|<\|channel\|>.*?<\|end\|>|<TTEXT>|</TTEXT>|<SYNOPSIS>|<\|im_end\|>|<\|file_separator\|>|</think>'
    #cleaned_text = re.sub(pattern, '', text, flags=re.DOTALL)
    pattern = r'''<SOURCE_TEXT>[\s\S]*?</SOURCE_TEXT>|<INITIAL_TRANSLATION>[\s\S]*?</INITIAL_TRANSLATION>|<DICTIONARY>[\s\S]*?</DICTIONARY>|<FIRST_TRANSLATION>[\s\S]*?</FIRST_TRANSLATION>|<EXPERT_SUGGESTIONS>[\s\S]*?</EXPERT_SUGGESTIONS>|<SYNOPSIS>[\s\S]*?</SYNOPSIS>|<think>[\s\S]*?</think>|<myheader>[\s\S]*?</myheader>|<myfooter>[\s\S]*?</myfooter>|<\|channel\|>[\s\S]*?<\|end\|>|```xml|```|OceanofPDF\.com|<a l:href="https://oceanofpdf.com">|</?(?:TRANSLATION|SOURCE|section|IMPROVED_TRANSLATION|target|TTEXT|SYNOPSIS)>|<\|im_end\|>|<\|file_separator\|>'''
    cleaned = re.sub(pattern, '', text, flags=re.IGNORECASE | re.VERBOSE)
    return cleaned

def check_and_print_tags(text):
    """
    Finds and returns a list of specific tags present in the text.
    """
    pattern = r'<SOURCE_TEXT>.*?</SOURCE_TEXT>|<INITIAL_TRANSLATION>.*?</INITIAL_TRANSLATION>|<EXPERT_SUGGESTIONS>.*?</EXPERT_SUGGESTIONS>|<TRANSLATION>.*?</TRANSLATION>|<SOURCE>|</SOURCE>|<SYNOPSIS>.*?</SYNOPSIS>|<think>.*?</think>|<myheader>.*?</myheader>|<myfooter>.*?</myfooter>|```xml.*?```'
    matches = re.findall(pattern, text)
    return matches

async def one_chunk_initial_translation(
        source_lang: str, target_lang: str, source_text: str, style: str, outline_text: str, vocab_dict, role: str
) -> str:
    """
    Translate the entire text as one chunk using an LLM.
    Includes length control: if the result differs by more than 15%, retries with higher temperature.
    """
    if config.example:
        outline_text = f"{outline_text}.{config.example}"

    prompt_key = "user_xml" if style == 'xml' else "user_text"
    if role == "Translate" and config.model_translate == "Hunyuan":
        prompt_key = "user_hunyuan"
        if config.debug:
            print(f"DEBUG: Selected Hunyuan prompt")

    current_temp = config.temp_translate
    source_len = len(source_text)
    f_translation = ""

    for attempt in range(3):
        translation = await llm_service.get_completion(
            role=role, 
            prompt_category="initial_translation", 
            prompt_key=prompt_key,
            source_lang=source_lang,
            target_lang=target_lang,
            outline_text=outline_text,
            vocab_dict=vocab_dict,
            source_text=source_text,
            temperature=current_temp
        )
        
        f_translation = remove_tags(translation)
        
        #if source_len == 0:
        #    return f_translation
            
        target_len = len(f_translation)
        diff_percent = abs(target_len - source_len) / source_len
        
        if diff_percent <= 0.22:
            if config.debug and attempt > 0:
                print(f"DEBUG: Translation1 successful on attempt {attempt + 1} with temp {current_temp:.2f}")
            return f_translation
        
        if config.debug:
            print(f"DEBUG: Translation1 attempt {attempt + 1} failed length check: diff {diff_percent:.2%}. Source: {source_len}, Target: {target_len}. Retrying with temp {current_temp + 0.05:.2f}")
        
        current_temp += 0.05

    if config.debug:
        print(f"DEBUG: All translation1 attempts failed length check. Returning last attempt.")
    return f_translation

async def one_chunk_referat(
         target_lang: str, final_translation: str,  role: str
) -> str:
    """
    Make the synopsis (referat) for chunk using an LLM.
    """
    translation = await llm_service.get_completion(
        role=role,
        prompt_category="synopsis",
        target_lang=target_lang,
        final_translation=final_translation,
        max_tokens=160
    )
    return remove_tags(translation)

async def one_chunk_editor(target_lang: str, source_text: str, style: str, lang: str, country: str, role: str
) -> str:
    """
    Edits and proofreads the text.
    """
    prompt_key = "user_xml" if style == 'xml' else "user_text"
    
    translation = await llm_service.get_completion(
        role=role,
        prompt_category="editor",
        prompt_key=prompt_key,
        lang=lang,
        country=country,
        source_text=source_text
    )
    return remove_tags(translation)

async def vocabulary(
        source_lang: str,
        target_lang: str,
        source_text: str,
        country: str,
        role: str,
) -> str:
    """
    Use an LLM to generate vocabulary for proper nouns.
    """
    translation = await llm_service.get_completion(
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

async def one_chunk_reflect_on_translation(
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
    translation = await llm_service.get_completion(
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

async def one_chunk_improve_translation(
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
    
    translation = await llm_service.get_completion(
        role=role,
        prompt_category="improve_translation",
        prompt_key=prompt_key,
        source_lang=source_lang,
        target_lang=target_lang,
        source_text=source_text,
        translation_1=translation_1,
        reflection=reflection
    )
    return remove_tags(translation)

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

async def translate(
        source_lang,
        target_lang,
        source_text,
        style,
        outline_text,
        country,
        vocab_dict,
        max_tokens=MAX_TOKENS_PER_CHUNK,

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
        translation_1 = await one_chunk_initial_translation(
            source_lang, target_lang, source_text, style, outline_text, vocab_dict, role
        )
        translation_1_time = time.time() - start_time
        if config.debug:
            print(f"DEBUG: Translation 1 time: {translation_1_time:.2f}s, tokens: {num_tokens_in_string(translation_1)}, translation: {translation_1}")
            #print(f"DEBUG: Style: {style}, Outline: {outline_text}, role: {role}")

        # Step 2: Outline (Moved to Step 2 to allow fast yielding for async chain)
        start_time = time.time()
        role = "Proofread"
        outline_text = await one_chunk_referat(target_lang, translation_1, role)
        outline_time = time.time() - start_time
        if config.debug:
            print(f"DEBUG: Outline time: {outline_time:.2f}s, tokens: {num_tokens_in_string(outline_text)}, outline: {outline_text} role: {role}")
          
        
        # YIELD OUTLINE EARLY
        yield ("outline", outline_text)

        if config.fast_trans:
            if config.debug:
               print("DEBUG: Fast translation mode: Skipping Reflection and Improvement steps")
            
            # Step 5: Final translation (using translation_1)
            start_time = time.time()
            role = "Proofread"
            # Note: vocab dict mapping was key-based in app.py logic, here passed into translate
            final_translation = await one_chunk_editor(target_lang, translation_1, style, target_lang, country, role)
            final_translation_time = time.time() - start_time
            if config.debug:
                 print(f"DEBUG: Final translation time: {final_translation_time:.2f}s, tokens: {num_tokens_in_string(final_translation)}")

        else:
            # Step 3: Reflection on the initial translation
            start_time = time.time()
            role = "Proofread"
            reflection = await one_chunk_reflect_on_translation(
                source_lang, target_lang, source_text, translation_1, country, vocab_dict, role
            )
            reflection_time = time.time() - start_time
            if config.debug:
                print(f"DEBUG: Reflection time: {reflection_time:.2f}s, tokens: {num_tokens_in_string(reflection)}, reflection: {reflection}")
                print(f"DEBUG: Style: {style}, role: {role}")

            # Step 4: Improved translation
            start_time = time.time()
            role = "Proofread"
            translation_2 = await one_chunk_improve_translation(
                source_lang, target_lang, source_text, translation_1, reflection, style, role
            )
            translation_2_time = time.time() - start_time
            if config.debug:
                print(f"DEBUG: Translation 2 time: {translation_2_time:.2f}s, tokens: {num_tokens_in_string(translation_2)}, translation_2: {translation_2}")
                print(f"DEBUG: Style: {style}, role: {role}")

            # Step 5: Final translation
            start_time = time.time()
            role = "Proofread"
            final_translation = await one_chunk_editor(target_lang, translation_2, style, target_lang, country, role)
            final_translation_time = time.time() - start_time
            if config.debug:
                print(f"DEBUG: Final translation time: {final_translation_time:.2f}s, tokens: {num_tokens_in_string(final_translation)}, final_translation: {final_translation}")


        yield ("final", final_translation)
    else:
        raise ValueError(f"Chunk of size {num_tokens_in_text} tokens exceeds limit of {max_tokens} tokens.")

import httpx

# ...

async def process_image_request(image_data: str, source_lang: str, target_lang: str, country: str, metadata: dict = None) -> str:
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
            response = await llm_service.clientImages.images.generate(
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
            response = await llm_service.clientImages.images.create_variation(
                image=buffer,
                n=1,
                size="1024x1024",
                # response_format="b64_json", # Removed
                model=config.model_images
            )
        
        # Determine if response has b64_json (unlikely per error) or url
        # Just handle URL as default fallback if b64_json is missing or explicitly not asked
        generated_data = response.data[0]
        
        img_bytes = None
        if hasattr(generated_data, 'b64_json') and generated_data.b64_json:
             img_bytes = base64.b64decode(generated_data.b64_json)
        elif hasattr(generated_data, 'url') and generated_data.url:
             if config.debug:
                 print(f"DEBUG: Downloading image from URL: {generated_data.url}")
             async with httpx.AsyncClient() as client:
                 r = await client.get(generated_data.url)
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

async def translate_metadata(metadata: dict, source_lang: str, target_lang: str, country: str) -> dict:
    """
    Translates a metadata dictionary using the LLM in JSON mode.
    """
    try:
        response_text = await llm_service.get_completion(
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
