"""Хэширование паролей и кодов через hashlib.pbkdf2_hmac из stdlib —
осознанный выбор вместо argon2-cffi/bcrypt: ноль C-расширений, ставится
без компилятора на минимальном Ubuntu-сервере. Если нагрузка вырастет,
меняется только этот файл."""

import hashlib
import hmac
import os
import secrets

_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return hmac.compare_digest(dk.hex(), hash_hex)


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)
