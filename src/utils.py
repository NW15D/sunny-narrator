from typing import  Union
import openai
import tiktoken
import re
from icecream import ic
from app import api_timeout,api_timeout2,api_key,api_key2,base_url,base_url2,sys_off,sys_off2,debug,nothink,nothink2,model,model2,temp,temp2,example
#from concurrent.futures import ThreadPoolExecutor
import time

# discrete chunks to translate one chunk at a time
MAX_TOKENS_PER_CHUNK = 32768 # if text is more than this many tokens, we'll break it up into, bytes x2 to tokens
outline_text = ""
big: bool = False

clientb = openai.OpenAI(
    api_key=api_key,  # This is the default and can be omitted
    base_url=base_url,
    timeout=api_timeout
)
clients = openai.OpenAI(
    api_key=api_key2,  # This is the default and can be omitted
    base_url=base_url2,
    timeout=api_timeout2
)

def remove_tags(text):
    # Определяем шаблон для поиска тегов и текста между ними
    pattern = r'<SOURCE_TEXT>.*?</SOURCE_TEXT>|<INITIAL_TRANSLATION>.*?</INITIAL_TRANSLATION>|<DICTIONARY>.*?</DICTIONARY>|<FIRST_TRANSLATION>.*?</FIRST_TRANSLATION>|<EXPERT_SUGGESTIONS>.*?</EXPERT_SUGGESTIONS>|<TRANSLATION>|</TRANSLATION>|<TTEXT>|</TTEXT>|<SYNOPSIS>.*?</SYNOPSIS>|<think>.*?</think>|<myheader>.*?</myheader>|<myfooter>.*?</myfooter>|</section>|<section>|<IMPROVED_TRANSLATION>|</IMPROVED_TRANSLATION>|```xml|```|'
    # Используем re.sub для удаления найденных совпадений
    cleaned_text = re.sub(pattern, '', text, flags=re.DOTALL)
    return cleaned_text

def check_and_print_tags(text):
    # Определяем шаблон для поиска тегов
    pattern = r'<SOURCE_TEXT>.*?</SOURCE_TEXT>|<INITIAL_TRANSLATION>.*?</INITIAL_TRANSLATION>|<EXPERT_SUGGESTIONS>.*?</EXPERT_SUGGESTIONS>|<TRANSLATION>.*?</TRANSLATION>|<TTEXT>|</TTEXT>|<SYNOPSIS>.*?</SYNOPSIS>|<think>.*?</think>|<myheader>.*?</myheader>|<myfooter>.*?</myfooter>```xml.*?```'
    # Ищем все вхождения тегов
    matches = re.findall(pattern, text)

    return matches

def get_completion_s(
        prompt: str,
        system_message: str ,
        model: str = model2,
        temperature: float = temp2,
        json_mode: bool = False,
        max_tokens: int = MAX_TOKENS_PER_CHUNK,
) -> Union[str, dict]:
    """
        Generate a completion using the OpenAI API.

    Args:
        prompt (str): The user's prompt or query.
        system_message (str, optional): The system message to set the context for the assistant.
            Defaults to "You are a helpful assistant.".
        model (str, optional): The name of the OpenAI model to use for generating the completion.
            Defaults to "gpt-4-turbo".
        temperature (float, optional): The sampling temperature for controlling the randomness of the generated text.
            Defaults to 0.3.
        json_mode (bool, optional): Whether to return the response in JSON format.
            Defaults to False.

    Returns:
        Union[str, dict]: The generated completion.
            If json_mode is True, returns the complete API response as a dictionary.
            If json_mode is False, returns the generated text as a string.
    """
    if sys_off is None:
        prompt =  f"{system_message}.{prompt}"
        system_message = None

    if nothink:
        system_message = f"{system_message}./no_think"
    num_tokens_in = num_tokens_in_string(prompt)

    if debug:
        ic(num_tokens_in)

    if json_mode:
        response = clients.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
    else:
        response = clients.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
        )
        if debug:
            ic("small one")
        return response.choices[0].message.content

