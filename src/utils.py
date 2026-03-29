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
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from PIL import Image

import openai
import tiktoken

from src.config import Config

# LLMService, TranslationPipeline, translate_chunk are defined in this module


# =============================================================================
# Schema Definitions (moved from src/schemas/translation.py)
# =============================================================================

class TranslationStage(Enum):
    """Stages in the translation pipeline."""
    INITIAL = "initial"
    SYNOPSIS = "synopsis"
    REFLECTION = "reflection"      # Merged: quality + nuances + suggestions
    IMPROVE = "improve"            # Apply reflection suggestions
    FINAL = "final"


class LLMRole(Enum):
    """LLM roles in the translation workflow."""
    PRIMARY = "primary"      # Hunyuan: translation + dictionary
    SECONDARY = "secondary"  # Instruction-based: quality + style


@dataclass
class TranslationContext:
    """Context passed through the translation pipeline."""
    source_lang: str
    target_lang: str
    source_text: str
    outline_text: str = ""
    vocab_dict: Dict[str, str] = field(default_factory=dict)
    country: str = ""
    style: str = "text"  # "xml" or "text"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "outline_text": self.outline_text,
            "vocab_dict": self.vocab_dict,
            "country": self.country,
            "style": self.style,
        }


@dataclass
class TranslationResult:
    """Result from a single translation stage."""
    stage: TranslationStage
    llm_role: LLMRole
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    processing_time: float = 0.0
    tokens_used: int = 0
    
    
@dataclass
class PipelineState:
    """Complete state of the translation pipeline."""
    context: TranslationContext
    initial_translation: Optional[str] = None
    synopsis: Optional[str] = None
    reflection: Optional[str] = None       # Merged quality + nuances
    final_translation: Optional[str] = None
    
    # Metadata
    stage_results: List[TranslationResult] = field(default_factory=list)
    start_time: float = 0.0
    total_tokens: int = 0
    
    def add_result(self, result: TranslationResult):
        """Add a stage result and update state."""
        self.stage_results.append(result)
        self.total_tokens += result.tokens_used
        
        if result.stage == TranslationStage.INITIAL:
            self.initial_translation = result.text
        elif result.stage == TranslationStage.SYNOPSIS:
            self.synopsis = result.text
        elif result.stage == TranslationStage.REFLECTION:
            self.reflection = result.text
        elif result.stage == TranslationStage.IMPROVE:
            self.final_translation = result.text
        elif result.stage == TranslationStage.FINAL:
            self.final_translation = result.text


# Workflow definition (5 stages - NEW ORDER)
TRANSLATION_WORKFLOW = [
    {
        "stage": TranslationStage.INITIAL,
        "llm_role": LLMRole.PRIMARY,
        "function": "initial_translation",
        "description": "Primary translation with dictionary and synopsis context"
    },
    {
        "stage": TranslationStage.REFLECTION,
        "llm_role": LLMRole.SECONDARY,
        "function": "reflection",
        "description": "Quality review + suggestions (country-aware)"
    },
    {
        "stage": TranslationStage.IMPROVE,
        "llm_role": LLMRole.SECONDARY,
        "function": "improve_translation",
        "description": "Apply reflection suggestions"
    },
    {
        "stage": TranslationStage.FINAL,
        "llm_role": LLMRole.SECONDARY,
        "function": "final_edit",
        "description": "Final proofreading against original (XML tag restoration)"
    },
    {
        "stage": TranslationStage.SYNOPSIS,
        "llm_role": LLMRole.PRIMARY,
        "function": "generate_synopsis",
        "description": "Summary from final translation (for next chunk context)"
    },
]

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
# Dual-LLM Translation Pipeline
# =============================================================================

