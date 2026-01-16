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

        self.api_key = os.getenv('API_KEY', 'a132b20c-96be-467f-a15a-ed08aed67345')
        self.base_url = os.getenv('API_BASE', 'http://192.168.0.55:6150/v1')
        self.sys_not_promt = bool(os.getenv('S_PROMT'))
        self.model = os.getenv('MODEL', 'Mistral') # Intruct model for proofreading
        self.temp = float(os.getenv('TEMP', 0.01))
        self.api_timeout = int(os.getenv('TIMEOUT', 6000))
        self.nothink = bool(os.getenv('NOTHINK'))

        self.temp2 = float(os.getenv('TEMP2', 0.7))
        self.api_key2 = os.getenv('API_KEY2', 'a132b20c-96be-467f-a15a-ed08aed67345')
        self.base_url2 = os.getenv('API_BASE2', 'https://api.openai.com/v1')
        self.sys_not_promt2 = bool(os.getenv('S_PROMT2'))
        self.model2 = os.getenv('MODEL2', 'tencent/Hunyuan-MT-7B') # Model for translating 
        self.api_timeout2 = int(os.getenv('TIMEOUT2', 6000))
        self.nothink2 = bool(os.getenv('NOTHINK2'))

        # Third endpoint group (Cover API)
        self.api_key3 = os.getenv('API_KEY3', '')
        self.base_url3 = os.getenv('API_BASE3', '')
        self.sys_not_promt3 = bool(os.getenv('S_PROMT3'))
        self.model3 = os.getenv('MODEL3', 'gpt-image-1.5') # Default to a vision capable model
        self.temp3 = float(os.getenv('TEMP3', 0.5))
        self.api_timeout3 = int(os.getenv('TIMEOUT3', 600))
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
        
        # File defaulted to books/Freedom.fb2 (stripped quotes)
        self.myfile = os.getenv('FILE', 'books/Cargo.fb2')
        if not os.path.isabs(self.myfile):
             self.myfile = str(Path(os.getcwd()) / self.myfile)
             
        # DEBUG defaulted to off
        self.debug = os.getenv('DEBUG', 'off').lower() in ['true', '1', 't', 'on']

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
