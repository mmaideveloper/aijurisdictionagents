from __future__ import annotations

from .domain import ProvisionRecord, SlovLexLawSnapshot


def baseline_snapshots() -> tuple[SlovLexLawSnapshot, ...]:
    return (
        SlovLexLawSnapshot(
            country_code="SK",
            collection_code="ZZ",
            year=2025,
            number=25,
            official_name="Stavebny zakon",
            lawyer_title="Stavebny zakon",
            publication_date="2025-02-05",
            effective_from="2025-04-01",
            version_token="2025-04-01",
            source_url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2025/25/",
            html_url=(
                "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2025/25/"
                "20250401/vyhlasene_znenie.html"
            ),
            pdf_url=(
                "https://www.slov-lex.sk/static/pdf/2025/25/"
                "SK_ZZ_2025_25_20250401.pdf"
            ),
            html_content="<html><body><h1>Stavebny zakon</h1><p>Vzorka textu.</p></body></html>",
            pdf_content=b"%PDF-1.4 stavebny-zakon",
            provisions=(
                ProvisionRecord(
                    anchor="par-1",
                    heading="Paragraf 1",
                    text="Tento zakon upravuje zakladne pravidla stavebneho konania.",
                ),
                ProvisionRecord(
                    anchor="par-14-2",
                    heading="Paragraf 14 ods. 2",
                    text="Lehota na vydanie rozhodnutia je 30 dni.",
                ),
            ),
            http_etag="sk-25-v20250401",
            http_last_modified="2025-02-05T08:00:00Z",
        ),
        SlovLexLawSnapshot(
            country_code="SK",
            collection_code="ZZ",
            year=2025,
            number=133,
            official_name="Oznamenie Ministerstva spravodlivosti",
            lawyer_title="Oznamenie Ministerstva spravodlivosti",
            publication_date="2025-06-05",
            effective_from="2025-06-05",
            version_token="2025-06-05",
            source_url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2025/133/",
            html_url=(
                "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2025/133/"
                "20250605/vyhlasene_znenie.html"
            ),
            pdf_url=(
                "https://www.slov-lex.sk/static/pdf/2025/133/"
                "SK_ZZ_2025_133_20250605.pdf"
            ),
            html_content="<html><body><h1>Oznamenie</h1><p>Vzorka textu.</p></body></html>",
            pdf_content=b"%PDF-1.4 oznamenie-ministerstva",
            provisions=(
                ProvisionRecord(
                    anchor="cl-1",
                    heading="Clanok 1",
                    text="Toto oznamenie zverejnuje aktualizovany zoznam vykonavacich predpisov.",
                ),
            ),
            http_etag="sk-133-v20250605",
            http_last_modified="2025-06-05T09:00:00Z",
        ),
    )


def delta_snapshots() -> tuple[SlovLexLawSnapshot, ...]:
    return (
        SlovLexLawSnapshot(
            country_code="SK",
            collection_code="ZZ",
            year=2025,
            number=25,
            official_name="Stavebny zakon",
            lawyer_title="Stavebny zakon po novele 2026",
            publication_date="2025-02-05",
            effective_from="2026-01-01",
            version_token="2026-01-01",
            source_url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2025/25/",
            html_url=(
                "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2025/25/"
                "20260101/vyhlasene_znenie.html"
            ),
            pdf_url=(
                "https://www.slov-lex.sk/static/pdf/2025/25/"
                "SK_ZZ_2025_25_20260101.pdf"
            ),
            html_content="<html><body><h1>Stavebny zakon</h1><p>Novela textu.</p></body></html>",
            pdf_content=b"%PDF-1.4 stavebny-zakon-novela",
            provisions=(
                ProvisionRecord(
                    anchor="par-1",
                    heading="Paragraf 1",
                    text="Tento zakon upravuje zakladne pravidla stavebneho konania.",
                ),
                ProvisionRecord(
                    anchor="par-14-2",
                    heading="Paragraf 14 ods. 2",
                    text="Lehota na vydanie rozhodnutia je 45 dni.",
                ),
            ),
            http_etag="sk-25-v20260101",
            http_last_modified="2025-12-20T12:15:00Z",
        ),
        SlovLexLawSnapshot(
            country_code="SK",
            collection_code="ZZ",
            year=2025,
            number=421,
            official_name="Zakon o digitalnej sluzbe verejnej spravy",
            lawyer_title="Zakon o digitalnej sluzbe verejnej spravy",
            publication_date="2025-12-10",
            effective_from="2025-12-15",
            version_token="2025-12-15",
            source_url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2025/421/",
            html_url=(
                "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2025/421/"
                "20251215/vyhlasene_znenie.html"
            ),
            pdf_url=(
                "https://www.slov-lex.sk/static/pdf/2025/421/"
                "SK_ZZ_2025_421_20251215.pdf"
            ),
            html_content="<html><body><h1>Digitalna sluzba</h1><p>Vzorka textu.</p></body></html>",
            pdf_content=b"%PDF-1.4 digitalna-sluzba",
            provisions=(
                ProvisionRecord(
                    anchor="par-2",
                    heading="Paragraf 2",
                    text="Organy verejnej spravy zverejnuju digitalne formulare v centralnom katalogu.",
                ),
            ),
            http_etag="sk-421-v20251215",
            http_last_modified="2025-12-10T15:45:00Z",
        ),
    )
