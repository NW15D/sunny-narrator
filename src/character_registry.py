"""
Character Registry

Unified character tracking across SynopsisManager and VocabularyManager.

Purpose:
- Centralized character storage (name, gender, aliases, mentions)
- Integration between vocabulary (source of truth for gender) and synopsis
- Cross-reference characters between dictionary and translated text
"""

import logging
from typing import Dict, List, Optional, Set, Tuple
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
    
    def to_vocab_format(self) -> str:
        """Format for vocabulary file (NEW comma-separated format)."""
        metadata = [self.category, self.gender, self.notes]
        return f"{self.name} = {self.target_name}, {', '.join(metadata)}"


class CharacterRegistry:
    """
    Central registry for all characters in a book.
    
    Integrates:
    - VocabularyManager (source of gender and translations)
    - SynopsisManager (needs character context)
    - TranslationEngine (tracks mentions during translation)
    
    Usage:
        registry = CharacterRegistry()
        
        # From VocabularyManager
        registry.load_from_vocab(vocab_manager.vocab, vocab_manager.characters)
        
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
    
    def load_from_vocab(self, vocab_entries: Dict, characters: Dict):
        """
        Load characters from VocabularyManager.
        
        Args:
            vocab_entries: Dictionary of VocabEntry objects
            characters: Dictionary of Character objects from VocabularyManager
        """
        for key, char in characters.items():
            normalized_key = self._normalize_key(char.name)
            
            # Create or update character
            if normalized_key not in self.characters:
                self.characters[normalized_key] = Character(
                    name=char.name,
                    target_name=char.aliases[0] if char.aliases else "",
                    gender=char.gender,
                    category="PERSON"
                )
            else:
                # Update gender from vocabulary (source of truth)
                self.characters[normalized_key].gender = char.gender
                if char.aliases:
                    self.characters[normalized_key].target_name = char.aliases[0]
            
            # Index for lookup
            self._index_character(self.characters[normalized_key])
            
            # Track gender stats
            if char.gender:
                self.gender_stats[char.gender] += 1
        
        if config.debug:
            logger.debug(f"[CharacterRegistry] Loaded {len(self.characters)} characters from vocabulary")
    
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
    
    def get_character(self, name: str) -> Optional[Character]:
        """Get character by name (any form)."""
        # Try direct lookup
        key = self._normalize_key(name)
        if key in self.characters:
            return self.characters[key]
        
        # Try via name index
        if name.lower() in self.name_index:
            return self.characters[self.name_index[name.lower()]]
        
        return None
    
    def get_character_gender(self, name: str) -> str:
        """Get gender for character (empty string if not found)."""
        char = self.get_character(name)
        return char.gender if char else ""
    
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
    
    def get_gender_for_pronoun(self, name: str, context_text: str = "") -> str:
        """
        Infer or get gender for pronoun resolution.
        
        1. Check registry (from vocabulary)
        2. Try to infer from context (he/she/it nearby)
        3. Return empty if unknown
        """
        # 1. Check registry
        char = self.get_character(name)
        if char and char.gender:
            return char.gender
        
        # 2. Try to infer from context
        if context_text:
            return self._infer_gender_from_context(name, context_text)
        
        return ""
    
    def _infer_gender_from_context(self, name: str, text: str) -> str:
        """Infer gender by looking for pronouns near character mentions."""
        text_lower = text.lower()
        name_lower = name.lower()
        
        # Find sentences with character name
        sentences = text_lower.split('.')
        relevant = [s for s in sentences if name_lower in s]
        
        if not relevant:
            return ""
        
        # Count pronouns in relevant sentences
        pronouns = {"he": 0, "she": 0, "it": 0, "they": 0}
        
        for sent in relevant:
            for pronoun in pronouns:
                # Simple word-based check (could be improved with NER)
                words = sent.split()
                if pronoun in words:
                    pronouns[pronoun] += 1
        
        # Return most frequent
        if any(pronouns.values()):
            return max(pronouns, key=pronouns.get)
        
        return ""
    
    def get_stats(self) -> Dict:
        """Get statistics about characters."""
        return {
            "total_characters": len(self.characters),
            "with_gender": sum(1 for c in self.characters.values() if c.gender),
            "gender_distribution": dict(self.gender_stats),
            "most_mentioned": sorted(
                [(c.name, c.get_mention_count()) for c in self.characters.values()],
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }
    
    def to_vocab_entries(self) -> List[str]:
        """Export all characters as vocabulary entries."""
        return [char.to_vocab_format() for char in self.characters.values()]


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