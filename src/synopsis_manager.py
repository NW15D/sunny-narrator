"""
Synopsis Manager

Manages synopsis generation and context tracking across chunks and sections.

Rules:
1. Synopsis is EMPTY for first chunk in each section
2. Synopsis is generated from FINAL TRANSLATION of previous chunks
3. Synopsis appears starting from 2nd chunk in section
4. Synopsis accumulates context (not replaces) within section
5. Synopsis resets on new section

Purpose:
- Track character gender (he/she/it)
- Maintain translation consistency
- Preserve key terminology across chunks
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field

from src.config import Config
from src.character_registry import CharacterRegistry, get_character_registry

config = Config()
logger = logging.getLogger(__name__)


@dataclass
class SectionContext:
    """Context for a single section."""
    section_idx: int
    chunk_synopses: List[str] = field(default_factory=list)  # Synopses for each chunk
    accumulated_synopsis: str = ""  # Combined synopsis for next chunk
    
    def add_chunk_synopsis(self, synopsis: str):
        """Add synopsis from a completed chunk."""
        self.chunk_synopses.append(synopsis)
        # Accumulate context (keep last N chunks to avoid overflow)
        self._update_accumulated_synopsis()
    
    def _update_accumulated_synopsis(self):
        """Update accumulated synopsis from chunk synopses."""
        # Keep last 3 chunks max to avoid token overflow
        recent_synopses = self.chunk_synopses[-3:]
        self.accumulated_synopsis = " ".join(recent_synopses)
    
    def get_synopsis_for_next_chunk(self) -> str:
        """Get synopsis for the next chunk in this section."""
        # First chunk: empty synopsis
        if len(self.chunk_synopses) == 0:
            return ""
        # Subsequent chunks: accumulated synopsis
        return self.accumulated_synopsis


class SynopsisManager:
    """
    Manages synopsis state across all sections.
    
    Usage:
        manager = SynopsisManager()
        
        # Before translating chunk
        synopsis = manager.get_synopsis(section_idx, chunk_idx)
        
        # After translating chunk
        manager.add_chunk_result(section_idx, chunk_idx, final_translation)
    """
    
    def __init__(self, max_synopsis_chars: int = 500, character_registry: Optional[CharacterRegistry] = None):
        self.section_contexts: Dict[int, SectionContext] = {}
        self.max_synopsis_chars = max_synopsis_chars
        self._synopsis_generator = None  # Lazy init
        
        # Character registry for gender tracking
        self.character_registry = character_registry or get_character_registry()
    
    @property
    def synopsis_cache(self) -> dict:
        """
        Get synopsis history as serializable dict.
        
        Returns:
            Dict with string keys "section_idx,chunk_idx" and synopsis values
        """
        cache = {}
        for section_idx, section in self.section_contexts.items():
            # Store chunk synopses list
            cache[f"section_{section_idx}"] = section.chunk_synopses
        return cache
    
    @synopsis_cache.setter
    def synopsis_cache(self, cache: dict):
        """
        Restore synopsis history from serializable dict.
        
        Args:
            cache: Dict with keys "section_X" and list of synopsis values
        """
        self.section_contexts = {}
        for key, chunk_synopses in cache.items():
            if key.startswith("section_"):
                section_idx = int(key.split("_")[1])
                section = self._get_or_create_section(section_idx)
                section.chunk_synopses = chunk_synopses
                # Rebuild accumulated synopsis
                section._update_accumulated_synopsis()
        
    def _get_or_create_section(self, section_idx: int) -> SectionContext:
        """Get or create section context."""
        if section_idx not in self.section_contexts:
            self.section_contexts[section_idx] = SectionContext(section_idx=section_idx)
        return self.section_contexts[section_idx]
    
    def get_synopsis(self, section_idx: int, chunk_idx: int) -> str:
        """
        Get synopsis for a specific chunk.
        
        Returns:
            Empty string for first chunk in section
            Accumulated synopsis for subsequent chunks
        """
        section = self._get_or_create_section(section_idx)
        
        # First chunk in section: no synopsis
        if chunk_idx == 0:
            if config.debug:
                logger.debug(f"[Synopsis] Section {section_idx}, Chunk {chunk_idx}: FIRST CHUNK - empty synopsis")
            return ""
        
        # Subsequent chunks: return accumulated synopsis
        synopsis = section.get_synopsis_for_next_chunk()
        if config.debug:
            logger.debug(f"[Synopsis] Section {section_idx}, Chunk {chunk_idx}: {len(synopsis)} chars")
        return synopsis
    
    def add_chunk_result(
        self, 
        section_idx: int, 
        chunk_idx: int, 
        final_translation: str,
        generated_synopsis: Optional[str] = None
    ):
        """
        Add result from a completed chunk.
        
        Args:
            section_idx: Section index
            chunk_idx: Chunk index within section
            final_translation: The translated text
            generated_synopsis: Optional pre-generated synopsis (from pipeline)
        """
        section = self._get_or_create_section(section_idx)
        
        # Generate synopsis from final translation if not provided
        if generated_synopsis is None:
            generated_synopsis = self._generate_synopsis(final_translation, section_idx, chunk_idx)
        
        # Update character mentions in registry
        if self.character_registry:
            self.character_registry.detect_mentions(final_translation, section_idx, chunk_idx)
        
        # Truncate if too long
        if len(generated_synopsis) > self.max_synopsis_chars:
            generated_synopsis = generated_synopsis[:self.max_synopsis_chars] + "..."
        
        section.add_chunk_synopsis(generated_synopsis)
        
        if config.debug:
            logger.debug(
                f"[Synopsis] Section {section_idx}, Chunk {chunk_idx}: "
                f"added {len(generated_synopsis)} chars synopsis"
            )
    
    def _generate_synopsis(self, text: str, section_idx: int = -1, chunk_idx: int = -1) -> str:
        """
        Generate synopsis from translated text.
        
        Includes character context from CharacterRegistry if available.
        """
        # Get character context line
        char_context = ""
        if section_idx >= 0 and chunk_idx >= 0 and self.character_registry:
            char_context = self.character_registry.get_character_context_line(section_idx, chunk_idx)
        
        # Generate content synopsis (first sentence as fallback)
        sentences = text.split('.')
        first_sentence = sentences[0].strip() if sentences else text
        
        # Clean up XML tags
        import re
        content = re.sub(r'<[^>]+>', '', first_sentence)
        content = content.strip()
        
        # Combine character context + content
        if char_context:
            synopsis = f"{char_context}. {content}"
        else:
            synopsis = content
        
        return synopsis[:self.max_synopsis_chars]
    
    def get_section_stats(self, section_idx: int) -> Dict:
        """Get statistics for a section."""
        section = self.section_contexts.get(section_idx)
        if not section:
            return {"chunks": 0, "total_synopsis_chars": 0}
        
        return {
            "chunks": len(section.chunk_synopses),
            "total_synopsis_chars": sum(len(s) for s in section.chunk_synopses),
            "accumulated_synopsis_chars": len(section.accumulated_synopsis)
        }
    
    def reset_section(self, section_idx: int):
        """Reset synopsis for a section (e.g., on retry)."""
        if section_idx in self.section_contexts:
            del self.section_contexts[section_idx]
            if config.debug:
                logger.debug(f"[Synopsis] Section {section_idx} reset")


class SynopsisGenerator:
    """
    LLM-based synopsis generator.
    
    Generates focused synopsis that captures:
    - Character names and gender (he/she/it)
    - Key terminology
    - Plot continuity markers
    """
    
    SYSTEM_PROMPT = """You are a literary context extractor.
