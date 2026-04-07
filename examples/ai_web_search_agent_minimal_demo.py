from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aijurisdictionagents.agents import AIWebSearchAgent


def main() -> None:
    agent = AIWebSearchAgent()
    consent_prompt = agent.build_screening_consent_prompt(
        entity_type="company",
        entity_value="OpenAI",
    )
    print(consent_prompt)
    print("Search is skipped in this demo until explicit user confirmation is granted.")


if __name__ == "__main__":
    main()
