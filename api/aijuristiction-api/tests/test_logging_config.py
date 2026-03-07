from __future__ import annotations

import logging

import app.logging_config as logging_config


def _restore_root_logger(level: int, handlers: list[logging.Handler]) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


def test_configure_logging_applies_api_log_level(monkeypatch) -> None:
    monkeypatch.setenv("API_LOG_LEVEL", "DEBUG")
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    root = logging.getLogger()
    original_level = root.level
    original_handlers = list(root.handlers)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    try:
        configured_level = logging_config.configure_logging()
        assert configured_level == logging.DEBUG
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert logging.getLogger("aijuristiction-api").level == logging.DEBUG
        assert logging.getLogger("aijurisdictionagents").level == logging.DEBUG
    finally:
        _restore_root_logger(original_level, original_handlers)


def test_configure_logging_invalid_level_falls_back_to_info(monkeypatch) -> None:
    monkeypatch.setenv("API_LOG_LEVEL", "NOT_A_LEVEL")

    root = logging.getLogger()
    original_level = root.level
    original_handlers = list(root.handlers)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    try:
        configured_level = logging_config.configure_logging()
        assert configured_level == logging.INFO
        assert root.level == logging.INFO
    finally:
        _restore_root_logger(original_level, original_handlers)
