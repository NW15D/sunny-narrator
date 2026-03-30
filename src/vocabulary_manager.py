"""
Vocabulary Manager

Manages dictionary/terminology for translation with model-specific formatting.

Features:
1. Dictionary initialization (create from NER or load from file)
2. Per-chunk vocabulary matching (cosine similarity)
3. Model-specific formatting (Hunyuan, standard, etc.)
4. Character gender tracking
5. Series consistency across books

Workflow:
1. Check for *.dic file
2. If missing: Run NER → Create dic → Translate → User edits
3. If exists: Load → Match terms per chunk → Format for model → Inject into prompts
"""

import os
import re
import logging
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from src.config import Config
from src import ner as ner_module
from src.character_registry import CharacterRegistry, get_character_registry, Character

config = Config()
logger = logging.getLogger(__name__)


@dataclass
class VocabEntry:
    """Single vocabulary entry."""
    source: str
    target: str
    category: str = ""  # PERSON, ORG, LOC, etc.
    gender: str = ""    # he, she, it (for characters)
    notes: str = ""     # User notes
    book_origin: str = ""  # Which book in series
    
    def to_dict(self) -> Dict:
        return {
            config.source_lang: self.source,
            config.target_lang: self.target,
            "category": self.category,
            "gender": self.gender,
            "notes": self.notes,
            "book_origin": self.book_origin
        }


# NOTE: Character class is defined in character_registry.py
# Use CharacterRegistry.Character for unified character tracking


