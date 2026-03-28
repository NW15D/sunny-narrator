"""
Translation Pipeline Schema Definitions

Defines the structured workflow for dual-LLM translation architecture:
- Primary LLM (Hunyuan): Translation + Dictionary + Synopsis
- Secondary LLM (Instruction-based): Quality Control + Style Preservation
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


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


@dataclass
class ReflectionPrompt:
    """
    Combined reflection + quality check with literary focus.
    
    Merged from:
    - reflect_on_translation (literary nuances)
    - quality_check (accuracy, terminology)
    
    Output: numbered list of specific improvements.
    """
    system: str = """You are a literary translation quality reviewer for {target_lang} ({country}).

Review the translation against the source and identify:
1. Accuracy issues (meaning changes, omissions, additions)
2. Terminology inconsistencies (vocabulary usage)
3. Grammar and syntax errors
4. Nuances and natural expression (literary quality)
5. Style deviations from the original tone

Output a numbered list of specific improvements."""
    
    user_template: str = """<source lang="{source_lang}">
{source_text}
</source>

<translation lang="{target_lang}">
{translation}
</translation>

<vocabulary>
{vocab_dict}
</vocabulary>

Review the translation:
1. ACCURACY: Meaning changes or omissions
2. TERMINOLOGY: Vocabulary compliance
3. GRAMMAR: Syntax issues
4. NUANCES: Literary quality improvements
5. STYLE: Tone mismatches

Output numbered suggestions. Focus on natural {target_lang} expression for {country}."""


@dataclass
class ImprovePrompt:
    """
    Apply reflection suggestions to improve translation.
    
    Merged from:
    - improve_translation (apply reflection)
    - style_edit (preserve obscene, cultural nuances)
    
    Output: final polished translation.
    """
    system: str = """You are a literary translation editor for {target_lang} ({country}).

Your task is to apply reflection suggestions while preserving:
- Original narrative voice and tone
- Obscene/profane language (if present in source)
- Character speech patterns
- Cultural nuances appropriate for {country}

Output the improved translation."""
    
    user_template: str = """<source lang="{source_lang}">
{source_text}
</source>

<translation lang="{target_lang}">
{translation}
</translation>

<suggestions>
{reflection}
</suggestions>

<vocabulary>
{vocab_dict}
</vocabulary>

Apply ALL numbered suggestions to improve the translation:
1. Fix accuracy issues
2. Apply vocabulary terms correctly
3. Fix grammar
4. Improve literary nuances
5. Maintain style and tone
6. Preserve obscene/profane language if present in source
7. Ensure cultural appropriateness for {country}

Output the final translation wrapped in <ttext>...</ttext>."""


# Workflow definition (merged reflection approach)
TRANSLATION_WORKFLOW = [
    {
        "stage": TranslationStage.INITIAL,
        "llm_role": LLMRole.PRIMARY,
        "function": "initial_translation",
        "description": "Primary translation with dictionary and synopsis"
    },
    {
        "stage": TranslationStage.SYNOPSIS,
        "llm_role": LLMRole.PRIMARY,
        "function": "generate_synopsis",
        "description": "Summary for next chunk context"
    },
    {
        "stage": TranslationStage.REFLECTION,
        "llm_role": LLMRole.SECONDARY,
        "function": "reflection",
        "description": "Quality + nuances + suggestions (merged)"
    },
    {
        "stage": TranslationStage.IMPROVE,
        "llm_role": LLMRole.SECONDARY,
        "function": "improve_translation",
        "description": "Apply reflection suggestions + preserve style"
    },
]
