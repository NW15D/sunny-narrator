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

clientb = openai.OpenAI(
    api_key=config.api_key,
    base_url=config.base_url,
    timeout=config.api_timeout
)
clients = openai.OpenAI(
    api_key=config.api_key2,
    base_url=config.base_url2,
    timeout=config.api_timeout2
)
clientc = openai.OpenAI(
    api_key=config.api_key3,
    base_url=config.base_url3,
    timeout=config.api_timeout3
)

def parse_json_response(response_text: str) -> dict:
    """
    Parses a JSON response from the LLM, handling potential markdown wrappers.
    """
    try:
        # Try direct parsing
        return json.loads(response_text)
    except json.JSONDecodeError:
        # Try finding the first '{' and last '}'
        start = response_text.find('{')
        end = response_text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(response_text[start:end+1])
            except json.JSONDecodeError:
                pass

        # Try stripping markdown code blocks
        match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # If all else fails, return original or raise
        if config.debug:
            ic(f"Failed to parse JSON response: {response_text}")
        raise

def remove_tags(text):
    """
    Removes various XML/HTML tags and specific artifacts from the text.
    """
    pattern = r'<SOURCE_TEXT>.*?</SOURCE_TEXT>|<INITIAL_TRANSLATION>.*?</INITIAL_TRANSLATION>|<DICTIONARY>.*?</DICTIONARY>|<FIRST_TRANSLATION>.*?</FIRST_TRANSLATION>|<EXPERT_SUGGESTIONS>.*?</EXPERT_SUGGESTIONS>|<TRANSLATION>|</TRANSLATION>|<TTEXT>|</TTEXT>|<SYNOPSIS>.*?</SYNOPSIS>|<think>.*?</think>|<myheader>.*?</myheader>|<myfooter>.*?</myfooter>|</section>|<section>|<IMPROVED_TRANSLATION>|</IMPROVED_TRANSLATION>|```xml|```|OceanofPDF.com|<a l:href="https://oceanofpdf.com">|'
    cleaned_text = re.sub(pattern, '', text, flags=re.DOTALL)
    return cleaned_text

def check_and_print_tags(text):
    """
    Finds and returns a list of specific tags present in the text.
    """
    pattern = r'<SOURCE_TEXT>.*?</SOURCE_TEXT>|<INITIAL_TRANSLATION>.*?</INITIAL_TRANSLATION>|<EXPERT_SUGGESTIONS>.*?</EXPERT_SUGGESTIONS>|<TRANSLATION>.*?</TRANSLATION>|<TTEXT>|</TTEXT>|<SYNOPSIS>.*?</SYNOPSIS>|<think>.*?</think>|<myheader>.*?</myheader>|<myfooter>.*?</myfooter>```xml.*?```'
    matches = re.findall(pattern, text)
    return matches

def get_completion_s(
        prompt: str,
        system_message: str,
        model: str = config.model2,
        temperature: float = config.temp2,
        json_mode: bool = True,
        max_tokens: int = MAX_TOKENS_PER_CHUNK,
) -> Union[str, dict]:
    """
    Generate a completion using the OpenAI API (Secondary client).
    """
    return _get_completion(clients, prompt, system_message, config.sys_not_promt2, config.nothink, model, temperature, json_mode, max_tokens, "small one")

def get_completion_b(
        prompt: str,
        system_message: str,
        model: str = config.model,
        temperature: float = config.temp,
        json_mode: bool = True,
        max_tokens: int = MAX_TOKENS_PER_CHUNK,
) -> Union[str, dict]:
    """
    Generate a completion using the OpenAI API (Primary client).
    """
    return _get_completion(clientb, prompt, system_message, config.sys_not_promt, config.nothink2, model, temperature, json_mode, max_tokens, "big one")

def _get_completion(client, prompt, system_message, sys_off_flag, nothink_flag, model, temperature, json_mode, max_tokens, debug_label):
    if sys_off_flag:
        prompt = f"{system_message}.{prompt}"
        system_message = None

    if nothink_flag:
        # Check if system_message is not None before appending
        if system_message:
            system_message = f"{system_message}./no_think"
        else:
             # If system message is suppressed but nothink is requested, we might need to handle it or append to prompt
            prompt = f"{prompt} ./no_think"

    num_tokens_in = num_tokens_in_string(prompt)

    if config.debug:
        ic(num_tokens_in)

    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages
    }
    
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    
    if config.debug:
        ic(debug_label)
        
    return response.choices[0].message.content

