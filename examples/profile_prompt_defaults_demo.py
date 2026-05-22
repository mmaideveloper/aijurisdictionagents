from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "api" / "aijuristiction-api"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import app.chat.api as chat_api  # noqa: E402
from app.chat.models import Session  # noqa: E402
from aijurisdictionagents.api_db import User  # noqa: E402


def main() -> None:
    user = User(
        user_id="demo-user",
        phone_number="+421900000000",
        email="demo@example.com",
        first_name="Marek",
        last_name="Matonok",
        full_name="Marek Matonok",
        address="Partizanska 665",
        city="Spisske Bystre",
        country="SK",
        zip_code="059 18",
        tax_number="1070000001",
        identity_card_number="AB123456",
        date_of_birth="1980-01-02",
        social_security_number="800102/1234",
        data_processing_consent_at=None,
        data_processing_consent_version=None,
        mcp_api_key_hash=None,
        mcp_api_key_expires_at=None,
    )
    chat_api._document_user_profile_for_session = lambda session: user  # type: ignore[method-assign]
    print(chat_api._build_signed_in_user_profile_prompt_note(Session(country="SK", language="SK")))


if __name__ == "__main__":
    main()
