"""Абстракция отправки email — по образцу того, как в родительском проекте
независимые LLM-провайдеры переключаются через .env (src/config.py).
Провайдер выбирается EMAIL_PROVIDER=console|resend|smtp2go, без изменений
в вызывающем коде (app/routers/auth_api.py)."""

import json
import logging
import smtplib
from email.mime.text import MIMEText
from urllib import request as urlrequest
from urllib.error import URLError

from app.config import config

logger = logging.getLogger("dictionary_hub.email")


class EmailSender:
    def send_code(self, to_email: str, code: str) -> None:
        raise NotImplementedError


class ConsoleEmailSender(EmailSender):
    """Провайдер по умолчанию: без реальных ключей, код только в лог —
    удобно для локальной разработки и первого прогона на сервере."""

    def send_code(self, to_email: str, code: str) -> None:
        logger.warning("[EMAIL_PROVIDER=console] код подтверждения для %s: %s", to_email, code)


class ResendEmailSender(EmailSender):
    def send_code(self, to_email: str, code: str) -> None:
        payload = json.dumps(
            {
                "from": config.resend_from,
                "to": [to_email],
                "subject": "Код подтверждения — Sunny Narrator Dictionary Hub",
                "text": f"Ваш код подтверждения: {code}\nОн действителен {config.code_ttl_minutes} минут.",
            }
        ).encode("utf-8")
        req = urlrequest.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {config.resend_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=10) as resp:
                resp.read()
        except URLError as e:
            logger.error("Не удалось отправить письмо через Resend: %s", e)
            raise


class Smtp2GoEmailSender(EmailSender):
    """SMTP2GO через прямой SMTP (порт 2525) — проще их REST API и не
    требует дополнительных зависимостей поверх stdlib smtplib."""

    def send_code(self, to_email: str, code: str) -> None:
        msg = MIMEText(
            f"Ваш код подтверждения: {code}\nОн действителен {config.code_ttl_minutes} минут.",
            _charset="utf-8",
        )
        msg["Subject"] = "Код подтверждения — Sunny Narrator Dictionary Hub"
        msg["From"] = config.smtp2go_from
        msg["To"] = to_email
        with smtplib.SMTP("mail.smtp2go.com", 2525, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(config.smtp2go_from, config.smtp2go_api_key)
            smtp.send_message(msg)


def get_email_sender() -> EmailSender:
    provider = config.email_provider
    if provider == "resend":
        return ResendEmailSender()
    if provider == "smtp2go":
        return Smtp2GoEmailSender()
    return ConsoleEmailSender()
