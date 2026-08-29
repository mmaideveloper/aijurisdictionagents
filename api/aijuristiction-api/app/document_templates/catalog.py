from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.document_templates.ministry_catalog import build_ministry_page_document_templates
from app.document_templates.models import (
    DocumentTemplateDefinition,
    DownloadedTemplateSource,
    RenderedTemplateResult,
    TemplateSourceReference,
)


def build_default_document_templates() -> list[DocumentTemplateDefinition]:
    return _merge_template_seeds(
        [
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
            description=(
                "Kontrolovany kanonicky zaklad slovenskej pracovnej zmluvy s povinnymi nalezitostami, "
                "zaverecnymi ustanoveniami a podpisovymi blokmi. Pred podpisom vyzaduje doplnenie faktov "
                "a individualnu kontrolu pravnikom alebo pracovnopravnym specialistom."
            ),
            source_format="HTML/LAW",
            source_url="https://www.aksamec.sk/pracovna-zmluva-vzor-2026/",
            body=(
                "PRACOVNÁ ZMLUVA\n"
                "uzatvorená podľa § 42 a nasl. zákona č. 311/2001 Z. z. Zákonník práce\n\n"
                "Zamestnávateľ:\n"
                "{{employer_business_name}}\n"
                "Sídlo: {{employer_seat}}\n"
                "IČO: {{employer_ico}}\n"
                "Osoba oprávnená konať: {{employer_representative}}\n"
                "E-mail: {{employer_email}}\n"
                "Telefón: {{employer_phone}}\n\n"
                "Zamestnanec:\n"
                "{{employee_full_name}}\n"
                "Dátum narodenia: {{employee_birth_date}}\n"
                "Rodné číslo: {{employee_birth_number}}\n"
                "Adresa trvalého pobytu: {{employee_residence}}\n"
                "Číslo občianskeho preukazu: {{employee_id_card_number}}\n"
                "E-mail: {{employee_email}}\n"
                "Telefón: {{employee_phone}}\n\n"
                "(ďalej spolu aj ako „zmluvné strany“) uzatvárajú túto pracovnú zmluvu:\n\n"
                "Článok I\n"
                "DRUH PRÁCE A JEHO STRUČNÁ CHARAKTERISTIKA\n"
                "1. Zamestnanec bude vykonávať druh práce: {{job_position}}.\n"
                "2. Stručná charakteristika dohodnutého druhu práce: {{job_description}}.\n\n"
                "Článok II\n"
                "MIESTO VÝKONU PRÁCE A DEŇ NÁSTUPU\n"
                "1. Miesto alebo miesta výkonu práce, prípadne pravidlo ich určovania: {{place_of_work}}.\n"
                "2. Dohodnutý deň nástupu do práce: {{start_date}}.\n\n"
                "Článok III\n"
                "TRVANIE PRACOVNÉHO POMERU A SKÚŠOBNÁ DOBA\n"
                "1. Pracovný pomer sa uzatvára na {{employment_term_description}}.\n"
                "2. Skúšobná doba je {{probation_period}}.\n\n"
                "Článok IV\n"
                "MZDOVÉ PODMIENKY\n"
                "1. Zamestnancovi patrí základná zložka mzdy vo výške {{base_monthly_salary}} brutto mesačne.\n"
                "2. Ďalšie zložky mzdy, podmienky ich priznania a výplatný termín: {{variable_salary_component}} "
                "Výplatný termín: {{salary_payday}}. Spôsob vyplácania mzdy: {{salary_payment_method}}.\n\n"
                "Článok V\n"
                "PRACOVNÉ PODMIENKY\n"
                "1. Ustanovený týždenný pracovný čas a jeho rozvrhnutie: {{weekly_working_hours}}; "
                "{{working_time_distribution}}.\n"
                "2. Výmera dovolenky: {{vacation_entitlement}}.\n"
                "3. Ďalšie pracovné podmienky a pracovné vybavenie: {{additional_work_conditions}}.\n\n"
                "Článok VI\n"
                "PRÁVA A POVINNOSTI ZMLUVNÝCH STRÁN\n"
                "1. Zamestnávateľ prideľuje zamestnancovi prácu podľa tejto zmluvy, vytvára podmienky na jej "
                "riadny výkon a vypláca dohodnutú mzdu.\n"
                "2. Zamestnanec vykonáva prácu osobne, riadne a v dohodnutom pracovnom čase a dodržiava "
                "právne a vnútorné predpisy, s ktorými bol preukázateľne oboznámený.\n"
                "3. Zamestnávateľ spracúva osobné údaje zamestnanca len v rozsahu a na účely potrebné na "
                "vznik, plnenie a evidenciu pracovnoprávneho vzťahu a poskytne mu samostatnú informáciu o "
                "spracúvaní osobných údajov.\n\n"
                "Článok VII\n"
                "ZÁVEREČNÉ USTANOVENIA\n"
                "1. Táto zmluva je vyhotovená v dvoch rovnopisoch; jeden dostane zamestnanec a jeden "
                "zamestnávateľ.\n"
                "2. Zmeny tejto zmluvy možno vykonať iba písomnou dohodou zmluvných strán, ak právny "
                "predpis neustanovuje inak.\n"
                "3. Práva a povinnosti výslovne neupravené touto zmluvou sa spravujú Zákonníkom práce a "
                "ostatnými všeobecne záväznými právnymi predpismi Slovenskej republiky.\n"
                "4. Zmluvné strany potvrdzujú, že si zmluvu prečítali, jej obsahu porozumeli a na znak "
                "súhlasu ju podpisujú slobodne a vážne.\n\n"
                "V {{signature_place}}, dňa {{signature_date}}\n\n"
                "Za zamestnávateľa: {{employer_signatory_name}}\n"
                "Zamestnanec: {{employee_signatory_name}}\n"
            ),
            keywords=("pracovna zmluva", "zamestnanec", "zamestnavatel"),
            flow_keys=(),
            placeholders=(
                "employer_business_name",
                "employer_seat",
                "employer_ico",
                "employer_representative",
                "employer_email",
                "employer_phone",
                "employee_full_name",
                "employee_birth_date",
                "employee_birth_number",
                "employee_residence",
                "employee_id_card_number",
                "employee_email",
                "employee_phone",
                "job_position",
                "job_description",
                "place_of_work",
                "start_date",
                "employment_term_description",
                "probation_period",
                "base_monthly_salary",
                "variable_salary_component",
                "salary_payday",
                "salary_payment_method",
                "weekly_working_hours",
                "working_time_distribution",
                "vacation_entitlement",
                "additional_work_conditions",
                "signature_place",
                "signature_date",
                "employer_signatory_name",
                "employee_signatory_name",
            ),
            source_refs=(
                TemplateSourceReference(
                    label="Pracovná zmluva – vzor 2026",
                    url="https://www.aksamec.sk/pracovna-zmluva-vzor-2026/",
                    publisher="AK Samec",
                    source_kind="reviewed_template_guidance",
                    notes=(
                        "Presna zdrojova stranka skontrolovana 2026-08-28; pouzita na strukturalnu kontrolu "
                        "povinnych a volitelnych nalezitosti. Kanonicke telo je povodny text JurisDigta."
                    ),
                ),
                TemplateSourceReference(
                    label="Zákon č. 311/2001 Z. z. Zákonník práce",
                    url="https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2001/311/",
                    publisher="Ministerstvo spravodlivosti SR – Slov-Lex",
                    source_kind="official_legislation",
                    notes=(
                        "Oficialne konsolidovane znenie skontrolovane 2026-08-28; pravny zaklad najma § 42 "
                        "az § 44. Pred pouzitim treba overit aktualne znenie a konkretne skutkove okolnosti."
                    ),
                ),
            ),
            disclaimer_title="Dôležité upozornenie",
            disclaimer_text=(
                "Toto je vzorový právny návrh vytvorený na základe všeobecných požiadaviek slovenského "
                "pracovného práva. Nie je právnym poradenstvom ani hotovou zmluvou. Pred podpisom doplňte "
                "všetky označené údaje, overte aktuálne právne znenie a zabezpečte individuálnu ľudskú kontrolu."
            ),
            disclaimer_footer="Vzorový návrh – pred podpisom vyžaduje individuálnu ľudskú a právnu kontrolu.",
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
        ],
        build_ministry_page_document_templates(),
    )


