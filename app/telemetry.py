"""Small structured event stream without request bodies, tokens or personal fields."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id = ContextVar("request_id", default=None)
logger = logging.getLogger("claims.events")


def configure_logging():
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def event(name, **fields):
    # Explicit field allowlist prevents accidental logging of a payload or exception.
    allowed = {key: value for key, value in fields.items()
               if key in {"method", "route", "status", "duration_ms", "reason"}}
    logger.info(json.dumps({"time": datetime.now(UTC).isoformat(), "event": name,
                            "request_id": request_id.get(), **allowed}))
