from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "api" / "aijuristiction-api"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.cases_api import _document_share_email_content  # noqa: E402
from app.services.email_templates import ensure_branded_email_metadata  # noqa: E402


def build_preview() -> str:
    share_url = "https://agent.jurisdigta.eu/shared-documents/golden602"
    content = _document_share_email_content(
        locale="sk",
        share_url=share_url,
        expires_at=datetime(2026, 8, 14, 12, 39, tzinfo=timezone.utc),
    )
    metadata = ensure_branded_email_metadata(
        subject=content["subject"],
        body=content["plain"],
        metadata={
            "event": "document_share_invitation",
            "locale": "sk",
            "html_body": content["html"],
        },
    )
    html = str(metadata["html_body"])
    for attachment in metadata.get("attachments", []):
        content_id = attachment.get("content_id")
        mime_type = attachment.get("mime_type")
        encoded = attachment.get("content_base64")
        if content_id and mime_type and encoded:
            base64.b64decode(encoded, validate=True)
            html = html.replace(f"cid:{content_id}", f"data:{mime_type};base64,{encoded}")
    return html


if __name__ == "__main__":
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "output" / "playwright" / "issue-602-email-preview.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_preview(), encoding="utf-8")
    print(output.resolve())
