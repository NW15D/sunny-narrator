import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _parse_bool_env(name, default='false'):
    """Parse boolean env var correctly. bool('false') == True in Python!"""
    val = os.getenv(name, default)
    return str(val).lower() in ('true', '1', 'on', 'yes')


def _same_local_server(url_a: str, url_b: str) -> bool:
    """Whether two API URLs are one server on this machine or the local
    network (localhost and 127.0.0.1 alike; the path, such as /v1, ignored)."""
    import ipaddress
    from urllib.parse import urlsplit

    def where(url):
        parts = urlsplit(url if '://' in url else f"http://{url}")
        host = (parts.hostname or '').lower()
        if host in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
            host = 'localhost'
        return host, parts.port or (443 if parts.scheme == 'https' else 80)

    a, b = where(url_a), where(url_b)
    if a != b:
        return False
    if a[0] == 'localhost':
        return True
    try:
        return ipaddress.ip_address(a[0]).is_private
    except ValueError:
        return False  # a hosted API by name


def _parse_json_env(name) -> dict:
    """A JSON object from an env var ({} when unset): EXTRA_BODY_* is merged
    into every request body of that model."""
    import json
    raw = os.getenv(name, '').strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"{name} is not valid JSON: {e}") from None
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object, got: {raw}")
    return value


def _parse_numeric_env(name, default, cast=float):
    """Parse numeric env var with fallback to default on invalid values."""
    try:
        return cast(os.getenv(name, default))
    except (ValueError, TypeError):
        logger.warning(f"Invalid {name} value, using default {default}")
        return default


# Language name (as written in SOURCE_LANG/TARGET_LANG) -> ISO 639-1 code.
# Module-level so src/lexicon.py can use it without building a Config.
LANG_CODE_MAP = {
    'russian': 'ru', 'english': 'en', 'french': 'fr', 'german': 'de',
    'spanish': 'es', 'italian': 'it', 'chinese': 'zh', 'japanese': 'ja',
    'dutch': 'nl', 'portuguese': 'pt', 'polish': 'pl', 'ukrainian': 'uk',
    'catalan': 'ca', 'danish': 'da', 'finnish': 'fi', 'swedish': 'sv',
    'norwegian': 'nb', 'korean': 'ko', 'romanian': 'ro', 'greek': 'el',
    'lithuanian': 'lt', 'macedonian': 'mk', 'croatian': 'hr', 'slovenian': 'sl',
    'arabic': 'ar', 'hungarian': 'hu', 'turkish': 'tr', 'indonesian': 'id',
    'hebrew': 'he', 'czech': 'cs', 'no': 'nb',
}


# COUNTRY default by target language: the prompts say "for readers in
# {country}", and a fixed "Россия" turned an English->Turkish run into a
# translation "for readers in Russia". Languages spoken in many countries
# get a neutral "<Language>-speaking countries" (default_country).
_DEFAULT_COUNTRY = {
    'ru': 'Россия', 'tr': 'Türkiye', 'de': 'Deutschland', 'fr': 'France', 'es': 'España',
    'it': 'Italia', 'pt': 'Portugal', 'pl': 'Polska', 'uk': 'Україна', 'nl': 'Nederland',
    'ja': '日本', 'ko': '대한민국', 'zh': '中国', 'cs': 'Česko', 'hu': 'Magyarország',
    'ro': 'România', 'el': 'Ελλάδα', 'fi': 'Suomi', 'sv': 'Sverige', 'da': 'Danmark',
    'nb': 'Norge', 'lt': 'Lietuva', 'hr': 'Hrvatska', 'sl': 'Slovenija', 'mk': 'Северна Македонија',
    'he': 'ישראל', 'id': 'Indonesia', 'ca': 'Catalunya',
}


def default_country(target_lang: str) -> str:
    lang = (target_lang or '').strip().lower()
    code = LANG_CODE_MAP.get(lang, lang)
    return _DEFAULT_COUNTRY.get(code) or f"{lang.capitalize()}-speaking countries"


