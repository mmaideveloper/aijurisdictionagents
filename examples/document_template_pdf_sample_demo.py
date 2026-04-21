"""Generate one sample third-party corporate PDF document.

Run:
    python examples/document_template_pdf_sample_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "api" / "aijuristiction-api"))

from app.chat.api import _build_simple_pdf


def main() -> None:
    output_path = REPO_ROOT / "runs" / "storage" / "api" / "pdf_previews" / "sample-third-party-template.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf_bytes = _build_simple_pdf(
        title="Car Rental Legal Memo",
        lines=[
            "Subject: Legal Memo on Liability and Insurance Issues in Car Rentals",
            "",
            "To: [Recipient's Name], CEO, [Your Company Name]",
            "From: [Your Name], [Your Job Title]",
            "Date: [Date]",
            "",
            "Re: Legal Analysis and Recommendations on Liability and Insurance Issues",
            "",
            "Dear [Recipient's Name],",
            "",
            "As requested, I have conducted a comprehensive legal analysis of liability and insurance risks.",
        ],
        country="US",
        language="en-US",
        header_line="AI Jurisdicta Solution | Generated: 2026-04-21 10:00:00 UTC",
        footer_line="AIJ | API 1.0 | Core 1.0",
        draw_logo_mark=True,
        include_title_block=False,
    )
    output_path.write_bytes(pdf_bytes)
    print(f"Generated: {output_path}")


if __name__ == "__main__":
    main()
