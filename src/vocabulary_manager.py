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

import csv
import io
import os
import re
import tempfile
import logging
import fcntl
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from src.config import Config
from src import ner as ner_module
from src import lexicon
from src.character_registry import get_character_registry, Character

config = Config()
logger = logging.getLogger(__name__)

# Languages written without spaces between words, where a "word" is typically
# 1-3 characters (Hangul syllable blocks / CJK ideographs). A min_word_length
# tuned for space-separated alphabetic languages (default 5) would discard
# almost every frequent word in these languages.
_CJK_LANGUAGES = {"ko", "ja", "zh"}


def min_word_length_for(source_lang: str) -> int:
    return 2 if lexicon.lang_code(source_lang) in _CJK_LANGUAGES else 5


def _dic_field(value: str) -> str:
    # Only the first field after "=" can be CSV-quoted: later fields follow
    # ", " and csv.reader (no skipinitialspace) would keep the quotes literally.
    return f'"{value}"' if ',' in value else value


_NAME_PARTICLES = {
    'of', 'the', 'de', 'del', 'della', 'di', 'da', 'von', 'van', 'der', 'den', 'la', 'le',
    'el', 'al', 'bin', 'ibn', 'du', 'des', 'af', 'zu',
}


def looks_like_proper_name(source: str) -> bool:
    """
    True when `source` can be a proper name: every word starts with a capital
    (name particles like "of"/"von" excepted), so "Jain soldier", "submind"
    and "worm fragment" are rejected. Scripts without letter case (CJK, Thai,
    Arabic, ...) have no such signal and always pass.
    """
    words = source.split()
    if not words or not any(c.isupper() or c.islower() for c in source):
        return bool(words)
    named = [w for w in words if w.casefold() not in _NAME_PARTICLES]
    return bool(named) and all(
        not w[0].isalpha() or w[0].isupper() for w in named
    )


class CandidateMatcher:
    """
    Decides what a dictionary candidate reported by the synopsis stage is
    with respect to the entries already known (the .dic file in
    apply_dictionary_candidates, the in-memory vocabulary in
    VocabularyManager.record_dictionary_candidates — both use this class).

    match() returns one of:
    - ('same', ref): the candidate IS an existing entry, written in another
      case or inflected ("Jain nodes" = "Jain node", "Gabbleducks" =
      "gabbleduck"; a name only inflected: "Jains" is "Jain", "Marie" is
      not "Mary");
      a PERSON also by its translated name
      ("김철수 | Чхольсу" = "철수 = Чхольсу");
    - ('covered', terms): the candidate contains existing terms ("Jain node",
      "jain shriek" contain "Jain"): the glossary already translates it, a
      separate entry would only shadow "Jain" with another translation;
    - ('new', None): nothing of it is in the dictionary.

    A hyphen, a space or no separator make different entries: "Jain-tech" is
    not "Jain tech", "gabble-duck" is not "gabbleduck" (lexicon.separators).

    The containment test is lexicon.covering_terms, the same matching rules
    the chunk lookup and the substitution use.
    """

    def __init__(self, source_lang: str):
        self.source_lang = source_lang
        self._by_words: Dict[str, object] = {}
        self._by_target: Dict[str, object] = {}
        self._by_source: Dict[str, object] = {}

    def add(self, source: str, target: str, ref) -> None:
        key = lexicon.word_key(source)
        if key:
            self._by_words.setdefault(key, ref)
        self._by_source.setdefault(source, ref)
        if target:
            self._by_target.setdefault(lexicon.normalize(target).strip(), ref)

    def match(self, cand: Dict[str, str]):
        source = cand['source']
        key = lexicon.word_key(source)
        if key in self._by_words:
            return 'same', self._by_words[key]
        person = cand.get('category', 'PERSON') == 'PERSON'
        # names by inflection only: "Jains" is "Jain", but "Marie" is not
        # "Mary", though both stem to "mari"
        covering = lexicon.covering_terms(source, self._by_source, self.source_lang, exact=person)
        if not lexicon.is_unspaced(source):
            # a term as long as the candidate is the candidate itself. In CJK
            # a shorter word inside a longer one is not the same entry, but
            # still covers it below (龙 covers 龙骑士)
            words, seps = len(lexicon.tokenize(source)), lexicon.separators(source)
            for term in covering:
                if len(lexicon.tokenize(term)) == words and lexicon.separators(term) == seps:
                    return 'same', self._by_source[term]
        if person and cand.get('target'):
            ref = self._by_target.get(lexicon.normalize(cand['target']).strip())
            if ref is not None:
                return 'same', ref
        if covering:
            return 'covered', covering
        return 'new', None


