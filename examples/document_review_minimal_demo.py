"""Offline synthetic accept/reject example; not real-model E2E evidence."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api" / "aijuristiction-api"))
from app.document_review import ModelReview, Proposal, accepted_text, build_proposals, export_docx


def main() -> None:
    paragraphs = ["Kúpna cena je 100 EUR.", "Splatnosť je 30 dní."]
    proposals = build_proposals(ModelReview(proposals=[Proposal(
        paragraph=1, original=paragraphs[1], replacement="Splatnosť je 15 dní.", reason="Synthetic example only.",
        source_ids=["synthetic-source"], section=1,
    )]), paragraphs, [{"source_id": "synthetic-source"}])
    proposals[0]["decision"] = "accepted"
    text = accepted_text({"paragraphs": paragraphs, "proposals": proposals})
    output = Path("runs/document-review-demo")
    output.mkdir(parents=True, exist_ok=True)
    (output / "synthetic-revision.docx").write_bytes(export_docx(text))
    assert paragraphs[1] == "Splatnosť je 30 dní."
    print("Synthetic revision created under runs/document-review-demo; original preserved.")


if __name__ == "__main__":
    main()
