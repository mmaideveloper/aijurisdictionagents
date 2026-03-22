from aijurisdictionagents.agents import AIUserSimulatorAgent, create_lawyer_agent
from aijurisdictionagents.llm import MockLLMClient
from aijurisdictionagents.schemas import Document, Message
import re


def test_lawyer_agent_routing() -> None:
    llm = MockLLMClient()
    slovak_agent = create_lawyer_agent(llm, "SK")
    assert slovak_agent.name == "LawyerSlovakia"

    default_agent = create_lawyer_agent(llm, "US")
    assert default_agent.name == "Lawyer"


def test_ai_user_simulator_agent_generates_answer() -> None:
    llm = MockLLMClient()
    simulator = AIUserSimulatorAgent(llm=llm, language="sk")

    answer = simulator.prepare_random_answer(
        question="Aký bol dátum podpisu zmluvy?",
        conversation=[Message(role="assistant", agent_name="CoreSystem", content="Aký bol dátum podpisu zmluvy?")],
        documents=[],
    )

    assert answer


def test_lawyer_prompt_requires_old_document_review() -> None:
    llm = MockLLMClient()
    lawyer = create_lawyer_agent(llm, "US")

    prompt_lower = lawyer.system_prompt.lower()
    assert "older version" in prompt_lower
    assert "upload" in prompt_lower
    assert "out of date" in prompt_lower


def test_mock_lawyer_returns_short_document_summary_for_summary_request() -> None:
    llm = MockLLMClient()
    lawyer = create_lawyer_agent(llm, "SK")

    reply = lawyer.respond(
        conversation=[
            Message(
                role="user",
                agent_name="User",
                content="Prosim sprav kratke zhrnutie nahraneho dokumentu v maximalne 5 vetach.",
            )
        ],
        documents=[
            Document(
                doc_id="doc-1",
                path="contract.pdf",
                content=(
                    "Najomna zmluva medzi Janou Novotnou a Tomasom Hlavatym. "
                    "Byt sa nachadza na Dunajskej 12 v Bratislave. "
                    "Najomne je 850 EUR mesacne a splatnost je do piateho dna v mesiaci."
                ),
            )
        ],
        sources=[],
    )

    assert "contract.pdf" in reply.content
    assert "850 EUR" in reply.content
    sentence_count = len(
        [part for part in re.split(r"(?<=[.!?])\s+", reply.content) if part.strip()]
    )
    assert sentence_count <= 5


def test_mock_lawyer_does_not_fall_back_for_slovak_sumarizovanie_request() -> None:
    llm = MockLLMClient()
    lawyer = create_lawyer_agent(llm, "SK")

    reply = lawyer.respond(
        conversation=[
            Message(
                role="user",
                agent_name="User",
                content="Prosim sprav sumarizovanie dokumenty a kratke zhrnutie v 5 vetach.",
            )
        ],
        documents=[
            Document(
                doc_id="doc-1",
                path="contract.pdf",
                content=(
                    "Najomna zmluva medzi Janou Novotnou a Tomasom Hlavatym. "
                    "Byt sa nachadza na Dunajskej 12 v Bratislave. "
                    "Najomne je 850 EUR mesacne."
                ),
            )
        ],
        sources=[],
    )

    assert "Aby som mohol pripravit presny navrh" not in reply.content
    assert "contract.pdf" in reply.content


def test_mock_lawyer_updates_document_for_slovak_revision_request() -> None:
    llm = MockLLMClient()
    lawyer = create_lawyer_agent(llm, "SK")

    reply = lawyer.respond(
        conversation=[
            Message(
                role="user",
                agent_name="User",
                content="Pozri na dokument a oprav ho podla poslednych zmien zakona.",
            )
        ],
        documents=[
            Document(
                doc_id="doc-1",
                path="contract.pdf",
                content=(
                    "Najomna zmluva medzi Janou Novotnou a Tomasom Hlavatym. "
                    "Byt sa nachadza na Dunajskej 12 v Bratislave. "
                    "Najomne je 850 EUR mesacne."
                ),
            )
        ],
        sources=[],
    )

    assert "Aby som mohol pripravit presny navrh" not in reply.content
    assert "Pripravil som aktualizovane znenie dokumentu" in reply.content
    assert "PDF" in reply.content
