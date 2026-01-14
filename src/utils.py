from typing import Union
import openai
import tiktoken
import re
import json
from icecream import ic
import time
import io
import base64
from PIL import Image
from src.config import Config

# Initialize global config (can be overridden or passed if needed, but for now this replaces the 'from app import ...')
config = Config()

# Discrete chunks to translate one chunk at a time
MAX_TOKENS_PER_CHUNK = config.max_len_chunk * 4  # if text is more than this many tokens, we'll break it up into bytes x2 to tokens
outline_text = ""
big: bool = False

class LLMService:
    def __init__(self):
        self.client1 = openai.AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.api_timeout
        )
        self.client2 = openai.AsyncOpenAI(
            api_key=config.api_key2,
            base_url=config.base_url2,
            timeout=config.api_timeout2
        )
        self.client3 = openai.AsyncOpenAI(
            api_key=config.api_key3,
            base_url=config.base_url3,
            timeout=config.api_timeout3
        )

    async def get_completion(self, use_big=True, prompt_category=None, prompt_key="user", json_mode=False, max_tokens=MAX_TOKENS_PER_CHUNK, **kwargs):
        if use_big:
            client, model, temp, sys_off, nothink, label = (
                self.client1, config.model, config.temp, config.sys_not_promt, config.nothink2, "big one"
            )
        else:
            client, model, temp, sys_off, nothink, label = (
                self.client2, config.model2, config.temp2, config.sys_not_promt2, config.nothink, "small one"
            )

        system_message = config.get_prompt(prompt_category, "system", **kwargs)
        user_message = config.get_prompt(prompt_category, prompt_key, **kwargs)

        if sys_off:
            user_message = f"{system_message}.{user_message}"
            system_message = None

        if nothink:
            if system_message:
                system_message = f"{system_message}./no_think"
            else:
                user_message = f"{user_message} ./no_think"

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": user_message})

        if config.debug:
            ic(num_tokens_in_string(user_message), label)

        comp_kwargs = {
            "model": model,
            "temperature": temp,
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
    pattern = r'<SOURCE_TEXT>.*?</SOURCE_TEXT>|<INITIAL_TRANSLATION>.*?</INITIAL_TRANSLATION>|<DICTIONARY>.*?</DICTIONARY>|<FIRST_TRANSLATION>.*?</FIRST_TRANSLATION>|<EXPERT_SUGGESTIONS>.*?</EXPERT_SUGGESTIONS>|<TRANSLATION>|</TRANSLATION>|<SOURCE>|</SOURCE>|<SYNOPSIS>.*?</SYNOPSIS>|<think>.*?</think>|<myheader>.*?</myheader>|<myfooter>.*?</myfooter>|</section>|<section>|<IMPROVED_TRANSLATION>|</IMPROVED_TRANSLATION>|```xml|```|OceanofPDF.com|<a l:href="https://oceanofpdf.com">|<\|channel\|>.*?<\|end\|>'
    cleaned_text = re.sub(pattern, '', text, flags=re.DOTALL)
    return cleaned_text

def check_and_print_tags(text):
    """
    Finds and returns a list of specific tags present in the text.
    """
    pattern = r'<SOURCE_TEXT>.*?</SOURCE_TEXT>|<INITIAL_TRANSLATION>.*?</INITIAL_TRANSLATION>|<EXPERT_SUGGESTIONS>.*?</EXPERT_SUGGESTIONS>|<TRANSLATION>.*?</TRANSLATION>|<SOURCE>|</SOURCE>|<SYNOPSIS>.*?</SYNOPSIS>|<think>.*?</think>|<myheader>.*?</myheader>|<myfooter>.*?</myfooter>```xml.*?```'
    matches = re.findall(pattern, text)
    return matches

async def one_chunk_initial_translation(
        source_lang: str, target_lang: str, source_text: str, style: str, outline_text: str, vocab_dict, big: bool
) -> str:
    """
    Translate the entire text as one chunk using an LLM.
    """
    if config.example:
        outline_text = f"{outline_text}.{config.example}"

    prompt_key = "user_xml" if style == 'xml' else "user_text"
    
    translation = await llm_service.get_completion(
        use_big=big, 
        prompt_category="initial_translation", 
        prompt_key=prompt_key,
        source_lang=source_lang,
        target_lang=target_lang,
        outline_text=outline_text,
        vocab_dict=vocab_dict,
        source_text=source_text
    )

    return remove_tags(translation)

async def one_chunk_referat(
         target_lang: str, final_translation: str,  big: bool
) -> str:
    """
    Make the synopsis (referat) for chunk using an LLM.
    """
    translation = await llm_service.get_completion(
        use_big=big,
        prompt_category="synopsis",
        target_lang=target_lang,
        final_translation=final_translation
    )
    return remove_tags(translation)

async def one_chunk_editor(target_lang: str,  source_text: str, style: str,  lang: str , country: str , big: bool
) -> str:
    """
    Edits and proofreads the text.
    """
    prompt_key = "user_xml" if style == 'xml' else "user_text"
    
    translation = await llm_service.get_completion(
        use_big=big,
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
        big: bool,
) -> str:
    """
    Use an LLM to generate vocabulary for proper nouns.
    """
    translation = await llm_service.get_completion(
        use_big=big,
        prompt_category="vocabulary",
        source_lang=source_lang,
        target_lang=target_lang,
        country=country,
        source_text=source_text
    )
    if config.debug:
        ic(translation)
    return translation

async def one_chunk_reflect_on_translation(
        source_lang: str,
        target_lang: str,
        source_text: str,
        translation_1: str,
        country: str ,
        vocab_dict,
        big: bool,
) -> str:
    """
    Reflect on the initial translation and provide suggestions for improvement.
    """
    translation = await llm_service.get_completion(
        use_big=big,
        prompt_category="reflect_on_translation",
        source_lang=source_lang,
        target_lang=target_lang,
        source_text=source_text,
        translation_1=translation_1,
        country=country,
        vocab_dict=vocab_dict
    )
    return remove_tags(translation)

async def one_chunk_improve_translation(
        source_lang: str,
        target_lang: str,
        source_text: str,
        translation_1: str,
        reflection: str,
        style: str,
        big: bool,
) -> str:
    """
    Use the reflection to improve the translation.
    """
    prompt_key = "user_xml" if style == 'xml' else "user_text"
    
    translation = await llm_service.get_completion(
        use_big=big,
        prompt_category="improve_translation",
        prompt_key=prompt_key,
        source_lang=source_lang,
        target_lang=target_lang,
        source_text=source_text,
        translation_1=translation_1,
        reflection=reflection
    )
    return translation

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
        ic(num_tokens_in_text)

    # Simplified check, original logic raise error if oversized but here we trust the chunker upstream for now or just process it.
    # The original code raised ValueError("Chunks is oversized!!!") if > max_tokens. 
    # We will keep that behavior but perhaps it should be handled more gracefully in production.
    if num_tokens_in_text < max_tokens:
        if config.debug:
            ic("Translating text as a single chunk")

                # Step 1: Initial translation
    start_time = time.time()
    use_big = True
    translation_1 = await one_chunk_initial_translation(
        source_lang, target_lang, source_text, style, outline_text, vocab_dict, use_big
    )
    translation_1_time = time.time() - start_time
    if config.debug:
        ic(source_text)
        ic(translation_1_time, (num_tokens_in_string(translation_1)), style, outline_text, translation_1)

    # Step 2: Reflection on the initial translation
    start_time = time.time()
    use_big = False
    reflection = await one_chunk_reflect_on_translation(
        source_lang, target_lang, source_text, translation_1, country, vocab_dict, use_big
    )
    reflection_time = time.time() - start_time
    if config.debug:
        ic(reflection_time, num_tokens_in_string(reflection), style, reflection)

    # Step 3: Improved translation
    start_time = time.time()
    use_big = False
    translation_2 = await one_chunk_improve_translation(
        source_lang, target_lang, source_text, translation_1, reflection, style, use_big
    )
    translation_2_time = time.time() - start_time
    if config.debug:
        ic(translation_2_time, num_tokens_in_string(translation_2), style, translation_2)

    # Step 4: Outline
    start_time = time.time()
    use_big = True
    outline_text = await one_chunk_referat(target_lang, translation_2, use_big)
    outline_time = time.time() - start_time
    if config.debug:
        ic(outline_time, num_tokens_in_string(outline_text), outline_text)

    # Step 5: Final translation
    start_time = time.time()
    use_big = False
    final_translation = await one_chunk_editor(target_lang, translation_2, style, target_lang, country, use_big)
    final_translation_time = time.time() - start_time
    if config.debug:
        ic(final_translation_time, num_tokens_in_string(final_translation), final_translation)


        return final_translation, outline_text
    else:
        raise ValueError(f"Chunk of size {num_tokens_in_text} tokens exceeds limit of {max_tokens} tokens.")

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
                ic(prompt)
            response = await llm_service.client3.images.generate(
                model=config.model3,
                prompt=prompt,
                n=1,
                size="1024x1024",
                response_format="b64_json"
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
                ic(prompt)
            response = await llm_service.client3.images.create_variation(
                image=buffer,
                n=1,
                size="1024x1024",
                response_format="b64_json",
                model=config.model3
            )
        
        generated_b64 = response.data[0].b64_json
        if not generated_b64:
            return None

        img_bytes = base64.b64decode(generated_b64)
        img = Image.open(io.BytesIO(img_bytes))
        img = img.resize((1024, 1536), Image.Resampling.LANCZOS)
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="JPEG", quality=70)
        return base64.b64encode(output_buffer.getvalue()).decode('utf-8')

    except Exception as e:
        if config.debug:
            ic(f"Error processing image request: {e}")
        return None

async def translate_metadata(metadata: dict, source_lang: str, target_lang: str, country: str) -> dict:
    """
    Translates a metadata dictionary using the LLM in JSON mode.
    """
    try:
        response_text = await llm_service.get_completion(
            use_big=False, # Use secondary for metadata usually
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
            ic(f"Error translating metadata: {e}")
        return metadata