class VocabularyManager:
    """
    Manages vocabulary for translation.
    
    Usage:
        manager = VocabularyManager(book_path="books/MyBook.fb2")
        
        # Initialize (creates or loads .dic)
        vocab = manager.initialize()
        
        # Get relevant terms for chunk
        chunk_vocab = manager.get_vocab_for_chunk(chunk_text)
        
        # Format for specific model
        formatted = manager.format_for_model(chunk_vocab, model="Hunyuan")
    """
    
    def __init__(self, book_path: str):
        self.book_path = book_path
        self.book_dir = os.path.dirname(book_path)
        self.book_name = Path(book_path).stem
        self.dict_file = os.path.join(self.book_dir, f"{self.book_name}.dic")
        
        self.vocab: Dict[str, VocabEntry] = {}
        self.characters: Dict[str, Character] = {}
        self.matched_terms_cache: Dict[Tuple[int, int], List[str]] = {}  # (s_idx, c_idx) -> terms
        
    def initialize(self) -> Dict[str, VocabEntry]:
        """
        Initialize vocabulary.
        
        Returns:
            Vocabulary dictionary
            
        Raises:
            SystemExit if dictionary needs to be created
        """
        if os.path.exists(self.dict_file):
            logger.info(f"Loading vocabulary from {self.dict_file}")
            self.vocab = self._load_from_file()
            self._extract_characters()
            return self.vocab
        else:
            logger.info(f"Dictionary not found. Creating: {self.dict_file}")
            self._create_dictionary()
            # Exit to let user edit the dictionary
            print(f"\nDictionary created: {self.dict_file}")
            print("Please review and edit the dictionary, then restart.")
            import sys
            sys.exit(0)
    
    def _create_dictionary(self):
        """
        Create dictionary from book using NER.
        
        Workflow:
        1. Parse book to extract text
        2. Run NER to find named entities and common words
        3. Translate terms using LLM
        4. Save to .dic file in standard format
        """
        # Parse book to get text
        from src import fb2_handler, epub_handler, txt_handler
        
        ext = Path(self.book_path).suffix.lower()
        if ext == '.fb2':
            body, header, footer = fb2_handler.parse_xml(self.book_path)
        elif ext == '.epub':
            body, header, footer = epub_handler.parse_epub(self.book_path)
        else:
            body, header, footer = txt_handler.parse_txt(self.book_path)
        
        # Run NER to extract entities
        if config.ner_opt and ner_module:
            logger.info("Running NER to extract entities and common words...")
            
            # Use new structured dictionary creation
            extracted_terms = ner_module.create_dictionary_from_text(
                body,
                min_count_ner=5,          # Entities with >= 5 occurrences
                min_count_word=10,        # Words with >= 10 occurrences
                min_word_length=5         # Words with length >= 5
            )
            
            logger.info(f"Extracted {len(extracted_terms)} terms from text")
            
            if extracted_terms:
                # Format terms for translation
                terms_text = '\n'.join([term for term, cat, notes in extracted_terms])
                
                # Translate terms using LLM
                from src import utils as ta
                vocab_translated = ta.vocabulary(
                    config.source_lang, 
                    config.target_lang, 
                    terms_text, 
                    config.country, 
                    "Proofread"
                )
                
                # Parse and save with structured format
                self._parse_and_save_structured(vocab_translated, extracted_terms)
            else:
                logger.warning("No terms extracted by NER")
                self._create_template()
        else:
            # Create empty dictionary template
            self._create_template()
    
    def _parse_and_save(self, vocab_text: str):
        """Parse translated vocabulary and save to file."""
        lines = vocab_text.strip().split('\n')
        
        with open(self.dict_file, 'w', encoding='utf-8') as f:
            f.write(f"# Vocabulary for {self.book_name}\n")
            f.write(f"# Format: source = target | category | gender | notes\n\n")
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Parse "Source = Target" format
                if '=' in line:
                    parts = line.split('=', 1)
                    source = parts[0].strip()
                    target = parts[1].strip()
                    
                    # Try to extract category from parentheses
                    category = ""
                    match = re.search(r'\(([^)]+)\)', source)
                    if match:
                        category = match.group(1)
                        source = re.sub(r'\s*\([^)]+\)', '', source).strip()
                    
                    # Write with template for user editing
                    f.write(f"{source} = {target}")
                    if category:
                        f.write(f" | {category}")
                    f.write(" | | \n")  # gender | notes
                    
                    # Add to memory
                    key = source.replace(' ', '_').lower()
                    self.vocab[key] = VocabEntry(
                        source=source,
                        target=target,
                        category=category
                    )
        
        logger.info(f"Dictionary saved: {self.dict_file}")
    
    def _parse_and_save_structured(self, vocab_text: str, extracted_terms: List[Tuple[str, str, str]]):
        """
        Parse translated vocabulary with structured format.
        
        Args:
            vocab_text: Translated terms from LLM (format: "source = target")
            extracted_terms: Original extracted terms with categories [(term, category, notes), ...]
        """
        # Parse translated lines into source=target pairs
        translations = {}
        for line in vocab_text.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if '=' in line:
                parts = line.split('=', 1)
                source = parts[0].strip()
                target = parts[1].strip()
                translations[source.lower()] = target
        
        # Write dictionary with proper format
        with open(self.dict_file, 'w', encoding='utf-8') as f:
            f.write(f"# Vocabulary for {self.book_name}\n")
            f.write(f"# Format: source = target | category | gender | notes\n")
            f.write(f"# Generated automatically by NER\n")
            f.write(f"# Please review and edit as needed\n\n")
            
            # Group by category
            categories = {'PERSON': [], 'LOC': [], 'ORG': [], 'TERM': [], 'OTHER': []}
            
            for term, category, notes in extracted_terms:
                term_lower = term.lower()
                if term_lower in translations:
                    target = translations[term_lower]
                    cat = category if category in ['PERSON', 'LOC', 'ORG'] else 'OTHER'
                    categories[cat].append((term, target, category, notes))
            
            # Write sections
            for cat_name in ['PERSON', 'LOC', 'ORG', 'TERM', 'OTHER']:
                entries = categories[cat_name]
                if not entries:
                    continue
                
                f.write(f"\n# {cat_name} ({len(entries)} terms)\n")
                for source, target, orig_cat, notes in entries:
                    # Format: source = target | category | gender | notes
                    f.write(f"{source} = {target} | {orig_cat} | | {notes}\n")
                    
                    # Add to memory
                    key = source.replace(' ', '_').lower()
                    self.vocab[key] = VocabEntry(
                        source=source,
                        target=target,
                        category=orig_cat,
                        notes=notes
                    )
        
        logger.info(f"Dictionary saved: {self.dict_file} ({len(self.vocab)} entries)")
    
    def _create_template(self):
        """Create empty dictionary template."""
        with open(self.dict_file, 'w', encoding='utf-8') as f:
            f.write(f"# Vocabulary for {self.book_name}\n")
            f.write(f"# Format: source = target | category | gender | notes\n\n")
            f.write("# Example:\n")
            f.write("# Alice = Алиса | PERSON | she | Main character\n")
            f.write("# Wonderland = Страна чудес | LOC | | Setting\n")
        
        logger.info(f"Template dictionary created: {self.dict_file}")
    
    def _load_from_file(self) -> Dict[str, VocabEntry]:
        """Load vocabulary from .dic file."""
        vocab = {}
        
        with open(self.dict_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                try:
                    # Format: source = target | category | gender | notes
                    # OR: source = target (legacy format)
                    
                    # Split by = first
                    if '=' not in line:
                        continue
                    
                    parts = line.split('=', 1)
                    source = parts[0].strip()
                    rest = parts[1].strip()
                    
                    # Split rest by | for extended format
                    if '|' in rest:
                        subparts = rest.split('|')
                        target = subparts[0].strip()
                        category = subparts[1].strip() if len(subparts) > 1 else ""
                        gender = subparts[2].strip() if len(subparts) > 2 else ""
                        notes = subparts[3].strip() if len(subparts) > 3 else ""
                    else:
                        target = rest
                        category = ""
                        gender = ""
                        notes = ""
                    
                    key = source.replace(' ', '_').lower()
                    vocab[key] = VocabEntry(
                        source=source,
                        target=target,
                        category=category,
                        gender=gender,
                        notes=notes
                    )
                    
                except Exception as e:
                    logger.warning(f"Error parsing line {line_num}: {line} - {e}")
        
        return vocab
    
    def _extract_characters(self):
        """Extract characters from vocabulary (PERSON category) and sync with CharacterRegistry."""
        # Get or create character registry
        registry = get_character_registry()
        
        for key, entry in self.vocab.items():
            if entry.category.upper() == "PERSON" or not entry.category:
                # Create local character
                self.characters[key] = Character(
                    name=entry.source,
                    gender=entry.gender,
                    aliases=[entry.target] if entry.target else []
                )
                
                # Sync with global registry
                registry.add_character(
                    name=entry.source,
                    target_name=entry.target,
                    gender=entry.gender,
                    category=entry.category or "PERSON",
                    notes=entry.notes
                )
        
        if config.debug:
            logger.debug(f"[VocabularyManager] Extracted {len(self.characters)} characters, synced with registry")
    
    def get_vocab_for_chunk(self, chunk_text: str, s_idx: int, c_idx: int) -> List[VocabEntry]:
        """
        Get vocabulary entries relevant to this chunk.
        
        Uses cosine similarity matching to find terms present in chunk.
        Automatically selects GPU or CPU mode based on availability.
        
        Args:
            chunk_text: Text to search for vocabulary terms
            s_idx: Section index (for caching)
            c_idx: Chunk index (for caching)
            
        Returns:
            List of matched VocabEntry objects
        """
        cache_key = (s_idx, c_idx)
        
        if cache_key in self.matched_terms_cache:
            matched_keys = self.matched_terms_cache[cache_key]
            return [self.vocab[k] for k in matched_keys if k in self.vocab]
        
        if not config.ner_opt or not ner_module:
            if config.debug:
                logger.warning(f"get_vocab_for_chunk: NER disabled or module not available (ner_opt={config.ner_opt}, ner_module={ner_module is not None})")
            # Fallback: return all vocabulary entries (no chunk-specific matching)
            # This ensures vocabulary is still used even without NER matching
            return list(self.vocab.values())
        
        # Check if GPU is available and select appropriate function
        use_gpu = False
        try:
            import torch
            use_gpu = torch.cuda.is_available()
        except ImportError:
            use_gpu = False
        
        # Select matching function based on GPU availability
        if use_gpu:
            # GPU-accelerated version (faster)
            matched = ner_module.find_matching_words_with_cosine_similarity(
                chunk_text, 
                self._vocab_to_ner_format(), 
                config.source_lang
            )
        else:
            # CPU-only version (slower but works everywhere)
            matched = ner_module.find_matching_words_with_cosine_similarity_cpu(
                chunk_text, 
                self._vocab_to_ner_format(), 
                config.source_lang
            )
        
        # Convert to VocabEntry list
        entries = []
        matched_keys = []
        
        for term in matched:
            key = term.replace(' ', '_').lower()
            if key in self.vocab:
                entries.append(self.vocab[key])
                matched_keys.append(key)
        
        # Cache results
        self.matched_terms_cache[cache_key] = matched_keys
        
        if config.debug:
            mode = "GPU" if use_gpu else "CPU"
            logger.debug(f"Chunk {s_idx}-{c_idx} ({mode}): {len(entries)} vocab terms matched")
        
        return entries
    
    def _vocab_to_ner_format(self) -> Dict:
        """Convert vocab to format expected by NER module."""
        result = {}
        for key, entry in self.vocab.items():
            result[key] = {
                config.source_lang: entry.source,
                config.target_lang: entry.target
            }
        return result
    
    def format_for_model(self, entries: List[VocabEntry], model: str = "") -> str:
        """
        Format vocabulary for specific model.
        
        Args:
            entries: Vocabulary entries to format
            model: Model name (e.g., "Hunyuan", "Mistral")
        
        Returns:
            Formatted vocabulary string for prompt injection
        """
        model_lower = model.lower() if model else config.model_translate.lower()
        
        if "hunyuan" in model_lower or "hy-mt" in model_lower:
            return self._format_hunyuan(entries)
        elif "gemma" in model_lower:
            return self._format_gemma(entries)
        else:
            return self._format_standard(entries)
    
    def _format_hunyuan(self, entries: List[VocabEntry]) -> str:
        """
        Format for Hunyuan MT model.
        
        Based on HY-MT1.5 documentation, Hunyuan supports terminology intervention.
        Format: comma-separated list with source=target pairs.
        """
        if not entries:
            return ""
        
        lines = []
        for entry in entries:
            line = f"{entry.source}={entry.target}"
            if entry.category:
                line += f"({entry.category})"
            lines.append(line)
        
        return " | ".join(lines)
    
    def _format_gemma(self, entries: List[VocabEntry]) -> str:
        """
        Format for Gemma/TranslateGemma model.
        
        Uses comma-separated format.
        """
        if not entries:
            return ""
        
        lines = []
        for entry in entries:
            if entry.category:
                lines.append(f"  {entry.source} → {entry.target}, {entry.category}")
            else:
                lines.append(f"  {entry.source} → {entry.target}")
        
        return "\n".join(lines)
    
    def _format_standard(self, entries: List[VocabEntry]) -> str:
        """
        Standard format for most models.
        Uses comma-separated format: source = target, category, gender, notes
        """
        if not entries:
            return ""
        
        lines = []
        for entry in entries:
            line = f"{entry.source} = {entry.target}"
            parts = []
            if entry.category:
                parts.append(entry.category)
            if entry.gender:
                parts.append(entry.gender)
            if entry.notes:
                parts.append(entry.notes)
            
            if parts:
                line += ", " + ", ".join(parts)
            
            lines.append(line)
        
        return "\n".join(lines)
    
    def get_character_gender(self, name: str) -> str:
        """Get character gender by name."""
        key = name.replace(' ', '_').lower()
        if key in self.characters:
            return self.characters[key].gender
        
        # Try to find by alias
        for char in self.characters.values():
            if name.lower() in [a.lower() for a in char.aliases]:
                return char.gender
        
        return ""
    
    def update_character_mentions(self, name: str, section_idx: int, chunk_idx: int):
        """Update character mention tracking."""
        key = name.replace(' ', '_').lower()
        if key in self.characters:
            self.characters[key].mentions.append((section_idx, chunk_idx))
    
    def get_series_vocab(self, previous_books: List[str]) -> Dict[str, VocabEntry]:
        """
        Load vocabulary from previous books in series.
        
        Args:
            previous_books: List of paths to previous books' .dic files
        
        Returns:
            Combined vocabulary from all books
        """
        series_vocab = {}
        
        for book_dic in previous_books:
            if os.path.exists(book_dic):
                book_vocab = self._load_from_file_with_path(book_dic)
                for key, entry in book_vocab.items():
                    if key not in series_vocab:
                        entry.book_origin = Path(book_dic).stem
                        series_vocab[key] = entry
        
        return series_vocab
    
    def _load_from_file_with_path(self, file_path: str) -> Dict[str, VocabEntry]:
        """Load vocabulary from specific file path."""
        vocab = {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                try:
                    if '=' not in line:
                        continue
                    
                    parts = line.split('=', 1)
                    source = parts[0].strip()
                    rest = parts[1].strip()
                    
                    if '|' in rest:
                        subparts = rest.split('|')
                        target = subparts[0].strip()
                        category = subparts[1].strip() if len(subparts) > 1 else ""
                        gender = subparts[2].strip() if len(subparts) > 2 else ""
                        notes = subparts[3].strip() if len(subparts) > 3 else ""
                    else:
                        target = rest
                        category = ""
                        gender = ""
                        notes = ""
                    
                    key = source.replace(' ', '_').lower()
                    vocab[key] = VocabEntry(
                        source=source,
                        target=target,
                        category=category,
                        gender=gender,
                        notes=notes
                    )
                    
                except Exception as e:
                    logger.warning(f"Error parsing line {line_num} in {file_path}: {e}")
        
        return vocab


# Global manager instance (lazy initialization)
_vocabulary_manager: Optional[VocabularyManager] = None

def get_vocabulary_manager(book_path: str) -> VocabularyManager:
    """Get or create vocabulary manager for book."""
    global _vocabulary_manager
    if _vocabulary_manager is None or _vocabulary_manager.book_path != book_path:
        _vocabulary_manager = VocabularyManager(book_path)
    return _vocabulary_manager