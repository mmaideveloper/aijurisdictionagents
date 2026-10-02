from app.chat.provision_citations import bind_citations, provision_evidence
from app.chat.mcp_law_context import _should_use_mcp_law_context
import pytest


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


def test_table_structure_survives_binding_and_unverified_rows_remain_visible():
    header = "| Category | Legal status and conditions from the supplied sources |"
    separator = "| --- | :---: |"
    supported = "| A | Synthetic category supported by evidence [[source:p1]] |"
    unsupported = "| B | An unsupported legal assertion with enough text to require a warning. |"
    text, citations = bind_citations("\n".join([header, separator, supported, unsupported]), sources(), "sk")
    lines = text.splitlines()
    assert lines[:2] == [header, separator]
    assert "§ 4 zákona" in lines[2]
    assert lines[3].endswith("*[Neoverené v zdrojoch]* |")
    assert len(citations) == 1
    assert all(line.count("|") == 3 for line in lines)


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


@pytest.mark.parametrize("structured", [False, True])
@pytest.mark.parametrize("url,expected", [
    ("https://static.slov-lex.sk/static/SK/ZZ/2003/190/20250701.html", True),
    ("https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2003/190/", True),
    ("http://internal-mcp/source", False),
    ("https://internal-mcp/source", False),
    ("https://www.slov-lex.sk.evil.test/source", False),
    ("https://user:password@www.slov-lex.sk/source", False),
    ("https://www.slov-lex.sk:8080/source", False),
    ("https://www.slov-lex.sk/source?token=synthetic", False),
    ("javascript:alert(1)", False),
])
def test_provision_metadata_preserves_only_official_public_urls(structured, url, expected):
    payload = {"document_id": "source", "law_number": 746, "law_year": 2026,
               "source_url": url, "content_text": "§ 4\nA synthetic provision with sufficient text."}
    if structured:
        payload["provisions"] = [{"anchor": "paragraf-4", "body_text": "Synthetic provision text."}]
    evidence = provision_evidence([payload])
    assert evidence[0]["source_url"] == (url if expected else None)


def test_latest_listing_retains_every_source_when_only_two_laws_have_provision_context(monkeypatch):
    from app.chat import mcp_law_context
    laws = [{"document_id": f"law-{index}", "law_number": index, "law_year": 2026,
             "law_identifier_text": f"{index}/2026", "title": f"Synthetic law {index}",
             "summary": f"Synthetic summary {index}", "effective_from": "2026-01-01"}
            for index in range(1, 6)]

    def call(name, arguments):
        if name == "searchLaws":
            return {"results": laws}
        return {"document_id": arguments["document_id"], "law_number": 1, "law_year": 2026,
                "content_text": "§ 4\nSynthetic provision which must not displace other laws."}

    monkeypatch.setattr(mcp_law_context, "_call_mcp_tool", call)
    context = mcp_law_context._build_laws_only_context(
        query="Daj mi poslednych 5 novych zakonov aj so sumarom coho sa tykaju.",
        search_limit=5, text_limit=2, max_chars_per_law=40000, language="sk", web_search_approved=False,
    )
    assert context.grounded_latest_laws_reply
    citations = context.processing_event["details"]["citations"]
    assert {item["source_id"] for item in citations} == {f"law-{index}" for index in range(1, 6)}
    assert all("evidence_id" not in item and "evidence_text" not in item for item in citations)
