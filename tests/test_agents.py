from io import BytesIO
import re

from aijurisdictionagents.agents.ai_web_search import (
    AIWebSearchAgent,
    CompanySearchAgent,
    EntityScreeningAgent,
    PersonSearchAgent,
    _parse_duckduckgo_html_results,
)
from aijurisdictionagents.agents import AIAddressValidatorAgent, AIUserSimulatorAgent, create_lawyer_agent
from aijurisdictionagents.llm import MockLLMClient
from aijurisdictionagents.schemas import Document, Message


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
    assert "full document package" in prompt_lower


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


def test_slovak_lawyer_prompt_includes_company_check_and_tool_first_policy() -> None:
    llm = MockLLMClient()
    lawyer = create_lawyer_agent(llm, "SK")
    prompt_lower = lawyer.system_prompt.lower()

    assert "obchodny_register_company_check" in prompt_lower
    assert "slovakia_property_lv_lookup" in prompt_lower
    assert "explicit_user_confirmation_required=no" in prompt_lower
    assert "použi tento nástroj ako prvý krok" in prompt_lower
    assert "neplatné alebo nezhodné údaje" in prompt_lower
    assert "celý balík týchto dokumentov" in prompt_lower
    assert "future_car_verification_check" not in prompt_lower


def test_parse_duckduckgo_html_results_extracts_title_url_and_snippet() -> None:
    payload = """
    <html>
      <body>
        <a class="result__a" href="https://platform.openai.com/docs/models/gpt-4o-mini">gpt-4o-mini Model</a>
        <div class="result__snippet">GPT-4o mini model page. Oct 01, 2023 knowledge cutoff.</div>
      </body>
    </html>
    """

    records = _parse_duckduckgo_html_results(payload=payload, max_results=5)

    assert len(records) == 1
    assert records[0].url == "https://platform.openai.com/docs/models/gpt-4o-mini"
    assert records[0].title == "gpt-4o-mini Model"
    assert "knowledge cutoff" in records[0].snippet


def test_parse_duckduckgo_html_results_normalizes_duckduckgo_redirect_url() -> None:
    payload = """
    <html>
      <body>
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fplatform.openai.com%2Fdocs%2Fmodels%2Fgpt-4o-mini">gpt-4o-mini Model</a>
        <div class="result__snippet">GPT-4o mini model page. Oct 01, 2023 knowledge cutoff.</div>
      </body>
    </html>
    """

    records = _parse_duckduckgo_html_results(payload=payload, max_results=5)

    assert len(records) == 1
    assert records[0].url == "https://platform.openai.com/docs/models/gpt-4o-mini"


def test_ai_web_search_agent_falls_back_to_duckduckgo_html(monkeypatch) -> None:
    class _Response:
        def __init__(self, body: str) -> None:
            self._payload = BytesIO(body.encode("utf-8"))

        def read(self) -> bytes:
            return self._payload.read()

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    responses = iter(
        [
            _Response('{"RelatedTopics":[],"Results":[]}'),
            _Response(
                """
                <html>
                  <body>
                    <a class="result__a" href="https://platform.openai.com/docs/models/gpt-4o-mini">gpt-4o-mini Model</a>
                    <div class="result__snippet">GPT-4o mini model page. Oct 01, 2023 knowledge cutoff.</div>
                  </body>
                </html>
                """
            ),
        ]
    )

    monkeypatch.setattr(
        "aijurisdictionagents.agents.ai_web_search.urlopen",
        lambda *_args, **_kwargs: next(responses),
    )

    records = AIWebSearchAgent().search(
        query='site:platform.openai.com/docs/models "gpt-4o-mini" "knowledge cutoff"',
        max_results=5,
    )

    assert len(records) == 1
    assert records[0].url == "https://platform.openai.com/docs/models/gpt-4o-mini"


def test_entity_screening_agent_and_ai_web_search_alias_share_consent_prompt() -> None:
    entity_prompt = EntityScreeningAgent().build_screening_consent_prompt(
        entity_type="company",
        entity_value="12345678",
    )
    alias_prompt = AIWebSearchAgent().build_screening_consent_prompt(
        entity_type="company",
        entity_value="12345678",
    )
    assert entity_prompt == alias_prompt


def test_company_search_agent_builds_structured_prompt_in_english() -> None:
    prompt = CompanySearchAgent().build_search_prompt(
        company_reference="ICO 12345678",
        country="SK",
    )
    assert "registered address" in prompt
    assert "list of companies owned by this company" in prompt
    assert "social insurance" in prompt
    assert "Country: SK" in prompt


def test_person_search_agent_builds_structured_prompt_in_english() -> None:
    prompt = PersonSearchAgent().build_search_prompt(
        person_reference="Jana Hraska",
        country="SK",
    )
    assert "list of companies linked to the person" in prompt
    assert "list of trade licenses / sole-trader businesses" in prompt
    assert "financial institutions" in prompt
    assert "Person reference: Jana Hraska" in prompt


def test_ai_address_validator_agent_extracts_slovak_mapping_and_lookup_url() -> None:
    agent = AIAddressValidatorAgent()
    result = agent.validate_from_text("Partizánska 665/101, 059 18 Spišské Bystré")

    assert result["ok"] is True
    mapping = result["mapping"]
    assert mapping["street"].startswith("Partiz")
    assert mapping["house_number"] == "665/101"
    assert mapping["postal_code"] == "05918"
    assert "registeradries.sk" in result["lookup_url"]
