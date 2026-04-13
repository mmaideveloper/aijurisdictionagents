"""Minimal demo for the Slovak share-transfer related-document offer.

Run:
    python examples/share_transfer_related_documents_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "api" / "aijuristiction-api"))


def main() -> None:
    from app.chat.api import _build_slovak_share_transfer_intake_reply

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    company_record = {
        "name": "ESolutions SK s.r.o.",
        "registration_number": "12345678",
        "seat": "Spišské Bystré",
        "status": "Aktívna",
    }
    print(_build_slovak_share_transfer_intake_reply(company_record=company_record))


if __name__ == "__main__":
    main()
