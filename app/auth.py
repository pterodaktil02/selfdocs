# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.paths import DATA_DIR

COOKIE_NAME = "selfdocs_session"
CSRF_COOKIE_NAME = "selfdocs_csrf"
SESSION_TTL = 12 * 60 * 60
LOGIN_WINDOW = 5 * 60
LOGIN_LIMIT = 5
MIN_PASSWORD_LENGTH = 6

USERNAME_PATH = DATA_DIR / "admin-username.txt"
PASSWORD_HASH_PATH = DATA_DIR / "admin-password.hash"
SESSION_SECRET_PATH = DATA_DIR / ".session-secret"

_password_hasher = PasswordHasher()
_failed_logins: dict[str, deque[float]] = defaultdict(deque)


@dataclass
class AuthRuntime:
    secret: bytes
    secure_cookie: bool


def _write_private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _read_or_create_secret(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    value = secrets.token_hex(32)
    _write_private(path, value)
    return value


def _migrate_legacy_credentials() -> None:
    """Preserve existing installations while fresh installs use /setup."""
    legacy_plain = DATA_DIR / "admin-password.txt"
    bootstrap_plain = DATA_DIR / "initial-admin-password.txt"

    if legacy_plain.exists() and not PASSWORD_HASH_PATH.exists():
        password = legacy_plain.read_text(encoding="utf-8").strip()
        _write_private(PASSWORD_HASH_PATH, _password_hasher.hash(password))
        legacy_plain.unlink()

    if PASSWORD_HASH_PATH.exists() and not USERNAME_PATH.exists():
        username = os.environ.get("SELFDOCS_USERNAME", "admin").strip() or "admin"
        _write_private(USERNAME_PATH, username)

    # Old bootstrap file is no longer part of the normal workflow. Keep it only
    # until credentials are known to exist, then remove the plaintext secret.
    if PASSWORD_HASH_PATH.exists() and USERNAME_PATH.exists() and bootstrap_plain.exists():
        bootstrap_plain.unlink()

    # Optional unattended bootstrap for deployments that explicitly provide
    # both values. A fresh interactive install still goes through /setup.
    supplied_password = os.environ.get("SELFDOCS_PASSWORD", "").strip()
    supplied_username = os.environ.get("SELFDOCS_USERNAME", "").strip()
    if supplied_password and not auth_configured():
        set_credentials(supplied_username or "admin", supplied_password)


def load_auth_runtime() -> AuthRuntime:
    secret_text = os.environ.get("SELFDOCS_SESSION_SECRET", "").strip()
    if not secret_text:
        secret_text = _read_or_create_secret(SESSION_SECRET_PATH)
    return AuthRuntime(
        secret=secret_text.encode("utf-8"),
        secure_cookie=os.environ.get("SELFDOCS_COOKIE_SECURE", "0") == "1",
    )


def auth_configured() -> bool:
    return USERNAME_PATH.is_file() and PASSWORD_HASH_PATH.is_file()


def current_username() -> str | None:
    if not USERNAME_PATH.exists():
        return None
    value = USERNAME_PATH.read_text(encoding="utf-8").strip()
    return value or None


def current_password_hash() -> str | None:
    if not PASSWORD_HASH_PATH.exists():
        return None
    value = PASSWORD_HASH_PATH.read_text(encoding="utf-8").strip()
    return value or None


def validate_username(username: str) -> str:
    username = username.strip()
    if not username:
        raise ValueError("Имя пользователя не может быть пустым.")
    if len(username) > 100:
        raise ValueError("Имя пользователя слишком длинное.")
    if any(character in username for character in "\r\n\t"):
        raise ValueError("Имя пользователя содержит недопустимые символы.")
    return username


def validate_new_password(password: str, confirmation: str | None = None) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Пароль должен содержать не менее {MIN_PASSWORD_LENGTH} символов."
        )
    if confirmation is not None and password != confirmation:
        raise ValueError("Пароли не совпадают.")
    return password


def set_credentials(username: str, password: str) -> None:
    username = validate_username(username)
    validate_new_password(password)
    _write_private(USERNAME_PATH, username)
    _write_private(PASSWORD_HASH_PATH, _password_hasher.hash(password))


def change_credentials(
    current_password: str,
    new_username: str,
    new_password: str = "",
    new_password_confirmation: str = "",
) -> str:
    username = current_username()
    if username is None or not credentials_valid(username, current_password):
        raise ValueError("Текущий пароль указан неверно.")

    new_username = validate_username(new_username)
    password_hash = current_password_hash()
    if password_hash is None:
        raise ValueError("Учетные данные не настроены.")

    if new_password or new_password_confirmation:
        validate_new_password(new_password, new_password_confirmation)
        password_hash = _password_hasher.hash(new_password)

    _write_private(USERNAME_PATH, new_username)
    _write_private(PASSWORD_HASH_PATH, password_hash)
    rotate_session_secret()
    return new_username


def credentials_valid(username: str, password: str) -> bool:
    expected_username = current_username()
    password_hash = current_password_hash()
    if expected_username is None or password_hash is None:
        return False
    if not hmac.compare_digest(
        username.encode("utf-8"),
        expected_username.encode("utf-8"),
    ):
        return False
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def login_allowed(key: str) -> bool:
    now = time.monotonic()
    attempts = _failed_logins[key]
    while attempts and attempts[0] < now - LOGIN_WINDOW:
        attempts.popleft()
    return len(attempts) < LOGIN_LIMIT


def record_login_failure(key: str) -> None:
    _failed_logins[key].append(time.monotonic())


def clear_login_failures(key: str) -> None:
    _failed_logins.pop(key, None)


def rotate_session_secret() -> None:
    value = secrets.token_hex(32)
    _write_private(SESSION_SECRET_PATH, value)
    AUTH.secret = value.encode("utf-8")


def make_session_token(username: str) -> str:
    expires = int(time.time()) + SESSION_TTL
    payload = f"{username}:{expires}"
    signature = hmac.new(AUTH.secret, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def session_user(token: str | None) -> str | None:
    if not token:
        return None
    try:
        username, expires_text, signature = token.rsplit(":", 2)
        expires = int(expires_text)
    except (ValueError, TypeError):
        return None
    if expires < int(time.time()):
        return None
    payload = f"{username}:{expires}"
    expected = hmac.new(AUTH.secret, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    configured_username = current_username()
    if configured_username is None or not hmac.compare_digest(
        username.encode("utf-8"), configured_username.encode("utf-8")
    ):
        return None
    return username


def make_csrf_token(session_token: str | None = None) -> str:
    nonce = secrets.token_urlsafe(24)
    binding = session_token or "anonymous"
    payload = f"{binding}:{nonce}"
    signature = hmac.new(AUTH.secret, payload.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{signature}"


def csrf_valid(
    value: str | None,
    cookie_value: str | None,
    session_token: str | None = None,
) -> bool:
    if not value or not cookie_value or not hmac.compare_digest(value, cookie_value):
        return False
    try:
        nonce, signature = value.rsplit(".", 1)
    except ValueError:
        return False
    binding = session_token or "anonymous"
    payload = f"{binding}:{nonce}"
    expected = hmac.new(AUTH.secret, payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def csrf_token(request) -> str:
    return request.state.csrf_token


def safe_next_url(value: str | None) -> str:
    """Allow only local absolute application paths."""
    if not value:
        return "/"
    value = value.strip()
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    lowered = value.casefold()
    if (
        "://" in lowered
        or lowered.startswith("/%5c")
        or lowered.startswith("/%2f")
    ):
        return "/"
    return value


AUTH = load_auth_runtime()
_migrate_legacy_credentials()