Create a concise synopsis (max 80 words) that captures:
1. Character names mentioned and their gender (he/she/it)
2. Key terminology or proper nouns
3. Current situation/location

Output plain text only, no formatting."""
    
    USER_TEMPLATE = """<text>
{text}
</text>

Extract context synopsis for translation continuity.
Focus on: character names + gender, key terms, situation.

Synopsis:"""
    
    def __init__(self):
        self.llm_service = None  # Will be injected
    
    def generate(self, text: str) -> str:
        """Generate synopsis using LLM."""
        if not self.llm_service:
            # Fallback to simple extraction
            return self._fallback_extract(text)
        
        try:
            # Truncate text if too long
            truncated = text[:2000] if len(text) > 2000 else text
            
            user_prompt = self.USER_TEMPLATE.format(text=truncated)
            
            # Use proofread LLM for synopsis (faster, cheaper)
            from src.utils import llm_service_compat, LLMRole
            
            result = llm_service_compat.complete(
                role=LLMRole.PROOFREAD,
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=150
            )
            
            return result.strip()
            
        except Exception as e:
            logger.warning(f"Synopsis generation failed: {e}, using fallback")
            return self._fallback_extract(text)
    
    def _fallback_extract(self, text: str) -> str:
        """Fallback extraction without LLM."""
        import re
        
        # Remove XML tags
        clean = re.sub(r'<[^>]+>', '', text)
        
        # Get first sentence or first 150 chars
        sentences = clean.split('.')
        first = sentences[0].strip() if sentences else clean
        
        return first[:150] + "..." if len(first) > 150 else first


# Global manager instance
synopsis_manager = SynopsisManager()