class LLMService:
    """Service for LLM interactions with role-based client selection."""
    
    def __init__(self):
        import openai
        
        # Primary LLM client (Hunyuan for translation)
        self._primary_client = openai.OpenAI(
            api_key=config.api_key_translate,
            base_url=config.base_url_translate,
            timeout=config.timeout_translate
        )
        
        # Secondary LLM client (Instruction-based for quality/style)
        self._secondary_client = openai.OpenAI(
            api_key=config.api_key_proofread,
            base_url=config.base_url_proofread,
            timeout=config.timeout_proofread
        )
        
        # Images client (separate)
        self._images_client = openai.OpenAI(
            api_key=config.api_key_images,
            base_url=config.base_url_images,
            timeout=config.timeout_images
        )
    
    def get_client(self, role: LLMRole):
        """Get appropriate client based on LLM role."""
        if role == LLMRole.PRIMARY:
            return self._primary_client, config.model_translate, config.temp_translate
        else:
            return self._secondary_client, config.model_proofread, config.temp_proofread
    
    def get_temperature_for_stage(self, stage: TranslationStage, role: LLMRole) -> float:
        """
        Get temperature for specific pipeline stage.
        
        Stage-specific temperatures provide better quality than single temperature:
        - INITIAL: Low temp (0.01) for consistent translation
        - REFLECTION: Medium temp (0.4) for creative analysis
        - IMPROVE: Medium temp (0.4) for flexible editing
        - FINAL_EDIT: Low temp (0.15) for precise proofreading
        - SYNOPSIS: Low temp (0.15) for accurate summary
        
        Args:
            stage: TranslationStage enum
            role: LLMRole (PRIMARY or SECONDARY)
            
        Returns:
            Temperature value for the stage
        """
        if stage == TranslationStage.INITIAL:
            return config.temp_initial
        elif stage == TranslationStage.REFLECTION:
            return config.temp_reflection
        elif stage == TranslationStage.IMPROVE:
            return config.temp_improve
        elif stage == TranslationStage.FINAL:
            return config.temp_final_edit
        elif stage == TranslationStage.SYNOPSIS:
            return config.temp_synopsis
        else:
            # Fallback to role-based default
            if role == LLMRole.PRIMARY:
                return config.temp_translate
            else:
                return config.temp_proofread
    
    def complete(
        self,
        role: LLMRole,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 8192,
        json_mode: bool = False,
        stage: TranslationStage = None  # NEW: for stage-specific temperature
    ) -> str:
        """
        Execute LLM completion with role-appropriate client.
        
        Handles sys_not_promt mode for models that don't support system prompts:
        - Gemma 2/3: System prompt merged into user prompt
        - Mistral, Llama 3.x: System prompt sent separately
        
        Args:
            role: LLMRole.PRIMARY or LLMRole.SECONDARY
            system_prompt: System instruction (may be merged with user_prompt)
            user_prompt: User message content
            max_tokens: Maximum tokens to generate
            json_mode: Enable JSON response format
            stage: TranslationStage for temperature selection (optional)
            
        Returns:
            Generated text from LLM
        """
        client, model, temp = self.get_client(role)
        
        # Use stage-specific temperature if provided
        if stage is not None:
            temp = self.get_temperature_for_stage(stage, role)
        
        # Determine if we need to merge system prompt into user prompt
        # Models that DON'T support system prompts: Gemma 2, Gemma 3
        # Config flags: config.sys_not_promt_translate / config.sys_not_promt_proofread
        use_sys_not_promt = False
        
        if role == LLMRole.PRIMARY:
            use_sys_not_promt = config.sys_not_promt_translate
        else:
            use_sys_not_promt = config.sys_not_promt_proofread
        
        messages = []
        
        if use_sys_not_promt and system_prompt:
            # Merge system prompt into user prompt (for Gemma and similar)
            merged_prompt = f"{system_prompt}\n\n{user_prompt}"
            messages.append({"role": "user", "content": merged_prompt})
        else:
            # Standard mode: separate system and user messages
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})
        
        comp_kwargs = {
            "model": model,
            "temperature": temp,
            "max_tokens": max_tokens,
            "messages": messages
        }
        if json_mode:
            comp_kwargs["response_format"] = {"type": "json_object"}
        
        if config.debug:
            logger.debug(f"LLM Request [{role.value}]: {model}, {len(user_prompt)} chars, temp={temp:.2f}, sys_not_promt={use_sys_not_promt}")
        
        response = client.chat.completions.create(**comp_kwargs)
        result = response.choices[0].message.content
        
        if config.debug:
            logger.debug(f"LLM Response [{role.value}]: {len(result)} chars")
        
        return result


# Global LLM service instance
llm_service = LLMService()


