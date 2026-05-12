"""Minimal runnable demo: verify chat-simulator testcases map to seeded flow packs."""

from __future__ import annotations

import json
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[1]
api_root = repo_root / "api" / "aijuristiction-api"
src_root = repo_root / "src"
if str(api_root) not in sys.path:
    sys.path.insert(0, str(api_root))
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))

from app.flow_packs.store import FlowPackStore, FlowPackStoreConfig  # noqa: E402


def _extract_instruction(testcase_path: Path) -> str:
    raw = testcase_path.read_text(encoding="utf-8").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(parsed, dict):
        return raw
    return str(parsed.get("CaseDescription") or parsed.get("CaseDescripton") or "")


def main() -> None:
    db_path = repo_root / "runs" / "storage" / "api" / "sqlite" / "chat_simulator_flowpacks_demo.sqlite3"
    store = FlowPackStore(FlowPackStoreConfig(db_option="sqlite", db_cloud="", sqlite_path=db_path))

    testcase_dir = repo_root / "api" / "chat-simulator-app" / "testcases"
    missing: list[str] = []
    for testcase_path in sorted(testcase_dir.glob("*.txt")):
        matched = store.find_best_match(request_text=_extract_instruction(testcase_path), country="SK")
        if matched is None:
            missing.append(testcase_path.name)
            continue
        print(f"{testcase_path.name} -> {matched.flow_key} (v{matched.version})")
        if testcase_path.name == "sample_potvrdenie.txt" and matched.flow_key != "sk.civil.payment_confirmation":
            raise SystemExit(
                f"sample_potvrdenie.txt matched {matched.flow_key}, expected sk.civil.payment_confirmation"
            )

    if missing:
        raise SystemExit(f"Missing flow pack matches: {', '.join(missing)}")

    print("All chat simulator testcases have matching flow packs.")


if __name__ == "__main__":
    main()
