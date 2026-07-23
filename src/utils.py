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
import dataclasses
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from PIL import Image

import openai
import tiktoken

from src.config import Config
from src.llm_logger import init_llm_logger, get_llm_logger, log_llm_call
from src.p_tags_processor import post_process_p_tags

# LLMService, TranslationPipeline, translate_chunk are defined in this module


# =============================================================================
# Translation Metrics Tracker
# =============================================================================

class TranslationMetrics:
    """
    Track translation quality metrics and token usage.
    
    Logs:
    - Rechunking events (ERROR)
    - Retry tokens (ERROR)
    - XML repairs (ERROR)
    - Language mismatch retries (ERROR)
    - Successful translations (INFO)
    """
    
    def __init__(self):
        self.total_tokens = 0
        self.retry_tokens = 0
        self.rechunk_count = 0
        self.xml_repair_count = 0
        self.language_mismatch_retries = 0
        self.successful_translations = 0
        self.failed_translations = 0
        
    def log_retry(self, tokens: int, reason: str):
        """Log retry event (ERROR level)."""
        self.retry_tokens += tokens
        logger.error(f"RETRY: {reason} (tokens: {tokens:,})")
        
    def log_rechunk(self, depth: int, percent_diff: float):
        """Log rechunk event (ERROR level)."""
        self.rechunk_count += 1
        logger.error(f"RECHUNK #{self.rechunk_count} at depth {depth}: {percent_diff:.1f}% length difference")
        
    def log_xml_repair(self, issue: str):
        """Log XML repair event (ERROR level)."""
        self.xml_repair_count += 1
        logger.error(f"XML REPAIR #{self.xml_repair_count}: {issue}")
        
    def log_language_mismatch(self, tokens: int):
        """Log language mismatch retry (ERROR level)."""
        self.language_mismatch_retries += 1
        self.retry_tokens += tokens
        logger.error(f"LANGUAGE MISMATCH RETRY #{self.language_mismatch_retries} (tokens: {tokens:,})")
        
    def log_success(self, tokens: int):
        """Log successful translation (INFO level)."""
        self.successful_translations += 1
        self.total_tokens += tokens
        logger.info(f"Translation successful (tokens: {tokens:,}, total: {self.total_tokens:,})")
        
    def log_failure(self, reason: str):
        """Log failed translation (ERROR level)."""
        self.failed_translations += 1
        logger.error(f"TRANSLATION FAILED: {reason}")
        
    def get_report(self) -> dict:
        """Generate metrics report."""
        total = max(1, self.total_tokens + self.retry_tokens)
        return {
            "successful_translations": self.successful_translations,
            "failed_translations": self.failed_translations,
            "total_tokens": self.total_tokens,
            "retry_tokens": self.retry_tokens,
            "retry_percentage": (self.retry_tokens / total) * 100,
            "rechunk_count": self.rechunk_count,
            "xml_repair_count": self.xml_repair_count,
            "language_mismatch_retries": self.language_mismatch_retries
        }
        
    def print_report(self):
        """Print formatted metrics report."""
        report = self.get_report()
        
        logger.info("=" * 60)
        logger.info("TRANSLATION METRICS REPORT")
        logger.info("=" * 60)
        logger.info(f"Successful translations: {report['successful_translations']}")
        logger.info(f"Failed translations: {report['failed_translations']}")
        logger.info(f"Total tokens: {report['total_tokens']:,}")
        logger.info(f"Retry tokens: {report['retry_tokens']:,} ({report['retry_percentage']:.1f}%)")
        logger.info(f"Rechunk events: {report['rechunk_count']}")
        logger.info(f"XML repairs: {report['xml_repair_count']}")
        logger.info(f"Language mismatch retries: {report['language_mismatch_retries']}")
        logger.info("=" * 60)


def replace_vocab_in_text(
    source_text: str, 
    vocab_dict: Dict[str, str],
    source_lang: str = None
) -> str:
    """
    Replace dictionary words in source_text with their translations.
    Uses word boundary matching for exact matches only.
    
    Args:
        source_text: Original text to translate
        vocab_dict: Dictionary mapping source words → target translations
        source_lang: Source language (reserved for future tokenizer use)
    
    Returns:
        Text with dictionary words replaced (e.g., "everytime dragon fly" → "everytime драккар fly")
    """
    if not vocab_dict or not source_text:
        return source_text
    
    # Sort by length desc to replace longer matches first (avoids partial replacements)
    sorted_keys = sorted(vocab_dict.keys(), key=len, reverse=True)
    escaped_keys = [re.escape(k) for k in sorted_keys]
    pattern = r'\b(' + '|'.join(escaped_keys) + r')\b'
    
    def replace_func(match):
        word = match.group(1)
        return vocab_dict.get(word, word)
    
    return re.sub(pattern, replace_func, source_text)


# Global metrics instance
metrics = TranslationMetrics()


# =============================================================================
# Global Statistics Counters (for metrics reporting)
# =============================================================================

class TranslationStats:
    """Global counters for translation statistics."""
    
    def __init__(self):
        self.rechunk_events = 0
        self.language_mismatch_retries = 0
    
    def reset(self):
        self.rechunk_events = 0
        self.language_mismatch_retries = 0
    
    def get_stats(self) -> dict:
        return {
            'rechunk_events': self.rechunk_events,
            'language_mismatch_retries': self.language_mismatch_retries,
        }


# Global statistics instance
translation_stats = TranslationStats()


def get_translation_stats() -> dict:
    """Get global translation statistics."""
    return translation_stats.get_stats()


def reset_translation_stats():
    """Reset global translation statistics."""
    translation_stats.reset()


# =============================================================================
# Vocabulary Auto-Substitution (before Stage 1 translation)
# =============================================================================

def _format_vocab_for_prompt(
    vocab_dict: Optional[Dict[str, str]] = None,
    vocab_entries: Optional[List[Any]] = None,
    model: str = ""
) -> str:
    """
    Format vocabulary for prompt injection.
    
    Two modes:
    1. Dict mode: {"source": "target"} → "source = target" (original format)
    2. Entries mode: List[VocabEntry] → "source = target, category, gender, notes"
    
    Args:
        vocab_dict: Dictionary mapping source words → target translations (deprecated)
        vocab_entries: List of VocabEntry objects with full metadata
        model: Model name for formatting (e.g., "Hunyuan", "Gemma")
        
    Returns:
        Formatted string for prompt injection
    """
    # Prefer entries mode if available
    if vocab_entries and len(vocab_entries) > 0:
        # Check if entries have required attributes
        try:
            # Try to use format_for_model from vocab_manager if available
            if hasattr(vocab_entries[0], 'source') and hasattr(vocab_entries[0], 'target'):
                # Import lazily to avoid circular dependency
                try:
                    from src.vocabulary_manager import VocabularyManager
                    vm = VocabularyManager()
                    # Use standard format with full metadata
                    return vm._format_standard(vocab_entries)
                except Exception:
                    # Fallback: format manually
                    return _format_entries_standard(vocab_entries)
        except Exception:
            pass
    
    # Fallback to dict mode (original behavior)
    if not vocab_dict:
        return ""
    
    lines = []
    for source, target in vocab_dict.items():
        line = f"{source} = {target}"
        lines.append(line)
    
    return "\n".join(lines)