class TranslationPipeline:
    """Main translation pipeline implementing dual-LLM workflow."""
    
    def __init__(self):
        # Prompts are loaded from prompts.json via config.get_prompt()
        pass
    
    @log_entry
    def initial_translation(self, context: TranslationContext) -> TranslationResult:
        """Stage 1: Primary LLM translation."""
        # Handle empty or very short input
        if not context.source_text or len(context.source_text.strip()) < 2:
            return TranslationResult(
                stage=TranslationStage.INITIAL,
                llm_role=LLMRole.PRIMARY,
                text="",
                metadata={"prompt_style": context.style, "skipped": "empty_input"}
            )
        
        if context.style == "xml":
            user_prompt = config.get_prompt(
                "initial_translation", "user_xml",
                source_lang=context.source_lang,
                target_lang=context.target_lang,
                outline_text=context.outline_text,
                vocab_dict=context.vocab_dict,
                source_text=context.source_text
            )
        elif config.model_translate == "Hunyuan":
            user_prompt = config.get_prompt(
                "initial_translation", "user_hunyuan",
                source_lang=context.source_lang,
                target_lang=context.target_lang,
                outline_text=context.outline_text,
                vocab_dict=context.vocab_dict,
                source_text=context.source_text
            )
        else:
            user_prompt = config.get_prompt(
                "initial_translation", "user_text",
                source_lang=context.source_lang,
                target_lang=context.target_lang,
                outline_text=context.outline_text,
                vocab_dict=context.vocab_dict,
                source_text=context.source_text
            )
        
        system_prompt = config.get_prompt("initial_translation", "system")
        
        text = llm_service.complete(
            role=LLMRole.PRIMARY,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=config.max_len_chunk * 4,
            stage=TranslationStage.INITIAL  # Stage-specific temperature
        )
        
        text = remove_tags(text)
        
        return TranslationResult(
            stage=TranslationStage.INITIAL,
            llm_role=LLMRole.PRIMARY,
            text=text,
            metadata={"prompt_style": context.style}
        )
    
    @log_entry
    def generate_synopsis(self, context: TranslationContext, translation: str) -> TranslationResult:
        """Stage 5: Generate synopsis from FINAL translation (moved to end)."""
        if config.model_translate == "Hunyuan":
            user_prompt = config.get_prompt(
                "synopsis", "user_hunyuan",
                target_lang=context.target_lang,
                final_translation=translation
            )
        else:
            user_prompt = config.get_prompt(
                "synopsis", "user",
                target_lang=context.target_lang,
                final_translation=translation
            )
        system_prompt = config.get_prompt("synopsis", "system")
        
        text = llm_service.complete(
            role=LLMRole.PRIMARY,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=160,
            stage=TranslationStage.SYNOPSIS  # Stage-specific temperature
        )
        
        text = remove_tags(text)
        
        return TranslationResult(
            stage=TranslationStage.SYNOPSIS,
            llm_role=LLMRole.PRIMARY,
            text=text
        )
    
    @log_entry
    def reflection(self, context: TranslationContext, translation: str) -> TranslationResult:
        """
        Stage 2: Secondary LLM reflection.
        Note: Does NOT use vocab_dict or synopsis - focuses on accuracy/style only.
        """
        user_prompt = config.get_prompt(
            "reflection", f"user_{context.style}",
            source_lang=context.source_lang,
            target_lang=context.target_lang,
            source_text=context.source_text,
            translation=translation,
            country=context.country
            # NO vocab_dict - reflection focuses on accuracy/style, not terminology
        )
        
        system_prompt = config.get_prompt("reflection", "system",
            target_lang=context.target_lang,
            country=context.country
        )
        
        text = llm_service.complete(
            role=LLMRole.SECONDARY,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=config.max_len_chunk,
            stage=TranslationStage.REFLECTION  # Stage-specific temperature
        )
        
        return TranslationResult(
            stage=TranslationStage.REFLECTION,
            llm_role=LLMRole.SECONDARY,
            text=text
        )
    
    @log_entry
    def improve_translation(self, context: TranslationContext, translation: str, reflection: str) -> TranslationResult:
        """Stage 4: Secondary LLM improvement."""
        user_prompt = config.get_prompt(
            "improve", f"user_{context.style}",
            source_lang=context.source_lang,
            target_lang=context.target_lang,
            country=context.country,
            source_text=context.source_text,
            translation=translation,
            reflection=reflection,
            vocab_dict=context.vocab_dict
        )
        
        system_prompt = config.get_prompt("improve", "system",
            target_lang=context.target_lang,
            country=context.country
        )
        
        text = llm_service.complete(
            role=LLMRole.SECONDARY,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=config.max_len_chunk * 4,
            stage=TranslationStage.IMPROVE  # Stage-specific temperature
        )
        
        text = remove_tags(text)
        
        return TranslationResult(
            stage=TranslationStage.IMPROVE,
            llm_role=LLMRole.SECONDARY,
            text=text
        )
    
    @log_entry
    def final_edit(self, context: TranslationContext, translation: str) -> TranslationResult:
        """
        Stage 4: Final editing/proofreading - compare with original and fix XML tags.
        Uses vocabulary to verify terminology consistency.
        """
        user_prompt = config.get_prompt(
            "editor", f"user_{context.style}",
            source_lang=context.source_lang,
            target_lang=context.target_lang,
            country=context.country,
            source_text=context.source_text,
            translation=translation,
            vocab_dict=context.vocab_dict  # Added for terminology verification
        )
        
        system_prompt = config.get_prompt("editor", "system",
            target_lang=context.target_lang,
            country=context.country
        )
        
        text = llm_service.complete(
            role=LLMRole.SECONDARY,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=config.max_len_chunk * 4,
            stage=TranslationStage.FINAL  # Stage-specific temperature
        )
        
        text = remove_tags(text)
        
        return TranslationResult(
            stage=TranslationStage.FINAL,
            llm_role=LLMRole.SECONDARY,
            text=text,
            metadata={"stage": "final_edit", "compared_with_original": True, "vocabulary_used": True}
        )
    
    def execute(self, source_lang: str, target_lang: str, source_text: str,
                outline_text: str, vocab_dict: dict, country: str,
                style: str = "text", fast_mode: bool = False) -> PipelineState:
        """
        Execute the complete translation pipeline.
        
        UPDATED ORDER (5 stages):
        1. INITIAL - Primary LLM translation
        2. REFLECTION - Secondary LLM quality review (NO vocab_dict)
        3. IMPROVE - Apply reflection suggestions
        4. FINAL_EDIT - Final proofreading WITH vocabulary (UPDATED)
        5. SYNOPSIS - Create summary from final translation
        """
        context = TranslationContext(
            source_lang=source_lang,
            target_lang=target_lang,
            source_text=source_text,
            outline_text=outline_text,
            vocab_dict=vocab_dict,
            country=country,
            style=style
        )
        
        state = PipelineState(context=context)
        state.start_time = time.time()
        
        # Stage 1: Initial Translation (Primary LLM)
        initial_result = self.initial_translation(context)
        state.add_result(initial_result)
        
        if fast_mode:
            # Fast path: skip reflection/improve/final_edit, return initial translation
            final_result = TranslationResult(
                stage=TranslationStage.FINAL,
                llm_role=LLMRole.PRIMARY,
                text=initial_result.text,
                metadata={"fast_mode": True, "applied_reflection": False}
            )
            state.add_result(final_result)
            
            # Even in fast mode, generate synopsis from final translation
            synopsis_result = self.generate_synopsis(context, initial_result.text)
            state.add_result(synopsis_result)
        else:
            # Stage 2: Reflection (Secondary LLM) - NO vocab_dict
            reflection_result = self.reflection(context, initial_result.text)
            state.add_result(reflection_result)
            
            # Stage 3: Improve (Secondary LLM)
            improve_result = self.improve_translation(
                context, initial_result.text, reflection_result.text
            )
            state.add_result(improve_result)
            
            # Stage 4: Final Edit (Secondary LLM) - WITH vocab_dict
            final_edit_result = self.final_edit(context, improve_result.text)
            state.add_result(final_edit_result)
            
            # Stage 5: Synopsis (Primary LLM) - from final translation
            synopsis_result = self.generate_synopsis(context, final_edit_result.text)
            state.add_result(synopsis_result)
            
            final_result = TranslationResult(
                stage=TranslationStage.FINAL,
                llm_role=LLMRole.SECONDARY,
                text=final_edit_result.text,
                metadata={"fast_mode": False, "applied_reflection": True, "final_edit": True}
            )
            state.add_result(final_result)
        
        return state


