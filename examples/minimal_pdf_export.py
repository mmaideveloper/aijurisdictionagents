from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "api" / "aijuristiction-api"
sys.path.insert(0, str(API_ROOT))

from app.chat.api import _build_simple_pdf  # noqa: E402


def main() -> None:
    output_path = REPO_ROOT / "runs" / "minimal-pdf-export.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf_bytes = _build_simple_pdf(
        title="Nájomná zmluva / Kündigung",
        lines=[
            "Čl. I - Zmluvné strany",
            "Ľubomír Žáček býva v Košiciach a žiada právne posúdenie nájmu.",
            "Deutsch: Kündigung, Straße, Größe und äußerst wichtige Frist.",
        ],
        country="SK",
        language="sk-SK",
        header_line="AI Jurisdicta Solution | Generated: 2026-03-16 20:00:00 UTC",
        footer_line="AIJ | API local | Core local",
        draw_logo_mark=True,
        include_title_block=True,
    )
    output_path.write_bytes(pdf_bytes)
    print(output_path)


if __name__ == "__main__":
    main()
