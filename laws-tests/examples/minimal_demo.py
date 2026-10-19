"""Public catalogue/private boundary, or --offline synthetic review contract."""

import argparse
import sys
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from laws_tests.management import QuestionInput

parser = argparse.ArgumentParser()
parser.add_argument("--offline", action="store_true")
parser.add_argument("--base-url", default="http://127.0.0.1:8411")
args = parser.parse_args()
if args.offline:
    question = QuestionInput(
        category="chemistry",
        number=1,
        title="Synthetic water",
        body="Formula of water?",
        answer="H2O",
        tags=["subject:chemistry", "school-year:1"],
    )
    assert question.answer == "H2O" and "school-year:1" in question.tags
    print(
        "Synthetic review valid. Publication and bank grants remain separate administrator decisions."
    )
else:
    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        client.get("/api/health").raise_for_status()
        response = client.get("/api/tests")
        response.raise_for_status()
        assert all("body" not in bank and "answer" not in bank for bank in response.json())
        assert client.get("/api/questions/E-1").status_code == 401
        assert client.get("/api/history").status_code == 401
        print("Public catalogue available; questions and history require authorized sign-in.")