def _by_priority(candidates: List[Dict[str, str]]) -> List[Dict[str, str]]:
    # The shorter candidate first: "Jain" reported together with "Jain node"
    # is added, and then covers "Jain node"
    return sorted(candidates, key=lambda c: lexicon.term_rank(c['source']))


def _merge_into(matcher: CandidateMatcher, candidates: List[Dict[str, str]],
                add, set_gender, where: str = "") -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """
    The one merge loop of the .dic file (apply_dictionary_candidates) and the
    in-memory vocabulary (VocabularyManager._merge_candidates), so the two
    can never follow different rules.

    add(cand) stores a new entry and returns its matcher ref (None: it takes
    no updates later); set_gender(ref, gender) fills an empty gender of an
    existing entry and returns whether it changed anything. Covered
    candidates and common nouns reported as characters are skipped.

    Returns (added, updated) candidates.
    """
    added, updated = [], []
    for cand in _by_priority(candidates):
        category = cand.get('category', 'PERSON')
        verdict, ref = matcher.match(cand)
        if verdict == 'covered':
            logger.info(f"Dictionary{where}: '{cand['source']}' not added, already covered by {ref}")
            continue
        if verdict == 'new':
            if category == 'PERSON' and not looks_like_proper_name(cand['source']):
                continue  # synopsis LLM reported a common noun, not a named character
            matcher.add(cand['source'], cand['target'], add(cand))
            logger.info(f"Dictionary{where}: added {cand['source']} = {cand['target']}, {category}")
            added.append(cand)
            continue
        if ref is not None and category == 'PERSON' and set_gender(ref, cand['gender']):
            updated.append(cand)
    return added, updated


# A gender report makes an entry without a category, or an earlier TERM, a PERSON
_PROMOTED_TO_PERSON = ('', 'TERM')


def apply_dictionary_candidates(dict_file: str, candidates: List[Dict[str, str]],
                                source_lang: Optional[str] = None) -> Tuple[int, int]:
    """
    Write the dictionary candidates reported by the synopsis stage into a .dic.

    What a candidate is decides CandidateMatcher:
    - an existing entry (PERSON): its gender is filled in only when the gender
      field is empty — a gender already in the file was set by the user or an
      earlier chunk and wins. An entry without a category, or one an earlier
      chunk added as TERM, then becomes PERSON. A TERM never touches an
      existing line;
    - covered by existing terms: skipped;
    - new: appended as "source = target, PERSON, gender, " (only a proper
      name, see looks_like_proper_name) or "source = target, TERM, , ".

    Returns (updated, added) counts.
    """
    with open(dict_file, 'r', encoding='utf-8-sig') as f:
        lines = f.read().split('\n')

    matcher = CandidateMatcher(source_lang or config.source_lang)
    rows = {}  # line_idx -> (source, fields)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        source, rest = (p.strip() for p in stripped.split('=', 1))
        fields = [f.strip() for f in next(csv.reader([rest]), [])]
        if not source or not fields:
            continue
        rows[i] = (source, fields)
        matcher.add(source, fields[0], i)

    appended = []

    def add(cand):
        category = cand.get('category', 'PERSON')
        appended.append(f"{cand['source']} = {_dic_field(cand['target'])}, {category}, {cand['gender']}, ")
        return None  # an appended line takes no gender update

    def set_gender(ref, gender):
        source, fields = rows[ref]
        fields += [''] * (4 - len(fields))
        if fields[2]:
            return False  # set by the user or an earlier chunk: it wins
        fields[2] = gender
        if fields[1] in _PROMOTED_TO_PERSON:
            fields[1] = 'PERSON'
        lines[ref] = f"{source} = {_dic_field(fields[0])}, " + ", ".join(fields[1:])
        return True

    _, updated_cands = _merge_into(matcher, candidates, add, set_gender, where=f" {dict_file}")
    updated = len(updated_cands)

    if not updated and not appended:
        return 0, 0

    while lines and not lines[-1].strip():
        lines.pop()
    content = '\n'.join(lines + appended) + '\n'
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(dict_file) or '.', suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp_path, dict_file)
    except Exception:
        os.unlink(tmp_path)
        raise
    return updated, len(appended)