def _format_entries_standard(entries: List[Any]) -> str:
    """
    Format VocabEntry list to standard format: source = target, category, gender, notes
    """
    if not entries:
        return ""
    
    lines = []
    for entry in entries:
        # Use to_dict() if available (VocabEntry)
        if hasattr(entry, 'to_dict'):
            d = entry.to_dict()
            source = d.get('source', entry.source if hasattr(entry, 'source') else '')
            target = d.get('target', entry.target if hasattr(entry, 'target') else '')
            category = d.get('category', '')
            gender = d.get('gender', '')
            notes = d.get('notes', '')
        else:
            # Fallback: direct attribute access
            source = getattr(entry, 'source', '')
            target = getattr(entry, 'target', '')
            category = getattr(entry, 'category', '')
            gender = getattr(entry, 'gender', '')
            notes = getattr(entry, 'notes', '')
        
        line = f"{source} = {target}"
        parts = []
        if category:
            parts.append(category)
        if gender:
            parts.append(gender)
        if notes:
            parts.append(notes)
        
        if parts:
            line += ", " + ", ".join(parts)
        
        lines.append(line)
    
    return "\n".join(lines)


def replace_vocab_in_text(
    source_text: str,
    vocab_dict: Dict[str, str],
    source_lang: str = None
) -> str:
    """
    Replace dictionary words in source_text with their translations.
    Uses word boundary matching for exact matches only.
    
    This function is called BEFORE Stage 1 (INITIAL) translation to ensure
    the LLM sees translated terms from the dictionary in context.
    
    Stages 2-4 (reflection, improve, final_edit) see the ORIGINAL source_text
    without substitutions, allowing quality verification.
    
    Args:
        source_text: Original text to translate
        vocab_dict: Dictionary mapping source words → target translations
        source_lang: Source language (reserved for future tokenizer use)
    
    Returns:
        Text with dictionary words replaced (e.g., "everytime dragon fly" → "everytime драккар fly")
    
    Examples:
        >>> replace_vocab_in_text("dragon fly", {"dragon": "драккар"})
        'драккар fly'
        >>> replace_vocab_in_text("dragonfly is dragon", {"dragon": "драккар"})
        'dragonfly is драккар'  # only full word match
        >>> replace_vocab_in_text("", {})
        ''
    """
    if not vocab_dict or not source_text:
        return source_text
    
    # Sort by length desc to replace longer matches first (avoids partial replacements)
    sorted_keys = sorted(vocab_dict.keys(), key=len, reverse=True)
    escaped_keys = [re.escape(k) for k in sorted_keys]
    pattern = r'\b(' + '|'.join(escaped_keys) + r')\b'
    
    def replace_func(match):
        word = match.group(1)
        return vocab_dict.get(word, word)
    
    return re.sub(pattern, replace_func, source_text)


def reset_translation_stats():
    """Reset global translation statistics."""
    translation_stats.reset()


# =============================================================================
# Unit Tests for replace_vocab_in_text()
# =============================================================================

def _test_replace_vocab_in_text():
    """Run tests for replace_vocab_in_text() function."""
    import sys
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Basic replacement
    try:
        result = replace_vocab_in_text("dragon fly dragon", {"dragon": "драккар"})
        assert result == "драккар fly драккар", f"Expected 'драккар fly драккар', got '{result}'"
        print("✓ Test 1 passed: Basic replacement")
        tests_passed += 1
    except AssertionError as e:
        print(f"✗ Test 1 failed: {e}")
        tests_failed += 1
    
    # Test 2: Word boundary matching
    try:
        result = replace_vocab_in_text("dragonfly is dragon", {"dragon": "драккар"})
        assert result == "dragonfly is драккар", f"Expected 'dragonfly is драккар', got '{result}'"
        print("✓ Test 2 passed: Word boundary matching")
        tests_passed += 1
    except AssertionError as e:
        print(f"✗ Test 2 failed: {e}")
        tests_failed += 1
    
    # Test 3: Empty inputs
    try:
        assert replace_vocab_in_text("", {}) == ""
        assert replace_vocab_in_text("text", {}) == "text"
        assert replace_vocab_in_text("dragon", {}) == "dragon"
        print("✓ Test 3 passed: Empty inputs")
        tests_passed += 1
    except AssertionError as e:
        print(f"✗ Test 3 failed: {e}")
        tests_failed += 1
    
    # Test 4: Multiple words with length ordering
    try:
        result = replace_vocab_in_text("dragon fly dragonfly", {"dragon": "драккар", "dragonfly": "драккарий"})
        # Longer matches first, so dragonfly → драккарий, then dragon → драккар
        expected = "драккар fly драккарий"
        assert result == expected, f"Expected '{expected}', got '{result}'"
        print("✓ Test 4 passed: Multiple words with length ordering")
        tests_passed += 1
    except AssertionError as e:
        print(f"✗ Test 4 failed: {e}")
        tests_failed += 1
    
    # Test 5: Special regex characters in dictionary keys
    try:
        result = replace_vocab_in_text("a.b c*d e?f", {"a.b": "X", "c*d": "Y", "e?f": "Z"})
        assert result == "X Y Z", f"Expected 'X Y Z', got '{result}'"
        print("✓ Test 5 passed: Special regex characters escaped")
        tests_passed += 1
    except AssertionError as e:
        print(f"✗ Test 5 failed: {e}")
        tests_failed += 1
    
    print(f"\nResults: {tests_passed} passed, {tests_failed} failed")
    return tests_failed == 0


