"""Run without a model or database to inspect synthetic citation binding."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api/aijuristiction-api"))
from app.chat.provision_citations import bind_citations, provision_evidence  # noqa: E402

evidence = provision_evidence([{
    "document_id": "synthetic-example", "law_number": 746, "law_year": 2026,
    "effective_from": "2026-01-01", "version_id": "synthetic-v1",
    "content_text": "§ 4\nSyntetická kategória A pre demonštráciu.",
}])
answer, citations = bind_citations(
    "Syntetická kategória A. [[source:p1]]\n"
    "Toto ďalšie dlhšie tvrdenie nemá žiadny overený právny podklad.", evidence, "sk",
)
assert len(citations) == 1 and "Neoverené" in answer
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
print(answer)