# Global pipeline instance
_pipeline = TranslationPipeline()


# =============================================================================
# Length Validation (Rechunking Support)
# =============================================================================

MIN_CHUNK_SIZE = 1000  # Minimum chunk size for rechunking
MAX_DEPTH = 3  # Maximum recursion depth


def validate_translation_length(source_text: str, translated_text: str, 
                                 stage_name: str = "") -> tuple:
    """
    Validate translation length and determine if rechunking is needed.
    
    Args:
        source_text: Original source text
        translated_text: Translated text
        stage_name: Name of pipeline stage (for logging)
        
    Returns:
        Tuple of (is_valid: bool, percent_diff: float, should_split: bool)
    """
    source_len = len(source_text)
    target_len = len(translated_text)
    
    if source_len == 0:
        return True, 0.0, False
    
    percent_diff = abs(target_len - source_len) / source_len * 100
    
    # Check if rechunking is needed
    should_split = (
        source_len >= MIN_CHUNK_SIZE and
        percent_diff > config.length_check_threshold
    )
    
    if config.debug:
        status = "⚠ SPLIT" if should_split else "✓ OK"
        logger.debug(f"[{stage_name}] {source_len} → {target_len} chars ({percent_diff:.1f}%) {status}")
    
    return not should_split, percent_diff, should_split


