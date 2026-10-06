"""Structured (JSON) logging configuration.

Never log secrets: passwords, JWTs, API keys, exchange credentials. Callers should
pass only identifiers (user id, strategy id, request id) as extra fields.
"""
import json
import logging
import sys
from datetime import datetime, timezone

_RESERVED = set(logging.LogRecord(
    name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
).__dict__.keys())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(debug: bool = False) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Quiet noisy third-party loggers unless debugging.
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.DEBUG if debug else logging.WARNING)
    # Signed exchange GET requests include signatures in query strings.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
