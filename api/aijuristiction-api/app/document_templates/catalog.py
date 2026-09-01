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
            source_url="https://www.aksamec.sk/vzory/pracovna-zmluva-vzor/",
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
                "2. Variabilná zložka mzdy a podmienky jej priznania: {{variable_salary_component}} "
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
                    label="AK Samec - Pracovna zmluva",
                    url="https://www.aksamec.sk/vzory/pracovna-zmluva-vzor/",
                    publisher="AK Samec",
                    source_kind="external_template_page",
                    notes=(
                        "Exact source page reviewed on 2026-08-28. Managed canonical body is source-aligned "
                        "but maintained in-product for deterministic drafting and auditability."
                    ),
                ),
                TemplateSourceReference(
                    label="Zakonnik prace c. 311/2001 Z. z.",
                    url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2001/311/",
                    publisher="Slov-Lex",
                    source_kind="official_legislation",
                    notes="Relevant legal basis for employment contract minimum requirements and labor-law framing.",
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
            description="Kontrolovaný vzor dohody o vykonaní práce; pred podpisom vyžaduje právnu kontrolu.",
            source_format="HTML/LAW",
            source_url="https://www.aksamec.sk/dpp-dohoda-2026/",
            body=(
                "DOHODA O VYKONANÍ PRÁCE\nuzatvorená podľa § 226 zákona č. 311/2001 Z. z. Zákonník práce\n\n"
                "Zamestnávateľ: {{employer_identification}}\nZamestnanec: {{employee_identification}}\n\n"
                "Článok I\nPREDMET DOHODY\n1. Zamestnanec sa zaväzuje vykonať pracovnú úlohu: {{work_task}}.\n"
                "2. Dohodnutý výsledok práce: {{work_result}}.\n\n"
                "Článok II\nROZSAH A ČAS VYKONANIA PRÁCE\n1. Predpokladaný rozsah práce je {{work_hours}} hodín.\n"
                "2. Práca bude vykonaná v období {{work_period}} na mieste {{place_of_work}}.\n\n"
                "Článok III\nODMENA A ZÁVEREČNÉ USTANOVENIA\n1. Odmena za vykonanie práce je {{remuneration}}; splatnosť a spôsob úhrady: {{payment_terms}}.\n"
                "2. Práva a povinnosti neupravené touto dohodou sa riadia Zákonníkom práce. Dohoda je vyhotovená v dvoch rovnopisoch.\n\n"
                "V {{signature_place}}, dňa {{signature_date}}\n\nZamestnávateľ: {{employer_signatory}}\nZamestnanec: {{employee_signatory}}\n"
            ),
            keywords=("dohoda o vykonani prace", "dohoda o pracovnej cinnosti", "brigada"),
            flow_keys=(),
            placeholders=("employer_identification", "employee_identification", "work_task", "work_result", "work_hours", "work_period", "place_of_work", "remuneration", "payment_terms", "signature_place", "signature_date", "employer_signatory", "employee_signatory"),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec - Dohoda o vykonaní práce",
                    url="https://www.aksamec.sk/dpp-dohoda-2026/",
                    publisher="AK Samec",
                    source_kind="external_template_page",
                    notes="Exact source page reviewed on 2026-09-01; canonical body is maintained in-product.",
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
            description="Kontrolovaný vzor výpovede zamestnanca s jasným prejavom vôle a doručením.",
            source_format="HTML/LAW",
            source_url="https://www.aksamec.sk/vypoved-z-prace-vzor-2026/",
            body=(
                "VÝPOVEĎ Z PRACOVNÉHO POMERU\npodľa § 67 zákona č. 311/2001 Z. z. Zákonník práce\n\n"
                "Zamestnanec: {{employee_identification}}\nZamestnávateľ: {{employer_identification}}\n\n"
                "Týmto Vám dávam výpoveď z pracovného pomeru založeného pracovnou zmluvou zo dňa {{employment_contract_date}}, na pracovnej pozícii {{job_position}}.\n\n"
                "Výpovedná doba plynie podľa Zákonníka práce; pracovný pomer sa skončí jej uplynutím. Výpoveď žiadam doručiť preukázateľným spôsobom.\n\n"
                "V {{signature_place}}, dňa {{signature_date}}\n\n{{employee_signatory}}\n"
            ),
            keywords=("vypoved z pracovneho pomeru", "vypoved", "skoncenie pracovneho pomeru"),
            flow_keys=(),
            placeholders=("employee_identification", "employer_identification", "employment_contract_date", "job_position", "signature_place", "signature_date", "employee_signatory"),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec - Výpoveď z práce",
                    url="https://www.aksamec.sk/vypoved-z-prace-vzor-2026/",
                    publisher="AK Samec",
                    source_kind="external_template_page",
                    notes="Exact source page reviewed on 2026-09-01; limited to an employee-initiated notice.",
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
            description="Kontrolovaný všeobecný vzor plnej moci; rozsah treba primerane obmedziť konkrétnemu účelu.",
            source_format="HTML/LAW",
            source_url="https://www.aksamec.sk/plna-moc-vzor-2026/",
            body=(
                "PLNÁ MOC\nuzatvorená podľa § 31 a nasl. zákona č. 40/1964 Zb. Občiansky zákonník\n\n"
                "Splnomocniteľ: {{principal_identification}}\nSplnomocnenec: {{agent_identification}}\n\n"
                "Splnomocniteľ splnomocňuje splnomocnenca, aby ho v jeho mene zastupoval vo veciach: {{scope_of_authority}}.\n"
                "Plná moc sa udeľuje na obdobie {{validity_period}} a možno ju odvolať v súlade so zákonom.\n\n"
                "V {{signature_place}}, dňa {{signature_date}}\n\nSplnomocniteľ: {{principal_signatory}}\n"
            ),
            keywords=("plna moc vseobecna", "splnomocnenie", "plna moc"),
            flow_keys=("sk.civil.power_of_attorney",),
            placeholders=(
                "principal_identification",
                "agent_identification",
                "scope_of_authority",
                "validity_period",
                "signature_place",
                "signature_date", "principal_signatory",
            ),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec - Plná moc",
                    url="https://www.aksamec.sk/plna-moc-vzor-2026/",
                    publisher="AK Samec",
                    source_kind="external_template_page",
                    notes="Exact source page reviewed on 2026-09-01; canonical body retains a visible scope limitation.",
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
            description="Kontrolovaný osobitný vzor plnej moci pre presne vymedzený úkon.",
            source_format="HTML/LAW",
            source_url="https://www.aksamec.sk/splnomocnenie-vzor-2026/",
            body=(
                "OSOBITNÁ PLNÁ MOC\npodľa § 31 a nasl. zákona č. 40/1964 Zb. Občiansky zákonník\n\n"
                "Splnomocniteľ: {{principal_identification}}\nSplnomocnenec: {{agent_identification}}\n\n"
                "Splnomocniteľ udeľuje splnomocnencovi oprávnenie výlučne na tento úkon alebo tieto úkony: {{scope_of_authority}}.\n"
                "Oprávnenie zahŕňa len úkony nevyhnutné na uvedený účel. Platnosť plnej moci: {{validity_period}}.\n"
                "Ak právny predpis alebo povaha úkonu vyžaduje úradné osvedčenie podpisu, splnomocniteľ zabezpečí jeho osvedčenie pred použitím tejto plnej moci.\n\n"
                "V {{signature_place}}, dňa {{signature_date}}\n\nSplnomocniteľ: {{principal_signatory}}\n"
            ),
            keywords=("plna moc specialna", "specialne splnomocnenie", "plna moc"),
            flow_keys=("sk.civil.power_of_attorney",),
            placeholders=("principal_identification", "agent_identification", "scope_of_authority", "validity_period", "signature_place", "signature_date", "principal_signatory"),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec - Špeciálne splnomocnenie",
                    url="https://www.aksamec.sk/splnomocnenie-vzor-2026/",
                    publisher="AK Samec",
                    source_kind="external_template_page",
                    notes="Exact source page reviewed on 2026-09-01; requires review of form and signature certification for the specific act.",
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
            description=(
                "Kontrolovany kanonicky zaklad slovenskej kupno-predajnej zmluvy pre prevod "
                "nehnutelnosti s identifikaciou stran, presnym opisom predmetu prevodu, kupnou "
                "cenou, platobnym mechanizmom, vyhlaseniami predavajuceho, odovzdanim a navrhom "
                "na vklad. Pred podpisom vyzaduje doplnenie faktov a individualnu kontrolu "
                "pravnikom alebo specialistom na nehnutelnosti."
            ),
            source_format="HTML/LAW",
            source_url="https://www.aksamec.sk/kupna-zmluva-2026/",
            body=(
                "KÚPNA ZMLUVA\n"
                "uzatvorená podľa § 588 a nasl. zákona č. 40/1964 Zb. Občiansky zákonník\n\n"
                "Predávajúci:\n"
                "{{seller_identification}}\n\n"
                "Kupujúci:\n"
                "{{buyer_identification}}\n\n"
                "(ďalej spolu aj ako „zmluvné strany“) uzatvárajú túto kúpnu zmluvu:\n\n"
                "Článok I\n"
                "PREDMET PREVODU\n"
                "1. Predávajúci prevádza na kupujúceho vlastnícke právo k tejto nehnuteľnosti: "
                "{{subject_description}}.\n"
                "2. Súčasťou prevodu sú aj príslušenstvo, súčasti a práva s nehnuteľnosťou "
                "spojené v rozsahu: {{included_accessories}}.\n\n"
                "Článok II\n"
                "KÚPNA CENA A PLATOBNÉ PODMIENKY\n"
                "1. Kúpna cena za predmet prevodu je dohodnutá vo výške {{purchase_price}}.\n"
                "2. Spôsob úhrady, splatnosť a podmienky uvoľnenia kúpnej ceny: {{payment_terms}}.\n"
                "3. Náklady spojené s úhradou kúpnej ceny, úschovou alebo vinkuláciou znášajú "
                "strany takto: {{cost_allocation}}.\n\n"
                "Článok III\n"
                "VYHLÁSENIA ZMLUVNÝCH STRÁN\n"
                "1. Predávajúci vyhlasuje, že je oprávnený s predmetom prevodu nakladať a že jeho "
                "právny stav je opísaný takto: {{title_warranty}}.\n"
                "2. Predávajúci vyhlasuje, že kupujúceho oboznámil so stavom nehnuteľnosti, vadami "
                "a faktickým užívaním v tomto rozsahu: {{property_condition}}.\n"
                "3. Kupujúci vyhlasuje, že sa so stavom predmetu prevodu oboznámil a nadobúda ho "
                "za podmienok podľa tejto zmluvy.\n\n"
                "Článok IV\n"
                "ODOVZDANIE A PREVZATIE NEHNUTEĽNOSTI\n"
                "1. Predávajúci odovzdá predmet prevodu kupujúcemu spôsobom a v lehote: "
                "{{handover_terms}}.\n"
                "2. O odovzdaní a prevzatí môže byť spísaný odovzdávací protokol, vrátane odpočtu "
                "meračov a zoznamu odovzdanej dokumentácie.\n"
                "3. Nebezpečenstvo škody a úžitky prechádzajú medzi stranami podľa tejto dohody: "
                "{{risk_transfer}}.\n\n"
                "Článok V\n"
                "NÁVRH NA VKLAD A SÚČINNOSŤ\n"
                "1. Zmluvné strany sa zaväzujú poskytnúť si súčinnosť potrebnú na povolenie vkladu "
                "vlastníckeho práva do katastra nehnuteľností.\n"
                "2. Návrh na vklad podá {{filing_party}} a správny poplatok znášajú strany takto: "
                "{{filing_cost_terms}}.\n"
                "3. Ak príslušný okresný úrad vyzve na odstránenie vád podania alebo zmluvy, "
                "zmluvné strany poskytnú bezodkladnú súčinnosť na ich odstránenie.\n\n"
                "Článok VI\n"
                "ZÁVEREČNÉ USTANOVENIA\n"
                "1. Vlastnícke právo prechádza na kupujúceho povolením vkladu do katastra "
                "nehnuteľností, ak právny predpis neustanovuje inak.\n"
                "2. Zmeny a doplnenia tejto zmluvy možno vykonať iba písomnou dohodou zmluvných "
                "strán.\n"
                "3. Práva a povinnosti výslovne neupravené touto zmluvou sa spravujú Občianskym "
                "zákonníkom a súvisiacimi právnymi predpismi Slovenskej republiky.\n"
                "4. Zmluvné strany potvrdzujú, že si zmluvu prečítali, porozumeli jej obsahu a na "
                "znak súhlasu ju podpisujú slobodne a vážne.\n\n"
                "V {{signature_place}}, dňa {{signature_date}}\n\n"
                "Predávajúci: {{seller_signatory_name}}\n"
                "Kupujúci: {{buyer_signatory_name}}\n"
            ),
            keywords=("kupno predajna zmluva", "kupna zmluva", "predaj nehnutelnosti", "predaj"),
            flow_keys=("sk.contract.sale_purchase",),
            placeholders=(
                "seller_identification",
                "buyer_identification",
                "subject_description",
                "purchase_price",
                "payment_terms",
                "included_accessories",
                "cost_allocation",
                "title_warranty",
                "property_condition",
                "handover_terms",
                "risk_transfer",
                "filing_party",
                "filing_cost_terms",
                "signature_place",
                "signature_date",
                "seller_signatory_name",
                "buyer_signatory_name",
            ),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec - Kupna zmluva",
                    url="https://www.aksamec.sk/kupna-zmluva-2026/",
                    publisher="AK Samec",
                    source_kind="external_template_page",
                    notes=(
                        "Exact source page reviewed on 2026-08-31. Managed canonical body is source-aligned "
                        "but maintained in-product for deterministic drafting and auditability."
                    ),
                ),
                TemplateSourceReference(
                    label="Obciansky zakonnik - kupna zmluva",
                    url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1964/40/",
                    publisher="Slov-Lex",
                    source_kind="official_legislation",
                    notes="Relevant legal basis for purchase agreements under § 588 a nasl. Občianskeho zákonníka.",
                ),
            ),
            disclaimer_title="Dôležité upozornenie",
            disclaimer_text=(
                "Toto je vzorový právny návrh kúpno-predajnej zmluvy pripravený podľa všeobecnej "
                "slovenskej úpravy prevodu vlastníctva. Nie je právnym poradenstvom ani hotovou "
                "zmluvou. Pred podpisom doplňte všetky údaje, overte list vlastníctva, ťarchy a "
                "platobné zabezpečenie a zabezpečte individuálnu ľudskú kontrolu."
            ),
            disclaimer_footer="Vzorový návrh – pred podpisom vyžaduje individuálnu ľudskú a právnu kontrolu.",
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
            description=(
                "Kontrolovany kanonicky zaklad slovenskej najomnej zmluvy na byt s identifikaciou "
                "zmluvnych stran, predmetom najmu, najomnym, kauciou, uzivacimi pravidlami, "
                "odovzdanim bytu a skoncenim najmu. Pred podpisom vyzaduje doplnenie faktov a "
                "individualnu kontrolu pravnikom alebo specialistom na nehnutelnosti."
            ),
            source_format="HTML/LAW",
            source_url="https://www.aksamec.sk/najomna-zmluva-vzor-2026/",
            body=(
                "NÁJOMNÁ ZMLUVA\n"
                "uzatvorená podľa § 685 a nasl. zákona č. 40/1964 Zb. Občiansky zákonník\n\n"
                "Prenajímateľ:\n"
                "{{landlord_identification}}\n\n"
                "Nájomca:\n"
                "{{tenant_identification}}\n\n"
                "(ďalej spolu aj ako „zmluvné strany“) uzatvárajú túto nájomnú zmluvu:\n\n"
                "Článok I\n"
                "PREDMET NÁJMU\n"
                "1. Prenajímateľ prenecháva nájomcovi do dočasného užívania nehnuteľnosť: "
                "{{property_identification}}.\n"
                "2. Súčasťou odovzdania predmetu nájmu je vybavenie a stav opísaný takto: "
                "{{handover_conditions}}.\n\n"
                "Článok II\n"
                "ÚČEL A DOBA NÁJMU\n"
                "1. Predmet nájmu sa prenecháva na tento účel užívania: {{lease_purpose}}.\n"
                "2. Nájom sa uzatvára {{lease_term}}.\n"
                "3. Pravidlá užívania predmetu nájmu a obmedzenia: {{use_limitations}}.\n\n"
                "Článok III\n"
                "NÁJOMNÉ A PLATOBNÉ PODMIENKY\n"
                "1. Nájomca sa zaväzuje platiť nájomné a úhrady za plnenia spojené s užívaním bytu "
                "takto: {{rent_terms}}.\n"
                "2. Spôsob úhrady, splatnosť a identifikácia platieb: {{payment_method}}.\n"
                "3. Zmluvné strany sa dohodli na peňažnej zábezpeke (kaucii) vo výške "
                "{{security_deposit}}.\n"
                "4. Vyúčtovanie služieb a nedoplatkov/preplatkov: {{final_settlement_terms}}.\n\n"
                "Článok IV\n"
                "PRÁVA A POVINNOSTI ZMLUVNÝCH STRÁN\n"
                "1. Prenajímateľ odovzdá predmet nájmu v stave spôsobilom na riadne užívanie a "
                "umožní nájomcovi pokojný výkon nájomného práva.\n"
                "2. Nájomca bude predmet nájmu užívať riadne, s odbornou starostlivosťou a bez "
                "porušenia domového poriadku alebo práv tretích osôb.\n"
                "3. Rozdelenie drobných opráv, údržby a oznamovacích povinností strán: "
                "{{maintenance_and_repairs}}.\n"
                "4. Pravidlá pre energie, služby a odpočty meračov: {{utilities_terms}}.\n\n"
                "Článok V\n"
                "SKONČENIE NÁJMU\n"
                "1. Nájom zaniká spôsobmi ustanovenými zákonom alebo touto zmluvou.\n"
                "2. Výpovedné, odstupné a odovzdávacie podmienky pri skončení nájmu: "
                "{{termination_terms}}.\n"
                "3. Pri skončení nájmu zmluvné strany spíšu odovzdávací protokol a vysporiadajú "
                "vzájomné nároky bez zbytočného odkladu.\n\n"
                "Článok VI\n"
                "ZÁVEREČNÉ USTANOVENIA\n"
                "1. Táto zmluva nadobúda účinnosť dňom podpisu oboma zmluvnými stranami, ak nie je "
                "uvedené inak.\n"
                "2. Zmeny a doplnenia tejto zmluvy možno vykonať iba písomnou dohodou zmluvných "
                "strán.\n"
                "3. Práva a povinnosti výslovne neupravené touto zmluvou sa spravujú Občianskym "
                "zákonníkom a súvisiacimi právnymi predpismi Slovenskej republiky.\n"
                "4. Zmluvné strany potvrdzujú, že si zmluvu prečítali, porozumeli jej obsahu a na "
                "znak súhlasu ju podpisujú slobodne a vážne.\n\n"
                "V {{signature_place}}, dňa {{signature_date}}\n\n"
                "Prenajímateľ: {{landlord_signatory_name}}\n"
                "Nájomca: {{tenant_signatory_name}}\n"
            ),
            keywords=("najomna zmluva", "prenajom", "najom bytu", "najom"),
            flow_keys=("sk.civil.lease_advisory",),
            placeholders=(
                "landlord_identification",
                "tenant_identification",
                "property_identification",
                "lease_term",
                "lease_purpose",
                "rent_terms",
                "payment_method",
                "security_deposit",
                "utilities_terms",
                "maintenance_and_repairs",
                "handover_conditions",
                "use_limitations",
                "final_settlement_terms",
                "termination_terms",
                "signature_place",
                "signature_date",
                "landlord_signatory_name",
                "tenant_signatory_name",
            ),
            source_refs=(
                TemplateSourceReference(
                    label="AK Samec - Najomna zmluva",
                    url="https://www.aksamec.sk/najomna-zmluva-vzor-2026/",
                    publisher="AK Samec",
                    source_kind="external_template_page",
                    notes=(
                        "Exact source page reviewed on 2026-08-31. Managed canonical body is source-aligned "
                        "but maintained in-product for deterministic drafting and auditability."
                    ),
                ),
                TemplateSourceReference(
                    label="Obciansky zakonnik - najom bytu",
                    url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1964/40/",
                    publisher="Slov-Lex",
                    source_kind="official_legislation",
                    notes="Relevant legal basis for standard lease agreements under § 685 a nasl. Občianskeho zákonníka.",
                ),
            ),
            disclaimer_title="Dôležité upozornenie",
            disclaimer_text=(
                "Toto je vzorový právny návrh nájomnej zmluvy pripravený podľa všeobecnej slovenskej "
                "úpravy nájmu bytu. Nie je právnym poradenstvom ani hotovou zmluvou. Pred podpisom "
                "doplňte všetky údaje, skontrolujte osobitný režim nájmu a zabezpečte individuálnu ľudskú kontrolu."
            ),
            disclaimer_footer="Vzorový návrh – pred podpisom vyžaduje individuálnu ľudskú a právnu kontrolu.",
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
    if template.template_key == "sk.employment.employment_contract":
        rendered = _normalize_employment_contract_rendered_text(rendered)
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
    raw_values = dict(values)
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
            "signature_place": _value(values, "signature_place", "[mesto]"),
            "signature_date": _value(values, "signature_date", "[datum]"),
        }
    )
    if template_key == "sk.employment.employment_contract" or template_kind == "employment_contract":
        values.update(_employment_contract_render_values(values))
    if template_key == "sk.real_estate.sale_purchase" or template_kind == "sale_purchase_agreement":
        values.update(_sale_purchase_render_values(values))
    if template_key == "sk.real_estate.lease_agreement" or template_kind == "rental_agreement":
        values.update(_lease_agreement_render_values(values))
    if template_key == "sk.employment.work_performance_agreement" or template_kind == "work_agreement":
        values.update(_work_agreement_render_values(raw_values))
    if template_key == "sk.employment.termination_notice" or template_kind == "employment_termination_notice":
        values.update(_employment_termination_render_values(raw_values))
    if template_key in _POWER_OF_ATTORNEY_TEMPLATE_KEYS or template_kind == "power_of_attorney":
        values.update(_power_of_attorney_render_values(raw_values))
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


