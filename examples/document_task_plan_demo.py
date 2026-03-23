from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "api" / "aijuristiction-api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.chat.intent_policy_service import build_document_policy_plan


def main() -> None:
    query = "Recreate the uploaded document based on new law and send me summary from document."
    print(f"Query: {query}")
    plan = build_document_policy_plan(query)
    print("Policies:")
    for index, policy in enumerate(plan.ordered_policies, start=1):
        print(f"{index}. {policy.policy_id}")
    print("Planned tasks:")
    for index, task in enumerate(plan.ordered_tasks, start=1):
        print(f"{index}. {task.task_id} -> {task.description}")


if __name__ == "__main__":
    main()
