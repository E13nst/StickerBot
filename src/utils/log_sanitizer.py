import logging
import re
from collections.abc import Mapping
from typing import Any

_REDACTED = "***REDACTED***"

_BOT_TOKEN_IN_URL_RE = re.compile(r"(https://api\.telegram\.org/bot)([0-9]{6,}:[A-Za-z0-9_-]{20,})")
_BOT_TOKEN_RE = re.compile(r"\b([0-9]{6,}:[A-Za-z0-9_-]{20,})\b")
_AUTH_BEARER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)([A-Za-z0-9._~+/\-=]+)")
_TELEGRAM_SECRET_HEADER_RE = re.compile(r"(?i)(x-telegram-bot-api-secret-token\s*[:=]\s*)([^,\s]+)")

_SENSITIVE_HEADERS = {
    "authorization",
    "x-telegram-bot-api-secret-token",
    "cookie",
    "set-cookie",
    "x-api-key",
}


def sanitize_text(value: str) -> str:
    """Скрывает секреты в произвольной строке логов."""
    sanitized = _BOT_TOKEN_IN_URL_RE.sub(r"\1" + _REDACTED, value)
    sanitized = _AUTH_BEARER_RE.sub(r"\1" + _REDACTED, sanitized)
    sanitized = _TELEGRAM_SECRET_HEADER_RE.sub(r"\1" + _REDACTED, sanitized)
    sanitized = _BOT_TOKEN_RE.sub(_REDACTED, sanitized)
    return sanitized


def _sanitize_obj(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, tuple):
        return tuple(_sanitize_obj(item) for item in value)
    if isinstance(value, list):
        return [_sanitize_obj(item) for item in value]
    if isinstance(value, dict):
        return {k: _sanitize_obj(v) for k, v in value.items()}
    return value


def sanitize_headers(headers: Mapping[str, Any]) -> dict[str, Any]:
    """Возвращает копию headers с маскированием чувствительных значений."""
    sanitized: dict[str, Any] = {}
    for key, value in headers.items():
        key_lower = str(key).lower()
        if key_lower in _SENSITIVE_HEADERS:
            sanitized[str(key)] = _REDACTED
        else:
            sanitized[str(key)] = _sanitize_obj(value)
    return sanitized


class SensitiveDataFilter(logging.Filter):
    """Фильтр логирования, скрывающий токены/секреты в msg и args."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _sanitize_obj(record.msg)
        if record.args:
            record.args = _sanitize_obj(record.args)
        return True


_configured = False


def configure_secure_logging() -> None:
    """Настраивает безопасные уровни логирования и фильтр маскирования."""
    global _configured
    if _configured:
        return

    for logger_name in ("httpx", "httpcore", "telegram.request"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    root_logger = logging.getLogger()
    has_root_filter = any(isinstance(existing, SensitiveDataFilter) for existing in root_logger.filters)
    if not has_root_filter:
        root_logger.addFilter(SensitiveDataFilter())

    for handler in root_logger.handlers:
        has_handler_filter = any(isinstance(existing, SensitiveDataFilter) for existing in handler.filters)
        if not has_handler_filter:
            handler.addFilter(SensitiveDataFilter())

    _configured = True
