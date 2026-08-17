from __future__ import annotations

import re
import unicodedata

from app.case_types.models import CaseTypeCreateRequest
from app.document_templates.models import DocumentTemplateDefinition


def build_default_case_types(
    templates: list[DocumentTemplateDefinition],
) -> list[CaseTypeCreateRequest]:
    items: list[CaseTypeCreateRequest] = []
    for template in templates:
        items.append(
            CaseTypeCreateRequest(
                case_type_key=_case_type_key_from_template_key(template.template_key),
                jurisdiction=template.jurisdiction,
                language=template.language,
                name=template.title,
                description=_default_case_description(template),
                keywords=list(_default_case_keywords(template)),
                prompt_text=build_default_case_prompt(template),
                template_keys=[template.template_key],
                is_enabled=template.is_enabled and not template.is_deleted,
            )
        )
    return items


def build_default_case_prompt(template: DocumentTemplateDefinition) -> str:
    return (
        f"Pomoz pouzivatelovi pripravit pravny pripad alebo dokument typu '{template.title}' "
        f"pre jurisdikciu {template.jurisdiction}. Najprv si vyziadaj len nevyhnutne skutkove "
        "udaje, over ci existuje vhodna sablona v katalogu, vysvetli ake informacie este "
        "chybaju a upozorni, ze pred podanim alebo podpisom je vhodna pravna kontrola clovekom."
    )


def _case_type_key_from_template_key(template_key: str) -> str:
    return template_key


def _default_case_description(template: DocumentTemplateDefinition) -> str:
    audience = _case_audience(template)
    purpose = _case_purpose(template)
    timing = _case_timing(template)
    inputs = _case_inputs(template)
    return (
        f"Pripad pre {audience}, {purpose}. "
        f"Typicky sa pouziva {timing}. "
        f"Zvycajne treba pripravit {inputs}. "
        "K pripadu existuje prepojena sablona v katalogu, ktoru je mozne pouzit ako vychodiskovy vzor."
    )


def _default_case_keywords(template: DocumentTemplateDefinition) -> tuple[str, ...]:
    values = [template.title, template.template_kind, template.category, *template.keywords]
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        compact = _compact_keyword(value)
        if compact and compact not in seen:
            normalized.append(compact)
            seen.add(compact)
    return tuple(normalized)


def _compact_keyword(value: str) -> str:
    lowered = value.strip().lower()
    if not lowered:
        return ""
    decomposed = unicodedata.normalize("NFD", lowered)
    no_diacritics = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    no_punctuation = re.sub(r"[^a-z0-9]+", " ", no_diacritics)
    return " ".join(no_punctuation.split())


def _case_audience(template: DocumentTemplateDefinition) -> str:
    category = _compact_keyword(template.category)
    title = _compact_keyword(template.title)
    template_kind = _compact_keyword(template.template_kind)
    if "oslobodenie od sudnych poplatkov" in category or "court fee exemption" in template_kind:
        if " fo" in f" {title}" or "fyzick" in title:
            return "fyzicku osobu alebo jej pravneho zastupcu"
        if " po" in f" {title}" or "pravnick" in title:
            return "pravnicku osobu, podnikatela alebo ich pravneho zastupcu"
        return "ziadatela alebo jeho pravneho zastupcu"
    if "obchodny register" in category or "company registry" in template_kind:
        return "obchodnu spolocnost, podnikatela alebo ich pravneho zastupcu"
    if "vyzivne" in category or "maintenance" in template_kind:
        return "rodica, manzela alebo inu opravnenu osobu, ktora riesi vyzivovaciu povinnost"
    if "exekutori" in category or "enforcement" in template_kind:
        return "opravneneho, povinneho, sudneho exekutora alebo ich zastupcu"
    if "konkurz" in category or "insolvency" in template_kind or "restrukturalizacia" in category:
        return "dlznika, veritela, spravcu alebo ineho ucastnika insolvencneho konania"
    if "pracovne" in category or "employment" in template_kind:
        return "zamestnavatela, zamestnanca alebo personalne oddelenie"
    if "nehnutelnosti" in category or "real estate" in template_kind or "najom" in category:
        return "vlastnika, kupujuceho, predavajuceho, prenajimatela alebo najomcu"
    if "plne moci" in category or "power of attorney" in template_kind:
        return "splnomocnitela, splnomocnenca alebo ich pravneho zastupcu"
    if "sudne" in category or "court" in template_kind or "platobne rozkazy" in category:
        return "zalobcu, zalovaneho alebo ich pravneho zastupcu"
    if "spolocenska zmluva" in title or "obchodne" in category:
        return "podnikatela, spolocnost alebo jej statutarny organ"
    return "pouzivatela alebo jeho pravneho zastupcu"


