from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.document_templates.models import (
    DocumentTemplateDefinition,
    DownloadedTemplateSource,
    RenderedTemplateResult,
    TemplateSourceReference,
)


def build_default_document_templates() -> list[DocumentTemplateDefinition]:
    return [
        DocumentTemplateDefinition(
            template_id="seed-sk-commercial-agency",
            template_key="sk.contract.commercial_agency",
            jurisdiction="SK",
            language="sk-SK",
            category="Obchodne a spolocenske zmluvy",
            title="Zmluva o obchodnom zastupeni",
            template_kind="commercial_agency_agreement",
            description="Seed metadata pre vzor zmluvy o obchodnom zastupeni.",
            source_format="PDF",
            source_url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
            body="",
            keywords=("obchodne zastupenie", "obchodny zastupca", "zmluva o obchodnom zastupeni"),
            flow_keys=(),
            placeholders=("principal_identification", "agent_identification", "scope_of_authority"),
            source_refs=(
                TemplateSourceReference(
                    label="Vzory pre FO a PO",
                    url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
                    publisher="Ministerstvo spravodlivosti SR",
                    source_kind="official_form_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-share-transfer",
            template_key="sk.company.share_transfer",
            jurisdiction="SK",
            language="sk-SK",
            category="Obchodne a spolocenske zmluvy",
            title="Zmluva o prevode obchodneho podielu",
            template_kind="share_transfer_agreement",
            description="Seed metadata a pracovny body pre prevod obchodneho podielu.",
            source_format="PDF",
            source_url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
            body=(
                "Zmluva o prevode obchodneho podielu\n\n"
                "Spolocnost: {{company_name}}, ICO: {{company_identifier}}, sidlo: {{company_seat}}\n"
                "Prevodca: {{transferor_identification}}\n"
                "Nadobudatel: {{transferee_identification}}\n\n"
                "Predmet prevodu: obchodny podiel v rozsahu {{share_scope}}\n"
                "Odplata: {{transfer_price}}\n\n"
                "V {{signature_place}}, dna {{signature_date}}\n"
            ),
            keywords=("prevod obchodneho podielu", "novy vlastnik firmy", "spolocnik", "podiel"),
            flow_keys=("sk.company.owner_transfer", "sk.company.registry_change"),
            placeholders=(
                "company_name",
                "company_identifier",
                "company_seat",
                "transferor_identification",
                "transferee_identification",
                "share_scope",
                "transfer_price",
                "signature_place",
                "signature_date",
            ),
            source_refs=(
                TemplateSourceReference(
                    label="Vzory pre FO a PO",
                    url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
                    publisher="Ministerstvo spravodlivosti SR",
                    source_kind="official_form_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-sro-articles",
            template_key="sk.company.sro_articles",
            jurisdiction="SK",
            language="sk-SK",
            category="Obchodne a spolocenske zmluvy",
            title="Spolocenska zmluva s.r.o.",
            template_kind="corporate_articles",
            description="Seed metadata pre spolocensku zmluvu s.r.o.",
            source_format="PDF",
            source_url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1991/513/",
            body=(
                "Spolocenska zmluva s.r.o.\n\n"
                "Obchodne meno spolocnosti: {{company_name}}\n"
                "Sidlo spolocnosti: {{company_seat}}\n"
                "Spolocnici: {{transferee_identification}}\n"
                "Vyska podielu alebo vkladu: {{share_scope}}\n"
            ),
            keywords=("spolocenska zmluva", "s.r.o.", "zakladatelska listina"),
            flow_keys=("sk.company.registry_change",),
            placeholders=("company_name", "company_seat", "transferee_identification", "share_scope"),
            source_refs=(
                TemplateSourceReference(
                    label="Obchodny zakonnik",
                    url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1991/513/",
                    publisher="Slov-Lex",
                    source_kind="official_legislation",
                    notes="Seed URL dodana pouzivatelom ako pravny zaklad pre corporate template.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-employment-contract",
            template_key="sk.employment.employment_contract",
            jurisdiction="SK",
            language="sk-SK",
            category="Pracovne a personalne dokumenty",
            title="Pracovna zmluva",
            template_kind="employment_contract",
            description="Seed metadata pre pracovnu zmluvu.",
            source_format="DOCX/PDF",
            source_url="https://www.aksamec.sk/vzory/",
            body="",
            keywords=("pracovna zmluva", "zamestnanec", "zamestnavatel"),
            flow_keys=(),
            placeholders=("principal_identification", "agent_identification"),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec vzory",
                    url="https://www.aksamec.sk/vzory/",
                    publisher="AK Samec",
                    source_kind="external_template_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-work-agreement",
            template_key="sk.employment.work_performance_agreement",
            jurisdiction="SK",
            language="sk-SK",
            category="Pracovne a personalne dokumenty",
            title="Dohoda o vykonani prace / o pracovnej cinnosti",
            template_kind="work_agreement",
            description="Seed metadata pre dohodu o vykonani prace alebo pracovnej cinnosti.",
            source_format="DOCX/PDF",
            source_url="https://www.aksamec.sk/vzory/",
            body="",
            keywords=("dohoda o vykonani prace", "dohoda o pracovnej cinnosti", "brigada"),
            flow_keys=(),
            placeholders=(),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec vzory",
                    url="https://www.aksamec.sk/vzory/",
                    publisher="AK Samec",
                    source_kind="external_template_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-employment-termination",
            template_key="sk.employment.termination_notice",
            jurisdiction="SK",
            language="sk-SK",
            category="Pracovne a personalne dokumenty",
            title="Vypoved z pracovneho pomeru",
            template_kind="employment_termination_notice",
            description="Seed metadata pre vypoved z pracovneho pomeru.",
            source_format="PDF",
            source_url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
            body="",
            keywords=("vypoved z pracovneho pomeru", "vypoved", "skoncenie pracovneho pomeru"),
            flow_keys=(),
            placeholders=(),
            source_refs=(
                TemplateSourceReference(
                    label="Vzory pre FO a PO",
                    url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
                    publisher="Ministerstvo spravodlivosti SR",
                    source_kind="official_form_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-maintenance-alimony",
            template_key="sk.court.alimony_petition",
            jurisdiction="SK",
            language="sk-SK",
            category="Sudne podania a konania",
            title="Navrh na platenie vyzivneho",
            template_kind="court_filing",
            description="Seed metadata pre navrh na platenie vyzivneho.",
            source_format="PDF",
            source_url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
            body="",
            keywords=("vyzivne", "navrh na vyzivne", "alimenty"),
            flow_keys=(),
            placeholders=(),
            source_refs=(
                TemplateSourceReference(
                    label="Vzory pre FO a PO",
                    url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
                    publisher="Ministerstvo spravodlivosti SR",
                    source_kind="official_form_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-payment-order",
            template_key="sk.court.payment_order",
            jurisdiction="SK",
            language="sk-SK",
            category="Sudne podania a konania",
            title="Platobny rozkaz",
            template_kind="court_filing",
            description="Seed metadata pre platobny rozkaz.",
            source_format="PDF",
            source_url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
            body="",
            keywords=("platobny rozkaz", "upominacie konanie", "dlh"),
            flow_keys=(),
            placeholders=(),
            source_refs=(
                TemplateSourceReference(
                    label="Vzory pre FO a PO",
                    url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
                    publisher="Ministerstvo spravodlivosti SR",
                    source_kind="official_form_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-court-action",
            template_key="sk.court.general_action",
            jurisdiction="SK",
            language="sk-SK",
            category="Sudne podania a konania",
            title="Zaloba / navrh na sudne konanie",
            template_kind="court_filing",
            description="Seed metadata pre vseobecnu zalobu alebo navrh na sudne konanie.",
            source_format="PDF",
            source_url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
            body="",
            keywords=("zaloba", "navrh na sudne konanie", "sudne podanie"),
            flow_keys=(),
            placeholders=(),
            source_refs=(
                TemplateSourceReference(
                    label="Vzory pre FO a PO",
                    url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
                    publisher="Ministerstvo spravodlivosti SR",
                    source_kind="official_form_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-general-poa",
            template_key="sk.authorization.general_power_of_attorney",
            jurisdiction="SK",
            language="sk-SK",
            category="Plne moci a autorizacie",
            title="Plna moc vseobecna",
            template_kind="power_of_attorney",
            description="Seed metadata a pracovny body pre vseobecnu plnu moc.",
            source_format="DOCX/PDF",
            source_url="https://www.aksamec.sk/vzory/",
            body=(
                "Plna moc\n\n"
                "Splnomocnitel: {{principal_identification}}\n"
                "Splnomocnenec: {{agent_identification}}\n\n"
                "Rozsah splnomocnenia: {{scope_of_authority}}\n"
                "Platnost: {{validity_period}}\n\n"
                "V {{signature_place}}, dna {{signature_date}}\n"
            ),
            keywords=("plna moc vseobecna", "splnomocnenie", "plna moc"),
            flow_keys=("sk.civil.power_of_attorney",),
            placeholders=(
                "principal_identification",
                "agent_identification",
                "scope_of_authority",
                "validity_period",
                "signature_place",
                "signature_date",
            ),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec vzory",
                    url="https://www.aksamec.sk/vzory/",
                    publisher="AK Samec",
                    source_kind="external_template_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-special-poa",
            template_key="sk.authorization.special_power_of_attorney",
            jurisdiction="SK",
            language="sk-SK",
            category="Plne moci a autorizacie",
            title="Plna moc specialna",
            template_kind="power_of_attorney",
            description="Seed metadata pre specialnu plnu moc.",
            source_format="PDF",
            source_url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
            body="",
            keywords=("plna moc specialna", "specialne splnomocnenie", "plna moc"),
            flow_keys=("sk.civil.power_of_attorney",),
            placeholders=("principal_identification", "agent_identification", "scope_of_authority"),
            source_refs=(
                TemplateSourceReference(
                    label="Vzory pre FO a PO",
                    url="https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/",
                    publisher="Ministerstvo spravodlivosti SR",
                    source_kind="official_form_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-sale-purchase",
            template_key="sk.real_estate.sale_purchase",
            jurisdiction="SK",
            language="sk-SK",
            category="Nehnutelnosti a najom",
            title="Kupno-predajna zmluva",
            template_kind="sale_purchase_agreement",
            description="Seed metadata a pracovny body pre kupno-predajnu zmluvu.",
            source_format="DOCX/PDF",
            source_url="https://www.aksamec.sk/vzory/",
            body=(
                "Kupna zmluva\n\n"
                "Predavajuci: {{seller_identification}}\n"
                "Kupujuci: {{buyer_identification}}\n"
                "Predmet kupy: {{subject_description}}\n"
                "Kupna cena: {{purchase_price}}\n"
                "Platobne podmienky: {{payment_terms}}\n"
            ),
            keywords=("kupno predajna zmluva", "kupna zmluva", "predaj nehnutelnosti", "predaj"),
            flow_keys=("sk.contract.sale_purchase",),
            placeholders=(
                "seller_identification",
                "buyer_identification",
                "subject_description",
                "purchase_price",
                "payment_terms",
            ),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec vzory",
                    url="https://www.aksamec.sk/vzory/",
                    publisher="AK Samec",
                    source_kind="external_template_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-donation",
            template_key="sk.real_estate.gift_agreement",
            jurisdiction="SK",
            language="sk-SK",
            category="Nehnutelnosti a najom",
            title="Darovacia zmluva",
            template_kind="gift_agreement",
            description="Seed metadata pre darovaciu zmluvu.",
            source_format="DOCX/PDF",
            source_url="https://www.aksamec.sk/vzory/",
            body="",
            keywords=("darovacia zmluva", "darovanie", "prevod darom"),
            flow_keys=(),
            placeholders=("seller_identification", "buyer_identification", "subject_description"),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec vzory",
                    url="https://www.aksamec.sk/vzory/",
                    publisher="AK Samec",
                    source_kind="external_template_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
        DocumentTemplateDefinition(
            template_id="seed-sk-lease",
            template_key="sk.real_estate.lease_agreement",
            jurisdiction="SK",
            language="sk-SK",
            category="Nehnutelnosti a najom",
            title="Najomna zmluva",
            template_kind="rental_agreement",
            description="Seed metadata a pracovny body pre najomnu zmluvu.",
            source_format="DOCX/PDF",
            source_url="https://www.aksamec.sk/vzory/",
            body=(
                "Najomna zmluva\n\n"
                "Prenajimatel: {{landlord_identification}}\n"
                "Najomca: {{tenant_identification}}\n"
                "Predmet najmu: {{property_identification}}\n"
                "Doba najmu: {{lease_term}}\n"
                "Najomne: {{rent_terms}}\n"
                "Kaucia: {{security_deposit}}\n"
                "Ukoncenie najmu: {{termination_terms}}\n"
            ),
            keywords=("najomna zmluva", "prenajom", "najom bytu", "najom"),
            flow_keys=("sk.civil.lease_advisory",),
            placeholders=(
                "landlord_identification",
                "tenant_identification",
                "property_identification",
                "lease_term",
                "rent_terms",
                "security_deposit",
                "termination_terms",
            ),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec vzory",
                    url="https://www.aksamec.sk/vzory/",
                    publisher="AK Samec",
                    source_kind="external_template_index",
                    notes="Seed URL dodana pouzivatelom.",
                ),
            ),
            is_enabled=True,
            is_deleted=False,
        ),
    ]


def render_template(
    *,
    template: DocumentTemplateDefinition,
    facts: dict[str, str],
    country: str,
    language: str | None,
) -> RenderedTemplateResult:
    if not template.body.strip():
        return RenderedTemplateResult(title=template.title, lines=[], unresolved_fields=[])
    context = _build_render_context(facts=facts, country=country, language=language)
    unresolved_fields: list[str] = []

    def replace(match: re.Match[str]) -> str:
        field_name = match.group(1).strip()
        value = context.get(field_name)
        if value is None:
            unresolved_fields.append(field_name)
            return _todo_marker(field_name=field_name, country=country, language=language)
        if value.startswith("[DOPLNIT:") or value.startswith("[TODO:"):
            unresolved_fields.append(field_name)
        return value

    rendered = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", replace, template.body)
    return RenderedTemplateResult(
        title=template.title,
        lines=[line.rstrip() for line in rendered.splitlines() if line.strip()],
        unresolved_fields=list(dict.fromkeys(unresolved_fields)),
    )


def download_template_sources(
    *,
    templates: list[DocumentTemplateDefinition],
    download_dir: Path,
) -> list[DownloadedTemplateSource]:
    download_dir.mkdir(parents=True, exist_ok=True)
    results: list[DownloadedTemplateSource] = []
    seen_urls: set[str] = set()
    for item in templates:
        urls = [item.source_url, *[source.url for source in item.source_refs]]
        for url in urls:
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            raw_name = Path(urlparse(url).path).name or "index.html"
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name) or "download.bin"
            target = download_dir / safe_name
            if not target.exists():
                request = Request(url, headers={"User-Agent": "aijurisdictionagents-template-catalog/1.0"})
                with urlopen(request, timeout=30) as response:
                    target.write_bytes(response.read())
            results.append(
                DownloadedTemplateSource(
                    template_key=item.template_key,
                    source_url=url,
                    downloaded_to=target,
                )
            )
    return results


def _build_render_context(*, facts: dict[str, str], country: str, language: str | None) -> dict[str, str]:
    values = {key: str(value).strip() for key, value in facts.items() if str(value).strip()}
    values.update(
        {
            "landlord_identification": _value(values, "prenajimatel"),
            "tenant_identification": _value(values, "najomca"),
            "property_identification": _value(values, "predmet"),
            "lease_term": _value(values, "doba"),
            "rent_terms": _value(values, "najomne"),
            "security_deposit": _value(values, "deposit"),
            "termination_terms": _value(values, "notice"),
            "principal_identification": _value(values, "client_name"),
            "agent_identification": _value(values, "opponent_name"),
            "scope_of_authority": _value(values, "topic", "urceny pravny ukon"),
            "validity_period": _value(values, "scheduled_for", "do splnenia ukonu"),
            "seller_identification": _value(values, "transferor_name", _value(values, "client_name")),
            "buyer_identification": _value(values, "transferee_name", _value(values, "opponent_name")),
            "subject_description": _value(values, "topic", _value(values, "facts_summary")),
            "purchase_price": _value(values, "transfer_price", "0 EUR"),
            "payment_terms": _value(values, "estimated_timeline", "dohodou zmluvnych stran"),
            "company_name": _value(values, "company_name"),
            "company_identifier": _value(values, "company_identifier"),
            "company_seat": _value(values, "company_seat"),
            "transferor_identification": _value(values, "transferor_name"),
            "transferee_identification": _value(values, "transferee_name"),
            "share_scope": _value(values, "transfer_share"),
            "transfer_price": _value(values, "transfer_price", "0 EUR"),
            "signature_place": "[mesto]",
            "signature_date": "[datum]",
        }
    )
    return {
        key: value if value else _todo_marker(field_name=key, country=country, language=language)
        for key, value in values.items()
    }


def _value(values: dict[str, str], key: str, default: str = "") -> str:
    return str(values.get(key, "")).strip() or default


def _todo_marker(*, field_name: str, country: str, language: str | None) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return f"[DOPLNIT: {field_name}]"
    return f"[TODO: {field_name}]"