def render_template(
    *,
    template: DocumentTemplateDefinition,
    facts: dict[str, str],
    country: str,
    language: str | None,
) -> RenderedTemplateResult:
    if not template.body.strip():
        return RenderedTemplateResult(title=template.title, lines=[], unresolved_fields=[])
    context = _build_render_context(
        facts=facts,
        country=country,
        language=language,
        template_key=template.template_key,
        template_kind=template.template_kind,
    )
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
        missing_required_fields=_missing_required_template_fields(
            template_key=template.template_key,
            facts=facts,
            country=country,
            language=language,
        ),
        follow_up_question=_template_follow_up_question(
            template_key=template.template_key,
            facts=facts,
            country=country,
            language=language,
        ),
    )


def apply_employment_profile_defaults(
    *,
    facts: dict[str, str],
    profile_defaults: dict[str, str],
) -> dict[str, str]:
    enriched = dict(facts)
    for field_name, profile_key in (
        ("employee_full_name", "display_name"),
        ("employee_signatory_name", "display_name"),
        ("employee_residence", "address"),
        ("employee_birth_date", "date_of_birth"),
        ("employee_birth_number", "birth_number"),
        ("employee_id_card_number", "identity_card_number"),
        ("employee_email", "email"),
        ("employee_phone", "phone_number"),
    ):
        if enriched.get(field_name):
            continue
        value = str(profile_defaults.get(profile_key, "")).strip()
        if value:
            enriched[field_name] = value
    return enriched


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


