"""Minimal runnable check for corporate-web GDPR/AI Act copy."""
from pathlib import Path

html = Path("corporate-web/index.html").read_text(encoding="utf-8")
required = [
    "GDPR",
    "EU AI Act",
    "legal_ai_act_title",
    "legal_ai_act_item_1",
]

missing = [token for token in required if token not in html]
if missing:
    raise SystemExit(f"Missing required tokens: {missing}")

print("Corporate web contains GDPR and EU AI Act legal disclosures.")
