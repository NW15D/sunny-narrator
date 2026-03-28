"""
Utility functions for translation pipeline.

This module serves as a compatibility layer over the new dual-LLM architecture.
Main translation logic moved to src/translation_pipeline.py

Used functions:
- translate() → pipeline wrapper
- split_text_smartly() → rechunking
- vocabulary() → dictionary generation  
- remove_tags() → cleanup
- translate_metadata() → metadata translation
- process_image_request() → cover processing
- llm_service → LLM client accessor
"""

import logging
import functools
import re
import json
import io
import base64
import httpx
from typing import Optional, Dict, Any
from PIL import Image

import openai
import tiktoken

from src.config import Config

# Import new pipeline
from src.translation_pipeline import translate_chunk, LLMService

# Initialize global config
config = Config()

# Setup logging
logger = logging.getLogger(__name__)
if config.debug:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def log_entry(func):
    """Decorator to log function entry for key functions."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"→ {func.__name__}")
        return func(*args, **kwargs)
    return wrapper


# Constants
MAX_TOKENS_PER_CHUNK = config.max_len_chunk * 4

# Language mapping for models requiring ISO codes
LANG_MAP = {
    "english": "en", "russian": "ru", "chinese": "zh",
    "french": "fr", "german": "de", "spanish": "es",
    "italian": "it", "japanese": "ja", "korean": "ko",
    "portuguese": "pt", "czech": "cs", "polish": "pl",
    "ukrainian": "uk", "dutch": "nl", "turkish": "tr",
    "vietnamese": "vi", "thai": "th", "arabic": "ar",
    "hebrew": "he", "hindi": "hi", "indonesian": "id",
    "swedish": "sv", "norwegian": "no", "danish": "da",
    "finnish": "fi", "greek": "el", "hungarian": "hu"
}


# =============================================================================
# LLM Service (compatibility layer)
# =============================================================================

class LLMServiceCompat:
    """
    Compatibility layer for old LLMService interface.
    Delegates to new translation_pipeline.LLMService.
    """
    
    def __init__(self):
        self._new_service = LLMService()
    
    @property
    def clientTranslate(self):
        """Primary LLM client (Hunyuan)."""
        return self._new_service._primary_client
    
    @property
    def clientProofread(self):
        """Secondary LLM client."""
        return self._new_service._secondary_client
    
    @property
    def clientImages(self):
        """Images LLM client."""
        return self._new_service._images_client
    
    def get_completion(self, role: str, prompt_category: str, prompt_key: str = None,
                       temperature: float = None, max_tokens: int = None, json_mode: bool = False,
                       **kwargs) -> str:
        """
        Get completion using prompts.json templates.
        Compatibility wrapper for old-style calls.
        """
        # Get prompt template
        template = config.prompts.get(prompt_category, {})
        if isinstance(template, dict):
            prompt_template = template.get(prompt_key, template.get('user', ''))
        else:
            prompt_template = str(template)
        
        # Format template
        try:
            user_prompt = prompt_template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing variable for prompt: {e}")
            user_prompt = prompt_template
        
        # Determine LLM role
        from src.translation_pipeline import LLMRole
        llm_role = LLMRole.PRIMARY if role == "Translate" else LLMRole.SECONDARY
        
        # Get completion
        return self._new_service.complete(
            role=llm_role,
            system_prompt="",  # Prompts are self-contained
            user_prompt=user_prompt,
            max_tokens=max_tokens or MAX_TOKENS_PER_CHUNK,
            json_mode=json_mode
        )


# Global LLM service instance
llm_service = LLMServiceCompat()


# =============================================================================
# Core Functions (used by app.py)
# =============================================================================

@log_entry
def remove_tags(text: str) -> str:
    """Remove XML-style tags from text."""
    patterns = [
        r'<SOURCE_TEXT>[\s\S]*?</SOURCE_TEXT>',
        r'<DICTIONARY>[\s\S]*?</DICTIONARY>',
        r'<EXPERT_SUGGESTIONS>[\s\S]*?</EXPERT_SUGGESTIONS>',
        r'<SYNOPSIS>[\s\S]*?</SYNOPSIS>',
        r'<INITIAL_TRANSLATION>[\s\S]*?</INITIAL_TRANSLATION>',
        r'<FIRST_TRANSLATION>[\s\S]*?</FIRST_TRANSLATION>',
        r'<TRANSLATION>[\s\S]*?</TRANSLATION>',
        r'```xml', r'```',
        r'</?(?:section|IMPROVED_TRANSLATION|target|TTEXT|TRANS)>',
        r'<\|im_end\|>', r'<\|file_separator\|>'
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    return text.strip()


@log_entry
def split_text_smartly(text: str) -> tuple:
    """
    Split text roughly in half, respecting paragraph boundaries.
    Used for rechunking when translation validation fails.
    """
    if not text:
        return "", ""
    
    length = len(text)
    mx = int((length // 2) * 1.1)
    
    # Try to find closing p tag
    split_pos = text.rfind('</p>', 0, mx)
    
    if split_pos == -1:
        split_pos = mx if mx < length else length // 2
    else:
        split_pos += 4  # Include the </p>
    
    return text[:split_pos], text[split_pos:]


@log_entry
def translate(source_lang: str, target_lang: str, source_text: str,
              style: str, outline_text: str, country: str, vocab_dict: dict,
              max_tokens: int = MAX_TOKENS_PER_CHUNK, temperature: float = None) -> tuple:
    """
    Translate source_text using dual-LLM pipeline.
    
    Args:
        source_lang: Source language
        target_lang: Target language
        source_text: Text to translate
        style: "xml" or "text"
        outline_text: Context synopsis
        country: Target country
        vocab_dict: Translation dictionary
        max_tokens: Max tokens per chunk
        temperature: Temperature override (ignored, uses config)
    
    Returns:
        (final_translation, synopsis)
    """
    # Token check
    num_tokens = num_tokens_in_string(source_text)
    if num_tokens > max_tokens:
        raise ValueError(f"Chunk of size {num_tokens} tokens exceeds limit of {max_tokens}")
    
    logger.info(f"→ [translate] Using dual-LLM pipeline (fast_mode={config.fast_trans})")
    
    final_translation, synopsis = translate_chunk(
        source_lang=source_lang,
        target_lang=target_lang,
        source_text=source_text,
        outline_text=outline_text,
        vocab_dict=vocab_dict if vocab_dict else {},
        country=country,
        style=style,
        fast_mode=config.fast_trans
    )
    
    return final_translation, synopsis


@log_entry
def vocabulary(source_lang: str, target_lang: str, source_text: str,
               country: str, role: str) -> str:
    """
    Generate vocabulary for proper nouns using LLM.
    """
    result = llm_service.get_completion(
        role=role,
        prompt_category="vocabulary",
        source_lang=source_lang,
        target_lang=target_lang,
        country=country,
        source_text=source_text
    )
    
    if config.debug:
        logger.debug(f"Vocabulary generated: {len(result)} chars")
    
    return result


@log_entry
def translate_metadata(metadata: dict, source_lang: str, target_lang: str,
                       country: str) -> dict:
    """
    Translate metadata dictionary using LLM in JSON mode.
    """
    try:
        response = llm_service.get_completion(
            role="Proofread",
            prompt_category="metadata_translation",
            json_mode=True,
            source_lang=source_lang,
            target_lang=target_lang,
            country=country,
            metadata_json=json.dumps(metadata, ensure_ascii=False)
        )
        
        if not response:
            return metadata
        
        # Extract JSON from response
        match = re.search(r'(\{.*\})', response, re.DOTALL)
        clean_json = match.group(1) if match else response.strip()
        
        return json.loads(clean_json)
        
    except Exception as e:
        logger.error(f"Error translating metadata: {e}")
        return metadata


@log_entry
def process_image_request(image_data: str, source_lang: str, target_lang: str,
                          country: str, metadata: dict = None) -> Optional[str]:
    """
    Process cover image: generate variation or new image.
    
    Args:
        image_data: Base64 encoded image data
        source_lang: Source language
        target_lang: Target language
        country: Target country
        metadata: Book metadata for prompt generation
    
    Returns:
        Base64 encoded result image or None on failure
    """
    try:
        # Build prompt
        if metadata:
            title = metadata.get('book-title', '')
            authors = metadata.get('author', [])
            authors_str = ", ".join(
                f"{a.get('first-name', '')} {a.get('last-name', '')}".strip()
                for a in authors if isinstance(a, dict)
            )
            genres = ", ".join(metadata.get('genre', []))
            annotation = " ".join(metadata.get('annotation', []))[:300]
            
            prompt = config.get_prompt(
                "image_generation", "generation",
                target_lang=target_lang, title=title,
                authors_str=authors_str, genres=genres, annotation=annotation
            )
        else:
            prompt = config.get_prompt(
                "image_generation", "variation",
                source_lang=source_lang, target_lang=target_lang
            )
        
        if config.debug:
            logger.debug(f"Image prompt: {prompt[:100]}...")
        
        client = llm_service.clientImages
        
        if metadata:
            # Generate new image
            response = client.images.generate(
                model=config.model_images,
                prompt=prompt,
                n=1,
                size="1024x1024"
            )
        else:
            # Create variation
            image_bytes = base64.b64decode(image_data)
            img = Image.open(io.BytesIO(image_bytes))
            
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Crop to square
            w, h = img.size
            size = min(w, h)
            left = (w - size) / 2
            top = (h - size) / 2
            img = img.crop((left, top, left + size, top + size))
            img = img.resize((1024, 1024), Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            
            response = client.images.create_variation(
                image=buffer,
                n=1,
                size="1024x1024",
                model=config.model_images
            )
        
        # Get image data
        generated = response.data[0]
        
        if hasattr(generated, 'b64_json') and generated.b64_json:
            img_bytes = base64.b64decode(generated.b64_json)
        elif hasattr(generated, 'url') and generated.url:
            logger.info(f"Downloading image from URL: {generated.url}")
            with httpx.Client() as client:
                r = client.get(generated.url)
                if r.status_code != 200:
                    logger.error(f"Failed to download image: {r.status_code}")
                    return None
                img_bytes = r.content
        else:
            logger.error("No image data in response")
            return None
        
        # Resize and encode
        img = Image.open(io.BytesIO(img_bytes))
        img = img.resize((1024, 1536), Image.Resampling.LANCZOS)
        
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=70)
        
        return base64.b64encode(output.getvalue()).decode('utf-8')
        
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        return None


# =============================================================================
# Utility Functions
# =============================================================================

def num_tokens_in_string(input_str: str, encoding_name: str = "cl100k_base") -> int:
    """Calculate number of tokens in string."""
    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(input_str))