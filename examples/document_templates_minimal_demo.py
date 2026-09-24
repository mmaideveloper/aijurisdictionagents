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

from app.document_templates.source_ingestion import TemplateSourceIngestor  # noqa: E402
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
    manifest = store.upsert_source_capture_manifest(
        template_key=matched.template_key,
        source_url=matched.source_url,
        content_sha256="",
        artifact_reference="runs/storage/api/template-sources/demo-metadata-only",
        capture_status="metadata_recorded",
    )
    print("Capture manifest status:", manifest.capture_status)

    if os.getenv("DOWNLOAD_TEMPLATE_SOURCES", "").strip() == "1":
        download_dir = repo_root / "runs" / "storage" / "api" / "template_sources"
        ingestor = TemplateSourceIngestor(store=store, storage_root=download_dir)
        captured = ingestor.capture(items)
        print(f"Captured source artifacts: {len(captured)}")
        print("Sample artifact:", captured[0].artifact_reference if captured else "n/a")


if __name__ == "__main__":
    main()