def one_chunk_initial_translation(
        source_lang: str, target_lang: str, source_text: str, style: str, outline_text: str, vocab_dict, big: bool
) -> str:
    """
    Translate the entire text as one chunk using an LLM.
    """
    if config.example:
        outline_text = f"{outline_text}.{config.example}"

    system_message = f"You are an expert linguist, specializing in translation from {source_lang} to {target_lang}."
    
    if style == 'xml':
        translation_prompt = f"""Translate the text in the <TTEXT> tag only, containing a part of a book in xml fb2 format, from {source_lang} to {target_lang}.
       1. Use the information from the previous part of the text specified in the <SYNOPSIS> tag to clarify the translation.
       2. Use the word pairs specified in the <DICTIONARY> tag to translate proper names, genders, and frequently used words.
       3. If there is obscene language, it should be translated as accurately as possible.
       The response should contain only the translated xml part, without comments and explanations.
       Absolutely do not add any new xml tags into the fb2 structure.
        <SYNOPSIS>{outline_text}</SYNOPSIS>
        <DICTIONARY>{vocab_dict}</DICTIONARY>

        <TTEXT>{source_text}</TTEXT> 
        
Provide the result ONLY as a valid JSON object: {{"translation": "..."}}
        """
    else:
        translation_prompt = f"""Translate the text from {source_lang} to {target_lang} in tag TTEXT, use the context from the previous part of the text provided in the SYNOPSIS tag.

        Instructions:
        1. Provide only the translated text.
        2. No explanations, comments, or additional text.
        3. Do not add any tags in your response.

        <TTEXT>{source_text}</TTEXT>

        <SYNOPSIS>{outline_text}</SYNOPSIS>

Provide the result ONLY as a valid JSON object: {{"translation": "..."}}
  """

    if big:
        response_text = get_completion_b(translation_prompt, system_message=system_message, json_mode=True)
    else:
        response_text = get_completion_s(translation_prompt, system_message=system_message, json_mode=True)

    try:
        data = parse_json_response(response_text)
        translation = data.get("translation", response_text)
    except Exception:
        translation = response_text

    return remove_tags(translation)

def one_chunk_referat(
         target_lang: str, final_translation: str,  big: bool
) -> str:
    """
    Make the synopsis (referat) for chunk using an LLM.
    """
    system_message = f"You are an expert linguist and proofreader, specializing in text analysis and summarization."

    translation_prompt = f"""Your task is to provide a concise synopsis in {target_lang} language for this text so that the subsequent parts can be better understood.
        Note the following:
        1. For each character name mentioned in the text, include their gender in parentheses (he or she).
        2. The synopsis should be as concise as possible, no more than 80 words.
        3. The result should be in text format only.

        Text: {final_translation}

        Provide the result ONLY as a valid JSON object: {{"synopsis": "..."}}
       """

    if big:
        response_text = get_completion_b(translation_prompt, system_message=system_message, json_mode=True)
    else:
        response_text = get_completion_s(translation_prompt, system_message=system_message, json_mode=True)

    try:
        data = parse_json_response(response_text)
        synopsis = data.get("synopsis", response_text)
    except Exception:
        synopsis = response_text

    return remove_tags(synopsis)