if __name__ == "__main__":
    success = _test_replace_vocab_in_text()
    sys.exit(0 if success else 1)


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
    vocab_entries: List[Any] = field(default_factory=list)  # Full VocabEntry objects
    country: str = ""
    style: str = "text"  # "xml" or "text"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "outline_text": self.outline_text,
            "vocab_dict": self.vocab_dict,
            "vocab_entries": [e.to_dict() if hasattr(e, 'to_dict') else {
                'source': e.source,
                'target': e.target,
                'category': getattr(e, 'category', ''),
                'gender': getattr(e, 'gender', ''),
                'notes': getattr(e, 'notes', '')
            } for e in self.vocab_entries],
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
MAX_TOKENS_PER_CHUNK = config.max_len_chunk * 2  # 2x chunk size for translation overhead

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
        stage: TranslationStage = None,  # NEW: for stage-specific temperature
        retry_count: int = 0,  # NEW: retry counter for empty responses
        track_tokens: bool = True,  # NEW: extract token usage from response
        allow_empty: bool = False,  # NEW: if True, don't retry on empty response (for synopsis)
        temperature: float = None,  # NEW: override temperature for smart retry
        force_json_mode: bool = False,  # NEW: force JSON mode ignoring config disable
        reasoning_budget: int = None,  # NEW: disable reasoning for vocabulary requests
        chat_template_kwargs: dict = None  # NEW: additional chat template kwargs
    ) -> tuple:
        """
        Execute LLM completion with role-appropriate client.
        
        Handles sys_not_promt mode for models that don't support system prompts:
        - Gemma 2/3: System prompt merged into user prompt
        - Mistral, Llama 3.x: System prompt sent separately
        
        NEW: Automatic retry on empty response (max 2 retries).
        NEW: Configurable JSON mode disable for local LLMs.
        NEW: Returns token usage from API response.
        NEW: reasoning_budget and chat_template_kwargs for vocabulary requests.
        
        Args:
            role: LLMRole.PRIMARY or LLMRole.SECONDARY
            system_prompt: System instruction (may be merged with user_prompt)
            user_prompt: User message content
            max_tokens: Maximum tokens to generate
            json_mode: Enable JSON response format
            stage: TranslationStage for temperature selection (optional)
            retry_count: Internal retry counter (do not set manually)
            track_tokens: Whether to extract token usage from response
            allow_empty: If True, accept empty response without retry (for synopsis stage)
            reasoning_budget: Set to 0 to disable reasoning (for vocabulary requests)
            chat_template_kwargs: Additional kwargs for chat template (e.g., {"enable_thinking": false})
            
        Returns:
            Tuple of (generated_text, tokens_used)
        """
        # Start timing for LLM call logging
        call_start_time = time.time()
        
        client, model, temp = self.get_client(role)
        
        # Use stage-specific temperature if provided
        if stage is not None:
            temp = self.get_temperature_for_stage(stage, role)
        
        # Override temperature if provided (for smart retry)
        if temperature is not None:
            temp = temperature
        
        # Determine if we need to merge system prompt into user prompt
        # Models that DON'T support system prompts: Gemma 2, Gemma 3
        # Config flags: config.sys_not_promt_translate / config.sys_not_promt_proofread
        use_sys_not_promt = False
        
        if role == LLMRole.PRIMARY:
            use_sys_not_promt = config.sys_not_promt_translate
        else:
            use_sys_not_promt = config.sys_not_promt_proofread
        
        # Check if JSON mode should be disabled for this role (for local LLMs)
        # But allow force_json_mode to override (for vocabulary translation)
        disable_json = False
        if role == LLMRole.PRIMARY:
            disable_json = config.disable_json_mode_translate
        else:
            disable_json = config.disable_json_mode_proofread
        
        # force_json_mode passed as parameter (not from kwargs)
        if disable_json and json_mode and not force_json_mode:
            json_mode = False
            if config.debug:
                logger.debug(f"JSON mode disabled for {role.value} LLM via config")
        
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
        
        # Add reasoning_budget if specified
        if reasoning_budget is not None:
            comp_kwargs["reasoning_budget"] = reasoning_budget
            
        if json_mode:
            comp_kwargs["response_format"] = {"type": "json_object"}
        
        # FIX: Disable thinking mode for local LLMs (gemma4, qwen3) when nothink config is True.
        # chat_template_kwargs is a llama.cpp-specific parameter, NOT a standard OpenAI API param.
        # The OpenAI Python SDK rejects unknown kwargs, so we must pass it via extra_body.
        nothink_enabled = False
        if role == LLMRole.PRIMARY and config.nothink_translate:
            nothink_enabled = True
        elif role == LLMRole.SECONDARY and config.nothink_proofread:
            nothink_enabled = True
        
        # If explicit chat_template_kwargs was passed, use it
        if chat_template_kwargs is not None:
            comp_kwargs["extra_body"] = {"chat_template_kwargs": chat_template_kwargs}
        elif nothink_enabled:
            comp_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
            if config.debug:
                logger.debug(f"Thinking mode DISABLED for [{role.value}] via nothink config (extra_body)")
        
        if config.debug:
            logger.debug(f"LLM Request [{role.value}]: {model}, {len(user_prompt)} chars, temp={temp:.2f}, sys_not_promt={use_sys_not_promt}, json_mode={json_mode}")
        
        # Store prompts for logging (before potential merge)
        log_system_prompt = system_prompt if not use_sys_not_promt else ""
        log_user_prompt = user_prompt if not use_sys_not_promt else (f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt)
        
        # Exponential backoff for API errors (network, rate limits, etc.)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(**comp_kwargs)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait = min(2 ** attempt * 2, 30)
                logger.warning(f"API error (attempt {attempt+1}/{max_retries}): {e}. Retrying in {wait}s")
                time.sleep(wait)
        
        # Debug: log full response structure
        if config.debug:
            try:
                logger.debug(f"LLM Raw Response [{role.value}]: choices={len(response.choices)}, model={response.model}")
                if response.choices:
                    msg = response.choices[0].message
                    content_type = type(msg.content).__name__ if msg else 'no message'
                    content_len = len(msg.content) if msg and msg.content else 0
                    content_is_none = msg.content is None if msg else True
                    logger.debug(f"  message.content: type={content_type}, len={content_len}, is_none={content_is_none}")
                    # Log reasoning tokens if present (gemma4 thinking mode)
                    if hasattr(msg, 'reasoning') and msg.reasoning:
                        logger.debug(f"  message.reasoning: {len(msg.reasoning)} chars (thinking mode detected!)")
                    if hasattr(response, 'usage') and response.usage:
                        # Check for separate reasoning/completion tokens
                        if hasattr(response.usage, 'completion_tokens_details'):
                            details = response.usage.completion_tokens_details
                            if details:
                                logger.debug(f"  completion_tokens_details: {details}")
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        logger.debug(f"  tool_calls={msg.tool_calls}")
            except Exception as e:
                logger.debug(f"Error logging response: {e}")
        
        result = response.choices[0].message.content
        
        # Extract token usage from response
        tokens_used = 0
        tokens_input = 0
        tokens_output = 0
        if track_tokens and hasattr(response, 'usage') and response.usage:
            tokens_used = response.usage.total_tokens or 0
            tokens_input = response.usage.prompt_tokens or 0
            tokens_output = response.usage.completion_tokens or 0
            if config.debug:
                logger.debug(f"LLM Response [{role.value}]: {len(result) if result else 0} chars, {tokens_used} tokens")
        else:
            if config.debug:
                logger.debug(f"LLM Response [{role.value}]: {len(result) if result else 0} chars")
        
        # Log LLM call if not a retry (avoid duplicate logs)
        if retry_count == 0 and config.llm_logging_enabled:
            duration_ms = int((time.time() - call_start_time) * 1000)
            stage_name = stage.value if stage else "unknown"
            log_llm_call(
                stage=stage_name,
                role=role.value,
                model=model,
                temperature=temp,
                duration_ms=duration_ms,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                tokens_total=tokens_used,
                prompt_system=log_system_prompt,
                prompt_user=log_user_prompt,
                response=result or ""
            )
        
        # Check for empty response and retry (unless allow_empty is True)
        # Log warning if tokens > 0 but result is empty (indicates LLM issue)
        if (not result or len(result.strip()) == 0) and tokens_used > 0:
            logger.warning(f"⚠️ EMPTY RESPONSE [{role.value}]: LLM returned {tokens_used} tokens but result=None/empty")
        
        if not result or len(result.strip()) == 0:
            if allow_empty:
                # For stages where empty response is acceptable (e.g., synopsis)
                logger.debug(f"Empty response for [{role.value}] - continuing (allow_empty=True)")
                return result or "", tokens_used
            
            logger.error(f"ERROR - Ответ 0 [{role.value}]: LLM returned empty response (retry {retry_count + 1}/2)")
            if retry_count < 2:  # Max 2 retries
                # Smart retry: modify parameters
                enhanced_temp = temp * (0.5 ** (retry_count + 1))  # Lower temp
                enhanced_system = system_prompt + "\nIMPORTANT: If you cannot translate, return the original text unchanged."
                
                # For JSON mode, add specific fallback instruction
                retry_json_mode = json_mode
                if json_mode:
                    enhanced_system += '\nIf no translation, return: {"translation": "ORIGINAL_TEXT"}'
                
                # FIX #3: On the final retry (retry_count >= 1), disable JSON mode and thinking
                # to maximize chance of getting ANY response content.
                if retry_count >= 1:
                    retry_json_mode = False
                    logger.debug(f"Final retry [{role.value}]: JSON mode DISABLED for max compatibility")
                
                logger.debug(f"Smart retry {retry_count + 1}: temp={enhanced_temp:.4f}, enhanced_prompt=True, json_mode={retry_json_mode}")
                
                # Small delay before retry
                time.sleep(0.5)
                retry_result, retry_tokens = self.complete(
                    role=role,
                    system_prompt=enhanced_system,  # Use enhanced system prompt
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                    json_mode=retry_json_mode,
                    stage=stage,
                    retry_count=retry_count + 1,
                    track_tokens=track_tokens,
                    allow_empty=allow_empty,
                    temperature=enhanced_temp  # Pass modified temperature
                )
                
                # Add retry tokens to metrics
                if retry_tokens > 0:
                    metrics.log_retry(retry_tokens, f"Empty response retry [{role.value}]")
                return retry_result, retry_tokens
            else:
                logger.error(f"Max retries exceeded for [{role.value}], returning empty result")
        
        return result, tokens_used


