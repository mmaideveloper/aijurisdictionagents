from app.mcp_law_retrieval import (
    build_legal_query_profile,
    build_postgres_legal_tsquery,
    build_postgres_legal_tsqueries,
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


def test_misspelled_prepare_purchase_agreement_still_selects_purchase_contract() -> None:
    profile = build_legal_query_profile("pripare kupno predoajnu zmluvu")

    assert profile.concepts == ("purchase_contract", "real_estate")
    assert "kup" in profile.query_roots
    assert {
        "predaj",
        "zmluv",
        "cena",
        "predav",
        "kupuj",
        "nehnutel",
        "katastr",
        "vklad",
    }.issubset(profile.expanded_roots)

    tsquery = build_postgres_legal_tsquery(profile)
    assert "kup:*" in tsquery
    assert "zmluv:*" in tsquery
    assert "kup:* | zmluv:*" not in tsquery


def test_ambiguous_sale_does_not_infer_property_transfer_formalities() -> None:
    profile = build_legal_query_profile("predaj")

    assert profile.concepts == ("purchase_contract",)
    assert "katastr" not in profile.expanded_roots
    assert len(build_postgres_legal_tsqueries(profile)) == 1


def test_purchase_of_garden_tsquery_uses_selective_contract_and_property_pairs() -> None:
    profile = build_legal_query_profile("kúpna zmluva na záhradu")

    tsquery = build_postgres_legal_tsquery(profile)

    assert "kup:*" in tsquery
    assert "zmluv:*" in tsquery
    assert "prevod:*" in tsquery
    assert "nehnutel:*" in tsquery
    assert "vklad:*" in tsquery
    assert "navrh:*" in tsquery
    assert "parcel:*" in tsquery
    assert "podpis:*" in tsquery
    assert len(build_postgres_legal_tsqueries(profile)) == 5


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


def test_provision_scoring_rewards_concept_terms_in_authoritative_title() -> None:
    profile = build_legal_query_profile("kúpna zmluva na záhradu")
    cadastral = score_provision_text(
        profile=profile,
        title="Zákon o katastri nehnuteľností (katastrálny zákon)",
        heading="Konanie o návrhu na vklad",
        body_text="Okresný úrad preskúma zmluvu o prevode nehnuteľnosti.",
    )
    incidental = score_provision_text(
        profile=profile,
        title="Všeobecný zákon",
        heading="Iné ustanovenie",
        body_text="Okresný úrad preskúma zmluvu o prevode nehnuteľnosti.",
    )

    assert cadastral.score > incidental.score


def test_compact_section_ranges_bridges_repealed_or_unmatched_neighbor() -> None:
    assert compact_section_ranges({46, 133, 588, 589, 590, 591, 592, 593, 595, 597, 599, 600}) == (
        (46, 46),
        (133, 133),
        (588, 600),
    )
    assert compact_section_ranges({28, 30, 31, 42}) == ((28, 31), (42, 42))
    assert compact_section_ranges({28, 31, 42}, maximum_gap=3) == ((28, 31), (42, 42))