def _build_render_context(
    *,
    facts: dict[str, str],
    country: str,
    language: str | None,
    template_key: str,
    template_kind: str,
) -> dict[str, str]:
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
    if template_key == "sk.employment.employment_contract" or template_kind == "employment_contract":
        values.update(_employment_contract_render_values(values))
    return {
        key: value if value else _todo_marker(field_name=key, country=country, language=language)
        for key, value in values.items()
    }


def _value(values: dict[str, str], key: str, default: str = "") -> str:
    return str(values.get(key, "")).strip() or default


def _employment_contract_render_values(values: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for field_name, aliases in _EMPLOYMENT_CONTRACT_FIELD_ALIASES.items():
        resolved[field_name] = _first_present(values, field_name, *aliases)
    optional_defaults = {
        "probation_period": "nedohodla sa",
        "variable_salary_component": "neuplatňujú sa ďalšie zložky mzdy, ak sa strany písomne nedohodnú inak.",
        "salary_payday": "najneskôr v kalendárny deň určený vnútornými pravidlami zamestnávateľa",
        "salary_payment_method": "bezhotovostným prevodom na určený účet zamestnanca",
        "working_time_distribution": "rozvrhnutie určí zamestnávateľ v súlade so Zákonníkom práce",
        "vacation_entitlement": "v rozsahu podľa Zákonníka práce",
        "additional_work_conditions": "ďalšie pracovné podmienky budú uvedené v písomnej informácii zamestnávateľa",
        "employer_email": "neuvedené",
        "employer_phone": "neuvedené",
        "employee_birth_number": "neuvedené",
        "employee_id_card_number": "neuvedené",
        "employee_email": "neuvedené",
        "employee_phone": "neuvedené",
        "signature_place": "miesto bude doplnené pred podpisom",
        "signature_date": "dátum bude doplnený pred podpisom",
    }
    for field_name, default in optional_defaults.items():
        if not resolved.get(field_name):
            resolved[field_name] = default
    if not resolved.get("employer_signatory_name"):
        resolved["employer_signatory_name"] = resolved.get("employer_representative", "")
    if not resolved.get("employee_signatory_name"):
        resolved["employee_signatory_name"] = resolved.get("employee_full_name", "")
    if not resolved.get("additional_work_conditions"):
        extra_parts = [
            resolved.get("working_time_distribution", ""),
            resolved.get("vacation_entitlement", ""),
        ]
        resolved["additional_work_conditions"] = "; ".join(part for part in extra_parts if part)
    return resolved


def _missing_required_template_fields(
    *,
    template_key: str,
    facts: dict[str, str],
    country: str,
    language: str | None,
) -> list[str]:
    if template_key != "sk.employment.employment_contract":
        return []
    resolved = _employment_contract_render_values(
        {key: str(value).strip() for key, value in facts.items() if str(value).strip()}
    )
    missing: list[str] = []
    for field_name in _EMPLOYMENT_CONTRACT_REQUIRED_FIELDS:
        value = resolved.get(field_name, "")
        if not value or value == _todo_marker(field_name=field_name, country=country, language=language):
            missing.append(field_name)
    return missing


def _template_follow_up_question(
    *,
    template_key: str,
    facts: dict[str, str],
    country: str,
    language: str | None,
) -> str | None:
    if template_key != "sk.employment.employment_contract":
        return None
    missing = _missing_required_template_fields(
        template_key=template_key,
        facts=facts,
        country=country,
        language=language,
    )
    if not missing:
        return None
    first = missing[0]
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return _EMPLOYMENT_CONTRACT_FIELD_QUESTIONS[first]
    return f"Please provide the required employment-contract field: {first}."


def _first_present(values: dict[str, str], key: str, *aliases: str) -> str:
    for candidate in (key, *aliases):
        value = str(values.get(candidate, "")).strip()
        if value:
            return value
    return ""


def _todo_marker(*, field_name: str, country: str, language: str | None) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return f"[DOPLNIT: {field_name}]"
    return f"[TODO: {field_name}]"


_EMPLOYMENT_CONTRACT_REQUIRED_FIELDS = (
    "employer_business_name",
    "employer_seat",
    "employer_ico",
    "employer_representative",
    "employee_full_name",
    "employee_birth_date",
    "employee_residence",
    "job_position",
    "job_description",
    "place_of_work",
    "start_date",
    "employment_term_description",
    "base_monthly_salary",
    "weekly_working_hours",
)

_EMPLOYMENT_CONTRACT_FIELD_QUESTIONS = {
    "employer_business_name": "Aké je obchodné meno zamestnávateľa?",
    "employer_seat": "Aké je sídlo zamestnávateľa?",
    "employer_ico": "Aké je IČO zamestnávateľa?",
    "employer_representative": "Kto je osoba oprávnená konať za zamestnávateľa?",
    "employee_full_name": "Aké je celé meno zamestnanca?",
    "employee_birth_date": "Aký je dátum narodenia zamestnanca?",
    "employee_residence": "Aký je trvalý pobyt zamestnanca?",
    "job_position": "Aká je pracovná pozícia zamestnanca?",
    "job_description": "Aký druh práce alebo stručná charakteristika práce sa má do zmluvy uviesť?",
    "place_of_work": "Aké je miesto výkonu práce?",
    "start_date": "Aký je dohodnutý deň nástupu do práce?",
    "employment_term_description": "Ide o pracovný pomer na dobu neurčitú alebo určitú?",
    "base_monthly_salary": "Aká je dohodnutá základná mesačná mzda?",
    "weekly_working_hours": "Aký je ustanovený týždenný pracovný čas?",
}

_EMPLOYMENT_CONTRACT_FIELD_ALIASES = {
    "employer_business_name": (
        "obchodne_meno",
        "obchodné_meno",
        "zamestnavatel",
        "zamestnávateľ",
        "employer_name",
        "company_name",
    ),
    "employer_seat": ("sidlo", "sídlo", "employer_seat", "company_seat"),
    "employer_ico": ("ico", "ičo", "company_identifier", "company_id"),
    "employer_representative": ("zastupeny", "zastúpený", "employer_representative"),
    "employer_email": ("zamestnavatel_email", "zamestnávateľ_email", "employer_email"),
    "employer_phone": ("zamestnavatel_telefon", "zamestnávateľ_telefón", "employer_phone"),
    "employee_full_name": ("meno_a_priezvisko", "employee_name", "client_name"),
    "employee_birth_date": ("datum_narodenia", "dátum_narodenia", "date_of_birth"),
    "employee_birth_number": ("rodne_cislo", "rodné_číslo", "social_security_number"),
    "employee_residence": ("trvaly_pobyt", "trvalý_pobyt", "employee_address", "address"),
    "employee_id_card_number": (
        "cislo_obcianskeho_preukazu",
        "číslo_občianskeho_preukazu",
        "identity_card_number",
    ),
    "employee_email": ("zamestnanec_email", "employee_email", "email"),
    "employee_phone": ("zamestnanec_telefon", "zamestnanec_telefón", "employee_phone", "phone_number"),
    "job_position": ("pracovna_pozicia", "pracovná_pozícia", "job_position"),
    "job_description": ("druh_prace", "druh_práce", "job_description"),
    "place_of_work": ("miesto_vykonu_prace", "miesto_výkonu_práce", "place_of_work"),
    "start_date": ("den_nastupu", "deň_nástupu", "start_date"),
    "employment_term_description": (
        "druh_pracovneho_pomeru",
        "druh_pracovného_pomeru",
        "employment_term_description",
    ),
    "probation_period": ("skusobna_doba", "skúšobná_doba", "probation_period"),
    "base_monthly_salary": (
        "zakladna_mesacna_mzda",
        "základná_mesačná_mzda",
        "base_monthly_salary",
    ),
    "variable_salary_component": (
        "variabilna_zlozka_mzdy",
        "variabilná_zložka_mzdy",
        "variable_salary_component",
    ),
    "salary_payday": ("vyplatny_termin", "výplatný_termín", "salary_payday"),
    "salary_payment_method": (
        "sposob_vyplacania_mzdy",
        "spôsob_vyplácania_mzdy",
        "salary_payment_method",
    ),
    "weekly_working_hours": (
        "tyzdenny_pracovny_cas",
        "týždenný_pracovný_čas",
        "weekly_working_hours",
    ),
    "working_time_distribution": (
        "rozvrhnutie_pracovneho_casu",
        "rozvrhnutie_pracovného_času",
        "working_time_distribution",
    ),
    "vacation_entitlement": ("dovolenka", "vacation_entitlement"),
    "additional_work_conditions": (
        "dalsie_pracovne_podmienky",
        "ďalšie_pracovné_podmienky",
        "additional_work_conditions",
    ),
    "signature_place": ("miesto_uzatvorenia", "miesto_uzatvorenia_zmluvy", "signature_place"),
    "signature_date": ("datum_uzatvorenia", "dátum_uzatvorenia", "signature_date"),
    "employer_signatory_name": ("za_zamestnavatela", "za_zamestnávateľa", "employer_signatory_name"),
    "employee_signatory_name": ("zamestnanec_podpis", "employee_signatory_name"),
}


def _merge_template_seeds(
    *groups: list[DocumentTemplateDefinition],
) -> list[DocumentTemplateDefinition]:
    merged: list[DocumentTemplateDefinition] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for item in group:
            key = (item.jurisdiction, item.template_key)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged

