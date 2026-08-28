from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "api" / "aijuristiction-api"
sys.path.insert(0, str(API_ROOT))

from app.document_templates.api import get_document_template_store, router  # noqa: E402
from app.document_templates.store import DocumentTemplateStore, DocumentTemplateStoreConfig  # noqa: E402
from app.security import require_api_key  # noqa: E402


def build_preview(output_path: Path) -> None:
    runtime_root = REPO_ROOT / "runs" / "storage" / "api" / "sqlite"
    runtime_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="employment-template-demo-", dir=runtime_root) as temp_dir:
        store = DocumentTemplateStore(
            DocumentTemplateStoreConfig(
                db_option="sqlite",
                db_cloud="",
                sqlite_path=Path(temp_dir) / "document_templates.sqlite3",
            )
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_document_template_store] = lambda: store
        app.dependency_overrides[require_api_key] = lambda: None
        response = TestClient(app).get(
            "/v1/document-templates/sk.employment.employment_contract/preview/pdf",
            params={"jurisdiction": "SK"},
        )
        response.raise_for_status()

    extracted_text = " ".join(
        (page.extract_text() or "") for page in PdfReader(BytesIO(response.content)).pages
    )
    expected_markers = (
        "DRUH PRÁCE A JEHO STRUČNÁ CHARAKTERISTIKA",
        "MZDOVÉ PODMIENKY",
        "Za zamestnávateľa",
        "individuálnu",
    )
    missing = [marker for marker in expected_markers if marker not in extracted_text]
    if missing:
        raise RuntimeError(f"Generated PDF is missing expected markers: {missing}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    print(f"employment_contract_preview => {output_path.resolve()}")
    print(f"pages={len(PdfReader(BytesIO(response.content)).pages)}; expected_markers=passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and validate the canonical Slovak employment-contract PDF.")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "runs" / "document-template-demo" / "employment-contract-preview.pdf",
    )
    args = parser.parse_args()
    build_preview(args.output)


if __name__ == "__main__":
    main()