# Global LLM service instance (for pipeline - returns tuple)
llm_service = LLMService()


class TranslationPipeline:
    """Main translation pipeline implementing dual-LLM workflow."""
    
    def __init__(self):
        # Prompts are loaded from prompts.json via config.get_prompt()
        pass
    
    @log_entry
    def initial_translation(self, context: TranslationContext) -> TranslationResult:
        """Stage 1: Primary LLM translation."""
        # Replace dictionary words in source_text BEFORE translation
        # This ensures LLM sees translated terms in context
        # Stages 2-4 will see original source_text (no substitution) for quality verification
        if context.vocab_dict:
            context = dataclasses.replace(
                context,
                source_text=replace_vocab_in_text(
                    context.source_text,
                    context.vocab_dict,
                    context.source_lang
                )
            )
        
        # Handle empty or very short input
        if not context.source_text or len(context.source_text.strip()) < 2:
            return TranslationResult(
                stage=TranslationStage.INITIAL,
                llm_role=LLMRole.PRIMARY,
                text="",
                metadata={"prompt_style": context.style, "skipped": "empty_input"}
            )
        
        # JSON mode: prepare structured JSON input
        json_mode = config.json_mode
        if json_mode:
            json_input = json.dumps({
                "source": context.source_text,
                "source_lang": context.source_lang,
                "target_lang": context.target_lang,
                "country": context.country,
                "vocabulary": context.vocab_dict or {},
                "synopsis": context.outline_text or ""
            }, ensure_ascii=False)
            
            prompt_style = "json"
        else:
            json_input = None
            prompt_style = context.style
        
        if prompt_style == "json":
            user_prompt = config.get_prompt(
                "initial_translation_json", "user_text",
                json_input=json_input
            )
            system_prompt = config.get_prompt("initial_translation_json", "system")
        elif context.style == "xml":
            # Format vocab for prompt: prefer vocab_entries, fallback to vocab_dict
            vocab_str = _format_vocab_for_prompt(
                vocab_dict=context.vocab_dict,
                vocab_entries=context.vocab_entries,
                model=config.model_translate
            )
            user_prompt = config.get_prompt(
                "initial_translation", "user_xml",
                source_lang=context.source_lang,
                target_lang=context.target_lang,
                outline_text=context.outline_text,
                vocab_dict=vocab_str,
                source_text=context.source_text
            )
        elif config.model_translate == "Hunyuan":
            # Format vocab for prompt: prefer vocab_entries, fallback to vocab_dict
            vocab_str = _format_vocab_for_prompt(
                vocab_dict=context.vocab_dict,
                vocab_entries=context.vocab_entries,
                model=config.model_translate
            )
            user_prompt = config.get_prompt(
                "initial_translation", "user_hunyuan",
                source_lang=context.source_lang,
                target_lang=context.target_lang,
                outline_text=context.outline_text,
                vocab_dict=vocab_str,
                source_text=context.source_text
            )
        else:
            # Format vocab for prompt: prefer vocab_entries, fallback to vocab_dict
            vocab_str = _format_vocab_for_prompt(
                vocab_dict=context.vocab_dict,
                vocab_entries=context.vocab_entries,
                model=config.model_translate
            )
            user_prompt = config.get_prompt(
                "initial_translation", "user_text",
                source_lang=context.source_lang,
                target_lang=context.target_lang,
                outline_text=context.outline_text,
                vocab_dict=vocab_str,
                source_text=context.source_text
            )
        
        # Use initial_translation_json category when json_mode is enabled
        prompt_category = "initial_translation_json" if json_mode else "initial_translation"
        system_prompt = config.get_prompt(prompt_category, "system")
        
        text, tokens_used = llm_service.complete(
            role=LLMRole.PRIMARY,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=MAX_TOKENS_PER_CHUNK,
            stage=TranslationStage.INITIAL,  # Stage-specific temperature
            json_mode=json_mode
        )
        
        text = remove_tags_with_check(text, "initial_translation", LLMRole.PRIMARY)
        
        # Retry if text became empty after remove_tags
        if not text or len(text.strip()) == 0:
            logger.error(f"Text became empty after remove_tags, retrying...")
            retry_text, retry_tokens = llm_service.complete(
                role=LLMRole.PRIMARY,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=MAX_TOKENS_PER_CHUNK,
                stage=TranslationStage.INITIAL
            )
            text = remove_tags_with_check(retry_text, "initial_translation_retry", LLMRole.PRIMARY)
            tokens_used += retry_tokens
            if retry_tokens > 0:
                metrics.log_retry(retry_tokens, "Empty after remove_tags retry [initial]")
        
        # Check if translation is in correct language (detect if LLM returned source language)
        if _detect_language_mismatch(text, context.target_lang, context.source_text):
            logger.error("Translation returned in wrong language! Retrying...")
            # Retry once with stronger instruction
            user_prompt = f"TRANSLATE to {context.target_lang} ONLY. DO NOT output English/source text.\n\n{user_prompt}"
            retry_text, retry_tokens = llm_service.complete(
                role=LLMRole.PRIMARY,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=MAX_TOKENS_PER_CHUNK,
                stage=TranslationStage.INITIAL
            )
            text = remove_tags_with_check(retry_text, "initial_translation_retry", LLMRole.PRIMARY)
            tokens_used += retry_tokens
            metrics.log_language_mismatch(retry_tokens)
        
        return TranslationResult(
            stage=TranslationStage.INITIAL,
            llm_role=LLMRole.PRIMARY,
            text=text,
            metadata={"prompt_style": context.style},
            tokens_used=tokens_used
        )
    
    @log_entry
    def generate_synopsis(self, context: TranslationContext, translation: str) -> TranslationResult:
        """Stage 5: Generate synopsis from FINAL translation using Secondary LLM.
        
        If translation is too short (< 200 chars), skip LLM call and return empty synopsis.
        """
        # Skip synopsis generation for short translations
        MIN_SYNOPSIS_LENGTH = 200
        if len(translation) < MIN_SYNOPSIS_LENGTH:
            logger.debug(f"[synopsis] Skipping: translation too short ({len(translation)} < {MIN_SYNOPSIS_LENGTH} chars)")
            return TranslationResult(
                stage=TranslationStage.SYNOPSIS,
                llm_role=LLMRole.SECONDARY,
                text="",
                tokens_used=0
            )
        
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
        
        text, tokens_used = llm_service.complete(
            role=LLMRole.SECONDARY,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=MAX_TOKENS_PER_CHUNK,
            stage=TranslationStage.SYNOPSIS,
            allow_empty=True  # Synopsis can be empty - no retry needed
        )
        
        text = remove_tags_with_check(text, "generate_synopsis", LLMRole.SECONDARY)
        
        # Synopsis can be empty - pipeline continues without it
        if not text or len(text.strip()) == 0:
            logger.warning(f"WARNING [synopsis]: Empty synopsis returned, continuing without synopsis")
            text = ""
        
        return TranslationResult(
            stage=TranslationStage.SYNOPSIS,
            llm_role=LLMRole.SECONDARY,
            text=text,
            tokens_used=tokens_used
        )
    
    @log_entry
    def reflection(self, context: TranslationContext, translation: str) -> TranslationResult:
        """
        Stage 2: Secondary LLM reflection.
        Returns ONLY numbered suggestions/improvements (not translation).
        
        Note: Uses vocab_dict to verify terminology consistency.
        """
        # JSON mode: prepare structured JSON input
        json_mode = config.json_mode
        if json_mode:
            json_input = json.dumps({
                "source": context.source_text,
                "translation": translation,
                "source_lang": context.source_lang,
                "target_lang": context.target_lang,
                "country": context.country,
                "vocabulary": context.vocab_dict or {}
            }, ensure_ascii=False)
            
            user_prompt = config.get_prompt(
                "reflection_json", "user_text",
                json_input=json_input
            )
            system_prompt = config.get_prompt("reflection_json", "system",
                target_lang=context.target_lang,
                country=context.country
            )
        else:
            # Format vocab for prompt: prefer vocab_entries, fallback to vocab_dict
            vocab_str = _format_vocab_for_prompt(
                vocab_dict=context.vocab_dict,
                vocab_entries=context.vocab_entries,
                model=config.model_translate
            )
            user_prompt = config.get_prompt(
                "reflection", f"user_{context.style}",
                source_lang=context.source_lang,
                target_lang=context.target_lang,
                source_text=context.source_text,
                translation=translation,
                country=context.country,
                vocab_dict=vocab_str
            )
            system_prompt = config.get_prompt("reflection", "system",
                target_lang=context.target_lang,
                country=context.country
            )
        
        text, tokens_used = llm_service.complete(
            role=LLMRole.SECONDARY,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=MAX_TOKENS_PER_CHUNK,
            stage=TranslationStage.REFLECTION,
            json_mode=json_mode
        )
        
        return TranslationResult(
            stage=TranslationStage.REFLECTION,
            llm_role=LLMRole.SECONDARY,
            text=text,
            metadata={"stage": "reflection", "output_type": "suggestions_only", "vocabulary_checked": True},
            tokens_used=tokens_used
        )
    
    @log_entry
    def improve_translation(self, context: TranslationContext, translation: str, reflection: str) -> TranslationResult:
        """Stage 3: Apply reflection suggestions to improve translation."""
        # JSON mode: prepare structured JSON input
        json_mode = config.json_mode
        if json_mode:
            # Convert reflection to list if it's a string
            suggestions = reflection.split('\n') if isinstance(reflection, str) else reflection
            json_input = json.dumps({
                "translation": translation,
                "suggestions": suggestions,
                "target_lang": context.target_lang,
                "country": context.country,
                "vocabulary": context.vocab_dict or {}
            }, ensure_ascii=False)
            
            user_prompt = config.get_prompt(
                "improve_json", "user_text",
                json_input=json_input
            )
            system_prompt = config.get_prompt("improve_json", "system",
                target_lang=context.target_lang,
                country=context.country
            )
        else:
            # Format vocab for prompt: prefer vocab_entries, fallback to vocab_dict
            vocab_str = _format_vocab_for_prompt(
                vocab_dict=context.vocab_dict,
                vocab_entries=context.vocab_entries,
                model=config.model_translate
            )
            user_prompt = config.get_prompt(
                "improve", f"user_{context.style}",
                target_lang=context.target_lang,
                country=context.country,
                translation=translation,
                reflection=reflection,
                vocab_dict=vocab_str
            )
            system_prompt = config.get_prompt("improve", "system",
                target_lang=context.target_lang,
                country=context.country
            )
        
        text, tokens_used = llm_service.complete(
            role=LLMRole.SECONDARY,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=MAX_TOKENS_PER_CHUNK,
            stage=TranslationStage.IMPROVE,
            json_mode=json_mode
        )
        
        text = remove_tags_with_check(text, "improve_translation", LLMRole.SECONDARY)
        
        # Retry if text became empty after remove_tags
        if (not text or len(text.strip()) == 0) and tokens_used > 0:
            logger.error(f"Text became empty after remove_tags (used {tokens_used} tokens), retrying...")
            retry_text, retry_tokens = llm_service.complete(
                role=LLMRole.SECONDARY,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=MAX_TOKENS_PER_CHUNK,
                stage=TranslationStage.IMPROVE
            )
            text = remove_tags_with_check(retry_text, "improve_translation_retry", LLMRole.SECONDARY)
            tokens_used += retry_tokens
            if retry_tokens > 0:
                metrics.log_retry(retry_tokens, "Empty after remove_tags retry [improve]")
        
        return TranslationResult(
            stage=TranslationStage.IMPROVE,
            llm_role=LLMRole.SECONDARY,
            text=text,
            tokens_used=tokens_used
        )
    
    @log_entry
    def final_edit(self, context: TranslationContext, translation: str) -> TranslationResult:
        """
        Stage 4: Final editing/proofreading - fix grammar, style, XML tags.
        Receives ONLY the improved translation (no original/vocabulary).
        """
        # JSON mode: prepare structured JSON input
        json_mode = config.json_mode
        if json_mode:
            json_input = json.dumps({
                "translation": translation,
                "target_lang": context.target_lang,
                "country": context.country
            }, ensure_ascii=False)
            
            user_prompt = config.get_prompt(
                "editor_json", "user_text",
                json_input=json_input
            )
            system_prompt = config.get_prompt("editor_json", "system",
                target_lang=context.target_lang,
                country=context.country
            )
        else:
            user_prompt = config.get_prompt(
                "editor", f"user_{context.style}",
                target_lang=context.target_lang,
                country=context.country,
                translation=translation
            )
            system_prompt = config.get_prompt("editor", "system",
                target_lang=context.target_lang,
                country=context.country
            )
        
        text, tokens_used = llm_service.complete(
            role=LLMRole.SECONDARY,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=MAX_TOKENS_PER_CHUNK,
            stage=TranslationStage.FINAL,
            json_mode=json_mode
        )
        
        text = remove_tags_with_check(text, "final_edit", LLMRole.SECONDARY)
        
        # NEW: Post-process <p> tags (validate balance or auto-structure)
        text = post_process_p_tags(text)
        
        # Retry if text became empty after remove_tags
        if (not text or len(text.strip()) == 0) and tokens_used > 0:
            logger.error(f"Text became empty after remove_tags (used {tokens_used} tokens), retrying...")
            retry_text, retry_tokens = llm_service.complete(
                role=LLMRole.SECONDARY,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=MAX_TOKENS_PER_CHUNK,
                stage=TranslationStage.FINAL
            )
            text = remove_tags_with_check(retry_text, "final_edit_retry", LLMRole.SECONDARY)
            tokens_used += retry_tokens
            if retry_tokens > 0:
                metrics.log_retry(retry_tokens, "Empty after remove_tags retry [final]")
        
        return TranslationResult(
            stage=TranslationStage.FINAL,
            llm_role=LLMRole.SECONDARY,
            text=text,
            metadata={"stage": "final_edit", "compared_with_original": True, "vocabulary_used": True},
            tokens_used=tokens_used
        )
    
    def execute(self, source_lang: str, target_lang: str, source_text: str,
                outline_text: str, vocab_dict: dict, vocab_entries: list = None,
                country: str = "", style: str = "text", fast_mode: bool = False) -> PipelineState:
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
            vocab_entries=vocab_entries or [],
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
            synopsis_result = self.generate_synopsis(context, initial_result.text)
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