def get_completion_b(
        prompt: str,
        system_message: str ,
        model: str = model,
        temperature: float = temp,
        json_mode: bool = False,
        max_tokens: int = MAX_TOKENS_PER_CHUNK,
) -> Union[str, dict]:
    """
        Generate a completion using the OpenAI API.

    Args:
        prompt (str): The user's prompt or query.
        system_message (str, optional): The system message to set the context for the assistant.
            Defaults to "You are a helpful assistant.".
        model (str, optional): The name of the OpenAI model to use for generating the completion.
            Defaults to "gpt-4-turbo".
        temperature (float, optional): The sampling temperature for controlling the randomness of the generated text.
            Defaults to 0.3.
        json_mode (bool, optional): Whether to return the response in JSON format.
            Defaults to False.

    Returns:
        Union[str, dict]: The generated completion.
            If json_mode is True, returns the complete API response as a dictionary.
            If json_mode is False, returns the generated text as a string.
    """
    if sys_off2:
        prompt =  f"{system_message}.{prompt}"
        system_message = None

    if nothink2:
        system_message  = f"{system_message}./no_think"
    num_tokens_in = num_tokens_in_string(prompt)

    if debug:
        ic(num_tokens_in)
    if json_mode:
        response = clientb.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
    else:
        response = clientb.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
        )

        if debug:
            ic("big one")
        return response.choices[0].message.content

def one_chunk_initial_translation(
        source_lang: str, target_lang: str, source_text: str, style: str, outline_text: str, vocab_dict, big: bool
) -> str:
    """
    Translate the entire text as one chunk using an LLM.

    Args:
        source_lang (str): The source language of the text.
        target_lang (str): The target language for translation.
        source_text (str): The text to be translated.

    Returns:
        str: The translated text.
    """
    if example:
        outline_text = f"{outline_text}.{example}"

    system_message = f"You are an expert linguist, specializing in translation from {source_lang} to {target_lang}."
    if style == 'xml':  # Исправлено '=' на '=='
       translation_prompt = f"""Translate the text in the <TTEXT> tag only, containing a part of a book in xml fb2 format, from {source_lang} to {target_lang}.
       1. Use the information from the previous part of the text specified in the <SYNOPSIS> tag to clarify the translation.
       2. Use the word pairs specified in the <DICTIONARY> tag to translate proper names, genders, and frequently used words.
       3. If there is obscene language, it should be translated as accurately as possible.
       The response should contain only the translated xml part, without comments and explanations.
       Absolutely do not add any new xml tags into the fb2 structure.
        <SYNOPSIS>{outline_text}</SYNOPSIS>
        <DICTIONARY>{vocab_dict}</DICTIONARY>

        <TTEXT>{source_text}</TTEXT> """

    else :
        translation_prompt = f"""Translate the text from {source_lang} to {target_lang} in tag TTEXT, use the context from the previous part of the text provided in the SYNOPSIS tag.

        Instructions:
        1. Provide only the translated text.
        2. No explanations, comments, or additional text.
        3. Do not add any tags in your response.

        <TTEXT>{source_text}</TTEXT>

        <SYNOPSIS>{outline_text}</SYNOPSIS>

  """


    if big:
        translation = get_completion_b(translation_prompt, system_message=system_message)
    else:
        translation = get_completion_s(translation_prompt, system_message=system_message)


    return remove_tags(translation)


def one_chunk_referat(
         target_lang: str, final_translation: str,  big: bool
) -> str:
    """
    Make the referat for chunk using an LLM.

    Args:
        target_lang (str): The target language for translation.
        final_translation (str): The text to be translated.

    Returns:
        str: The translated text.
    """
    system_message = f"You are an expert linguist and proofreader, specializing in text analysis and summarization."

    translation_prompt = f"""Your task is to provide a concise synopsis in {target_lang} language for this text so that the subsequent parts can be better understood.
        Note the following:
        1. For each character name mentioned in the text, include their gender in parentheses (he or she).
        2. The synopsis should be as concise as possible, no more than 80 words.
        3. The result should be in text format only.

        Text: {final_translation}

        Synopsis:
       """

    if big:
        translation = get_completion_b(translation_prompt, system_message=system_message)
    else:
        translation = get_completion_s(translation_prompt, system_message=system_message)


    return remove_tags(translation)


