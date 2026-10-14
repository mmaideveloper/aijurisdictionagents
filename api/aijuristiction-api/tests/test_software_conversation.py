from types import SimpleNamespace

import pytest

from app.software_assessment import conversation as chat


def report():
    return chat.BusinessReport(summary="Administratívny prepis pre ordináciu.", regulations=["GDPR: zdravotné údaje."],
        answers=[chat.Answer(question_id="Q1", question="Ako chránite správy?", quote="DB bude šifrovaná")],
        questions=["Q2: Kde sa ukladá audio?"], controls=[chat.Control(compliance="GDPR", description="Ochrana správ",
            action="Doložiť nastavenie a test oprávnení.", question_ids=["Q1"], source_ids=["s1"])])


def source():
    return SimpleNamespace(source_id="s1", title="Synthetic", provision="Article 32", source_url="https://eur-lex.europa.eu/eli/reg/2016/679/oj")


def test_declaration_never_becomes_pass_and_provision_is_server_derived():
    value = report()
    chat.validate_report(value, [source()], ["Odpoveď: DB bude šifrovaná"])
    text = chat.render(value, [source()])
    assert "Deklarované – overiť" in text and "Article 32" in text
    assert "| Results | State |" in text and "Q1: DB bude šifrovaná" in text
    assert "pass" not in text.lower() and "&lt;script&gt;" in chat.cell("<script>")
    synthetic = source()
    synthetic.title = "E2E source — NOT actual legislation"
    assert "syntetické právne zdroje" in chat.render(value, [synthetic])


@pytest.mark.parametrize("mutation", ["quote", "source", "question", "duplicate"])
def test_rejects_unsupported_answer_or_reference(mutation):
    value = report()
    if mutation == "quote":
        value.answers[0].quote = "Fabricated configuration"
    if mutation == "source":
        value.controls[0].source_ids = ["unknown"]
    if mutation == "question":
        value.controls[0].question_ids = ["Q9"]
    if mutation == "duplicate":
        value.answers.append(value.answers[0])
    with pytest.raises(ValueError):
        chat.validate_report(value, [source()], ["DB bude šifrovaná"])


def test_consent_is_case_bound_and_model_is_not_called_before_it(monkeypatch):
    saved = {}
    store = SimpleNamespace(get_software_assessment=lambda **_: saved.get("state"),
        save_software_assessment=lambda **kw: saved.update(state=dict(kw["payload"], revision=1)))
    monkeypatch.setattr(chat, "get_document_template_store", lambda: SimpleNamespace(
        get_case_type=lambda **_: SimpleNamespace(is_enabled=True, is_deleted=False)))
    monkeypatch.setattr(chat, "retrieve_sources", lambda *_: pytest.fail("No external retrieval before consent"))
    question = "Mám dodávateľa software pre AI recepciu."
    assert chat.eligible(store, "case", question)
    reply, route = chat.respond(store, case_id="case", user_id="user", content=question)
    assert chat.CONSENT in reply and route is None and saved["state"]["consented"] is False
    assert saved["state"]["turns"] == [question]
    saved["state"]["consented"] = True
    reply, route = chat.respond(store, case_id="case", user_id="user", content="Nesúhlasím")
    assert route is None and saved["state"]["consented"] is False


def test_answer_quotes_are_server_derived_and_generated_replacements_are_rejected():
    evidence = chat.user_evidence(["DB bude sifrovana, pristup ma len ordinacia."])
    value = report()
    value.answers[0].quote = ""
    value.answers[0].evidence_id = "u1.1"
    chat.ground_answers(value, evidence)
    assert value.answers[0].quote == "DB bude sifrovana"
    with pytest.raises(ValueError):
        chat.ground_answers(value, evidence)
    value.answers[0].quote = ""
    value.answers[0].evidence_id = "u99.1"
    with pytest.raises(ValueError):
        chat.ground_answers(value, evidence)


@pytest.mark.parametrize("selected", [None, "unavailable-profile"])
def test_chat_answers_belong_to_the_asked_question_not_model_inventions(monkeypatch, selected):
    from app.software_assessment.models import LegalSource
    saved = {"state": {"revision": 1, "consented": True, "turns": ["Software pre ordináciu."],
        "answers": [], "pending_question": "Q1", "report": {}}}
    store = SimpleNamespace(get_software_assessment=lambda **_: saved["state"],
        save_software_assessment=lambda **kw: saved.update(state=dict(kw["payload"], revision=2)))
    monkeypatch.setattr(chat, "get_document_template_store", lambda: SimpleNamespace(
        get_case_type=lambda **_: SimpleNamespace(is_enabled=True, is_deleted=False, prompt=None)))
    legal = LegalSource(source_id="s1", title="Synthetic", provision="Article 32",
        source_url="https://eur-lex.europa.eu/eli/reg/2016/679/oj", text="Synthetic security source for tests.")
    monkeypatch.setattr(chat, "retrieve_sources", lambda *_: ([legal], []))
    model = chat.BusinessReport(summary="Prepis pre ordináciu, sestra potvrdzuje údaje.", regulations=["GDPR"],
        controls=[chat.Control(compliance="GDPR", description="Prístup", action="Overiť prístupové testy.",
                              question_ids=["Q1"], source_ids=["s1"])])
    calls = []
    def route(**kwargs):
        calls.append(kwargs.get("selected_model_profile_id"))
        if kwargs.get("selected_model_profile_id"):
            raise chat.ModelRouteUnavailable("Unavailable profile", status_code=404)
        return SimpleNamespace(client=SimpleNamespace(complete=lambda *_: model.model_dump_json(exclude={"answers", "questions"})),
            provider="unit-fixture", model="unit-fixture")
    monkeypatch.setattr(chat, "get_routed_llm_client", route)
    reply, _ = chat.respond(store, case_id="case", user_id="user", content="Q1: DB bude šifrovaná, prístup má ordinácia.",
        selected_model_profile_id=selected)
    assert calls == ([selected, None] if selected else [None])
    if selected:
        assert "predvolený reálny model" in reply
        assert saved["state"]["requested_model_profile_id"] == selected
    assert saved["state"]["pending_question"] == "Q2"
    assert saved["state"]["answers"][0]["question"] == chat.INTAKE["Q1"]
    assert "Q1: DB bude šifrovaná, prístup má ordinácia." in reply
    assert "Deklarované – overiť" in reply and "Q2:" in reply
    assert "test neoprávneného prístupu" in reply


def test_business_safeguards_link_q1_even_when_model_omits_reference():
    value = report()
    value.controls[0].question_ids = []
    value.regulations = ["MDR: chýbajú klinické dôkazy", "IVDR: chýbajú výkonové testy"]
    chat.apply_business_safeguards(value, [source()])
    assert value.controls[0].question_ids == ["Q1"]
    assert "podmienené" in value.regulations[0] and "podmienené" in value.regulations[1]
    assert "Deklarované – overiť" in chat.render(value, [source()])