def _lease_agreement_render_values(values: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for field_name, aliases in _LEASE_AGREEMENT_FIELD_ALIASES.items():
        resolved[field_name] = _first_present(values, field_name, *aliases)
    optional_defaults = {
        "lease_purpose": "na riadne bývanie nájomcu a osôb, ktoré s ním budú bývať v súlade so zmluvou",
        "payment_method": "bezhotovostným prevodom na účet prenajímateľa uvedený pri podpise alebo iným preukázateľným spôsobom dohodnutým stranami",
        "security_deposit": "bez zloženej kaucie, ak sa strany písomne nedohodnú inak",
        "utilities_terms": "podľa skutočnej spotreby a pravidelného vyúčtovania dodávateľov alebo správcu",
        "maintenance_and_repairs": "nájomca znáša bežné drobné opravy a prenajímateľ zabezpečuje odstránenie podstatných vád, ak zákon alebo zmluva neustanovujú inak",
        "handover_conditions": "stav bytu, vybavenie a odpočty meračov budú zachytené v odovzdávacom protokole",
        "use_limitations": "bez písomného súhlasu prenajímateľa nemožno vykonávať podstatné stavebné úpravy ani prenechať byt do podnájmu, ak zákon alebo zmluva neustanovujú inak",
        "final_settlement_terms": "najneskôr do 30 dní po skončení nájmu po doručení všetkých podkladov na vyúčtovanie",
        "termination_terms": "podľa Občianskeho zákonníka, dohodnutých výpovedných dôvodov a písomného odovzdania bytu",
        "signature_place": "miesto bude doplnené pred podpisom",
        "signature_date": "dátum bude doplnený pred podpisom",
    }
    for field_name, default in optional_defaults.items():
        if not resolved.get(field_name):
            resolved[field_name] = default
    if not resolved.get("landlord_signatory_name"):
        resolved["landlord_signatory_name"] = resolved.get("landlord_identification", "")
    if not resolved.get("tenant_signatory_name"):
        resolved["tenant_signatory_name"] = resolved.get("tenant_identification", "")
    return resolved


def _sale_purchase_render_values(values: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for field_name, aliases in _SALE_PURCHASE_FIELD_ALIASES.items():
        resolved[field_name] = _first_present(values, *aliases, field_name)
    optional_defaults = {
        "included_accessories": "všetko príslušenstvo, súčasti a dokumentácia, ktoré patria k prevádzanej nehnuteľnosti, ak sa strany písomne nedohodnú inak",
        "payment_terms": "bezhotovostným prevodom alebo cez notársku úschovu / vinkuláciu podľa samostatnej dohody strán",
        "cost_allocation": "podľa osobitnej dohody strán; ak taká dohoda chýba, každá strana znáša svoje vlastné náklady",
        "title_warranty": "podľa aktuálneho listu vlastníctva a vyhlásení predávajúceho pri podpise zmluvy",
        "property_condition": "v stave známom kupujúcemu ku dňu podpisu tejto zmluvy",
        "handover_terms": "na základe samostatného odovzdávacieho protokolu po splnení dohodnutých platobných a vkladových podmienok",
        "risk_transfer": "podľa dohody strán uvedenej v odovzdávacom protokole alebo podľa všeobecne záväzných právnych predpisov",
        "filing_party": "strana určená vzájomnou dohodou zmluvných strán",
        "filing_cost_terms": "podľa dohody strán uvedenej pri podpise tejto zmluvy",
        "signature_place": "miesto bude doplnené pred podpisom",
        "signature_date": "dátum bude doplnený pred podpisom",
    }
    for field_name, default in optional_defaults.items():
        if not resolved.get(field_name):
            resolved[field_name] = default
    if not resolved.get("seller_signatory_name"):
        resolved["seller_signatory_name"] = resolved.get("seller_identification", "")
    if not resolved.get("buyer_signatory_name"):
        resolved["buyer_signatory_name"] = resolved.get("buyer_identification", "")
    return resolved


def _work_agreement_render_values(values: dict[str, str]) -> dict[str, str]:
    return {
        field_name: _first_present(values, field_name, *aliases)
        for field_name, aliases in _WORK_AGREEMENT_FIELD_ALIASES.items()
    }


def _employment_termination_render_values(values: dict[str, str]) -> dict[str, str]:
    resolved = {
        field_name: _first_present(values, field_name, *aliases)
        for field_name, aliases in _EMPLOYMENT_TERMINATION_FIELD_ALIASES.items()
    }
    if not resolved.get("employee_signatory"):
        resolved["employee_signatory"] = resolved.get("employee_identification", "")
    return resolved


def _power_of_attorney_render_values(values: dict[str, str]) -> dict[str, str]:
    resolved = {
        field_name: _first_present(values, field_name, *aliases)
        for field_name, aliases in _POWER_OF_ATTORNEY_FIELD_ALIASES.items()
    }
    if not resolved.get("principal_signatory"):
        resolved["principal_signatory"] = resolved.get("principal_identification", "")
    return resolved


def _normalize_employment_contract_rendered_text(rendered: str) -> str:
    """Keep current and already-persisted canonical salary clauses unambiguous."""
    normalized = rendered.replace(
        "Ďalšie zložky mzdy, podmienky ich priznania a výplatný termín:",
        "Variabilná zložka mzdy a podmienky jej priznania:",
    )
    return re.sub(r"\bbrutto(?:\s+brutto)+\b", "brutto", normalized, flags=re.IGNORECASE)


def _missing_required_template_fields(
    *,
    template_key: str,
    facts: dict[str, str],
    country: str,
    language: str | None,
) -> list[str]:
    raw_values = {key: str(value).strip() for key, value in facts.items() if str(value).strip()}
    required_fields: tuple[str, ...]
    if template_key == "sk.employment.employment_contract":
        resolved = _employment_contract_render_values(raw_values)
        required_fields = _EMPLOYMENT_CONTRACT_REQUIRED_FIELDS
    elif template_key == "sk.real_estate.sale_purchase":
        resolved = _sale_purchase_render_values(raw_values)
        required_fields = _SALE_PURCHASE_REQUIRED_FIELDS
    elif template_key == "sk.real_estate.lease_agreement":
        resolved = _lease_agreement_render_values(raw_values)
        required_fields = _LEASE_AGREEMENT_REQUIRED_FIELDS
    elif template_key == "sk.employment.work_performance_agreement":
        resolved = _work_agreement_render_values(raw_values)
        required_fields = _WORK_AGREEMENT_REQUIRED_FIELDS
    elif template_key == "sk.employment.termination_notice":
        resolved = _employment_termination_render_values(raw_values)
        required_fields = _EMPLOYMENT_TERMINATION_REQUIRED_FIELDS
    elif template_key in _POWER_OF_ATTORNEY_TEMPLATE_KEYS:
        resolved = _power_of_attorney_render_values(raw_values)
        required_fields = _POWER_OF_ATTORNEY_REQUIRED_FIELDS
    else:
        return []
    missing: list[str] = []
    for field_name in required_fields:
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
    if template_key == "sk.employment.employment_contract":
        questions = _EMPLOYMENT_CONTRACT_FIELD_QUESTIONS
        english_label = "employment-contract"
    elif template_key == "sk.real_estate.sale_purchase":
        questions = _SALE_PURCHASE_FIELD_QUESTIONS
        english_label = "sale-purchase-agreement"
    elif template_key == "sk.real_estate.lease_agreement":
        questions = _LEASE_AGREEMENT_FIELD_QUESTIONS
        english_label = "lease-agreement"
    elif template_key == "sk.employment.work_performance_agreement":
        questions = _WORK_AGREEMENT_FIELD_QUESTIONS
        english_label = "work-agreement"
    elif template_key == "sk.employment.termination_notice":
        questions = _EMPLOYMENT_TERMINATION_FIELD_QUESTIONS
        english_label = "employment-termination-notice"
    elif template_key in _POWER_OF_ATTORNEY_TEMPLATE_KEYS:
        questions = _POWER_OF_ATTORNEY_FIELD_QUESTIONS
        english_label = "power-of-attorney"
    else:
        return None
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return questions[first]
    return f"Please provide the required {english_label} field: {first}."


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

_WORK_AGREEMENT_REQUIRED_FIELDS = (
    "employer_identification",
    "employee_identification",
    "work_task",
    "work_result",
    "work_hours",
    "work_period",
    "place_of_work",
    "remuneration",
    "payment_terms",
    "signature_place",
    "signature_date",
)

_WORK_AGREEMENT_FIELD_QUESTIONS = {
    "employer_identification": "Kto je zamestnávateľ a ako má byť v dohode presne označený?",
    "employee_identification": "Kto je zamestnanec a ako má byť v dohode presne označený?",
    "work_task": "Akú konkrétnu pracovnú úlohu má zamestnanec vykonať?",
    "work_result": "Aký konkrétny výsledok práce sa má odovzdať?",
    "work_hours": "Aký je predpokladaný rozsah práce v hodinách?",
    "work_period": "V akom období sa má práca vykonať?",
    "place_of_work": "Kde sa má práca vykonávať?",
    "remuneration": "Aká je dohodnutá odmena za vykonanie práce?",
    "payment_terms": "Aká je splatnosť a spôsob úhrady odmeny?",
    "signature_place": "V akom mieste sa dohoda uzatvára?",
    "signature_date": "Aký je dátum uzatvorenia dohody?",
}

_WORK_AGREEMENT_FIELD_ALIASES = {
    "employer_identification": ("employer_name", "employer", "zamestnavatel", "zamestnávateľ", "company_name"),
    "employee_identification": ("employee_name", "employee_full_name", "meno_a_priezvisko", "client_name"),
    "work_task": ("task_description", "job_description", "druh_prace", "druh_práce", "work_description"),
    "work_result": ("result_description", "expected_result", "work_result"),
    "work_hours": ("hours", "expected_hours", "work_hours"),
    "work_period": ("period", "work_period", "performance_period", "term"),
    "place_of_work": ("workplace", "miesto_vykonu_prace", "miesto_výkonu_práce", "place_of_work"),
    "remuneration": ("payment_amount", "agreed_remuneration", "remuneration", "odmena"),
    "payment_terms": ("payment_method", "payment_terms", "sposob_uhrady", "spôsob_úhrady"),
    "signature_place": ("miesto_uzatvorenia", "miesto_podpisu", "signature_place"),
    "signature_date": ("datum_uzatvorenia", "datum_podpisu", "dátum_podpisu", "signature_date"),
    "employer_signatory": ("employer_signatory", "employer_representative", "za_zamestnavatela", "za_zamestnávateľa"),
    "employee_signatory": ("employee_signatory", "employee_full_name", "employee_name", "meno_a_priezvisko"),
}

_EMPLOYMENT_TERMINATION_REQUIRED_FIELDS = (
    "employee_identification",
    "employer_identification",
    "employment_contract_date",
    "job_position",
    "signature_place",
    "signature_date",
)

_EMPLOYMENT_TERMINATION_FIELD_QUESTIONS = {
    "employee_identification": "Kto dáva výpoveď a ako má byť vo výpovedi presne označený?",
    "employer_identification": "Komu je výpoveď určená a ako má byť zamestnávateľ presne označený?",
    "employment_contract_date": "Kedy bola uzatvorená pracovná zmluva, z ktorej sa dáva výpoveď?",
    "job_position": "Aká pracovná pozícia je uvedená v pracovnej zmluve?",
    "signature_place": "V akom mieste sa výpoveď podpisuje?",
    "signature_date": "Aký je dátum podpisu výpovede?",
}

_EMPLOYMENT_TERMINATION_FIELD_ALIASES = {
    "employee_identification": ("employee_name", "employee_full_name", "meno_a_priezvisko", "client_name"),
    "employer_identification": ("employer_name", "employer", "zamestnavatel", "zamestnávateľ", "company_name"),
    "employment_contract_date": ("contract_date", "employment_start_date", "employment_contract_date", "datum_pracovnej_zmluvy"),
    "job_position": ("position", "job_title", "pracovna_pozicia", "pracovná_pozícia"),
    "signature_place": ("miesto_podpisu", "miesto_uzatvorenia", "signature_place"),
    "signature_date": ("datum_podpisu", "dátum_podpisu", "signature_date"),
    "employee_signatory": ("employee_signatory", "employee_full_name", "employee_name", "meno_a_priezvisko"),
}

_POWER_OF_ATTORNEY_TEMPLATE_KEYS = frozenset(
    {"sk.authorization.general_power_of_attorney", "sk.authorization.special_power_of_attorney"}
)

_POWER_OF_ATTORNEY_REQUIRED_FIELDS = (
    "principal_identification",
    "agent_identification",
    "scope_of_authority",
    "validity_period",
    "signature_place",
    "signature_date",
)

_POWER_OF_ATTORNEY_FIELD_QUESTIONS = {
    "principal_identification": "Kto je splnomocniteľ a ako má byť v plnej moci presne označený?",
    "agent_identification": "Kto je splnomocnenec a ako má byť v plnej moci presne označený?",
    "scope_of_authority": "Aký presný rozsah oprávnenia sa má splnomocnencovi udeliť?",
    "validity_period": "Na aké obdobie sa plná moc udeľuje?",
    "signature_place": "V akom mieste sa plná moc podpisuje?",
    "signature_date": "Aký je dátum podpisu plnej moci?",
}

_POWER_OF_ATTORNEY_FIELD_ALIASES = {
    "principal_identification": ("principal_name", "client_identification", "client_name", "splnomocnitel", "splnomocniteľ"),
    "agent_identification": ("agent_name", "authorized_person", "opponent_name", "splnomocnenec"),
    "scope_of_authority": ("authorization_scope", "scope_of_authority", "topic", "urceny_pravny_ukon", "určený_právny_úkon"),
    "validity_period": ("validity", "duration", "validity_period", "scheduled_for"),
    "signature_place": ("miesto_podpisu", "miesto_uzatvorenia", "signature_place"),
    "signature_date": ("datum_podpisu", "dátum_podpisu", "signature_date"),
    "principal_signatory": ("principal_signatory", "principal_name", "client_name", "splnomocnitel", "splnomocniteľ"),
}

_LEASE_AGREEMENT_REQUIRED_FIELDS = (
    "landlord_identification",
    "tenant_identification",
    "property_identification",
    "lease_term",
    "rent_terms",
)

_LEASE_AGREEMENT_FIELD_QUESTIONS = {
    "landlord_identification": "Kto je prenajímateľ a ako má byť v zmluve presne označený?",
    "tenant_identification": "Kto je nájomca a ako má byť v zmluve presne označený?",
    "property_identification": "Ako má byť presne označený predmet nájmu, vrátane adresy alebo identifikácie bytu?",
    "lease_term": "Na akú dobu sa nájom uzatvára?",
    "rent_terms": "Aká je výška nájomného a ako sa má platiť?",
}

_LEASE_AGREEMENT_FIELD_ALIASES = {
    "landlord_identification": (
        "prenajimatel",
        "prenajímateľ",
        "landlord",
        "owner_identification",
    ),
    "tenant_identification": (
        "najomca",
        "nájomca",
        "tenant",
        "subtenant",
        "podnajomnik",
        "podnájomník",
    ),
    "property_identification": (
        "predmet",
        "predmet_najmu",
        "predmet_nájmu",
        "property_address",
        "adresa_nehnutelnosti",
        "adresa_nehnuteľnosti",
        "property_identification",
    ),
    "lease_term": (
        "doba",
        "doba_najmu",
        "doba_nájmu",
        "lease_duration",
        "term",
    ),
    "lease_purpose": (
        "ucel_najmu",
        "účel_nájmu",
        "lease_purpose",
        "purpose_of_use",
    ),
    "rent_terms": (
        "najomne",
        "nájomné",
        "mesacne_najomne",
        "mesačné_nájomné",
        "rent",
    ),
    "payment_method": (
        "payment_method",
        "sposob_platby",
        "spôsob_platby",
        "splatnost_najomneho",
        "splatnosť_nájomného",
    ),
    "security_deposit": (
        "deposit",
        "depozit",
        "kaucia",
        "security_deposit",
    ),
    "utilities_terms": (
        "utilities_terms",
        "sluzby",
        "služby",
        "energie",
        "service_charges",
    ),
    "maintenance_and_repairs": (
        "maintenance_and_repairs",
        "opravy",
        "udrzba",
        "údržba",
    ),
    "handover_conditions": (
        "handover_conditions",
        "odovzdanie",
        "odovzdavaci_protokol",
        "odovzdávací_protokol",
        "vybavenie_bytu",
    ),
    "use_limitations": (
        "use_limitations",
        "obmedzenia_uzivania",
        "obmedzenia_užívania",
        "podnajom",
        "podnájom",
    ),
    "final_settlement_terms": (
        "final_settlement_terms",
        "vyuctovanie",
        "vyúčtovanie",
        "settlement_terms",
    ),
    "termination_terms": (
        "termination_terms",
        "notice",
        "vypoved",
        "výpoveď",
        "vypovedna_lehota",
        "výpovedná_lehota",
    ),
    "signature_place": (
        "signature_place",
        "miesto_podpisu",
    ),
    "signature_date": (
        "signature_date",
        "datum_podpisu",
        "dátum_podpisu",
    ),
    "landlord_signatory_name": (
        "landlord_signatory_name",
        "prenajimatel_podpis",
        "prenajímateľ_podpis",
    ),
    "tenant_signatory_name": (
        "tenant_signatory_name",
        "najomca_podpis",
        "nájomca_podpis",
    ),
}

_SALE_PURCHASE_REQUIRED_FIELDS = (
    "seller_identification",
    "buyer_identification",
    "subject_description",
    "purchase_price",
)

_SALE_PURCHASE_FIELD_QUESTIONS = {
    "seller_identification": "Kto je predávajúci a ako má byť v zmluve presne označený?",
    "buyer_identification": "Kto je kupujúci a ako má byť v zmluve presne označený?",
    "subject_description": "Ako má byť presne označená prevádzaná nehnuteľnosť?",
    "purchase_price": "Aká je dohodnutá kúpna cena?",
}

_SALE_PURCHASE_FIELD_ALIASES = {
    "seller_identification": (
        "seller_identification",
        "predavajuci",
        "predávajúci",
        "transferor_name",
        "seller_name",
        "client_name",
    ),
    "buyer_identification": (
        "buyer_identification",
        "kupujuci",
        "kupujúci",
        "transferee_name",
        "buyer_name",
        "opponent_name",
    ),
    "subject_description": (
        "subject_description",
        "predmet_kupy",
        "predmet_kúpy",
        "nehnutelnost",
        "nehnuteľnosť",
        "property_identification",
        "property_description",
        "topic",
    ),
    "purchase_price": (
        "kupna_cena",
        "kúpna_cena",
        "transfer_price",
        "purchase_price",
    ),
    "payment_terms": (
        "payment_terms",
        "platobne_podmienky",
        "platobné_podmienky",
    ),
    "included_accessories": (
        "included_accessories",
        "prislusenstvo",
        "príslušenstvo",
    ),
    "cost_allocation": (
        "cost_allocation",
        "naklady_prevodu",
        "náklady_prevodu",
    ),
    "title_warranty": (
        "title_warranty",
        "tarchy",
        "ťarchy",
        "pravny_stav",
        "právny_stav",
    ),
    "property_condition": (
        "property_condition",
        "stav_nehnutelnosti",
        "stav_nehnuteľnosti",
    ),
    "handover_terms": (
        "handover_terms",
        "odovzdanie",
        "termin_odovzdania",
        "termín_odovzdania",
    ),
    "risk_transfer": (
        "risk_transfer",
        "prechod_nebezpecenstva_skody",
        "prechod_nebezpečenstva_škody",
    ),
    "filing_party": (
        "filing_party",
        "navrh_na_vklad_poda",
        "návrh_na_vklad_podá",
    ),
    "filing_cost_terms": (
        "filing_cost_terms",
        "spravny_poplatok",
        "správny_poplatok",
    ),
    "signature_place": (
        "signature_place",
        "miesto_podpisu",
    ),
    "signature_date": (
        "signature_date",
        "datum_podpisu",
        "dátum_podpisu",
    ),
    "seller_signatory_name": (
        "seller_signatory_name",
        "predavajuci_podpis",
        "predávajúci_podpis",
    ),
    "buyer_signatory_name": (
        "buyer_signatory_name",
        "kupujuci_podpis",
        "kupujúci_podpis",
    ),
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