def translate_chunk(source_lang: str, target_lang: str, source_text: str,
                    outline_text: str, vocab_dict: dict, country: str,
                    style: str = "text", fast_mode: bool = False,
                    depth: int = 0) -> tuple:
    """
    Translate a single chunk using the dual-LLM pipeline.
    
    Includes automatic rechunking if length validation fails.
    
    Args:
        source_lang: Source language
        target_lang: Target language
        source_text: Text to translate
        outline_text: Context synopsis from previous chunks
        vocab_dict: Translation dictionary
        country: Target country for cultural context
        style: "xml" or "text"
        fast_mode: Skip reflection/improve stages
        depth: Current recursion depth (for rechunking)
    
    Returns:
        Tuple of (final_translation, synopsis)
    """
    # Execute pipeline
    state = _pipeline.execute(
        source_lang=source_lang,
        target_lang=target_lang,
        source_text=source_text,
        outline_text=outline_text,
        vocab_dict=vocab_dict,
        country=country,
        style=style,
        fast_mode=fast_mode
    )
    
    # Validate final translation length
    is_valid, percent_diff, should_split = validate_translation_length(
        source_text, state.final_translation, "FINAL"
    )
    
    # Rechunking if needed
    if should_split and depth < MAX_DEPTH:
        logger.info(f"Rechunking at depth {depth}: {percent_diff:.1f}% length difference")
        
        # Split source text
        part1, part2 = split_text_smartly(source_text)
        
        # Translate parts recursively
        result1, syn1 = translate_chunk(
            source_lang, target_lang, part1, outline_text,
            vocab_dict, country, style, fast_mode, depth + 1
        )
        result2, syn2 = translate_chunk(
            source_lang, target_lang, part2, outline_text,
            vocab_dict, country, style, fast_mode, depth + 1
        )
        
        # Combine results
        combined_translation = (result1 or "") + (result2 or "")
        combined_synopsis = (syn1 or "") + " " + (syn2 or "")
        
        return combined_translation, combined_synopsis
    
    return state.final_translation, state.synopsis


# =============================================================================
# LLM Service (compatibility layer)
# =============================================================================

