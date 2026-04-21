from __future__ import annotations

import logging
import os
from pathlib import Path
import tempfile
from uuid import uuid4

import pytest

from app.chat.api import _warn_if_flow_pack_missing
from app.chat.models import Session
from app.flow_packs.api import get_flow_pack_store


@pytest.fixture(autouse=True)
def isolated_flow_pack_store() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "flow_packs.sqlite3"
        os.environ["API_FLOW_PACKS_SQLITE_PATH"] = str(db_path)
        get_flow_pack_store.cache_clear()
        yield
        get_flow_pack_store.cache_clear()
        os.environ.pop("API_FLOW_PACKS_SQLITE_PATH", None)


def test_warn_if_flow_pack_missing_logs_warning(caplog) -> None:
    caplog.set_level(logging.WARNING)
    session = Session(country="SK", discussion_type="advice", language="SK")

    _warn_if_flow_pack_missing(
        session_id=uuid4(),
        session=session,
        request_text="uplne neexistujuci typ pravneho procesu bez mapovania",
    )

    assert any("No flow-pack matched user request" in message for message in caplog.messages)


def test_warn_if_flow_pack_missing_no_warning_for_known_intent(caplog) -> None:
    caplog.set_level(logging.WARNING)
    session = Session(country="SK", discussion_type="advice", language="SK")

    _warn_if_flow_pack_missing(
        session_id=uuid4(),
        session=session,
        request_text="Potrebujem pripravit kupnu zmluvu na auto",
    )

    assert not any("No flow-pack matched user request" in message for message in caplog.messages)
