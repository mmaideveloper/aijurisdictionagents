from __future__ import annotations

import json
from pathlib import Path

from app.flow_packs.store import FlowPackStore, FlowPackStoreConfig


def _extract_instruction(testcase_path: Path) -> str:
    raw = testcase_path.read_text(encoding="utf-8").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(parsed, dict):
        return raw
    return str(parsed.get("CaseDescription") or parsed.get("CaseDescripton") or "")


def _build_store(tmp_path: Path) -> FlowPackStore:
    return FlowPackStore(
        FlowPackStoreConfig(
            db_option="sqlite",
            db_cloud="",
            sqlite_path=tmp_path / "flow_packs.sqlite3",
        )
    )


def test_each_chat_simulator_testcase_has_matching_flowpack(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    testcase_dir = Path(__file__).resolve().parents[2] / "chat-simulator-app" / "testcases"

    missing: list[str] = []
    for testcase_path in sorted(testcase_dir.glob("*.txt")):
        instruction = _extract_instruction(testcase_path)
        matched = store.find_best_match(request_text=instruction, country="SK")
        if matched is None:
            missing.append(testcase_path.name)

    assert not missing, f"Missing flow pack match for: {', '.join(missing)}"


def test_matched_flowpacks_include_steps_and_document_delivery_contract(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    testcase_dir = Path(__file__).resolve().parents[2] / "chat-simulator-app" / "testcases"

    for testcase_path in sorted(testcase_dir.glob("*.txt")):
        instruction = _extract_instruction(testcase_path)
        matched = store.find_best_match(request_text=instruction, country="SK")
        assert matched is not None, f"Expected a flow pack for {testcase_path.name}"

        definition = matched.definition
        steps = definition.get("steps")
        outputs = definition.get("outputs")
        delivery = definition.get("delivery")

        assert isinstance(steps, list) and steps, f"Flow {matched.flow_key} must declare steps"
        assert isinstance(outputs, list) and outputs, f"Flow {matched.flow_key} must declare outputs"
        assert isinstance(delivery, dict), f"Flow {matched.flow_key} must declare delivery policy"

        if len(outputs) > 1:
            assert delivery.get("multi_document_bundle") == "zip", (
                f"Flow {matched.flow_key} must produce zip bundle for multiple outputs"
            )
        else:
            assert isinstance(delivery.get("single_document"), str) and delivery.get("single_document"), (
                f"Flow {matched.flow_key} must produce one document for single-output flows"
            )
