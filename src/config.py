import os
from pathlib import Path
from dotenv import load_dotenv

class Config:
    def __init__(self, env_path: str = None):
        if env_path:
            load_dotenv(env_path)
        else:
            config_dir = Path(__file__).resolve().parent.parent
            load_dotenv(config_dir / ".env")

        # Translation API (Primary/Big model)
        self.api_key_translate = os.getenv('API_KEY_TRANSLATE', os.getenv('API_KEY', 'a132b20c-96be-467f-a15a-ed08aed67345'))
        self.base_url_translate = os.getenv('API_BASE_TRANSLATE', os.getenv('API_BASE', 'http://192.168.0.55:6150/v1'))
        self.sys_not_promt_translate = bool(os.getenv('S_PROMT_TRANSLATE', os.getenv('S_PROMT')))
        self.model_translate = os.getenv('MODEL_TRANSLATE', os.getenv('MODEL', 'Mistral'))
        self.temp_translate = float(os.getenv('TEMP_TRANSLATE', os.getenv('TEMP', 0.01)))
        self.timeout_translate = int(os.getenv('TIMEOUT_TRANSLATE', os.getenv('TIMEOUT', 6000)))
        self.nothink_translate = bool(os.getenv('NOTHINK_TRANSLATE', os.getenv('NOTHINK2')))
        
        # Stage-specific temperatures (override general temp_translate/temp_proofread)
        # Stage 1: INITIAL translation
        self.temp_initial = float(os.getenv('TEMP_INITIAL', self.temp_translate))
        
        # JSON mode control - use structured JSON for LLM input/output
        # Default: false (disabled) - use traditional XML tags
        self.json_mode = os.getenv('JSON_MODE', 'false').lower() in ['true', '1', 't', 'on', 'yes']
        
        # Legacy JSON mode controls (deprecated, use JSON_MODE instead)
        self.disable_json_mode_translate = os.getenv('DISABLE_JSON_MODE_TRANSLATE', 'true').lower() in ['true', '1', 't', 'on', 'yes']
        self.disable_json_mode_proofread = os.getenv('DISABLE_JSON_MODE_PROOFREAD', 'true').lower() in ['true', '1', 't', 'on', 'yes']
        # Stage 2: REFLECTION (quality review)
        self.temp_reflection = float(os.getenv('TEMP_REFLECTION', 0.4))
        # Stage 3: IMPROVE (apply suggestions)
        self.temp_improve = float(os.getenv('TEMP_IMPROVE', 0.4))
        # Stage 4: FINAL_EDIT (proofreading)
        self.temp_final_edit = float(os.getenv('TEMP_FINAL_EDIT', 0.15))
        # Stage 5: SYNOPSIS
        self.temp_synopsis = float(os.getenv('TEMP_SYNOPSIS', 0.15))

        # Proofread API (Secondary/Small model)
        self.api_key_proofread = os.getenv('API_KEY_PROOFREAD', os.getenv('API_KEY2', 'a132b20c-96be-467f-a15a-ed08aed67345'))
        self.base_url_proofread = os.getenv('API_BASE_PROOFREAD', os.getenv('API_BASE2', 'https://api.openai.com/v1'))
        self.sys_not_promt_proofread = bool(os.getenv('S_PROMT_PROOFREAD', os.getenv('S_PROMT2')))
        self.model_proofread = os.getenv('MODEL_PROOFREAD', os.getenv('MODEL2', 'tencent/Hunyuan-MT-7B'))
        self.temp_proofread = float(os.getenv('TEMP_PROOFREAD', os.getenv('TEMP2', 0.7)))
        self.timeout_proofread = int(os.getenv('TIMEOUT_PROOFREAD', os.getenv('TIMEOUT2', 6000)))
        self.nothink_proofread = bool(os.getenv('NOTHINK_PROOFREAD', os.getenv('NOTHINK')))

        # Images API (Cover API)
        self.api_key_images = os.getenv('API_KEY_IMAGES', os.getenv('API_KEY3', ''))
        self.base_url_images = os.getenv('API_BASE_IMAGES', os.getenv('API_BASE3', ''))
        self.sys_not_promt_images = bool(os.getenv('S_PROMT_IMAGES', os.getenv('S_PROMT3')))
        self.model_images = os.getenv('MODEL_IMAGES', os.getenv('MODEL3', 'gpt-image-1.5'))
        self.temp_images = float(os.getenv('TEMP_IMAGES', os.getenv('TEMP3', 0.5)))
        self.timeout_images = int(os.getenv('TIMEOUT_IMAGES', os.getenv('TIMEOUT3', 600)))
        self.cover_prompt = os.getenv('COVER_PROMPT', '')
        
        self.example = os.getenv('EXAMPLE', '')
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
        
        # NER defaulted to True in .env
        self.ner_opt = os.getenv('NER', 'True').lower() in ['true', '1', 't']
        self.country = os.getenv('COUNTRY', 'Россия')
        
        # Determine default model from mapping if not specified in ENV
        default_model = self.lang_model_map.get(self.source_lang.lower(), 'en_core_web_lg')
        self.nermodel = os.getenv('NERMODEL', default_model)
        self.fast_trans = os.getenv('FAST_TRANS', 'on').lower() in ['true', '1', 'on', 'yes']
        self.concurrent_limit = int(os.getenv('CONCURRENT_LIMIT', 1))
        self.short = os.getenv('SHORT')
        self.max_len_chunk = int(os.getenv('MAX_LEN_CHUNK', 8192))
        self.length_check_threshold = int(os.getenv('LENGTH_CHECK_THRESHOLD', 20))
        
        # File defaulted to books/Freedom.fb2 (stripped quotes)
        self.myfile = os.getenv('FILE', 'books/Cargo.fb2')
        if not os.path.isabs(self.myfile):
             self.myfile = str(Path(os.getcwd()) / self.myfile)
             
        # DEBUG defaulted to off
        self.debug = os.getenv('DEBUG', 'off').lower() in ['true', '1', 't', 'on']
        
        # LLM Logging configuration
        self.llm_logging_enabled = os.getenv('LLM_LOGGING', 'false').lower() in ['true', '1', 't', 'on', 'yes']
        self.llm_logging_dir = os.getenv('LLM_LOGGING_DIR', 'logs')

        # Output format: 'fb2' or 'epub' (default: fb2)
        self.output_format = os.getenv('OUTPUT_FORMAT', 'fb2').lower()
        if self.output_format not in ['fb2', 'epub']:
            self.output_format = 'fb2'
        
        # FB2 auto-repair: write _fixed version alongside original (default: false)
        self.fb2_auto_repair = os.getenv('FB2_AUTO_REPAIR', 'false').lower() in ['true', '1', 't', 'on', 'yes']

        # Load prompts
        self.prompts = self._load_prompts()

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
            except KeyError as e:
                if self.debug:
                    print(f"Missing variable for prompt {category}.{key}: {e}")
                return template
        return ""