def _case_purpose(template: DocumentTemplateDefinition) -> str:
    title = template.title.strip()
    category = template.category.strip()
    template_kind = _compact_keyword(template.template_kind)
    if "court fee exemption" in template_kind or "Oslobodenie od sudnych poplatkov" in category:
        return (
            f"ktory potrebuje sudu preukazat svoje majetkove a prijmove pomery pri poziadavke na "
            f"oslobodenie od sudnych poplatkov v konani '{title}'"
        )
    if "company registry" in template_kind:
        return (
            f"ktory potrebuje pripravit alebo skontrolovat podanie '{title}' "
            "pre zapis, zmenu alebo vymaz udajov v obchodnom registri"
        )
    if "maintenance" in template_kind:
        return f"ktora potrebuje pripravit navrh alebo vyjadrenie k veci '{title}'"
    if "payment order" in template_kind or "bill of exchange" in template_kind:
        return f"ktory riesi podanie alebo obranu v suvislosti s konanim '{title}'"
    if "insolvency" in template_kind or "preventive restructuring" in template_kind:
        return f"ktory potrebuje spracovat povinne podklady alebo podanie typu '{title}'"
    if "enforcement" in template_kind:
        return f"ktory riesi exekucny ukon alebo procesny krok oznaceny ako '{title}'"
    if "employment" in template_kind or "work_agreement" in template_kind:
        return f"ktory potrebuje upravit pracovnopravny vztah alebo dokument '{title}'"
    if "sale purchase" in template_kind or "gift agreement" in template_kind or "rental agreement" in template_kind:
        return f"ktory potrebuje pripravit alebo skontrolovat zmluvny vztah typu '{title}'"
    if "power of attorney" in template_kind:
        return f"ktory potrebuje udelit, prijat alebo preukazat opravnenie cez dokument '{title}'"
    if "share transfer" in template_kind or "corporate articles" in template_kind:
        return f"ktory potrebuje upravit zakladne korporatne vztahy alebo transakciu typu '{title}'"
    return f"ktory potrebuje pripravit, podat alebo skontrolovat dokument alebo podanie typu '{title}' v oblasti '{category}'"