def one_chunk_editor(target_lang: str,  source_text: str, style: str,  big: bool
) -> str:
    """
    Args:
        target_lang (str): The target language for translation.
        source_text (str): The text to be translated.

    Returns:
        str: The adopted text.
    """
    system_message = f"You are an translator and proofreader of fiction texts"

    if style == 'xml':  # Исправлено '=' на '=='
        translation_prompt = f"""Your task is to  correct the text in the <TTEXT> tag only, containing a part of a book in fb2 format.
        Ensure all stylistic and grammatical errors are fixed. Leave as is the XML structure, adding <p> or </p> tags only where necessary to properly define paragraphs.
        The result should contain the same xml structure with text without explanations.
        <TTEXT>{source_text}</TTEXT>"""
    else:  # Отступ исправлен
        translation_prompt = f"""You are tasked with proofreading and correcting the text. Ensure that all stylistic and grammatical errors are corrected. \n
            Output improved text and nothing else. Don't add any comment. \n
            Here is the text to be corrected: {source_text} """


    if big:
        translation = get_completion_b(translation_prompt, system_message=system_message)
    else:
        translation = get_completion_s(translation_prompt, system_message=system_message)

    return remove_tags(translation)


def vocabulary(
        source_lang: str,
        target_lang: str,
        source_text: str,
        country: str,
        big: bool,
) -> str:
    """
    Use an LLM to make vocabulary proper nouns, treating the entire text as one chunk.

    Args:
        source_lang (str): The source language of the text.
        target_lang (str): The target language of the translation.
        source_text (str): The original text in the source language.
        country (str): Country specified for the target language.

    Returns:
        str: The LLM's reflection on the translation, providing constructive criticism and suggestions for improvement.
    """

    system_message = f"You are a translator, specializing in translations from {source_lang} to {target_lang}, from {country}"

    reflection_prompt = f"""Translate a list of commonly used words and names from {source_lang} to {target_lang},
    If there is obscene language, it should be translated as accurately as possible,
    remove the category in brackets,
    use the category only for context translation,
    format result as a list of strings:
    {source_lang} text={target_lang} translation

    {source_text}"""
    if big:
        translation = get_completion_b(reflection_prompt, system_message=system_message)
    else:
        translation = get_completion_s(reflection_prompt, system_message=system_message)

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
    Use an LLM to reflect on the translation, treating the entire text as one chunk.

    Args:
        source_lang (str): The source language of the text.
        target_lang (str): The target language of the translation.
        source_text (str): The original text in the source language.
        translation_1 (str): The initial translation of the source text.
        country (str): Country specified for the target language.

    Returns:
        str: The LLM's reflection on the translation, providing constructive criticism and suggestions for improvement.
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
        
        <SOURCE_TEXT>
        {source_text}
        </SOURCE_TEXT>

        <DICTIONARY>{vocab_dict}</DICTIONARY>

        <INITIAL_TRANSLATION>
        {translation_1}
        </INITIAL_TRANSLATION>"""


    if big:
        translation = get_completion_b(reflection_prompt, system_message=system_message)
    else:
        translation = get_completion_s(reflection_prompt, system_message=system_message)

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
    Use the reflection to improve the translation, treating the entire text as one chunk.

    Args:
        source_lang (str): The source language of the text.
        target_lang (str): The target language for the translation.
        source_text (str): The original text in the source language.
        translation_1 (str): The initial translation of the source text.
        reflection (str): Expert suggestions and constructive criticism for improving the translation.

    Returns:
        str: The improved translation based on the expert suggestions.
    """

    system_message = f"You are the proofreader and translator of the books, and you help with the translation of the part of book from {source_lang} language to {target_lang}"
    if style == 'xml':  #
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

