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
import tempfile
import logging
import fcntl
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from src.config import Config
from src import ner as ner_module
from src.character_registry import CharacterRegistry, get_character_registry, Character

config = Config()
logger = logging.getLogger(__name__)


class DictionaryCreatedSignal(Exception):
    """Raised when a new dictionary has been created and the pipeline should stop for user review."""
    def __init__(self, dict_path: str):
        self.dict_path = dict_path
        super().__init__(f"Dictionary created at {dict_path}. Review it, then re-run to start translation.")


def validate_dictionary(dict_file: str) -> List[str]:
    """
    Validate CSV dictionary format.
    
    Expected format: source = target, category, gender, notes
    Comment lines start with # and are ignored.
    
    Args:
        dict_file: Path to .dic file
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    try:
        if not os.path.exists(dict_file):
            errors.append(f"Dictionary file not found: {dict_file}")
            return errors
        
        with open(dict_file, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
        
        # Filter out comment lines and empty lines
        entry_lines = []
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                entry_lines.append((line_num, stripped))
        
        if not entry_lines:
            errors.append("Dictionary file is empty (no entries found)")
            return errors
        
        # CSV pattern: source = target, category, gender, notes
        # At minimum: source = target
        csv_pattern = re.compile(r'^[^=]+=\s*\S+')
        
        sources_seen = []
        for line_num, line in entry_lines:
            if not csv_pattern.match(line):
                errors.append(f"Line {line_num}: does not match 'source = target' format: {line[:80]}")
                continue
            
            # Parse source for duplicate check
            source = line.split('=', 1)[0].strip()
            if source:
                sources_seen.append(source.lower())
        
        # Check for duplicates
        duplicates = set([s for s in sources_seen if sources_seen.count(s) > 1])
        if duplicates:
            errors.append(f"Duplicate source terms: {', '.join(duplicates)}")
        
    except FileNotFoundError:
        errors.append(f"Dictionary file not found: {dict_file}")
    except Exception as e:
        errors.append(f"Unexpected error: {e}")
    
    return errors


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
            DictionaryCreatedSignal: if dictionary was created and needs user review
        """
        if os.path.exists(self.dict_file):
            logger.info(f"Loading vocabulary from {self.dict_file}")
            self.vocab = self._load_from_file()
            self._extract_characters()
            return self.vocab
        else:
            logger.info(f"Dictionary not found. Creating: {self.dict_file}")
            self._create_dictionary()
            # Check if auto-continue is enabled
            if getattr(config, 'auto_continue_after_dict', False):
                logger.info("Auto-continue enabled, proceeding without manual review")
                return self.vocab
            else:
                # Signal that dictionary was created and needs review
                raise DictionaryCreatedSignal(self.dict_file)
    
    def _atomic_write(self, content: str):
        """Write content to dict_file atomically (write to temp, then rename)."""
        dir_path = os.path.dirname(self.dict_file)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(tmp_path, self.dict_file)
        except:
            os.unlink(tmp_path)
            raise

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
                
                # Split into chunks based on MAX_LEN_CHUNK configuration
                CHUNK_SIZE = int(config.max_len_chunk) if hasattr(config, 'max_len_chunk') else 16384
                logger.info(f"Using chunk size: {CHUNK_SIZE} characters (from MAX_LEN_CHUNK)")
                
                lines = terms_text.split('\n')
                chunks = []
                current = []
                current_len = 0
                for line in lines:
                    current.append(line)
                    current_len += len(line) + 1
                    if current_len >= CHUNK_SIZE:
                        chunks.append('\n'.join(current))
                        current = []
                        current_len = 0
                if current:
                    chunks.append('\n'.join(current))
                
                logger.info(f"Split {len(terms_text)} chars into {len(chunks)} chunk(s) for translation")
                
                from src import utils as ta
                import json as _json
                
                # Write header once
                with open(self.dict_file, 'w', encoding='utf-8') as f:
                    f.write(f"# Vocabulary for {self.book_name}\n")
                    f.write(f"# Format: source = target, category, gender, notes\n")
                    f.write(f"# Generated automatically by NER\n\n")
                
                # Clear existing vocab to avoid duplicates
                self.vocab.clear()
                
                total_parsed = 0
                for idx, chunk in enumerate(chunks):
                    logger.info(f"Translating chunk {idx + 1}/{len(chunks)} ({len(chunk)} chars)...")
                    
                    vocab_translated = ta.vocabulary(
                        config.source_lang,
                        config.target_lang,
                        chunk,
                        config.country,
                        "Translate"
                    )
                    
                    # Parse JSON response and write immediately
                    parsed = self._parse_and_append_chunk(vocab_translated, idx + 1, len(chunks))
                    total_parsed += parsed
                    logger.info(f"Chunk {idx + 1}: wrote {parsed} entries")
                
                logger.info(f"Dictionary saved: {self.dict_file} ({total_parsed} total entries)")
            else:
                logger.warning("No terms extracted by NER")
                self._create_template()
        else:
            # Create empty dictionary template
            self._create_template()
    
    def _parse_and_save(self, vocab_text: str):
        """Parse translated vocabulary and save to file."""
        lines = vocab_text.strip().split('\n')
        
        content_lines = []
        content_lines.append(f"# Vocabulary for {self.book_name}\n")
        content_lines.append(f"# Format: source = target | category | gender | notes\n\n")
        
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
                
                # Build line with template for user editing
                entry_line = f"{source} = {target}"
                if category:
                    entry_line += f" | {category}"
                entry_line += " | | \n"  # gender | notes
                content_lines.append(entry_line)
                
                # Add to memory
                key = source.replace(' ', '_').lower()
                self.vocab[key] = VocabEntry(
                    source=source,
                    target=target,
                    category=category
                )
        
        self._atomic_write(''.join(content_lines))
        logger.info(f"Dictionary saved: {self.dict_file}")
    
    def _parse_and_save_structured(self, vocab_text: str, extracted_terms: List[Tuple[str, str, str]]):
        """
        Parse translated vocabulary and save in JSON format.
        
        Args:
            vocab_text: Translated terms from LLM (format: "source = target")
            extracted_terms: Original extracted terms with categories [(term, category, notes), ...]
        """
        import json
        
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
        
        # Build vocabulary list
        vocab_list = []
        
        for term, category, notes in extracted_terms:
            term_lower = term.lower()
            if term_lower in translations:
                target = translations[term_lower]
                entry = {
                    "source": term,
                    "target": target,
                    "category": category if category in ['PERSON', 'LOC', 'ORG'] else 'TERM',
                    "gender": "",
                    "notes": notes
                }
                vocab_list.append(entry)
                
                # Add to memory
                key = term.replace(' ', '_').lower()
                self.vocab[key] = VocabEntry(
                    source=term,
                    target=target,
                    category=entry["category"],
                    gender="",
                    notes=notes
                )
        
        # Write dictionary in JSON format atomically
        import io
        buf = io.StringIO()
        buf.write(f"# Vocabulary for {self.book_name}\n")
        buf.write(f"# Format: JSON array of vocabulary entries\n")
        buf.write(f"# Generated automatically by NER\n")
        buf.write(f"# Please review and edit as needed\n\n")
        json.dump(vocab_list, buf, indent=2, ensure_ascii=False)
        self._atomic_write(buf.getvalue())
        
        logger.info(f"Dictionary saved: {self.dict_file} ({len(self.vocab)} entries)")
    
    def _parse_and_append_chunk(self, vocab_translated: str, chunk_num: int, total_chunks: int) -> int:
        """
        Parse LLM response and append entries to the dictionary file in consistent CSV format.
        
        This method handles various LLM response formats but expects structured data
        with source, target, and optional category fields.
        
        Args:
            vocab_translated: Response from LLM (may contain JSON, markdown, or plain text)
            chunk_num: Current chunk number (1-based)
            total_chunks: Total number of chunks
            
        Returns:
            Number of entries parsed and written
        """
        import json
        import re
        
        parsed = 0
        terms = []
        
        # Strategy 1: Try to find and parse JSON array or object
        try:
            # Look for JSON array first
            json_array_match = re.search(r'\[\s*\{.*?\}\s*\]', vocab_translated, re.DOTALL)
            if json_array_match:
                json_str = json_array_match.group(0)
                terms = json.loads(json_str)
                if not isinstance(terms, list):
                    terms = []
            else:
                # Look for JSON object with terms array
                json_obj_match = re.search(r'\{\s*"terms"\s*:\s*\[.*?\]\s*\}', vocab_translated, re.DOTALL)
                if json_obj_match:
                    json_str = json_obj_match.group(0)
                    obj = json.loads(json_str)
                    terms = obj.get('terms', []) if isinstance(obj, dict) else []
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(f"JSON parsing failed for chunk {chunk_num}: {e}")
            pass
        
        # Strategy 2: If no JSON found, try to extract structured data from markdown/table format
        if not terms:
            # Look for markdown table format
            table_pattern = r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|'
            matches = re.findall(table_pattern, vocab_translated)
            if matches:
                for match in matches:
                    source = match[0].strip()
                    target = match[1].strip()
                    category = match[2].strip() if match[2].strip() else "TERM"
                    if source and target and not source.startswith('-') and not target.startswith('-'):
                        terms.append({
                            "source": source,
                            "target": target,
                            "category": category
                        })
        
        # Strategy 3: Last resort - look for simple key-value pairs
        if not terms:
            # Look for patterns like "source: target" or "source -> target"
            kv_patterns = [
                r'"([^"]+)"\s*:\s*"([^"]+)"',  # "source": "target"
                r'([^:\n]+):\s*([^\n]+)',         # source: target
                r'([^→\n]+)→\s*([^\n]+)',        # source → target
                r'([^=\n]+)=\s*([^\n]+)'         # source = target
            ]
            
            for pattern in kv_patterns:
                matches = re.findall(pattern, vocab_translated)
                if matches:
                    for match in matches:
                        source = match[0].strip()
                        target = match[1].strip()
                        # Skip if looks like metadata or instruction
                        if source.lower() in ['terms', 'translation', 'note', 'example']:
                            continue
                        if source and target and len(source) > 1 and len(target) > 1:
                            terms.append({
                                "source": source,
                                "target": target,
                                "category": "TERM"
                            })
                    break  # Use first successful pattern
        
        if not terms:
            logger.warning(f"Chunk {chunk_num}: No valid terms found in response")
            # Log a sample of the response for debugging
            sample = vocab_translated[:200] if len(vocab_translated) > 200 else vocab_translated
            logger.debug(f"Chunk {chunk_num} response sample: {repr(sample)}")
            return 0
        
        # Validate and normalize terms
        valid_terms = []
        valid_categories = {'PERSON', 'LOC', 'ORG', 'TERM'}
        
        for term in terms:
            if isinstance(term, dict):
                source = str(term.get('source', '')).strip()
                target = str(term.get('target', '')).strip()
                category = str(term.get('category', 'TERM')).strip()
                
                # Skip empty or invalid entries
                if not source or not target:
                    continue
                
                # Normalize category
                if category.upper() not in valid_categories:
                    category = "TERM"
                else:
                    category = category.upper()
                
                valid_terms.append({
                    "source": source,
                    "target": target,
                    "category": category
                })
        
        if not valid_terms:
            logger.warning(f"Chunk {chunk_num}: No valid terms after normalization")
            return 0
        
        # Build new lines to append
        new_lines = []
        if chunk_num == 1:
            new_lines.append(f"\n# --- Translated Terms (Format: source = target, category, gender, notes) ---\n")
        else:
            new_lines.append(f"\n# --- Chunk {chunk_num}/{total_chunks} ---\n")
        
        for term in valid_terms:
            source = term["source"]
            target = term["target"]
            category = term["category"]
            
            # Write in format: source = target, category, gender, notes
            new_lines.append(f"{source} = {target}, {category}, , \n")
            
            # Add to memory
            key = source.replace(' ', '_').lower()
            self.vocab[key] = VocabEntry(
                source=source,
                target=target,
                category=category,
                gender="",
                notes=""
            )
            parsed += 1
        
        # Append with file lock to prevent lost updates from concurrent access
        self._locked_append(self.dict_file, ''.join(new_lines))
        return parsed
    
    def _create_template(self):
        """Create empty dictionary template with CSV format."""
        content = (
            f"# Vocabulary for {self.book_name}\n"
            f"# Format: source = target, category, gender, notes\n"
            f"# Valid categories: PERSON, LOC, ORG, TERM\n"
            f"# Valid genders: he, she, it, they (optional)\n"
            f"# Add your vocabulary entries below this line\n\n"
        )
        self._atomic_write(content)
        
        logger.info(f"Template dictionary created: {self.dict_file}")
    
    def _load_from_file(self) -> Dict[str, VocabEntry]:
        """Load vocabulary from .dic file using CSV format.
        
        Format: source = target, category, gender, notes
        Fields separated by commas after the = sign.
        Comments start with # and are ignored.
        """
        import csv
        
        vocab = {}
        
        with open(self.dict_file, 'r', encoding='utf-8-sig') as f:
            # Skip comment lines at the beginning
            lines = []
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    lines.append(stripped)
            
            if not lines:
                logger.warning(f"No valid entries found in {self.dict_file}")
                return vocab
            
            for line_num, line in enumerate(lines, 1):
                try:
                    # Parse: source = target, category, gender, notes
                    if '=' not in line:
                        logger.warning(f"Line {line_num}: Missing '=' separator, skipping")
                        continue
                    
                    parts = line.split('=', 1)
                    source = parts[0].strip()
                    rest = parts[1].strip()
                    
                    if not source or not rest:
                        logger.warning(f"Line {line_num}: Empty source or rest, skipping")
                        continue
                    
                    # Parse comma-separated values: target, category, gender, notes
                    csv_reader = csv.reader([rest])
                    try:
                        row = next(csv_reader)
                    except StopIteration:
                        logger.warning(f"Line {line_num}: Empty fields after '=', skipping")
                        continue
                    
                    # Ensure we have at least source and target
                    if len(row) < 1:
                        logger.warning(f"Line {line_num}: Insufficient fields (need at least target)")
                        continue
                    
                    target = row[0].strip() if len(row) > 0 else ""
                    category = row[1].strip() if len(row) > 1 else ""
                    gender = row[2].strip() if len(row) > 2 else ""
                    notes = row[3].strip() if len(row) > 3 else ""
                    
                    if not source or not target:
                        logger.warning(f"Line {line_num}: Empty source or target")
                        continue
                    
                    # NO VALIDATION - allow any category and gender values (may be in any language)
                    # category and gender are passed as-is to prompts
                    
                    key = source.replace(' ', '_').lower()
                    vocab[key] = VocabEntry(
                        source=source,
                        target=target,
                        category=category,
                        gender=gender,
                        notes=notes
                    )
                    
                except Exception as e:
                    logger.warning(f"Error parsing line {line_num}: {row} - {e}")
        
        logger.info(f"Loaded {len(vocab)} entries from CSV format")
        return vocab
    
    def _locked_append(self, filepath: str, new_content: str):
        """Append content with file lock to prevent lost updates."""
        with open(filepath, 'a', encoding='utf-8') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(new_content)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _extract_characters(self):
        """Extract characters from vocabulary (PERSON category) and sync with CharacterRegistry."""
        # Get or create character registry
        registry = get_character_registry()
        
        for key, entry in self.vocab.items():
            if entry.category.upper() == "PERSON":
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
                logger.debug(f"get_vocab_for_chunk: NER disabled, using text matching (ner_opt={config.ner_opt}, ner_module={ner_module is not None})")
            # Fallback: simple text matching — find vocab terms present in chunk
            chunk_lower = chunk_text.lower()
            entries = []
            matched_keys = []
            for key, entry in self.vocab.items():
                # Match by source term (with spaces instead of underscores)
                source_lower = entry.source.lower() if entry.source else key.replace('_', ' ')
                if source_lower in chunk_lower:
                    entries.append(entry)
                    matched_keys.append(key)
            # Cache results
            self.matched_terms_cache[cache_key] = matched_keys
            if config.debug:
                logger.debug(f"Chunk {s_idx}-{c_idx} (text match): {len(entries)}/{len(self.vocab)} vocab terms matched")
            return entries
        
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
        """Load vocabulary from specific file path using CSV format.
        
        Format: source = target, category, gender, notes
        Fields separated by commas after the = sign.
        """
        import csv
        
        vocab = {}
        
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            # Skip comment lines
            lines = []
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    lines.append(stripped)
            
            if not lines:
                return vocab
            
            for line_num, line in enumerate(lines, 1):
                try:
                    # Parse: source = target, category, gender, notes
                    if '=' not in line:
                        continue
                    
                    parts = line.split('=', 1)
                    source = parts[0].strip()
                    rest = parts[1].strip()
                    
                    if not source or not rest:
                        continue
                    
                    # Parse comma-separated values: target, category, gender, notes
                    csv_reader = csv.reader([rest])
                    try:
                        row = next(csv_reader)
                    except StopIteration:
                        continue
                    
                    if len(row) < 1:
                        continue
                    
                    target = row[0].strip() if len(row) > 0 else ""
                    category = row[1].strip() if len(row) > 1 else ""
                    gender = row[2].strip() if len(row) > 2 else ""
                    notes = row[3].strip() if len(row) > 3 else ""
                    
                    if not source or not target:
                        continue
                    
                    # NO VALIDATION - allow any category and gender values (may be in any language)
                    
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