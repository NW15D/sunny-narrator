"""
Dual-LLM Translation Pipeline

Architecture:
- Primary LLM (Hunyuan): Handles translation, dictionary usage, synopsis generation
- Secondary LLM (Instruction-based): Handles quality control, style preservation, consistency

Workflow:
1. PRIMARY: Initial translation with vocabulary and synopsis
2. SECONDARY: Quality check (accuracy, terminology, grammar, style)
3. SECONDARY: Style editing (apply fixes, preserve obscene language, cultural nuances)
"""

import logging
import functools
import time
from typing import Optional, Callable
import re

from src.config import Config
from src.schemas.translation import (
    TranslationStage, LLMRole, TranslationContext, 
    TranslationResult, PipelineState,
    QualityCheckPrompt, StyleEditorPrompt
)

config = Config()
logger = logging.getLogger(__name__)


def log_stage(func):
    """Decorator to log pipeline stage execution."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        stage_name = func.__name__
        logger.info(f"→ [{stage_name}] Starting")
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"← [{stage_name}] Completed in {elapsed:.2f}s")
        return result
    return wrapper


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
    
    def complete(
        self,
        role: LLMRole,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 8192,
        json_mode: bool = False
    ) -> str:
        """Execute LLM completion with role-appropriate client."""
        client, model, temp = self.get_client(role)
        
        messages = []
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
            logger.debug(f"LLM Request [{role.value}]: {model}, {len(user_prompt)} chars")
        
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
        self.quality_prompt = QualityCheckPrompt()
        self.style_prompt = StyleEditorPrompt()
    
    @log_stage
    def initial_translation(
        self,
        context: TranslationContext
    ) -> TranslationResult:
        """
        Stage 1: Primary LLM translation.
        Uses Hunyuan for translation with vocabulary and synopsis.
        """
        # Build prompt based on style
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
            max_tokens=config.max_len_chunk * 4
        )
        
        # Clean up tags
        text = self._remove_tags(text)
        
        return TranslationResult(
            stage=TranslationStage.INITIAL,
            llm_role=LLMRole.PRIMARY,
            text=text,
            metadata={"prompt_style": context.style}
        )
    
    @log_stage
    def generate_synopsis(
        self,
        context: TranslationContext,
        translation: str
    ) -> TranslationResult:
        """
        Generate synopsis using Primary LLM.
        """
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
            max_tokens=160
        )
        
        text = self._remove_tags(text)
        
        return TranslationResult(
            stage=TranslationStage.SYNOPSIS,
            llm_role=LLMRole.PRIMARY,
            text=text
        )
    
    @log_stage
    def quality_check(
        self,
        context: TranslationContext,
        translation: str
    ) -> TranslationResult:
        """
        Stage 2: Secondary LLM quality control.
        Checks accuracy, terminology, grammar, style.
        """
        user_prompt = self.quality_prompt.user_template.format(
            source_lang=context.source_lang,
            target_lang=context.target_lang,
            source_text=context.source_text,
            translation=translation,
            vocab_dict=context.vocab_dict
        )
        
        text = llm_service.complete(
            role=LLMRole.SECONDARY,
            system_prompt=self.quality_prompt.system,
            user_prompt=user_prompt,
            max_tokens=config.max_len_chunk
        )
        
        return TranslationResult(
            stage=TranslationStage.QUALITY_CHECK,
            llm_role=LLMRole.SECONDARY,
            text=text
        )
    
    @log_stage
    def style_edit(
        self,
        context: TranslationContext,
        translation: str,
        quality_report: str
    ) -> TranslationResult:
        """
        Stage 3: Secondary LLM style editing.
        Applies quality feedback, preserves style and obscene language.
        """
        user_prompt = self.style_prompt.user_template.format(
            source_lang=context.source_lang,
            target_lang=context.target_lang,
            country=context.country,
            source_text=context.source_text,
            translation=translation,
            quality_report=quality_report,
            vocab_dict=context.vocab_dict
        )
        
        text = llm_service.complete(
            role=LLMRole.SECONDARY,
            system_prompt=self.style_prompt.system,
            user_prompt=user_prompt,
            max_tokens=config.max_len_chunk * 4
        )
        
        text = self._remove_tags(text)
        
        return TranslationResult(
            stage=TranslationStage.STYLE_EDIT,
            llm_role=LLMRole.SECONDARY,
            text=text
        )
    
    def _remove_tags(self, text: str) -> str:
        """Remove XML/HTML tags and artifacts."""
        patterns = [
            r'<SOURCE_TEXT>[\s\S]*?</SOURCE_TEXT>',
            r'<DICTIONARY>[\s\S]*?</DICTIONARY>',
            r'<EXPERT_SUGGESTIONS>[\s\S]*?</EXPERT_SUGGESTIONS>',
            r'<SYNOPSIS>[\s\S]*?</SYNOPSIS>',
            r'\<\|channel\|\>[\s\S]*?\<\|end\|\>',
            r'```xml', r'```',
            r'</?(?:INITIAL_TRANSLATION|FIRST_TRANSLATION|TRANSLATION|SOURCE|section|IMPROVED_TRANSLATION|target|TTEXT|SYNOPSIS|TRANS)>',
            r'<\|im_end\|>', r'<\|file_separator\|>'
        ]
        
        for pattern in patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.VERBOSE)
        
        return text.strip()
    
    def execute(
        self,
        source_lang: str,
        target_lang: str,
        source_text: str,
        outline_text: str,
        vocab_dict: dict,
        country: str,
        style: str = "text",
        fast_mode: bool = False
    ) -> PipelineState:
        """
        Execute the complete translation pipeline.
        
        Args:
            source_lang: Source language
            target_lang: Target language  
            source_text: Text to translate
            outline_text: Context synopsis
            vocab_dict: Translation dictionary
            country: Target country for cultural context
            style: "xml" or "text"
            fast_mode: Skip quality/style stages if True
        
        Returns:
            PipelineState with all stage results
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
        
        # Stage 2: Synopsis (Primary LLM)
        synopsis_result = self.generate_synopsis(context, initial_result.text)
        state.add_result(synopsis_result)
        
        if fast_mode:
            # Fast path: just return initial translation
            final_result = TranslationResult(
                stage=TranslationStage.FINAL,
                llm_role=LLMRole.PRIMARY,
                text=initial_result.text
            )
            state.add_result(final_result)
        else:
            # Stage 3: Quality Check (Secondary LLM)
            quality_result = self.quality_check(context, initial_result.text)
            state.add_result(quality_result)
            
            # Stage 4: Style Edit (Secondary LLM)
            style_result = self.style_edit(
                context,
                initial_result.text,
                quality_result.text
            )
            state.add_result(style_result)
            
            # Final result
            final_result = TranslationResult(
                stage=TranslationStage.FINAL,
                llm_role=LLMRole.SECONDARY,
                text=style_result.text
            )
            state.add_result(final_result)
        
        return state


# Global pipeline instance
_pipeline = TranslationPipeline()


def translate_chunk(
    source_lang: str,
    target_lang: str,
    source_text: str,
    outline_text: str,
    vocab_dict: dict,
    country: str,
    style: str = "text",
    fast_mode: bool = False
) -> tuple[str, str]:
    """
    Translate a single chunk using the dual-LLM pipeline.
    
    Returns:
        (final_translation, synopsis)
    """
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
    
    return state.final_translation, state.synopsis
