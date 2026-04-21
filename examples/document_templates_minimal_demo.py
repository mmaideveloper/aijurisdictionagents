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

demo_db = repo_root / "runs" / "storage" / "api" / "sqlite" / "document_templates_demo.sqlite3"
os.environ.setdefault("API_DOCUMENT_TEMPLATES_SQLITE_PATH", str(demo_db))

from app.document_templates.catalog import download_template_sources  # noqa: E402
from app.document_templates.store import DocumentTemplateStore  # noqa: E402


def main() -> None:
    store = DocumentTemplateStore.from_env()
    items = store.list(jurisdiction="SK")
    print(f"Seeded SK templates: {len(items)}")
    print("First 5 template keys:", [item.template_key for item in items[:5]])

    score, matched = store.find_best_match(
        request_text="Potrebujem pripravit najomnu zmluvu na byt v Bratislave.",
        country="SK",
        template_kind="rental_agreement",
    )
    if matched is None:
        raise SystemExit("No template matched the demo request.")
    print("Matched template:", matched.template_key, "score=", score)
    print("Matched source:", matched.source_url)

    if os.getenv("DOWNLOAD_TEMPLATE_SOURCES", "").strip() == "1":
        download_dir = repo_root / "runs" / "storage" / "api" / "template_sources"
        downloaded = download_template_sources(templates=items, download_dir=download_dir)
        print(f"Downloaded source artifacts: {len(downloaded)}")
        print("Sample artifact:", downloaded[0].downloaded_to if downloaded else "n/a")


if __name__ == "__main__":
    main()