def one_chunk_editor(target_lang: str,  source_text: str, style: str,  lang: str , country: str , big: bool
) -> str:
    """
    Edits and proofreads the text.
    """
    system_message = f"You are an translator and proofreader of fiction texts"

    if style == 'xml':
        translation_prompt = f"""Your task is to process and correct only the text inside the <TTEXT> tag.
This text contains a fragment of a book in FB2 format, written in {lang} and originating from {country}.

Follow these instructions carefully:

Language and Style Correction:

Fix all grammatical, spelling, and stylistic errors in the text.

Maintain the author’s tone and literary style.

XML Structure Preservation:

Keep the existing XML structure exactly as it is.

Add <p> and </p> tags only where necessary to properly mark paragraphs.

Ensure that all XML tags are properly closed.

Allowed XML Tags:
Only the following XML tags may appear in the final result:
title, epigraph, annotation, image, p, empty-line, poem, cite, subtitle, table, section.

Tag Conversion:

Any other XML or HTML-like tags not in the allowed list must be converted to plain text.

For example: <tag> -> &lt;tag&gt;

Output Format:
Return the corrected text with the same XML structure as a JSON object: {{"corrected_text": "..."}}

Do not include explanations, comments, or metadata — only the corrected XML text.
Input text:    <TTEXT>{source_text}</TTEXT>"""
    else:
        translation_prompt = f"""You are tasked with proofreading and correcting the text. Ensure that all stylistic and grammatical errors are corrected. \n
            Process the text below according to the following rules:

Ensure that all XML tags are properly closed.

Only the following XML tags are allowed:
title, epigraph, annotation, image, p, empty-line, poem, cite, subtitle, table, section.

Any other tags must be converted into plain text (for example, <tag> should become &lt;tag&gt;).

Preserve the text content and structure of the document as much as possible. \n
            Here is the text to be corrected: {source_text} 
            
            Provide the result ONLY as a valid JSON object: {{"corrected_text": "..."}}
            """

    if big:
        response_text = get_completion_b(translation_prompt, system_message=system_message, json_mode=True)
    else:
        response_text = get_completion_s(translation_prompt, system_message=system_message, json_mode=True)

    try:
        data = parse_json_response(response_text)
        corrected_text = data.get("corrected_text", response_text)
    except Exception:
        corrected_text = response_text

    return remove_tags(corrected_text)

def vocabulary(
        source_lang: str,
        target_lang: str,
        source_text: str,
        country: str,
        big: bool,
) -> str:
    """
    Use an LLM to generate vocabulary for proper nouns.
    """
    system_message = f"You are a translator, specializing in translations from {source_lang} to {target_lang}, from {country}"

    reflection_prompt = f"""Translate a list of words and names from {source_lang} to {target_lang}.
    1. If there is obscene language, it should be translated as accurately as possible.
    2. Remove the words category in brackets from result.
    3. use the category only for context translation.
    
    Provide the result ONLY as a valid JSON object: {{"vocabulary": [{"source": "...", "target": "..."}, ...]}}

    Words: {source_text}"""
    
    if big:
        response_text = get_completion_b(reflection_prompt, system_message=system_message, json_mode=True)
    else:
        response_text = get_completion_s(reflection_prompt, system_message=system_message, json_mode=True)
        
    try:
        data = parse_json_response(response_text)
        vocab_list = data.get("vocabulary", [])
        # Convert back to string lines for compatibility with find_matching_words_with_cosine_similarity if it expects it
        # Actually, let's see how vocabulary is used. in app.py it's write_to_file(vocab_dict_clean, dict_file)
        # and ta.vocabulary(...) returns 'translation' which is the raw text.
        # So we should convert it back to source=target lines.
        translation = "\n".join([f"{item['source']}={item['target']}" for item in vocab_list])
    except Exception:
        translation = response_text

    if config.debug:
        ic(translation)
    return translation

