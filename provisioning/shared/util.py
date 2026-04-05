from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

SENSITIVE_FIELD_NAMES = {
    "authorization",
    "authkey",
    "auth_key",
    "bootstrap_env_json",
    "bootstrap_files_json",
    "client_secret",
    "content",
    "env",
    "file_content",
    "files",
    "key",
    "oauth_secret",
    "secret",
    "secret_payload",
    "tailscale_auth_key",
    "token",
    "ts_api_client_secret",
}

STANDARD_RECORD_KEYS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def isoformat_z(value: datetime) -> str:
    return ensure_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)[:length]


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return isoformat_z(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return str(value)


def redact_structure(value: Any, key_name: str | None = None) -> Any:
    lowered_key = key_name.lower() if key_name else None
    if lowered_key and lowered_key in SENSITIVE_FIELD_NAMES:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {key: redact_structure(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_structure(item, key_name) for item in value]
    if isinstance(value, tuple):
        return [redact_structure(item, key_name) for item in value]
    return value


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in STANDARD_RECORD_KEYS and not key.startswith("_")
        }
        record.redacted_message = redact_structure(record.msg)
        record.redacted_extras = redact_structure(extras)
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        message = getattr(record, "redacted_message", record.getMessage())
        if isinstance(message, dict):
            rendered_message = json.dumps(message, default=_json_default, sort_keys=True)
        else:
            rendered_message = str(message)

        payload: dict[str, Any] = {
            "timestamp": isoformat_z(datetime.fromtimestamp(record.created, tz=timezone.utc)),
            "service": self.service_name,
            "logger": record.name,
            "level": record.levelname.lower(),
            "message": rendered_message,
        }
        payload.update(getattr(record, "redacted_extras", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=_json_default, separators=(",", ":"))


def configure_json_logging(service_name: str, level: str = "INFO") -> None:
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(JsonFormatter(service_name=service_name))
    root_logger.handlers = [handler]
    root_logger.setLevel(level.upper())
