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
    QUALITY_CHECK = "quality_check"
    STYLE_EDIT = "style_edit"
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
    quality_report: Optional[str] = None
    style_corrections: Optional[str] = None
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
        elif result.stage == TranslationStage.QUALITY_CHECK:
            self.quality_report = result.text
        elif result.stage == TranslationStage.STYLE_EDIT:
            self.style_corrections = result.text
        elif result.stage == TranslationStage.FINAL:
            self.final_translation = result.text


@dataclass
class QualityCheckPrompt:
    """Prompt structure for quality control stage."""
    system: str = """You are a translation quality controller. 
Review the translation against the source text and identify:
1. Accuracy issues (meaning changes, omissions, additions)
2. Terminology inconsistencies (check against provided vocabulary)
3. Grammar and syntax errors
4. Style deviations from the original

Output a structured report with specific issues and suggestions."""
    
    user_template: str = """<source lang="{source_lang}">
{source_text}
</source>

<translation lang="{target_lang}">
{translation}
</translation>

<vocabulary>
{vocab_dict}
</vocabulary>

Provide a quality report:
1. ACCURACY: List any meaning changes or omissions
2. TERMINOLOGY: Check vocabulary usage
3. GRAMMAR: List syntax issues
4. STYLE: Note any tone mismatches

Format: Numbered list with specific examples."""


@dataclass
class StyleEditorPrompt:
    """Prompt structure for style editing stage."""
    system: str = """You are a literary style editor. 
Your task is to refine the translation while preserving:
- Original narrative voice and tone
- Obscene/profane language (if present in source)
- Character speech patterns
- Cultural nuances appropriate for {country}

Apply quality feedback and produce the final polished text."""
    
    user_template: str = """<source lang="{source_lang}">
{source_text}
</source>

<translation lang="{target_lang}">
{translation}
</translation>

<quality_feedback>
{quality_report}
</quality_feedback>

<vocabulary>
{vocab_dict}
</vocabulary>

Edit the translation:
1. Apply all quality feedback
2. Preserve obscene/profane language if present in source
3. Maintain narrative style and character voices
4. Ensure cultural appropriateness for {country}

Output the final translation wrapped in <ttext>...</ttext>."""


# Workflow definition
TRANSLATION_WORKFLOW = [
    {
        "stage": TranslationStage.INITIAL,
        "llm_role": LLMRole.PRIMARY,
        "function": "initial_translation",
        "description": "Primary translation with dictionary and synopsis"
    },
    {
        "stage": TranslationStage.QUALITY_CHECK,
        "llm_role": LLMRole.SECONDARY,
        "function": "quality_check",
        "description": "Quality control and consistency verification"
    },
    {
        "stage": TranslationStage.STYLE_EDIT,
        "llm_role": LLMRole.SECONDARY,
        "function": "style_edit",
        "description": "Style preservation and final polishing"
    },
]