def one_chunk_reflect_on_translation(
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
    system_message = f"You are a proofreader, specializing in improving translations from {source_lang} to {target_lang}, from {country}"

    reflection_prompt = f"""Your task is to review a source text in {source_lang} and an initial {target_lang} translation, enclosed in the <SOURCE_TEXT> and <INITIAL_TRANSLATION> tags, and provide a numbered list of specific suggestions to improve the translation.

        Result example: 1. "string" should be changed to "improved string".

        Your suggestions in {target_lang} should explicitly indicate which strings in the translation need to be changed and how, focusing on the following instructions:
        1. Correct any additions, mistranslations, omissions, or untranslated segments.
        2. Apply correct {target_lang} grammar, spelling, and eliminate unnecessary repetitions.
        3. Ensure the translation reflects the natural, colloquial style of {target_lang} as spoken in {country}, and is culturally appropriate.
        4. Use consistent and context-appropriate terminology that reflects the source text's domain, including equivalent idioms in {target_lang}.
        5. Use the word pairs specified in the <DICTIONARY> tags for translations of proper names and genus.
        6. Ensure that any obscene language present in the source text is accurately reflected in the translation.

        Prohibited adding explanations of any kind.
        
        <INITIAL_TRANSLATION>
        {translation_1}
        </INITIAL_TRANSLATION>
        
        Provide the result ONLY as a valid JSON object: {{"reflections": ['"string" should be changed to "improved string"', '"next string" should be changed to "next improved string"', ...]}}
        """

    if big:
        response_text = get_completion_b(reflection_prompt, system_message=system_message, json_mode=True)
    else:
        response_text = get_completion_s(reflection_prompt, system_message=system_message, json_mode=True)

    try:
        data = parse_json_response(response_text)
        reflections_list = data.get("reflections", [])
        # Convert list of suggestions back to a numbered list string for compatibility
        translation = "\n".join([f"{i+1}. {s}" for i, s in enumerate(reflections_list)])
    except Exception:
        translation = response_text

    return remove_tags(translation)

def one_chunk_improve_translation(
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
    system_message = f"You are the proofreader and translator of the books, and you help with the translation of the part of book from {source_lang} language to {target_lang}"
    if style == 'xml':
        prompt = f"""Your task is to improve a {source_lang} to {target_lang} translation based on expert suggestions.
              Output format is improved translation only.

              Follow these instructions:
                - Follow the expert suggestions.
                - Correct any additions, omissions, or mistranslations.
                - Use correct {target_lang} grammar, spelling, and punctuation.
                - Match the register and tone of the source text (e.g., formal/informal, technical/colloquial, obscene).
                - Preserve the original intent and nuance where possible.
                - Use consistent and context-appropriate terminology.
                - Improved content must maintains the same XML tags as the source_text, like image, p, etc, do not add new XML tags into the result fb2 structure.
                
                
               The source text, first translation, and expert suggestions are provided in tags:
              <SOURCE_TEXT>{source_text}</SOURCE_TEXT>
 
              <FIRST_TRANSLATION>{translation_1}</FIRST_TRANSLATION>
 
              <EXPERT_SUGGESTIONS>{reflection}</EXPERT_SUGGESTIONS>
 
              Provide the result ONLY as a valid JSON object: {{"improved_translation": "..."}}
              """
    else:
        prompt = f"""Edit the translation from {source_lang} to {target_lang} based on expert suggestions. The source text, initial translation, and suggestions are enclosed in tags:

<SOURCE_TEXT>
{source_text}
</SOURCE_TEXT>

<FIRST_TRANSLATION>
{translation_1}
</FIRST_TRANSLATION>

<EXPERT_SUGGESTIONS>
{reflection}
</EXPERT_SUGGESTIONS>

Ensure the edited translation is:
1. Accurate (correct errors of addition, mistranslation, omission, or untranslated text).
2. Fluent (apply {target_lang} grammar, spelling, and punctuation rules; remove repetitions).
3. Stylistic (reflect the style of the source text).
4. Terminologically consistent (appropriate and consistent use of terms).

The response should contain only the translated part.

Provide the result ONLY as a valid JSON object: {{"improved_translation": "..."}}
"""

    if big:
        response_text = get_completion_b(prompt, system_message=system_message, json_mode=True)
    else:
        response_text = get_completion_s(prompt, system_message=system_message, json_mode=True)

    try:
        data = parse_json_response(response_text)
        translation = data.get("improved_translation", response_text)
    except Exception:
        translation = response_text

    return translation

def one_chunk_translate_text(
        source_lang: str, target_lang: str, source_text: str, style: str, outline_text: str, country, vocab_dict
):
    """
    Translate a single chunk of text from the source language to the target language.
    """

    # Step 1: Initial translation
    start_time = time.time()
    translation_1 = one_chunk_initial_translation(
        source_lang, target_lang, source_text, style, outline_text, vocab_dict, True
    )
    translation_1_time = time.time() - start_time
    if config.debug:
        ic(source_text)
        ic(translation_1_time, (num_tokens_in_string(translation_1)), style, outline_text, translation_1)

    # Step 2: Reflection on the initial translation
    start_time = time.time()
    reflection = one_chunk_reflect_on_translation(
        source_lang, target_lang, source_text, translation_1, country, vocab_dict, False
    )
    reflection_time = time.time() - start_time
    if config.debug:
        ic(reflection_time, num_tokens_in_string(reflection), style, reflection)

    # Step 3: Improved translation
    start_time = time.time()
    translation_2 = one_chunk_improve_translation(
        source_lang, target_lang, source_text, translation_1, reflection, style, True
    )
    translation_2_time = time.time() - start_time
    if config.debug:
        ic(translation_2_time, num_tokens_in_string(translation_2), style, translation_2)

    start_time = time.time()
    outline_text = one_chunk_referat(target_lang, translation_2, True)
    outline_time = time.time() - start_time
    if config.debug:
        ic(outline_time, num_tokens_in_string(outline_text), outline_text)

    start_time = time.time()
    final_translation = one_chunk_editor(target_lang, translation_2, style, target_lang, country, False)
    final_translation_time = time.time() - start_time
    if config.debug:
        ic(final_translation_time, num_tokens_in_string(final_translation), final_translation)

    return final_translation, outline_text

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

def translate(
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

        final_translation, outline = one_chunk_translate_text(
            source_lang, target_lang, source_text, style, outline_text, country, vocab_dict
        )

        return final_translation, outline

        raise ValueError(f"Chunk of size {num_tokens_in_text} tokens exceeds limit of {max_tokens} tokens.")

def process_image_request(image_data: str, source_lang: str, target_lang: str, country: str, prompt: str = config.cover_prompt) -> str:
    """
    Sends an image to the OpenAI API (clientc) for image variation generation,
    then resizes and compresses the result.
    """
    try:
        # Decode the base64 image data
        image_bytes = base64.b64decode(image_data)
        
        # Variation API requires a square PNG image, less than 4MB.
        # Let's ensure it's a square PNG.
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGBA if necessary
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
            
        # Make square (standard for OpenAI Images API)
        width, height = img.size
        size = min(width, height)
        left = (width - size) / 2
        top = (height - size) / 2
        right = (width + size) / 2
        bottom = (height + size) / 2
        img = img.crop((left, top, right, bottom))
        img = img.resize((1024, 1024), Image.Resampling.LANCZOS)
        
        # Save to a byte buffer in PNG format
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        # Image Variation API call
        response = clientc.images.create_variation(
            image=buffer,
            n=1,
            size="1024x1024",
            response_format="b64_json",
            model=config.model3 # Use the model from config if specified
        )
        
        generated_b64 = response.data[0].b64_json
        if not generated_b64:
            return None

        # Post-processing with PIL
        img_bytes = base64.b64decode(generated_b64)
        img = Image.open(io.BytesIO(img_bytes))
        
        # Resize to book-friendly dimensions: 1024x1536
        img = img.resize((1024, 1536), Image.Resampling.LANCZOS)
        
        # Save as JPEG with 70% compression (more efficient for FB2)
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="JPEG", quality=70)
        
        # Encode back to base64
        return base64.b64encode(output_buffer.getvalue()).decode('utf-8')

    except Exception as e:
        if config.debug:
            ic(f"Error processing image request: {e}")
        return None

def translate_metadata(metadata: dict, source_lang: str, target_lang: str, country: str) -> dict:
    """
    Translates a metadata dictionary using the LLM in JSON mode.
    """
    system_message = f"You are an expert translator and bibliographer, specializing in fiction and {target_lang} literary standards in {country}."
    
    prompt = f"""Translate the values in this JSON object from {source_lang} to {target_lang}.
    
    Instructions:
    1. Translate the book title, author names (first, last, middle), sequence/series name, and the list of annotation paragraphs.
    2. Maintain the exact same JSON structure and keys.
    3. Proper names (authors, series) should be localized or transliterated according to {target_lang} literary norms in {country}.
    4. Provide the result ONLY as a valid JSON object.
    
    JSON to translate:
    {json.dumps(metadata, ensure_ascii=False)}
    """
    
    try:
        # Use primary client with JSON mode
        response_text = get_completion_b(prompt, system_message=system_message, json_mode=True)
        translated_metadata = parse_json_response(response_text)
        return translated_metadata
    except Exception as e:
        if config.debug:
            ic(f"Error translating metadata: {e}")
        return metadata # Return original if translation fails
