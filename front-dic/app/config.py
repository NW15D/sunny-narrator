import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    def __init__(self):
        self.data_dir = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
        self.db_path = self.data_dir / "app.db"
        self.uploads_dir = self.data_dir / "uploads"

        self.min_file_size_bytes = int(os.getenv("MIN_FILE_SIZE_BYTES", "1"))
        self.max_file_size_bytes = int(os.getenv("MAX_FILE_SIZE_BYTES", str(32 * 1024 * 1024)))

        self.session_secret = os.getenv("SESSION_SECRET", "dev-insecure-secret-change-me")

        self.email_provider = os.getenv("EMAIL_PROVIDER", "console")
        self.resend_api_key = os.getenv("RESEND_API_KEY", "")
        self.resend_from = os.getenv("RESEND_FROM", "noreply@example.com")
        self.smtp2go_api_key = os.getenv("SMTP2GO_API_KEY", "")
        self.smtp2go_from = os.getenv("SMTP2GO_FROM", "noreply@example.com")

        self.code_ttl_minutes = int(os.getenv("CODE_TTL_MINUTES", "15"))
        self.code_max_attempts = int(os.getenv("CODE_MAX_ATTEMPTS", "5"))

        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)


config = Config()
