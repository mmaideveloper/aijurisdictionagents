from app.chat.provision_citations import bind_citations, provision_evidence
from app.chat.mcp_law_context import _should_use_mcp_law_context


def test_ordinary_legal_questions_do_not_need_keywords():
    for question in ("Môžem vlastniť samočinnú zbraň?", "Môže ma prenajímateľ vysťahovať?", "A ak som ešte neplnoletý?"):
        assert _should_use_mcp_law_context(query=question, country="SK", language="sk")
    assert not _should_use_mcp_law_context(query="Ďakujem!", country="SK", language="sk")


def sources():
    return provision_evidence([{
        "document_id": "synthetic", "law_number": 746, "law_year": 2026,
        "version_id": "v1", "effective_from": "2026-01-01",
        "content_text": "§ 4\nKategória A\n(1) Syntetická kategória A.\n(2) Ďalšia podmienka.\n§ 5\nKategória B je samostatná kategória.",
    }])


def test_binds_multiple_provisions_and_subsections_without_inventing_sources():
    evidence = sources()
    text, citations = bind_citations("- A [[source:p2]]\n- B [[source:p4]]\n- C [[source:fake]]", evidence, "sk")
    assert "§ 4 ods. 1 zákona č. 746/2026" in text
    assert "§ 5 zákona č. 746/2026" in text
    assert "Neoverené" in text
    assert [item["section"] for item in citations] == ["§ 4 ods. 1", "§ 5"]
    assert all("evidence_text" not in item for item in citations)


def test_model_written_citation_does_not_establish_provenance():
    text, citations = bind_citations("Toto tvrdenie údajne vyplýva zo zákona 190/2003 a jeho § 999.", sources(), "sk")
    assert "Neoverené" in text
    assert citations == []


def test_truncated_last_section_cannot_be_cited():
    assert provision_evidence([{"content_text": "§ 4\nIncomplete provision of sufficient length", "content_truncated": True}]) == []


def test_structured_anchor_ignores_cross_references_in_body():
    evidence = provision_evidence([{
        "document_id": "source", "law_number": 746, "law_year": 2026,
        "provisions": [{"anchor": "paragraf-4", "body_text": "Odkaz na § 99 a ďalší text.", "heading": "Category A"}],
    }])
    assert [item["section"] for item in evidence] == ["§ 4"]


def test_disjoint_sections_are_fetched_separately_and_truncation_is_excluded(monkeypatch):
    from app.chat import mcp_law_context
    calls = []

    def call(name, arguments):
        calls.append(arguments)
        return {"section_found": True, "content_text": "selected", "content_truncated": arguments["section_number"] == 60}

    monkeypatch.setattr(mcp_law_context, "_call_mcp_tool", call)
    result = mcp_law_context._law_text_payloads(result={"document_id": "source", "relevant_sections": [4, 60, 4]}, max_chars=40000)
    assert [item["section_number"] for item in calls] == [4, 60]
    assert len(result) == 1
    assert all("section_start" not in item and "section_end" not in item for item in calls)


def test_multiple_laws_preserve_distinct_associations():
    evidence = sources() + provision_evidence([{
        "document_id": "second-source", "law_number": 555, "law_year": 2003,
        "content_text": "§ 10\nAnother synthetic law and its provision.",
    }])
    # Tokens are unique within the combined retrieval, as produced by provision_evidence.
    for index, item in enumerate(evidence):
        item["evidence_id"] = f"p{index + 1}"
    text, used = bind_citations("First [[source:p2]]\nSecond [[source:p4]]\nThird [[source:p5]]", evidence, "en")
    assert [item["section"] for item in used] == ["§ 4 ods. 1", "§ 5", "§ 10"]
    assert "555/2003" in text and "746/2026" in text


def test_classification_prefers_defining_heading_to_incidental_references():
    from app.mcp_law_retrieval import build_legal_query_profile, score_provision_text
    profile = build_legal_query_profile("Ake skupiny zbrani definuje zakon, strucne popis?")
    definition = score_provision_text(profile=profile, title="Zbrane", heading="Zbrane kategórie A", body_text="Definícia zbraní.")
    incidental = score_provision_text(profile=profile, title="Zbrane", heading="Dovoz", body_text="Zbrane kategórie A pri dovoze.", database_rank=1.0)
    assert definition.score > incidental.score
