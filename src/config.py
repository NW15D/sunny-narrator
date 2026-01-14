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
        self.model = os.getenv('MODEL', 'Mistral')
        self.temp = float(os.getenv('TEMP', 0.01))
        self.api_timeout = int(os.getenv('TIMEOUT', 6000))
        self.nothink = bool(os.getenv('NOTHINK'))

        self.temp2 = float(os.getenv('TEMP2', 0.7))
        self.api_key2 = os.getenv('API_KEY2', 'a132b20c-96be-467f-a15a-ed08aed67345')
        self.base_url2 = os.getenv('API_BASE2', 'http://192.168.0.55:6155/v1')
        self.sys_not_promt2 = bool(os.getenv('S_PROMT2'))
        self.model2 = os.getenv('MODEL2', 'tencent/Hunyuan-MT-7B')
        self.api_timeout2 = int(os.getenv('TIMEOUT2', 6000))
        self.nothink2 = bool(os.getenv('NOTHINK2'))

        # Third endpoint group (Cover API)
        self.api_key3 = os.getenv('API_KEY3', '') #sk-WuUzNIbNLdje6GHjyZrbh66trdAC9T2O')
        self.base_url3 = os.getenv('API_BASE3', '') #https://api.proxyapi.ru/openai/v1')
        self.sys_not_promt3 = bool(os.getenv('S_PROMT3'))
        self.model3 = os.getenv('MODEL3', 'gpt-image-1.5') # Default to a vision capable model
        self.temp3 = float(os.getenv('TEMP3', 0.5))
        self.api_timeout3 = int(os.getenv('TIMEOUT3', 600))
        self.cover_prompt = os.getenv('COVER_PROMPT', '')
        
        self.example = os.getenv('EXAMPLE', '')
        self.source_lang = os.getenv('SOURCE_LANG', 'english')
        self.target_lang = os.getenv('TARGET_LANG', 'russian')
        
                
        # NER defaulted to True in .env
        self.ner_opt = os.getenv('NER', 'True').lower() in ['true', '1', 't']
        self.country = os.getenv('COUNTRY', 'Россия')
        self.nermodel = os.getenv('NERMODEL', 'en_core_web_lg')
        self.short = os.getenv('SHORT')
        self.max_len_chunk = int(os.getenv('MAX_LEN_CHUNK', 8192))
        
        # File defaulted to books/Freedom.fb2 (stripped quotes)
        self.myfile = os.getenv('FILE', 'books/Cargo.fb2')
        if not os.path.isabs(self.myfile):
             self.myfile = str(Path(os.getcwd()) / self.myfile)
             
        # DEBUG defaulted to 1
        self.debug = os.getenv('DEBUG', '1').lower() in ['true', '1', 't']

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