class Config:
    def __init__(self, env_path: str = None):
        if env_path:
            load_dotenv(env_path)
        else:
            config_dir = Path(__file__).resolve().parent.parent
            load_dotenv(config_dir / ".env")

        # Translation API (translate model)
        self.api_key_translate = os.getenv('API_KEY_TRANSLATE', os.getenv('API_KEY', ''))
        self.base_url_translate = os.getenv('API_BASE_TRANSLATE', os.getenv('API_BASE', 'http://localhost:11434/v1'))
        self.sys_not_promt_translate = os.getenv('S_PROMT_TRANSLATE', os.getenv('S_PROMT', '')).lower() in ('true', '1', 'on')
        self.model_translate = os.getenv('MODEL_TRANSLATE', os.getenv('MODEL', 'Mistral'))
        self.temp_translate = _parse_numeric_env('TEMP_TRANSLATE', os.getenv('TEMP', 0.01))
        self.timeout_translate = _parse_numeric_env('TIMEOUT_TRANSLATE', os.getenv('TIMEOUT', 6000), cast=int)
        # Thinking is off unless asked for: the stages expect the answer
        # itself, and a hosted Qwen 3.6 thinks by default (paid tokens)
        self.nothink_translate = _parse_bool_env('NOTHINK_TRANSLATE', os.getenv('NOTHINK2', 'true'))
        # EXTRA_BODY_*: a JSON object added to every request body, e.g. the
        # OpenRouter provider choice {"provider": {"require_parameters": true}}
        self.extra_body_translate = _parse_json_env('EXTRA_BODY_TRANSLATE')
        # presence_penalty, sent with every request instead of the server's
        # default (llama.cpp with the Qwen preset: 1.5): a stage that writes
        # the text again is penalized for the tokens of a word it just wrote
        # and puts a Latin twin in («сприна» -> «спринa»). REFLECTION writes a
        # list instead and needs the penalty: without it the list repeats
        # until max_tokens (a novel's bench: 2 truncations in 24 chunks
        # at 0, none at 1.5)
        self.presence_penalty_translate = _parse_numeric_env('PRESENCE_PENALTY_TRANSLATE', 0.0)
        
        # Stage-specific temperatures (override general temp_translate/temp_proofread)
        # Stage 1: INITIAL translation
        self.temp_initial = _parse_numeric_env('TEMP_INITIAL', self.temp_translate)
        
        # JSON mode control - use structured JSON for LLM input/output
        # JSON is on by default for all stages; JSON_MODE=false switches to
        # the XML-tag prompts (the DISABLE_JSON_MODE_* switches then apply)
        self.json_mode = os.getenv('JSON_MODE', 'true').lower() in ['true', '1', 't', 'on', 'yes']
        
        # Legacy JSON mode controls (deprecated, ignored unless JSON_MODE=false)
        if self.json_mode:
            # JSON_MODE=true enables JSON for all stages, ignore DISABLE flags
            self.disable_json_mode_translate = False
            self.disable_json_mode_proofread = False
        else:
            self.disable_json_mode_translate = os.getenv('DISABLE_JSON_MODE_TRANSLATE', 'true').lower() in ['true', '1', 't', 'on', 'yes']
            self.disable_json_mode_proofread = os.getenv('DISABLE_JSON_MODE_PROOFREAD', 'true').lower() in ['true', '1', 't', 'on', 'yes']
        # Stage 2: REFLECTION (quality review)
        self.temp_reflection = _parse_numeric_env('TEMP_REFLECTION', 0.4)
        # Stage 3: IMPROVE (apply suggestions)
        self.temp_improve = _parse_numeric_env('TEMP_IMPROVE', 0.4)
        # Stage 4: FINAL_EDIT (proofreading)
        self.temp_final_edit = _parse_numeric_env('TEMP_FINAL_EDIT', 0.15)
        # Stage 5: SYNOPSIS
        self.temp_synopsis = _parse_numeric_env('TEMP_SYNOPSIS', 0.15)
        # GENDER stage (fix of the sentences GENDER_CHECK found)
        self.temp_gender = _parse_numeric_env('TEMP_GENDER', 0.05)

        # Proofread API (proofread model)
        self.api_key_proofread = os.getenv('API_KEY_PROOFREAD', os.getenv('API_KEY2', ''))
        self.base_url_proofread = os.getenv('API_BASE_PROOFREAD', os.getenv('API_BASE2', 'https://api.openai.com/v1'))
        self.sys_not_promt_proofread = os.getenv('S_PROMT_PROOFREAD', os.getenv('S_PROMT2', '')).lower() in ('true', '1', 'on')
        self.model_proofread = os.getenv('MODEL_PROOFREAD', os.getenv('MODEL2', 'tencent/Hunyuan-MT-7B'))
        # The proofread LLM is usable next to the translate one: with FAST_TRANS
        # (GENDER_LLM=auto) the GENDER stage goes to it. Not when it is another
        # model on the same local server (one Ollama, env.sample): a call there
        # swaps the loaded model every chunk with a gender error. A hosted API
        # serving both models swaps nothing.
        self.proofread_configured = (bool(os.getenv('API_BASE_PROOFREAD') or os.getenv('API_BASE2'))
                                     and not (_same_local_server(self.base_url_proofread, self.base_url_translate)
                                              and self.model_proofread != self.model_translate))
        self.temp_proofread = _parse_numeric_env('TEMP_PROOFREAD', os.getenv('TEMP2', 0.7))
        self.timeout_proofread = _parse_numeric_env('TIMEOUT_PROOFREAD', os.getenv('TIMEOUT2', 6000), cast=int)
        self.nothink_proofread = _parse_bool_env('NOTHINK_PROOFREAD', os.getenv('NOTHINK', 'true'))
        self.extra_body_proofread = _parse_json_env('EXTRA_BODY_PROOFREAD')
        self.presence_penalty_proofread = _parse_numeric_env('PRESENCE_PENALTY_PROOFREAD', 0.0)
        self.presence_penalty_reflection = _parse_numeric_env('PRESENCE_PENALTY_REFLECTION', 1.5)

        # Images API (Cover API)
        self.api_key_images = os.getenv('API_KEY_IMAGES', os.getenv('API_KEY3', ''))
        self.base_url_images = os.getenv('API_BASE_IMAGES', os.getenv('API_BASE3', ''))
        self.model_images = os.getenv('MODEL_IMAGES', os.getenv('MODEL3', 'gpt-image-1.5'))
        self.timeout_images = _parse_numeric_env('TIMEOUT_IMAGES', os.getenv('TIMEOUT3', 600), cast=int)

        # DICTIONARY: explicit path to the .dic vocabulary file to use for
        # translation, overriding the automatic <book_name>.dic lookup next
        # to the source file (VocabularyManager — used by both pipelines).
        # Empty/unset keeps the default auto-detection. Also settable per run
        # via --dictionary (see app.py argparse block).
        self.dictionary = os.getenv('DICTIONARY', '') or None
        self.source_lang = os.getenv('SOURCE_LANG', 'english')
        self.target_lang = os.getenv('TARGET_LANG', 'russian')
        
        # Mapping for default nermodel based on source_lang (largest non-transformer models) for dictionary
        self.lang_model_map = {
            "english": "en_core_web_lg", "en": "en_core_web_lg",
            "russian": "ru_core_news_lg", "ru": "ru_core_news_lg",
            "french": "fr_core_news_lg", "fr": "fr_core_news_lg",
            "german": "de_core_news_lg", "de": "de_core_news_lg",
            "spanish": "es_core_news_lg", "es": "es_core_news_lg",
            "italian": "it_core_news_lg", "it": "it_core_news_lg",
            "chinese": "zh_core_web_lg", "zh": "zh_core_web_lg",
            "japanese": "ja_core_news_lg", "ja": "ja_core_news_lg",
            "dutch": "nl_core_news_lg", "nl": "nl_core_news_lg",
            "portuguese": "pt_core_news_lg", "pt": "pt_core_news_lg",
            "polish": "pl_core_news_lg", "pl": "pl_core_news_lg",
            "ukrainian": "uk_core_news_lg", "uk": "uk_core_news_lg",
            "catalan": "ca_core_news_lg", "ca": "ca_core_news_lg",
            "danish": "da_core_news_lg", "da": "da_core_news_lg",
            "finnish": "fi_core_news_lg", "fi": "fi_core_news_lg",
            "swedish": "sv_core_news_lg", "sv": "sv_core_news_lg",
            "norwegian": "nb_core_news_lg", "nb": "nb_core_news_lg",
            "korean": "ko_core_news_lg", "ko": "ko_core_news_lg",
            "romanian": "ro_core_news_lg", "ro": "ro_core_news_lg",
            "greek": "el_core_news_lg", "el": "el_core_news_lg",
            "lithuanian": "lt_core_news_lg", "lt": "lt_core_news_lg",
            "macedonian": "mk_core_news_lg", "mk": "mk_core_news_lg",
            "croatian": "hr_core_news_lg", "hr": "hr_core_news_lg",
            "slovenian": "sl_core_news_lg", "sl": "sl_core_news_lg"
        }
        
        # NER: on unless NER=false
        self.ner_opt = os.getenv('NER', 'True').lower() in ['true', '1', 't']
        # DICT_FREQUENT_WORDS: also put frequent ordinary words (not named
        # entities) into a new dictionary. Off by default: they flood the .dic
        # with translations of common vocabulary and pin the LLM to one
        # context-free translation of every such word.
        self.dict_frequent_words = os.getenv('DICT_FREQUENT_WORDS', 'false').lower() in ['true', '1', 't', 'on', 'yes']
        # DICT_AUTO_SAVE: write the names and coined terms found while
        # translating into the .dic file. Off by default: they still join the
        # in-memory dictionary for the rest of the run (and its resume), but
        # the reviewed .dic stays as the user left it.
        self.dict_auto_save = os.getenv('DICT_AUTO_SAVE', 'false').lower() in ['true', '1', 't', 'on', 'yes']
        # DICT_CHECK: before a translation the dictionary is checked against
        # the book (src/dict_review.py): categories and genders by the NER of
        # the source and its pronouns. DICT_AUTOFIX: the sure findings are
        # applied for the run (the .dic is not changed; --no-autofix turns it
        # off). DICT_FORCE: without autofix the run translates by the .dic as
        # it is, a contradiction is only reported; false stops the run.
        # SPACY_AUTO_DOWNLOAD: a missing spaCy model is downloaded on first use
        # (the dictionary check, the gender check, NER); false - only logged
        self.spacy_auto_download = _parse_bool_env('SPACY_AUTO_DOWNLOAD', 'true')
        self.dict_check = _parse_bool_env('DICT_CHECK', 'true')
        self.dict_autofix = _parse_bool_env('DICT_AUTOFIX', 'true')
        self.dict_force = _parse_bool_env('DICT_FORCE', 'true')  # --force
        self.country = os.getenv('COUNTRY') or default_country(self.target_lang)
        
        # Determine default model from mapping if not specified in ENV
        # A language without its own spaCy pipeline (Turkish, Hungarian,
        # Arabic, ...) gets the multilingual NER model, not the English one
        default_model = self.lang_model_map.get(self.source_lang.lower(), 'xx_ent_wiki_sm')
        self.nermodel = os.getenv('NERMODEL') or default_model  # empty = by SOURCE_LANG
        self.fast_trans = os.getenv('FAST_TRANS', 'false').lower() in ['true', '1', 'on', 'yes']
        # GENDER_CHECK: the GENDER stage after the last text stage (both modes,
        # FAST_TRANS too): "fix" - a sentence where a dictionary character's
        # predicate has the other gender goes to the LLM for a fix; "warn" -
        # only logged; "off".
        gender_check = os.getenv('GENDER_CHECK', 'fix').strip().lower()
        self.gender_check = gender_check if gender_check in ('fix', 'warn', 'off') else 'fix'
        # GENDER_LLM: which LLM gets the GENDER call. "auto": the proofread
        # LLM, with FAST_TRANS too when API_BASE_PROOFREAD is set; "translate"
        # or "proofread" always that one (FAST_TRANS with only the translate
        # model loaded: "translate", or every fix reloads the other model)
        gender_llm = os.getenv('GENDER_LLM', 'auto').strip().lower()
        self.gender_llm = gender_llm if gender_llm in ('auto', 'translate', 'proofread') else 'auto'
        # PARALLEL_STAGES: 1 = one chunk at a time; 2 = translate stages of the next
        # chunk overlap with the proofread stages of this one (needs the two LLMs
        # on separate GPUs). More than 2 gains nothing: one request per GPU.
        self.parallel_stages = 2 if _parse_numeric_env('PARALLEL_STAGES', 1, cast=int) >= 2 else 1
        self.max_len_chunk = _parse_numeric_env('MAX_LEN_CHUNK', 8192, cast=int)
        self.length_check_threshold = _parse_numeric_env('LENGTH_CHECK_THRESHOLD', 20, cast=int)
        
        # FILE: the book to translate (relative paths are resolved from the CWD)
        self.myfile = os.getenv('FILE', 'books/ExampleBook.fb2')
        if not os.path.isabs(self.myfile):
             self.myfile = str(Path(os.getcwd()) / self.myfile)
             
        # DEBUG defaulted to off
        self.debug = os.getenv('DEBUG', 'off').lower() in ['true', '1', 't', 'on']
        
        # LLM Logging configuration
        self.llm_logging_enabled = os.getenv('LLM_LOGGING', 'false').lower() in ['true', '1', 't', 'on', 'yes']
        self.llm_logging_dir = os.getenv('LLM_LOGGING_DIR', 'logs')

        # Output format (default: fb2). Classic pipeline (FB2/TXT input) writes
        # fb2 or epub; the Calibre pipeline (EPUB/DOCX/PDF input) epub, docx or pdf.
        # app.py checks the value against the pipeline that is actually used.
        self.output_format = os.getenv('OUTPUT_FORMAT', 'fb2').lower()
        if self.output_format not in ['fb2', 'epub', 'docx', 'pdf']:
            self.output_format = 'fb2'
        
        # FB2 auto-repair of the finished book (default: true). Only acts on a book
        # that fails schema validation and never changes its text.
        self.fb2_auto_repair = os.getenv('FB2_AUTO_REPAIR', 'true').lower() in ['true', '1', 't', 'on', 'yes']

        # Calibre pipeline: pandoc/ebook-convert are run on a whole book, so
        # large books need batching + timeouts instead of one unbounded
        # in-memory conversion (see src/calibre_pipeline.py:build_output).
        # PANDOC_BATCH_CHARS: split markdown into pandoc-sized batches instead
        # of converting the whole book in a single pypandoc.convert_text call.
        self.pandoc_batch_chars = _parse_numeric_env('PANDOC_BATCH_CHARS', 200000, cast=int)
        # PANDOC_TIMEOUT/CALIBRE_TIMEOUT: seconds before the corresponding
        # subprocess is killed instead of hanging forever.
        self.pandoc_timeout = _parse_numeric_env('PANDOC_TIMEOUT', 900, cast=int)
        self.calibre_timeout = _parse_numeric_env('CALIBRE_TIMEOUT', 1800, cast=int)
        # MAX_FAILED_CHUNK_RATIO: fraction of failed translation chunks above
        # which translate_chunks logs an ERROR (Calibre pipeline). Reporting is
        # non-blocking: the book is still assembled with the original text in
        # the failed places; any failure always produces at least a warning.
        self.max_failed_chunk_ratio = _parse_numeric_env('MAX_FAILED_CHUNK_RATIO', 0.0, cast=float)
        # DEBUG_HTTP: when off (default), suppresses noisy DEBUG logging from
        # pypandoc/httpx/httpcore/openai even when DEBUG=on, and stops pypandoc
        # from double-logging (it attaches its own handler and propagates).
        self.debug_http = os.getenv('DEBUG_HTTP', 'off').lower() in ['true', '1', 't', 'on', 'yes']

        # Language name -> ISO 639-1 code (metadata, output-file marker, src/lexicon.py)
        self.lang_code_map = dict(LANG_CODE_MAP)

        # Validate API keys
        if not self.api_key_translate:
            logger.warning("API_KEY_TRANSLATE not set — LLM calls will fail")
        if not self.api_key_proofread:
            logger.warning("API_KEY_PROOFREAD not set — proofread LLM calls will fail")

        # Load prompts
        self.prompts = self._load_prompts()

    def lang_marker(self, lang: str = None) -> str:
        """Language marker of output file names, shared by both pipelines:
        the ISO code of `lang` (default TARGET_LANG), "russian" -> "ru";
        an unknown language stays as written, lowercased."""
        lang = (lang or self.target_lang or '').strip().lower()
        return self.lang_code_map.get(lang, lang)

    def _load_prompts(self):
        import json
        prompts_path = Path(__file__).resolve().parent / "prompts.json"
        try:
            with open(prompts_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            if hasattr(self, 'debug') and self.debug:
                print(f"Error loading prompts: {e}")
            return {}

    def get_prompt(self, category, key, **kwargs):
        template = self.prompts.get(category, {}).get(key, "")
        if template:
            try:
                return template.format(**kwargs)
            except (KeyError, IndexError, ValueError) as e:
                # The model would get the raw template with "{target_lang}"
                # left in it: tests/test_prompts.py guards against this
                logger.warning(f"Prompt {category}.{key} is not formatted: missing or bad placeholder {e}")
                return template
        return ""
