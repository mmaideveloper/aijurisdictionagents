from __future__ import annotations

import os
from pathlib import Path
import sys

# Ensure deterministic local demo database path under runs/storage/api/sqlite.
repo_root = Path(__file__).resolve().parents[1]
api_root = repo_root / "api" / "aijuristiction-api"
src_root = repo_root / "src"
if str(api_root) not in sys.path:
    sys.path.insert(0, str(api_root))
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))
demo_db = repo_root / "runs" / "storage" / "api" / "sqlite" / "flow_packs_demo.sqlite3"
os.environ.setdefault("API_FLOW_PACKS_SQLITE_PATH", str(demo_db))

from app.flow_packs.models import FlowPackCreateRequest, FlowPackCreateVersionRequest  # noqa: E402
from app.flow_packs.store import FlowPackStore  # noqa: E402


def main() -> None:
    store = FlowPackStore.from_env()

    packs = store.list(include_deleted=False)
    print(f"Seeded flow packs: {len(packs)}")
    print("First 3 flow keys:", [item.flow_key for item in packs[:3]])

    created = store.create(
        FlowPackCreateRequest(
            flow_key="sk.civil.notice_template_demo",
            jurisdiction="SK",
            domain="civil",
            title="Predžalobná výzva (demo)",
            description="Demo flow pack for pre-litigation notice.",
            definition={"required_facts": ["counterparty", "claim_summary"]},
            is_enabled=True,
        )
    )
    print("Created:", created.flow_key, "v", created.version)

    v2 = store.create_version(
        flow_key=created.flow_key,
        payload=FlowPackCreateVersionRequest(
            description="Demo flow pack for pre-litigation notice (v2).",
            definition={"required_facts": ["counterparty", "claim_summary", "deadline"]},
            is_enabled=False,
        ),
    )
    print("Created version:", v2.flow_key, "v", v2.version, "enabled=", v2.is_enabled)


if __name__ == "__main__":
    main()
