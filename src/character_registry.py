"""
Character Registry

Unified character tracking across SynopsisManager and VocabularyManager.

Purpose:
- Centralized character storage (name, gender, aliases, mentions)
- Integration between vocabulary (source of truth for gender) and synopsis
- Cross-reference characters between dictionary and translated text
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from src.config import Config

config = Config()
logger = logging.getLogger(__name__)


@dataclass
class Character:
    """
    Character with comprehensive tracking.
    
    Source of truth for gender: VocabularyManager (user-editable .dic file)
    """
    name: str  # Source language name (primary key)
    target_name: str = ""  # Translated name
    gender: str = ""  # he, she, it, they (from vocabulary)
    category: str = ""  # PERSON, ORG, etc.
    aliases: List[str] = field(default_factory=list)  # Alternative names
    
    # Tracking
    first_mention_section: int = -1
    first_mention_chunk: int = -1
    mentions: List[Tuple[int, int]] = field(default_factory=list)  # (section, chunk) list
    
    # Context
    notes: str = ""  # From vocabulary
    book_origin: str = ""  # For series
    
    def get_display_name(self) -> str:
        """Get name for display (target if available, else source)."""
        return self.target_name or self.name
    
    def get_all_forms(self) -> List[str]:
        """Get all name forms for matching."""
        forms = [self.name, self.target_name] if self.target_name else [self.name]
        forms.extend(self.aliases)
        return [f for f in forms if f]
    
    def add_mention(self, section_idx: int, chunk_idx: int):
        """Record a mention of this character."""
        mention = (section_idx, chunk_idx)
        if mention not in self.mentions:
            self.mentions.append(mention)
            
            # Update first mention if not set
            if self.first_mention_section == -1:
                self.first_mention_section = section_idx
                self.first_mention_chunk = chunk_idx
    
    def get_mention_count(self) -> int:
        """Get total number of mentions."""
        return len(self.mentions)
    
    def to_synopsis_format(self) -> str:
        """Format for inclusion in synopsis."""
        parts = [self.get_display_name()]
        if self.gender:
            parts.append(f"({self.gender})")
        return " ".join(parts)
    


class CharacterRegistry:
    """
    Central registry for all characters in a book.
    
    Integrates:
    - VocabularyManager (source of gender and translations)
    - SynopsisManager (needs character context)
    - TranslationEngine (tracks mentions during translation)
    
    Usage:
        registry = CharacterRegistry()
        
        # Filled from the dictionary by VocabularyManager._extract_characters
        registry.add_character("Alice", "Алиса", "she")

        # During translation
        registry.detect_mentions(text, section_idx, chunk_idx)
        
        # For synopsis
        recent_chars = registry.get_characters_for_synopsis(section_idx, chunk_idx)
        synopsis = f"Characters: {', '.join(c.to_synopsis_format() for c in recent_chars)}"
    """
    
    def __init__(self):
        self.characters: Dict[str, Character] = {}  # key = normalized name
        self.name_index: Dict[str, str] = {}  # form -> normalized key (for lookup)
        self.gender_stats: Dict[str, int] = defaultdict(int)  # gender -> count
        
    def _normalize_key(self, name: str) -> str:
        """Create normalized key for character."""
        return name.lower().replace(' ', '_').strip()
    
    def _index_character(self, char: Character):
        """Index all name forms for quick lookup."""
        key = self._normalize_key(char.name)
        for form in char.get_all_forms():
            self.name_index[form.lower()] = key

    def add_character(self, name: str, target_name: str = "", gender: str = "", 
                      category: str = "PERSON", notes: str = "") -> Character:
        """
        Add a new character to registry.
        
        Returns:
            Character object (existing or newly created)
        """
        key = self._normalize_key(name)
        
        if key in self.characters:
            # Update existing
            char = self.characters[key]
            if target_name and not char.target_name:
                char.target_name = target_name
            if gender is not None and gender and not char.gender:
                char.gender = gender
            if notes and not char.notes:
                char.notes = notes
        else:
            # Create new
            char = Character(
                name=name,
                target_name=target_name,
                gender=gender,
                category=category,
                notes=notes
            )
            self.characters[key] = char
            self._index_character(char)
            
            # Track gender stats
            if gender is not None and gender:
                self.gender_stats[gender] += 1
        
        return char

    def detect_mentions(self, text: str, section_idx: int, chunk_idx: int) -> List[Character]:
        """
        Detect character mentions in text and record them.
        
        Returns:
            List of characters mentioned in this text
        """
        mentioned = []
        text_lower = text.lower()
        
        for char in self.characters.values():
            # Check if any form of character name appears in text
            for form in char.get_all_forms():
                if form.lower() in text_lower:
                    char.add_mention(section_idx, chunk_idx)
                    mentioned.append(char)
                    break  # Only count once per character
        
        if config.debug and mentioned:
            logger.debug(f"[CharacterRegistry] Detected {len(mentioned)} characters in section {section_idx}, chunk {chunk_idx}")
        
        return mentioned
    
    def get_characters_for_synopsis(self, section_idx: int, chunk_idx: int, 
                                     max_chars: int = 200) -> List[Character]:
        """
        Get characters to include in synopsis for this chunk.
        
        Strategy:
        1. Characters mentioned in recent chunks (last 3)
        2. Main characters (high mention count)
        3. New characters (first mention in recent chunks)
        
        Args:
            section_idx: Current section
            chunk_idx: Current chunk
            max_chars: Maximum characters for synopsis line
        
        Returns:
            List of characters to include
        """
        candidates = []
        
        # Priority 1: Characters mentioned in recent chunks (same section)
        for char in self.characters.values():
            recent_mentions = [
                (s, c) for s, c in char.mentions 
                if s == section_idx and chunk_idx - 3 <= c < chunk_idx
            ]
            if recent_mentions:
                candidates.append((char, len(recent_mentions)))
        
        # Priority 2: Main characters (overall mention count)
        main_chars = [
            (char, char.get_mention_count()) 
            for char in self.characters.values()
            if char.get_mention_count() > 5 and char not in [c for c, _ in candidates]
        ]
        candidates.extend(main_chars)
        
        # Sort by priority (mention count in recent context)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Select until max_chars reached
        selected = []
        current_len = 0
        
        for char, _ in candidates:
            char_str = char.to_synopsis_format()
            if current_len + len(char_str) + 2 > max_chars:  # +2 for ", "
                break
            selected.append(char)
            current_len += len(char_str) + 2
        
        return selected
    
    def get_character_context_line(self, section_idx: int, chunk_idx: int) -> str:
        """
        Generate character context line for synopsis.
        
        Example: "Characters: Alice (she), Bob (he), the Cat (it)"
        """
        chars = self.get_characters_for_synopsis(section_idx, chunk_idx)
        
        if not chars:
            return ""
        
        char_strs = [c.to_synopsis_format() for c in chars]
        return f"Characters: {', '.join(char_strs)}"
    
    
    
    


# Global registry instance (lazy initialization)
_character_registry: Optional[CharacterRegistry] = None

def get_character_registry() -> CharacterRegistry:
    """Get or create global character registry."""
    global _character_registry
    if _character_registry is None:
        _character_registry = CharacterRegistry()
    return _character_registry

def reset_character_registry():
    """Reset global registry (for new book)."""
    global _character_registry
    _character_registry = None