class DictionaryCreatedSignal(Exception):
    """Raised when a new dictionary has been created and the pipeline should stop for user review."""
    def __init__(self, dict_path: str):
        self.dict_path = dict_path
        super().__init__(f"Dictionary created at {dict_path}. Review it, then re-run to start translation.")


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
    
    def __init__(self, book_path: str, dict_file: Optional[str] = None,
                 source_lang: Optional[str] = None, target_lang: Optional[str] = None,
                 country: Optional[str] = None):
        self.book_path = book_path
        # Languages of this book; default to SOURCE_LANG/TARGET_LANG/COUNTRY.
        # The Calibre pipeline passes its run_pipeline() arguments so the
        # dictionary is built and matched for the languages actually translated.
        self.source_lang = source_lang or config.source_lang
        self.target_lang = target_lang or config.target_lang
        self.country = country or config.country
        self.book_dir = os.path.dirname(book_path)
        self.book_name = Path(book_path).stem
        # Explicit dict_file argument > DICTIONARY env/config > auto lookup
        # next to the source file (<book_name>.dic).
        self.dict_file = dict_file or config.dictionary or os.path.join(self.book_dir, f"{self.book_name}.dic")
        
        self.vocab: Dict[str, VocabEntry] = {}
        self.characters: Dict[str, Character] = {}
        self.matched_terms_cache: Dict[Tuple[int, int], List[str]] = {}  # (s_idx, c_idx) -> terms
        # Candidates the synopsis stage added during this run (checkpointed)
        self.session_candidates: List[Dict[str, str]] = []
        # CandidateMatcher over self.vocab, built on first use, reset by load()
        self._matcher: Optional[CandidateMatcher] = None
        
    def initialize(self, source_text: Optional[str] = None) -> Dict[str, VocabEntry]:
        """
        Initialize vocabulary.

        Args:
            source_text: Book text to build a missing dictionary from. When
                None, the text is parsed from book_path (FB2/EPUB/TXT).

        Returns:
            Vocabulary dictionary
            
        Raises:
            DictionaryCreatedSignal: if dictionary was created and needs user review
        """
        if os.path.exists(self.dict_file):
            logger.info(f"Loading vocabulary from {self.dict_file}")
            return self.load()
        else:
            logger.info(f"Dictionary not found. Creating: {self.dict_file}")
            self.build_dictionary(source_text)
            self._extract_characters()
            # Check if auto-continue is enabled
            if getattr(config, 'auto_continue_after_dict', False):
                logger.info("Auto-continue enabled, proceeding without manual review")
                return self.vocab
            else:
                # Signal that dictionary was created and needs review
                raise DictionaryCreatedSignal(self.dict_file)

    def load(self) -> Dict[str, VocabEntry]:
        """Load the .dic file if it exists (empty vocabulary otherwise)."""
        self.vocab = self._load_from_file() if os.path.exists(self.dict_file) else {}
        self.matched_terms_cache.clear()
        self._matcher = None
        self._extract_characters()
        return self.vocab

    def _atomic_write(self, content: str):
        """Write content to dict_file atomically (write to temp, then rename)."""
        dir_path = os.path.dirname(self.dict_file)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(tmp_path, self.dict_file)
        except Exception:
            os.unlink(tmp_path)
            raise

    def build_dictionary(self, source_text: Optional[str] = None,
                         min_count_ner: int = 5, min_count_word: int = 10,
                         include_words: Optional[bool] = None,
                         use_ner: Optional[bool] = None):
        """
        Create the .dic file from the book text with NER + LLM.

        Workflow:
        1. Parse book to extract text (unless source_text is given — the
           Calibre pipeline passes its Markdown, main() the parsed FB2/TXT)
        2. Run NER to find named entities (and, with include_words, frequent
           ordinary words; None = DICT_FREQUENT_WORDS, off by default)
        3. Translate terms with the proofread LLM
        4. Save to .dic file in standard format

        use_ner: None = NER setting; --build-dict passes True because an
        explicit build request must not silently produce an empty template.

        The file is assembled next to dict_file and only renamed into place
        when every chunk is translated: an LLM error or Ctrl-C must not leave
        a partial .dic that the next run would load as a reviewed dictionary.
        """
        if source_text is not None:
            body = source_text
        else:
            from src import fb2_handler, epub_handler, txt_handler

            ext = Path(self.book_path).suffix.lower()
            if ext == '.fb2':
                body, header, footer = fb2_handler.parse_xml(self.book_path)
            elif ext == '.epub':
                body, header, footer = epub_handler.parse_epub(self.book_path)
            else:
                body, header, footer = txt_handler.parse_txt(self.book_path)
        
        if use_ner is None:
            use_ner = config.ner_opt
        if use_ner and not ner_module:
            raise RuntimeError("NER module (spaCy) is not available, cannot build the dictionary")

        # Run NER to extract entities
        if use_ner:
            logger.info("Running NER to extract entities and common words...")
            
            # Use new structured dictionary creation
            extracted_terms = ner_module.create_dictionary_from_text(
                body,
                min_count_ner=min_count_ner,
                min_count_word=min_count_word,
                include_words=include_words,
                min_word_length=min_word_length_for(self.source_lang),
                lang=self.source_lang,
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
                
                building_path = f"{self.dict_file}.building"
                with open(building_path, 'w', encoding='utf-8') as f:
                    f.write(
                        f"# Vocabulary for {self.book_name}\n"
                        f"# Format: source = target, category, gender, notes\n"
                        f"# Generated automatically by NER\n\n"
                    )

                self.vocab.clear()
                total_parsed = 0
                try:
                    for idx, chunk in enumerate(chunks):
                        logger.info(f"Translating chunk {idx + 1}/{len(chunks)} ({len(chunk)} chars)...")
                        vocab_translated = ta.vocabulary(
                            self.source_lang,
                            self.target_lang,
                            chunk,
                            self.country,
                            "proofread"
                        )
                        parsed = self._parse_and_append_chunk(vocab_translated, idx + 1, len(chunks),
                                                              out_path=building_path)
                        total_parsed += parsed
                        logger.info(f"Chunk {idx + 1}: wrote {parsed} entries")
                    os.replace(building_path, self.dict_file)
                except BaseException:
                    self.vocab.clear()
                    if os.path.exists(building_path):
                        os.unlink(building_path)
                    raise

                logger.info(f"Dictionary saved: {self.dict_file} ({total_parsed} total entries)")
            else:
                logger.warning("No terms extracted by NER")
                self._create_template()
        else:
            # Create empty dictionary template
            self._create_template()

    def _parse_and_append_chunk(self, vocab_translated: str, chunk_num: int, total_chunks: int,
                                out_path: Optional[str] = None) -> int:
        """
        Parse LLM response and append entries to the dictionary file in consistent CSV format.
        out_path: file to append to (default dict_file; build_dictionary passes
        its temporary file).
        
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
                # Skip table header rows ("Source | Target | Category") —
                # they are not terms (audit 05-vocabulary: header ended up in the dictionary).
                _header_words = {'source', 'target', 'category', 'original', 'translation',
                                 'term', 'word', 'gender', 'notes', 'перевод', 'термин'}
                for match in matches:
                    source = match[0].strip()
                    target = match[1].strip()
                    category = match[2].strip() if match[2].strip() else "TERM"
                    if source.lower() in _header_words and target.lower() in _header_words:
                        continue
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
            
            # Write in format: source = target, category, gender, notes.
            # CSV-quote fields so commas inside values survive the roundtrip
            # (the reader parses the part after '=' with csv.reader).
            buf = io.StringIO()
            csv.writer(buf, quoting=csv.QUOTE_MINIMAL).writerow(
                [target, category, term.get("gender", ""), term.get("notes", "")]
            )
            new_lines.append(f"{source} = {buf.getvalue().rstrip()}\n")
            
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
        self._locked_append(out_path or self.dict_file, ''.join(new_lines))
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
        seen_words: Dict[str, str] = {}

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
                    
                    # "Jain tech" and "jain tech" are one entry ("Jain-tech"
                    # is another one, lexicon.word_key): the first line wins
                    # (the top of the file is usually the reviewed part), the
                    # others are reported
                    words = lexicon.word_key(source)
                    if words and words in seen_words:
                        logger.warning(f"Line {line_num}: '{source}' duplicates "
                                       f"'{seen_words[words]}', skipping")
                        continue
                    seen_words[words] = source
                    key = source.replace(' ', '_').lower()
                    vocab[key] = VocabEntry(
                        source=source,
                        target=target,
                        category=category,
                        gender=gender,
                        notes=notes
                    )
                    
                except Exception as e:
                    # Note: 'row' may be unbound if the error happened before
                    # csv parsing, so log the raw line instead.
                    logger.warning(f"Error parsing line {line_num}: {line[:80]} - {e}")
        
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

    def record_dictionary_candidates(self, candidates: List[Dict[str, str]]):
        """Grow the dictionary while the book is translated (every format).

        Candidates reported by the synopsis stage go into the in-memory
        vocabulary right away, so the following chunks already get them in
        the prompt and in the substitution. A candidate the dictionary
        already covers is dropped (CandidateMatcher: the same entry in another
        form, or a phrase containing a known term). With spaCy, a one-word
        term the model has a word vector for is an ordinary word of the
        language and is dropped too.

        The .dic file is written only with DICT_AUTO_SAVE (off by default);
        the accepted candidates are kept in session_candidates for the
        checkpoint, so a resumed run keeps them either way.
        """
        if not candidates:
            return
        terms = [c['source'] for c in candidates if c.get('category') == 'TERM']
        if terms and config.ner_opt and ner_module:
            known = ner_module.known_words(terms)
            if known:
                logger.info(f"Dictionary: ordinary words not added as terms: {sorted(known)}")
                candidates = [c for c in candidates
                              if not (c.get('category') == 'TERM' and c['source'] in known)]
        accepted = self._merge_candidates(candidates)
        if accepted and config.dict_auto_save and os.path.exists(self.dict_file):
            updated, added = apply_dictionary_candidates(self.dict_file, accepted, self.source_lang)
            if updated or added:
                logger.info(f"Dictionary {self.dict_file}: gender set for {updated}, added {added} entr(y/ies)")

    def restore_session_candidates(self, candidates: Optional[List[Dict[str, str]]]):
        """Put the candidates of an interrupted run (from its checkpoint)
        back into the in-memory vocabulary. The file is not written: with
        DICT_AUTO_SAVE they are there already, without it they never go."""
        if candidates:
            self._merge_candidates(candidates)

    def _merge_candidates(self, candidates: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Apply the candidates to self.vocab by the rules of
        apply_dictionary_candidates; return the ones that changed it."""
        if self._matcher is None:
            self._matcher = CandidateMatcher(self.source_lang)
            for key, entry in self.vocab.items():
                self._matcher.add(entry.source, entry.target, key)

        def add(cand):
            key = cand['source'].replace(' ', '_').lower()
            self.vocab[key] = VocabEntry(source=cand['source'], target=cand['target'],
                                         category=cand.get('category', 'PERSON'),
                                         gender=cand.get('gender', ''))
            return key

        def set_gender(key, gender):
            entry = self.vocab.get(key)
            if entry is None or entry.gender:
                return False
            entry.gender = gender
            if entry.category in _PROMOTED_TO_PERSON:
                entry.category = 'PERSON'
            return True

        added, updated = _merge_into(self._matcher, candidates, add, set_gender)
        accepted = added + updated
        if accepted:
            self.session_candidates.extend(accepted)
            self.matched_terms_cache.clear()
            self._extract_characters()
        return accepted

    def get_vocab_for_chunk(self, chunk_text: str, s_idx: int, c_idx: int) -> List[VocabEntry]:
        """
        Get vocabulary entries relevant to this chunk.
        
        Same matching for every input format (classic and Calibre pipelines):
        lexical match incl. inflected forms (lexicon.resolve_terms), plus cosine
        similarity of word vectors when NER/spaCy is enabled. GPU or CPU mode
        is selected by availability.
        
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
        
        key_by_source = {(entry.source or key.replace('_', ' ')): key for key, entry in self.vocab.items()}

        if not config.ner_opt or not ner_module:
            # No spaCy: lexical match only (surface forms + Snowball stems,
            # substring for CJK) — see lexicon.find_terms
            matched = lexicon.find_terms(chunk_text, key_by_source, self.source_lang)
            mode = "lexical"
        else:
            # cupy is optional even on a CUDA machine (extra [gpu])
            use_gpu = getattr(ner_module, 'CUPY_AVAILABLE', False)
            if use_gpu:
                try:
                    import torch
                    use_gpu = torch.cuda.is_available()
                except ImportError:
                    use_gpu = False
            match_fn = (ner_module.find_matching_words_with_cosine_similarity if use_gpu
                        else ner_module.find_matching_words_with_cosine_similarity_cpu)
            matched = match_fn(chunk_text, self._vocab_to_ner_format(), self.source_lang)
            mode = "GPU" if use_gpu else "CPU"

        # Higher-priority entries first (lexicon.term_rank: more words, then
        # longer), so the prompt lists the specific entry before the general
        # one; lexicon.resolve_terms already dropped the shadowed ones
        matched = sorted((t for t in matched if t in key_by_source),
                         key=lexicon.term_rank, reverse=True)
        matched_keys = [key_by_source[term] for term in matched]
        self.matched_terms_cache[cache_key] = matched_keys

        if config.debug:
            logger.debug(f"Chunk {s_idx}-{c_idx} ({mode}): {len(matched_keys)}/{len(self.vocab)} vocab terms matched")

        return [self.vocab[k] for k in matched_keys]
    
    def _vocab_to_ner_format(self) -> Dict:
        """Convert vocab to format expected by NER module."""
        result = {}
        for key, entry in self.vocab.items():
            result[key] = {
                self.source_lang: entry.source,
                self.target_lang: entry.target
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
    
    
    
    


# Global manager instance (lazy initialization)
_vocabulary_manager: Optional[VocabularyManager] = None

def get_vocabulary_manager(book_path: str, dict_file: Optional[str] = None,
                           source_lang: Optional[str] = None, target_lang: Optional[str] = None,
                           country: Optional[str] = None) -> VocabularyManager:
    """Get or create vocabulary manager for book.

    dict_file: explicit .dic path (DICTIONARY env/--dictionary CLI override).
    See VocabularyManager.__init__ for precedence and the language arguments.
    The cached instance is reused only for the same book, .dic and languages.
    """
    global _vocabulary_manager
    candidate = VocabularyManager(book_path, dict_file=dict_file, source_lang=source_lang,
                                  target_lang=target_lang, country=country)
    current = _vocabulary_manager
    if (current is None
            or current.book_path != book_path
            or current.dict_file != candidate.dict_file
            or (current.source_lang, current.target_lang, current.country)
            != (candidate.source_lang, candidate.target_lang, candidate.country)):
        _vocabulary_manager = candidate
    return _vocabulary_manager
