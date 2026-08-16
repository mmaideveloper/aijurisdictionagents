from app.mcp_law_retrieval import (
    build_legal_query_profile,
    compact_section_ranges,
    parse_provision_anchor,
    relevance_confidence,
    score_provision_text,
)


def test_purchase_of_garden_query_expands_to_contract_and_real_estate_concepts() -> None:
    profile = build_legal_query_profile("chcem kupno predajnu zmluvu na zahradu")

    assert profile.concepts == ("purchase_contract", "real_estate")
    assert {"kup", "predaj", "zahrad"}.issubset(profile.query_roots)
    assert {"zmluv", "prevod", "vlastnict", "katastr", "vklad"}.issubset(
        profile.expanded_roots
    )
    assert {"kup", "kúp", "nehnutel", "nehnuteľ"}.issubset(profile.search_terms)


def test_query_normalization_supports_slovak_diacritics() -> None:
    accented = build_legal_query_profile("Kúpno-predajná zmluva na záhradu")
    unaccented = build_legal_query_profile("kupno predajna zmluva na zahradu")

    assert accented.query_roots == unaccented.query_roots
    assert accented.concepts == unaccented.concepts


def test_parse_provision_anchor_returns_section_and_paragraph() -> None:
    parsed = parse_provision_anchor("paragraf-133.odsek-2.text")

    assert parsed is not None
    assert parsed.section_number == 133
    assert parsed.paragraph_number == 2
    assert parse_provision_anchor("clanok-1.odsek-2.text") is None


def test_provision_scoring_prefers_grounded_purchase_and_property_text() -> None:
    profile = build_legal_query_profile("kúpno-predajná zmluva na záhradu")
    relevant = score_provision_text(
        profile=profile,
        title="Občiansky zákonník",
        heading="Kúpna zmluva",
        body_text=(
            "Z kúpnej zmluvy vznikne predávajúcemu povinnosť predmet odovzdať "
            "a kupujúcemu povinnosť predmet prevziať a zaplatiť dohodnutú cenu."
        ),
    )
    unrelated = score_provision_text(
        profile=profile,
        title="Zákon o reklame",
        heading="Všeobecné ustanovenia",
        body_text="Tento zákon upravuje požiadavky na reklamu.",
    )

    assert relevant.score > unrelated.score
    assert relevance_confidence(relevant.score) in {"medium", "high"}
    assert relevance_confidence(unrelated.score) == "low"


def test_compact_section_ranges_bridges_repealed_or_unmatched_neighbor() -> None:
    assert compact_section_ranges({46, 133, 588, 589, 590, 591, 592, 593, 595, 597, 599, 600}) == (
        (46, 46),
        (133, 133),
        (588, 600),
    )
    assert compact_section_ranges({28, 30, 31, 42}) == ((28, 31), (42, 42))
