"""Use --execute only with an owner-approved policy; reports contain counts only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "api" / "aijuristiction-api"))

from aijurisdictionagents.api_db import ApiDatabaseStore  # noqa: E402
from aijurisdictionagents.privacy import PrivacyControls  # noqa: E402
from aijurisdictionagents.privacy_retention import (  # noqa: E402
    cleanup_files, purge_case, require_approved_policy, retention_candidates,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=ROOT / "config/privacy_retention.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    if args.execute:
        require_approved_policy(policy)
    store = ApiDatabaseStore.from_env()
    store.initialize()
    candidates = retention_candidates(store, policy)
    result = {"mode": "execute" if args.execute else "dry_run", "candidate_cases": len(candidates), "purged_cases": 0}
    if args.execute:
        from app.case_workflows.store import CaseWorkflowStore
        workflows = CaseWorkflowStore.from_env()
        for case_id, user_id in candidates:
            if PrivacyControls(store).state(user_id)["legal_hold"]:
                continue
            workflows.delete_case_workflows(case_id=case_id, user_id=user_id)
            result["purged_cases"] += int(purge_case(store, case_id, user_id))
        result.update(cleanup_files(store))
    PrivacyControls(store).event("retention", "completed" if args.execute else "dry_run", count=len(candidates))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