class LLMServiceCompat:
    """
    Compatibility layer for old LLMService interface.
    Delegates to LLMService in the same module.
    """
    
    def __init__(self):
        self._new_service = llm_service
    
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
    
    def complete(self, role: LLMRole, system_prompt: str, user_prompt: str,
                 max_tokens: int = 8192, json_mode: bool = False,
                 stage: 'TranslationStage' = None) -> str:
        """
        Direct LLM completion (delegates to translation_pipeline.LLMService).
        Used by synopsis_manager.py and other modules.
        
        Args:
            role: LLM role (PRIMARY or SECONDARY)
            system_prompt: System message
            user_prompt: User message
            max_tokens: Maximum tokens to generate
            json_mode: Enable JSON response format
            stage: TranslationStage for temperature selection (optional)
            
        Returns:
            Generated text from LLM
        """
        return self._new_service.complete(
            role=role,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            json_mode=json_mode,
            stage=stage  # Pass stage for temperature selection
        )
    
    def get_completion(self, role: str, prompt_category: str, prompt_key: str = None,
                       temperature: float = None, max_tokens: int = None, json_mode: bool = False,
                       stage: 'TranslationStage' = None,  # For stage-specific temperature
                       **kwargs) -> str:
        """
        Get completion using prompts.json templates.
        Compatibility wrapper for old-style calls.
        
        Args:
            role: LLM role ("Translate" or "Proofread")
            prompt_category: Category in prompts.json (e.g., "vocabulary")
            prompt_key: Key in category (e.g., "user", "user_hunyuan")
            temperature: Override temperature (optional)
            max_tokens: Override max tokens (optional)
            json_mode: Enable JSON response format
            stage: TranslationStage for temperature selection (optional)
            **kwargs: Template variables for prompt formatting
            
        Returns:
            Generated text from LLM
        """
        # Get prompt template
        template = config.prompts.get(prompt_category, {})
        if isinstance(template, dict):
            prompt_template = template.get(prompt_key, template.get('user', ''))
        else:
            prompt_template = str(template)
        
        # Filter out None values from kwargs to prevent formatting errors
        safe_kwargs = {k: v for k, v in kwargs.items() if v is not None}
        
        # Format template
        try:
            user_prompt = prompt_template.format(**safe_kwargs)
        except KeyError as e:
            logger.warning(f"Missing variable for prompt: {e}")
            user_prompt = prompt_template
        
        # Determine LLM role
        llm_role = LLMRole.PRIMARY if role == "Translate" else LLMRole.SECONDARY
        
        # Get completion
        return self._new_service.complete(
            role=llm_role,
            system_prompt="",  # Prompts are self-contained
            user_prompt=user_prompt,
            max_tokens=max_tokens or MAX_TOKENS_PER_CHUNK,
            json_mode=json_mode,
            stage=stage  # Pass stage for temperature selection
        )


# Global LLM service instance
llm_service = LLMServiceCompat()


# =============================================================================
# Core Functions (used by app.py)
# =============================================================================

@log_entry
def remove_tags(text: str) -> str:
    """
    Remove XML/HTML tags and artifacts from translation output.
    Uses regex patterns to clean common LLM output artifacts.
    
    Note: For FB2 XML validation and cleaning, use xmlcheck.rem_tags()
    
    Args:
        text: Text with XML tags to remove
        
    Returns:
        Cleaned text without tags
    """
    if not text:
        return ""
    
    # Remove meta-commentary from LLM (common pattern)
    # E.g., "I'm ready to help...", "Could you please provide...", etc.
    if "I'm ready to help" in text or "Could you please" in text or "I don't see any" in text:
        logger.warning("LLM returned meta-commentary instead of translation")
        return ""
    
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
    
    Args:
        source_lang: Source language
        target_lang: Target language
        source_text: Text with terms to translate (from NER)
        country: Target country
        role: LLM role ("Translate" or "Proofread")
        
    Returns:
        Translated vocabulary terms
    """
    # Validate input
    if not source_text or not source_text.strip():
        logger.warning("vocabulary() called with empty source_text")
        return ""
    
    # Use standard prompt for vocabulary translation (not Hunyuan-specific)
    # Vocabulary translation uses Secondary LLM with standard prompt
    prompt_key = "user"
    
    result = llm_service.get_completion(
        role=role,
        prompt_category="vocabulary",
        prompt_key=prompt_key,
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
        # Use Hunyuan-specific prompt if model is Hunyuan
        prompt_key = "user_hunyuan" if config.model_translate == "Hunyuan" else "user"
        
        response = llm_service.get_completion(
            role="Proofread",
            prompt_category="metadata_translation",
            prompt_key=prompt_key,
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