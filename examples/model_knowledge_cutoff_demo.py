from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "api" / "aijuristiction-api"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.chat.result_metadata import get_law_knowledge_snapshot  # noqa: E402


def main() -> None:
    snapshot = get_law_knowledge_snapshot("SK")
    print(
        json.dumps(
            {
                "last_law_update_date": snapshot.last_law_update_date,
                "last_law_update_source": snapshot.last_law_update_source,
                "last_collector_run_at": snapshot.last_collector_run_at,
                "last_processed_law": snapshot.last_processed_law,
                "model_knowledge_cutoff_date": snapshot.model_knowledge_cutoff_date,
                "model_knowledge_cutoff_source": snapshot.model_knowledge_cutoff_source,
                "law_reference_links": list(snapshot.reference_links),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