MIN_CHUNK_SIZE = 2000  # Minimum chunk size for rechunking
MAX_DEPTH = 3  # Maximum recursion depth
MAX_LLM_CALLS_PER_CHUNK = 15  # Cap total LLM calls per chunk (prevents exponential blowup)


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
    
    if should_split:
        logger.error(f"⚠ SPLIT [{stage_name}] {source_len} → {target_len} chars ({percent_diff:.1f}%) - rechunking needed")
    elif config.debug:
        logger.debug(f"[{stage_name}] {source_len} → {target_len} chars ({percent_diff:.1f}%) ✓ OK")
    
    return not should_split, percent_diff, should_split


def translate_chunk(source_lang: str, target_lang: str, source_text: str,
                    outline_text: str, vocab_dict: dict, vocab_entries: list = None,
                    country: str = "", style: str = "text", fast_mode: bool = False,
                    depth: int = 0, _llm_call_count: list = None) -> tuple:
    """
    Translate a single chunk using the dual-LLM pipeline.
    
    Includes automatic rechunking if length validation fails.
    
    Args:
        source_lang: Source language
        target_lang: Target language
        source_text: Text to translate
        outline_text: Context synopsis from previous chunks
        vocab_dict: Translation dictionary
        vocab_entries: Full VocabEntry objects for rich formatting (optional)
        country: Target country for cultural context
        style: "xml" or "text"
        fast_mode: Skip reflection/improve stages
        depth: Current recursion depth (for rechunking)
    
    Returns:
        Tuple of (final_translation, synopsis)
    """
    # Initialize LLM call counter (mutable list to share across recursive calls)
    if _llm_call_count is None:
        _llm_call_count = [0]
    _llm_call_count[0] += 1  # Count this invocation
    
    # Debug: Log vocabulary status
    if config.debug:
        vocab_count = len(vocab_dict) if vocab_dict else 0
        entries_count = len(vocab_entries) if vocab_entries else 0
        logger.debug(f"translate_chunk: vocab_dict={vocab_count} terms, vocab_entries={entries_count}, outline_len={len(outline_text) if outline_text else 0}")
    
    # Execute pipeline
    state = _pipeline.execute(
        source_lang=source_lang,
        target_lang=target_lang,
        source_text=source_text,
        outline_text=outline_text,
        vocab_dict=vocab_dict,
        vocab_entries=vocab_entries,
        country=country,
        style=style,
        fast_mode=fast_mode
    )
    
    # Validate final translation length
    is_valid, percent_diff, should_split = validate_translation_length(
        source_text, state.final_translation, "FINAL"
    )
    
    # Check for empty translation (indicates LLM failure)
    if not state.final_translation or len(state.final_translation.strip()) == 0:
        metrics.log_failure("Empty translation from LLM")
        logger.error(f"EMPTY TRANSLATION at depth {depth}: LLM returned empty result")
        # Don't rechunk - retry with same chunk
        if depth < MAX_DEPTH and _llm_call_count[0] < MAX_LLM_CALLS_PER_CHUNK:
            logger.error(f"Retrying translation at depth {depth}...")
            return translate_chunk(
                source_lang, target_lang, source_text, outline_text,
                vocab_dict, vocab_entries, country, style, fast_mode, depth + 1,
                _llm_call_count=_llm_call_count
            )
        if _llm_call_count[0] >= MAX_LLM_CALLS_PER_CHUNK:
            logger.warning(f"LLM call cap ({MAX_LLM_CALLS_PER_CHUNK}) reached, stopping recursion")
        return "", ""
    
    # Rechunking if needed (ERROR logging)
    if should_split and depth < MAX_DEPTH:
        if _llm_call_count[0] >= MAX_LLM_CALLS_PER_CHUNK:
            logger.warning(f"LLM call cap ({MAX_LLM_CALLS_PER_CHUNK}) reached before split, stopping recursion")
            return state.final_translation, state.synopsis
        metrics.log_rechunk(depth, percent_diff)  # ERROR level
        
        # Split source text
        part1, part2 = split_text_smartly(source_text)
        
        # Translate parts recursively
        result1, syn1 = translate_chunk(
            source_lang, target_lang, part1, outline_text,
            vocab_dict, vocab_entries, country, style, fast_mode, depth + 1,
            _llm_call_count=_llm_call_count
        )
        result2, syn2 = translate_chunk(
            source_lang, target_lang, part2, outline_text,
            vocab_dict, vocab_entries, country, style, fast_mode, depth + 1,
            _llm_call_count=_llm_call_count
        )
        
        # Combine results
        combined_translation = (result1 or "") + "\n\n" + (result2 or "")
        combined_synopsis = (syn1 or "") + " " + (syn2 or "")
        
        return combined_translation, combined_synopsis
    
    # Success - log tokens
    tokens = state.final_result.tokens_used if hasattr(state, 'final_result') and hasattr(state.final_result, 'tokens_used') else 0
    metrics.log_success(tokens)  # INFO level
    
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
            Generated text from LLM (tokens_used discarded for compatibility)
        """
        text, _ = self._new_service.complete(
            role=role,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            json_mode=json_mode,
            stage=stage,  # Pass stage for temperature selection
            track_tokens=False  # Don't track tokens for compatibility layer
        )
        return text
    
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
        
        # Get completion (discard tokens for compatibility)
        # Pass force_json_mode to override config disable_json flags
        text, _ = self._new_service.complete(
            role=llm_role,
            system_prompt="",  # Prompts are self-contained
            user_prompt=user_prompt,
            max_tokens=max_tokens or MAX_TOKENS_PER_CHUNK,
            json_mode=json_mode,
            stage=stage,  # Pass stage for temperature selection
            track_tokens=False,
            force_json_mode=kwargs.get('force_json_mode', False),
            reasoning_budget=kwargs.get('reasoning_budget', None),
            chat_template_kwargs=kwargs.get('chat_template_kwargs', None)
        )
        return text


# Compatibility layer for legacy code
llm_service_compat = LLMServiceCompat()


# =============================================================================
# JSON Parsing Functions
# =============================================================================

def _strip_markdown_fences(text: str) -> str:
    """
    Remove markdown code fences (```json ... ``` or ``` ... ```).
    LLMs often wrap JSON in code fences even when asked not to.
    """
    if not text:
        return text
    # Match ```json\n...\n``` or ```\n...\n```
    stripped = re.sub(r'```(?:json)?\s*\n([\s\S]*?)\n```', r'\1', text)
    return stripped


def _extract_json_brace(text: str) -> str:
    """
    Extract a complete JSON object by counting braces.
    More robust than simple regex — handles nested objects, arrays, escaped quotes.
    Returns the first complete JSON string found, or empty string.
    """
    if not text:
        return ""
    
    start = text.find('{')
    if start == -1:
        return ""
    
    depth = 0
    in_string = False
    escape_next = False
    
    for i in range(start, len(text)):
        ch = text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if ch == '\\':
            if in_string:
                escape_next = True
            continue
        
        if ch == '"':
            in_string = not in_string
            continue
        
        if in_string:
            continue
        
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    
    return ""


def parse_json_response(text: str) -> tuple:
    """
    Parse JSON response from LLM.
    Returns: (result: str or list, success: bool)
    
    Priority:
    1. Strip markdown fences, find complete JSON by brace counting
    2. Extract translation or suggestions
    3. Fallback to non-JSON if invalid
    """
    if not text:
        return "", False
    
    # Strip markdown code fences first
    cleaned = _strip_markdown_fences(text)
    
    # Extract JSON by brace counting (handles nested structures)
    json_str = _extract_json_brace(cleaned)
    if not json_str:
        return text.strip(), False  # No JSON found, return as-is
    
    try:
        data = json.loads(json_str)
        
        # Check for translation (INITIAL, IMPROVE, EDITOR stages)
        if 'translation' in data:
            return data['translation'].strip(), True
        
        # Check for suggestions (REFLECTION stage)
        if 'suggestions' in data:
            suggestions = data['suggestions']
            if isinstance(suggestions, list):
                return suggestions, True
            elif isinstance(suggestions, str) and suggestions.strip():
                return suggestions.strip(), True
        
        # JSON found but no valid content
        logger.debug(f"JSON parsed but no valid 'translation' or 'suggestions' key")
        return text.strip(), False
        
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.debug(f"Failed to parse JSON: {e}")
        return text.strip(), False


# =============================================================================
# Core Functions (used by app.py)
# =============================================================================

@log_entry
def remove_tags(text: str) -> str:
    """
    Extract translation from wrapper tags. Minimal cleanup.
    
    Priority:
    1. JSON: {"translation": "..."}
    2. <ttext>...</ttext>
    3. <translated>...</translated>
    4. <TRANSLATION>...</TRANSLATION>
    5. Fallback: return entire text (no cleanup)
    
    This conservative approach prevents false positives where valid translation
    content was being removed by aggressive cleanup patterns.
    
    Args:
        text: Raw LLM response (may contain wrapper tags)
        
    Returns:
        Extracted translation or full text if no wrapper found
    """
    if not text:
        return ""
    
    # STEP 1: Try to extract from JSON format (PREFERRED)
    # Use brace-counting extraction to handle escaped quotes and multi-line JSON
    json_str = _extract_json_brace(text)
    if json_str:
        try:
            data = json.loads(json_str)
            if 'translation' in data and data['translation']:
                logger.debug("Extracted translation from JSON format (robust parser)")
                return data['translation'].strip()
        except json.JSONDecodeError:
            pass  # Fall through to regex fallback
    
    # Regex fallback for simple JSON cases
    json_match = re.search(r'\{[\s]*["\']translation["\'][\s]*:[\s]*["\']([\s\S]*?)["\'][\s]*\}', text)
    if json_match:
        logger.debug("Extracted translation from JSON format (regex fallback)")
        return json_match.group(1).strip()
    
    # STEP 2: Try wrapper tags in priority order
    # These are the tags we explicitly ask LLM to use in prompts
    wrapper_tags = [
        'ttext',           # Primary wrapper tag (used in most prompts)
        'translated',      # Alternative wrapper
        'TRANSLATION',     # Fallback wrapper
        'TRANS',           # Short form
        'target',          # From older prompts
        'IMPROVED_TRANSLATION',  # From reflection pipeline
        'source'           # From initial_translation prompt (contains lang attribute)
    ]
    
    for tag in wrapper_tags:
        match = re.search(rf'<{tag}[^>]*>([\s\S]*?)</{tag}>', text, re.IGNORECASE)
        if match and match.group(1).strip():
            logger.debug(f"Extracted content from <{tag}> wrapper")
            return match.group(1).strip()
    
    # STEP 3: Fallback — return entire text without any cleanup
    # This prevents losing valid translation when LLM doesn't use wrapper tags
    logger.debug("No wrapper tags found, returning full text")
    return text.strip()


def remove_tags_with_check(text: str, stage_name: str = "", role: LLMRole = None) -> str:
    """
    Remove tags and check for empty result. Log ERROR if result is empty.
    
    Priority:
    1. JSON parsing (new - for JSON_MODE)
    2. XML tag extraction (existing)
    3. Fallback to original text
    
    Args:
        text: Raw LLM response
        stage_name: Name of pipeline stage for logging
        role: LLM role for context
        
    Returns:
        Cleaned text, or original text if cleanup failed
    """
    if not text:
        logger.error(f"ERROR - Ответ 0 [{stage_name}]: LLM returned None/empty before remove_tags")
        return ""
    
    original_len = len(text)
    
    # PRIORITY 1: Try JSON parsing first (JSON_MODE)
    parsed, is_json = parse_json_response(text)
    if is_json and parsed:
        # Handle list (suggestions from reflection) vs string (translation)
        if isinstance(parsed, list):
            logger.debug(f"Extracted {len(parsed)} suggestions from JSON [{stage_name}]")
            return '\n'.join(str(s) for s in parsed) if parsed else ""
        else:
            logger.debug(f"Extracted translation from JSON [{stage_name}]")
            return parsed
    
    # PRIORITY 2: Fall back to XML tag extraction
    cleaned = remove_tags(text)
    cleaned_len = len(cleaned)
    
    # Check if result became empty after cleanup
    if original_len > 0 and cleaned_len == 0:
        role_str = role.value if role else "unknown"
        logger.warning(f"⚠️ FALLBACK [{stage_name}/{role_str}]: {original_len} chars → 0 chars after remove_tags, using original text")
        # Log the original content for debugging
        preview = text[:500].replace('\n', ' ').replace('\r', ' ')
        logger.debug(f"DEBUG - Content that became empty [{stage_name}]: {preview}")
        if len(text) > 500:
            logger.debug(f"DEBUG - ... (truncated, total {original_len} chars)")
        
        # FALLBACK: Return original text instead of empty string
        # This prevents losing valid translations when remove_tags fails to extract
        return text.strip()
    
    return cleaned


def _detect_language_mismatch(text: str, expected_lang: str, source_text: str) -> bool:
    """
    Detect if translation is in wrong language (e.g., English instead of Russian).
    
    Args:
        text: Translated text to check
        expected_lang: Expected target language (e.g., 'russian', 'ru')
        source_text: Original source text
        
    Returns:
        True if language mismatch detected
    """
    if not text or not source_text:
        return False
    
    # Common Russian characters that shouldn't be in English
    russian_chars = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ')
    
    # Common English characters
    english_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
    
    # Count characters
    text_chars = set(text)
    
    # If expected Russian but no Cyrillic characters
    if 'ru' in expected_lang.lower() or 'russian' in expected_lang.lower():
        has_cyrillic = bool(text_chars & russian_chars)
        has_english = bool(text_chars & english_chars)
        
        # If text is mostly English (no Cyrillic), it's likely not translated
        if not has_cyrillic and has_english:
            # Check if text is similar to source (not translated)
            if len(text) > 50 and len(source_text) > 50:
                # Simple similarity check
                text_words = set(text.lower().split())
                source_words = set(source_text.lower().split())
                overlap = len(text_words & source_words) / min(len(text_words), len(source_words))
                
                if overlap > 0.5:  # More than 50% word overlap
                    logger.warning(f"Language mismatch detected: expected {expected_lang}, got English. Overlap: {overlap:.1%}")
                    return True
    
    return False


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
    
    # Translate a single chunk (chunking is done by the caller)
    max_tokens = 32512  # Always use 32K tokens for vocabulary
    
    result = llm_service_compat.get_completion(
        role=role,
        prompt_category="vocabulary",
        prompt_key=prompt_key,
        source_lang=source_lang,
        target_lang=target_lang,
        country=country,
        source_text=source_text,
        max_tokens=max_tokens,
        json_mode=True,
        force_json_mode=True
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
        
        response = llm_service_compat.get_completion(
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


# =============================================================================
# Translation Report
# =============================================================================

def print_translation_report():
    """Print translation metrics summary at end of translation."""
    metrics.print_report()


# =============================================================================
# Unit Tests for replace_vocab_in_text
# =============================================================================

if __name__ == "__main__":
    import sys
    
    def test_replace_vocab_in_text():
        """Test the replace_vocab_in_text function."""
        
        # Test 1: Basic word replacement
        vocab = {"hello": "привет", "world": "мир"}
        result = replace_vocab_in_text("hello world", vocab)
        assert result == "привет мир", f"Test 1 failed: {result}"
        print("✓ Test 1: Basic word replacement")
        
        # Test 2: Partial word should NOT be replaced
        vocab = {"cat": "кошка"}
        result = replace_vocab_in_text("catastrophe", vocab)
        assert result == "catastrophe", f"Test 2 failed: {result}"
        print("✓ Test 2: Partial word NOT replaced")
        
        # Test 3: Multiple occurrences
        vocab = {"dragon": "дракон"}
        result = replace_vocab_in_text("the dragon saw another dragon", vocab)
        assert result == "the дракон saw another дракон", f"Test 3 failed: {result}"
        print("✓ Test 3: Multiple occurrences")
        
        # Test 4: Longer match takes priority (avoids partial matches)
        vocab = {"catastrophe": "катастрофа", "cat": "кошка"}
        result = replace_vocab_in_text("catastrophe has cat", vocab)
        # Longest match takes priority - cat in catastrophe should NOT be replaced
        assert result == "катастрофа has кошка", f"Test 4 failed: {result}"
        print("✓ Test 4: Longer match priority (avoids partial matches)")
        
        # Test 5: Empty vocab
        result = replace_vocab_in_text("hello world", {})
        assert result == "hello world", f"Test 5 failed: {result}"
        print("✓ Test 5: Empty vocab returns original")
        
        # Test 6: Empty text
        result = replace_vocab_in_text("", {"hello": "привет"})
        assert result == "", f"Test 6 failed: {result}"
        print("✓ Test 6: Empty text returns empty")
        
        # Test 7: Example from spec
        vocab = {"everytime": "everytime", "dragon": "драккар"}
        result = replace_vocab_in_text("everytime dragon fly", vocab)
        assert result == "everytime драккар fly", f"Test 7 failed: {result}"
        print("✓ Test 7: Spec example")
        
        # Test 8: Special regex characters in vocab (escaped via re.escape)
        vocab = {"it's": "это", "don't": "не"}
        result = replace_vocab_in_text("it's a test don't worry", vocab)
        assert result == "это a test не worry", f"Test 8 failed: {result}"
        print("✓ Test 8: Special regex characters escaped")
        
        # Test 9: None vocab returns original
        result = replace_vocab_in_text("hello", None)
        assert result == "hello", f"Test 9 failed: {result}"
        print("✓ Test 9: None vocab returns original")
        
        print("\n✅ All tests passed!")
        sys.exit(0)
    
    test_replace_vocab_in_text()