from __future__ import annotations

import os
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[1]
api_root = repo_root / "api" / "aijuristiction-api"
src_root = repo_root / "src"
if str(api_root) not in sys.path:
    sys.path.insert(0, str(api_root))
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))

demo_db = repo_root / "runs" / "storage" / "api" / "sqlite" / "case_types_demo.sqlite3"
os.environ.setdefault("API_DOCUMENT_TEMPLATES_SQLITE_PATH", str(demo_db))

from app.document_templates.store import DocumentTemplateStore  # noqa: E402


def main() -> None:
    store = DocumentTemplateStore.from_env()
    case_types = store.list_case_types(jurisdiction="SK")
    print(f"Seeded SK case types: {len(case_types)}")
    print("First 5 case type keys:", [item.case_type_key for item in case_types[:5]])

    score, matched = store.resolve_case_type(
        request_text="Potrebujem odpor proti platobnemu rozkazu v upominacom konani.",
        country="SK",
    )
    if matched is None:
        raise SystemExit("No case type matched the demo request.")

    print("Matched case type:", matched.case_type_key, "score=", score)
    print("Linked templates:", [item.template_key for item in matched.templates])
    print("Prompt preview:", matched.prompt.prompt_text if matched.prompt is not None else "n/a")


if __name__ == "__main__":
    main()
