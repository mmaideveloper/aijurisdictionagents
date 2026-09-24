"""Capture approved document-template sources into runtime review storage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "api" / "aijuristiction-api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.document_templates.source_ingestion import TemplateSourceIngestor  # noqa: E402
from app.document_templates.store import DocumentTemplateStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true", help="Required before fetching third-party sources.")
    parser.add_argument("--template-key", action="append", default=[], help="Capture only this exact template key.")
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--cleanup-only", action="store_true")
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=REPO_ROOT / "runs" / "storage" / "api" / "template_sources",
    )
    args = parser.parse_args()
    if not args.allow_network and not args.cleanup_only:
        parser.error("--allow-network is required for source capture; use --cleanup-only without network access.")

    store = DocumentTemplateStore.from_env()
    ingestor = TemplateSourceIngestor(store=store, storage_root=args.storage_root)
    deleted = ingestor.cleanup_expired(retention_days=args.retention_days)
    if args.cleanup_only:
        print(json.dumps({"deleted_artifacts": deleted}, ensure_ascii=False))
        return 0
    templates = store.list(jurisdiction="SK", latest_only=True)
    if args.template_key:
        requested = set(args.template_key)
        templates = [template for template in templates if template.template_key in requested]
        missing = requested - {template.template_key for template in templates}
        if missing:
            parser.error(f"unknown template key(s): {', '.join(sorted(missing))}")
    results = ingestor.capture(templates)
    print(json.dumps({"captured": [result.__dict__ for result in results], "deleted_artifacts": deleted}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
