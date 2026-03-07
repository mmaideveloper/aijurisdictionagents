from __future__ import annotations

import logging
import os

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def _resolve_log_level() -> int:
    candidate = os.getenv("API_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")).upper().strip()
    return getattr(logging, candidate, logging.INFO)


def configure_logging() -> int:
    level = _resolve_log_level()
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root_logger.addHandler(stream_handler)
    root_logger.setLevel(level)

    for logger_name in ("aijuristiction-api", "aijurisdictionagents"):
        logging.getLogger(logger_name).setLevel(level)

    return level