def _case_timing(template: DocumentTemplateDefinition) -> str:
    title = template.title.strip()
    category = _compact_keyword(template.category)
    template_kind = _compact_keyword(template.template_kind)
    if "obchodny register" in category or "company registry" in template_kind:
        return "pri zmene udajov spolocnosti, pri jej vzniku, vymaze alebo pri procese odvolania ci namietok proti rozhodnutiu registra"
    if "court fee exemption" in template_kind or "oslobodenie od sudnych poplatkov" in category:
        return "spolu so zalobou, odvolanim alebo inym sudnym podanim, ak by sudny poplatok predstavoval neprimeranu zataz"
    if "maintenance" in template_kind:
        return "pri spore alebo dohode o rozsahu vyzivovacej povinnosti a pri potrebe predlozit vec sudu"
    if "payment order" in template_kind or "bill of exchange" in template_kind:
        return "pri uplatnovani penazneho naroku, pri obrane proti rozkazu alebo pri ziadosti o splatkovy rezim"
    if "insolvency" in template_kind or "preventive restructuring" in template_kind:
        return "pri zacati, priebehu alebo dokumentovani konkurzneho, restrukturalizacneho alebo preventivneho restrukturalizacneho konania"
    if "enforcement" in template_kind:
        return "pri vedeni exekucie, pri oznamovani vykonanych ukonov alebo pri formalnom zaznamenani priebehu exekucneho konania"
    if "employment" in template_kind or "work_agreement" in template_kind:
        return "pri vzniku, zmene alebo skonceni pracovneho vztahu a pri potrebe zachytit dohodnute prava a povinnosti"
    if "rental agreement" in template_kind or "sale purchase" in template_kind or "gift agreement" in template_kind:
        return "pred uzatvorenim, zmenou alebo ukoncenim zmluvneho vztahu k nehnutelnosti alebo inemu majetku"
    if "power of attorney" in template_kind:
        return "pred vykonanim pravneho ukonu, pri zastupovani pred uradmi alebo pri potrebe formalne preukazat rozsah opravnenia"
    if "share transfer" in template_kind or "corporate articles" in template_kind:
        return "pri zmene vlastnickych, riadiacich alebo zakladatelskych pomerov v spolocnosti"
    return f"v situacii, ked je potrebne formalne spracovat alebo podat dokument '{title}'"


def _case_inputs(template: DocumentTemplateDefinition) -> str:
    template_kind = _compact_keyword(template.template_kind)
    category = _compact_keyword(template.category)
    if "court fee exemption" in template_kind or "oslobodenie od sudnych poplatkov" in category:
        return (
            "udaje o prijmoch, vydavkoch, majetku, vyzivovacich povinnostiach a podklady preukazujuce financnu situaciu"
        )
    if "company registry" in template_kind or "obchodny register" in category:
        return (
            "identifikacne udaje spolocnosti, presny rozsah zmeny, rozhodnutia prislusnych organov, prilohy pozadovane registrom a elektronicke podanie"
        )
    if "maintenance" in template_kind:
        return (
            "udaje o ucastnikoch, vztahu k opravnenej osobe, doterajsom plneni, prijmoch, vydavkoch a listiny podporujuce tvrdeny narok"
        )
    if "payment order" in template_kind or "bill of exchange" in template_kind:
        return (
            "udaje o pohladavke, splatnosti, protistrane, dorucovani, dokazoch a podklady preukazujuce vznik a vysku naroku"
        )
    if "insolvency" in template_kind or "preventive restructuring" in template_kind:
        return (
            "udaje o majetku, zavazkoch, veriteloch, zmluvach, cash-flow alebo inych povinnych ekonomickych a procesnych podkladoch"
        )
    if "enforcement" in template_kind:
        return (
            "identifikacne udaje ucastnikov, spisove a exekucne udaje, popis vykonavaneho ukonu a prilohy alebo zaznamy potrebne pre dany exekucny krok"
        )
    if "employment" in template_kind or "work_agreement" in template_kind:
        return (
            "udaje o zamestnavatelovi a zamestnancovi, dohodnute pracovnopravne podmienky, datumy, odmenu a suvisiace prilohy"
        )
    if "rental agreement" in template_kind or "sale purchase" in template_kind or "gift agreement" in template_kind:
        return (
            "identifikacne udaje zmluvnych stran, popis predmetu zmluvy, cenu alebo odplatu, casovy rezim, platobne podmienky a podporne listiny"
        )
    if "power of attorney" in template_kind:
        return (
            "udaje o splnomocnitelovi a splnomocnencovi, presny rozsah opravnenia, dobu platnosti a okolnosti pravneho ukonu"
        )
    if "share transfer" in template_kind or "corporate articles" in template_kind:
        return (
            "udaje o spolocnosti, spolocnikoch alebo prevodcoch, rozsahu podielu, rozhodnutiach organov a prislusnych korporatnych prilohach"
        )
    return (
        "identifikacne udaje ucastnikov, opis skutkoveho stavu, hlavne pravne alebo procesne dokumenty a prilohy potrebne pre spracovanie daneho podania"
    )