The response should contain only the translated part."""

    if big:
        translation = get_completion_b(prompt, system_message=system_message)
    else:
        translation = get_completion_s(prompt, system_message=system_message)

    return translation


def one_chunk_translate_text(
        source_lang: str, target_lang: str, source_text: str, style: str, outline_text: str, country, vocab_dict
) -> str:
    """
    Translate a single chunk of text from the source language to the target language.

    This function performs a two-step translation process:
    1. Get an initial translation of the source text.
    2. Reflect on the initial translation and generate an improved translation.

    Args:
        source_lang (str): The source language of the text.
        target_lang (str): The target language for the translation.
        source_text (str): The text to be translated.
        country (str): Country specified for the target language.
    Returns:
        str: The improved translation of the source text.
    """


    # Step 1: Initial translation
    start_time = time.time()
    translation_1 = one_chunk_initial_translation(
        source_lang, target_lang, source_text, style, outline_text, vocab_dict, True
    )
    translation_1_time = time.time() - start_time
    if debug:
        ic(source_text)
        ic(translation_1_time,(num_tokens_in_string(translation_1)), style, outline_text, translation_1)


    # Step 2: Reflection on the initial translation
    start_time = time.time()
    reflection = one_chunk_reflect_on_translation(
        source_lang, target_lang, source_text, translation_1, country, vocab_dict,False
    )
    reflection_time = time.time() - start_time
    if debug:
        ic(reflection_time,num_tokens_in_string(reflection), style, reflection)


    # Step 3: Improved translation
    start_time = time.time()
    translation_2 = one_chunk_improve_translation(
        source_lang, target_lang, source_text, translation_1, reflection, style, True
    )
    translation_2_time = time.time() - start_time
    if debug:
        ic(translation_2_time,num_tokens_in_string(translation_2), style, translation_2)

    # Concurrently execute one_chunk_referat and one_chunk_editor , beyond base old  code
    """///* with ThreadPoolExecutor(max_workers=2) as executor:
        future_outline = executor.submit(one_chunk_referat, target_lang, translation_2, False)
        future_final_translation = executor.submit(one_chunk_editor, target_lang, translation_2, style, True)

        start_time = time.time()
        outline_text = future_outline.result()
        outline_time = time.time() - start_time
        if debug:
            ic(outline_time, num_tokens_in_string(outline_text), outline_text)
        start_time = time.time()
        final_translation = future_final_translation.result()
        final_translation_time = time.time() - start_time
        if debug:
            ic(final_translation_time,num_tokens_in_string(final_translation), final_translation)
    ***///"""

    start_time = time.time()
    outline_text = one_chunk_referat(target_lang, translation_2, True)
    outline_time = time.time() - start_time
    if debug:
        ic(outline_time, num_tokens_in_string(outline_text), outline_text)

    start_time = time.time()
    final_translation = one_chunk_editor(target_lang, translation_2, style, False)
    final_translation_time = time.time() - start_time
    if debug:
        ic(final_translation_time, num_tokens_in_string(final_translation), final_translation)

    return final_translation, outline_text

def num_tokens_in_string(
        input_str: str, encoding_name: str = "cl100k_base"
) -> int:
    """
    Calculate the number of tokens in a given string using a specified encoding.

    Args:
        input_str (str): The input string to be tokenized.
        encoding_name (str, optional): The name of the encoding to use. Defaults to "cl100k_base",
            which is the most commonly used encoder (used by GPT-4).

    Returns:
        int: The number of tokens in the input string.

    Example:
        >>> text = "Hello, how are you?"
        >>> num_tokens = num_tokens_in_string(text)
        >>> print(num_tokens)
        5
    """
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(input_str))
    return num_tokens




def calculate_chunk_size(token_count: int, token_limit: int) -> int:
    """
    Calculate the chunk size based on the token count and token limit.

    Args:
        token_count (int): The total number of tokens.
        token_limit (int): The maximum number of tokens allowed per chunk.

    Returns:
        int: The calculated chunk size.

    Description:
        This function calculates the chunk size based on the given token count and token limit.
        If the token count is less than or equal to the token limit, the function returns the token count as the chunk size.
        Otherwise, it calculates the number of chunks needed to accommodate all the tokens within the token limit.
        The chunk size is determined by dividing the token limit by the number of chunks.
        If there are remaining tokens after dividing the token count by the token limit,
        the chunk size is adjusted by adding the remaining tokens divided by the number of chunks.

    Example:
        >>> calculate_chunk_size(1000, 500)
        500
        >>> calculate_chunk_size(1530, 500)
        389
        >>> calculate_chunk_size(2242, 500)
        496
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

    if debug:
        ic(num_tokens_in_text)

    if num_tokens_in_text < max_tokens:
        if debug:
            ic("Translating text as a single chunk")

        final_translation , outline = one_chunk_translate_text(
            source_lang, target_lang, source_text, style,outline_text, country , vocab_dict
        )

        return final_translation, outline

    else:
        raise ValueError("Chunks is oversized!!!")


