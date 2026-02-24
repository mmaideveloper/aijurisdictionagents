from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Sequence

from .base import LLMClient
from ..schemas import Document, Message


class MockLLMClient:
    def complete(
        self,
        agent_name: str,
        system_prompt: str,
        conversation: Sequence[Message],
        documents: Sequence[Document],
    ) -> str:
        user_message = _latest_user_message(conversation)
        first_user_message = _first_user_message(conversation)
        prefers_slovak = _prefers_slovak(system_prompt, first_user_message, user_message)

        doc_list = ", ".join(Path(doc.path).name for doc in documents[:3])
        if not doc_list:
            doc_list = "no documents"

        agent_key = agent_name.lower()
        if "aiusersimulatoragent" in agent_key:
            return _simulate_user_answer(user_message, prefers_slovak, conversation)

        if "lawyer" in agent_key:
            if _wants_slovak_rental_template(first_user_message) or _wants_slovak_rental_template(
                user_message
            ):
                return _slovak_rental_template_response(
                    first_user_message=first_user_message,
                    latest_user_message=user_message,
                    conversation=conversation,
                )
            if prefers_slovak:
                if not _has_answered_lawyer_question(conversation):
                    return (
                        "Aby som mohol pripravit presny navrh, potrebujem doplnit klucove udaje: "
                        "kedy vznikol spor, ake su hlavne datumy a co je vas hlavny ciel?"
                    )
                return (
                    "Pravne posudenie: podla dostupnych faktov je poziadavka klienta obhajitelna. "
                    f"Hlavny kontext: {user_message}. Dostupne dokumenty: {doc_list}. "
                    "Dalsi krok: doplnte konkretne datumy, strany a zmluvne podmienky pre finalny navrh. "
                    "Chcete finalny vystup aj vo formate PDF?"
                )
            if not _has_answered_lawyer_question(conversation):
                return (
                    "To prepare an accurate draft, I need key details first: "
                    "when the dispute started, the main dates, and your concrete target outcome?"
                )
            return (
                "Legal assessment: based on the provided facts, the user's requested outcome is supportable. "
                f"Primary context: {user_message}. Available documents: {doc_list}. "
                "Next step: provide concrete dates, party names, and contract terms so I can draft an actionable response. "
                "Do you want the final result in PDF format?"
            )

        if "judge" in agent_key:
            if prefers_slovak:
                return (
                    "Pohlad sudcu: argumenty a dokazy hodnotim nestranne. "
                    "Spresnujuca otazka: Ake rozhodne pravo alebo jurisdikcia sa uplatni? "
                    f"Fokus pouzivatela: {user_message}"
                )
            return (
                "Judicial view: I weigh the arguments and evidence neutrally. "
                "Clarifying question: What jurisdiction or governing law applies? "
                f"User focus: {user_message}"
            )

        if "finalsummary" in agent_key:
            if _wants_slovak_rental_template(first_user_message) or _wants_slovak_rental_template(
                user_message
            ):
                return (
                    "Recommendation: Pripravit a pouzit pisomny vzor najomnej zmluvy s konkretnymi udajmi o stranach, "
                    "predmete, platbach a ukonceni.\n"
                    "Rationale: Diskusia potvrdila, ze vzor najomnej zmluvy je poziadovany a vhodny vystup."
                )
            if prefers_slovak:
                return (
                    "Recommendation: Pokracovat podla poziadavky klienta s doplnenim chybanucich skutocnosti.\n"
                    "Rationale: Diskusia poskytla dostatocny zaklad pre dalsi postup."
                )
            return (
                "Recommendation: Proceed with the user's requested position.\n"
                "Rationale: The discussion supports the user's arguments based on the provided facts."
            )

        return f"Response prepared for {agent_name}. User focus: {user_message}"


def _latest_user_message(conversation: Sequence[Message]) -> str:
    for message in reversed(conversation):
        if message.role == "user":
            return message.content
    return ""


def _first_user_message(conversation: Sequence[Message]) -> str:
    for message in conversation:
        if message.role == "user":
            return message.content
    return ""


def _slovak_rental_template_response(
    *,
    first_user_message: str,
    latest_user_message: str,
    conversation: Sequence[Message],
) -> str:
    facts = _collect_rental_facts(conversation)
    if not facts["has_parties_and_property"]:
        return (
            "Aby som pripravil presny vzor najomnej zmluvy, potrebujem doplnit: "
            "kto je prenajimatel a najomca a aka je presna adresa bytu?"
        )
    if not facts["has_rent_and_start"]:
        return (
            "Dakujem. Prosim doplnte este vysku mesacneho najomneho "
            "a datum zaciatku najmu?"
        )
    if _is_pdf_request(latest_user_message):
        return (
            "Perfektne, vsetky podstatne udaje uz mam. "
            "Pripravil som finalne znenie zmluvy a samostatne zhrnutie diskusie "
            "na export do PDF."
        )

    draft = _build_slovak_contract_draft(first_user_message, facts)
    return f"{draft}\nChcete finalny vystup aj vo formate PDF?"


def _simulate_user_answer(
    user_message: str,
    prefers_slovak: bool,
    conversation: Sequence[Message],
) -> str:
    question = _extract_core_question(user_message)
    lowered = _normalize_text(question)
    slovak = prefers_slovak or "language: sk" in _normalize_text(user_message)

    if "pdf" in lowered:
        if slovak:
            return "Ano, po dokonceni vsetkych otazok chcem finalny vystup aj v PDF."
        return "Yes, after all clarifying questions are completed, I want the final output in PDF."
    if any(token in lowered for token in ("prenajimatel", "najomca", "stran", "party", "adresa", "byt")):
        if slovak:
            return (
                "Prenajimatel je Jana Novotna, najomca je Tomas Hlavaty s manzelkou, "
                "byt je na adrese Dunajska 12, Bratislava."
            )
        return (
            "The landlord is Jana Novotna, the tenants are Tomas Hlavaty and his spouse, "
            "and the apartment is at Dunajska 12, Bratislava."
        )
    if ("najom" in lowered or "rent" in lowered) and (
        "datum" in lowered or "date" in lowered or "zaciat" in lowered or "start" in lowered
    ):
        if slovak:
            return (
                "Najomne je 850 EUR mesacne a zaciatok najmu je 01.04.2026; "
                "platba prebieha do piateho dna v mesiaci."
            )
        return (
            "The rent is EUR 850 monthly and the lease starts on 2026-04-01; "
            "payment is due by the fifth day of each month."
        )
    if "datum" in lowered or "date" in lowered or "zaciat" in lowered or "start" in lowered:
        if slovak:
            return "Najom sa ma zacat 01.04.2026 a zmluva bola dohodnuta 15.03.2026."
        return "The lease should start on 2026-04-01 and the agreement was settled on 2026-03-15."
    if "vypoved" in lowered or "termination" in lowered or "notice" in lowered:
        if slovak:
            return "Chcem vypovednu dobu jeden mesiac, dorucenie pisomne aj emailom."
        return "I want a one-month notice period, delivered in writing and by email."
    if "najom" in lowered or "rent" in lowered:
        if slovak:
            return "Najomne je 850 EUR mesacne, splatne do piateho dna v mesiaci, plus dvojmesacna platba vopred."
        return "Rent is EUR 850 monthly, due by the 5th day of the month, plus two months paid in advance."
    if "stran" in lowered or "party" in lowered:
        if slovak:
            return "Prenajimatel je fyzicka osoba a najomca je manzelsky par; identifikacne udaje doplnim do finalneho navrhu."
        return "The landlord is a private person and the tenants are a married couple; I will provide identifiers for the final draft."
    if "jurisdik" in lowered or "governing law" in lowered or "rozhodne pravo" in lowered:
        if slovak:
            return "Uplatni sa pravo Slovenskej republiky a miestna prislusnost podla miesta nehnutelnosti."
        return "Slovak law applies and local jurisdiction follows the location of the property."
    if slovak:
        fallback = [
            "Rozumiem, doplnam potrebne fakty a prosim pokracujte dalsou otazkou.",
            "Suhlasim, mozem doplnit aj cislo listu vlastnictva a kontaktne udaje stran.",
            "Mam aj emailovu komunikaciu o podmienkach najmu, viem ju doplnit.",
        ]
        return fallback[_user_turn_count(conversation) % len(fallback)]
    return "Understood. I am providing the requested facts, please continue with the next question."


def _extract_core_question(user_message: str) -> str:
    for line in user_message.splitlines():
        if line.lower().startswith("core question:"):
            return line.partition(":")[2].strip()
    return user_message.strip()


def _user_turn_count(conversation: Sequence[Message]) -> int:
    return len([message for message in conversation if message.role == "user"])


def _has_answered_lawyer_question(conversation: Sequence[Message]) -> bool:
    for index, message in enumerate(conversation):
        if message.role != "assistant":
            continue
        if "lawyer" not in (message.agent_name or "").lower():
            continue
        if "?" not in message.content:
            continue
        if "pdf" in message.content.lower():
            continue
        if any(next_msg.role == "user" for next_msg in conversation[index + 1 :]):
            return True
    return False


def _collect_rental_facts(conversation: Sequence[Message]) -> dict[str, object]:
    user_messages = [message.content for message in conversation if message.role == "user"]
    combined = " ".join(user_messages)
    normalized = _normalize_text(combined)

    rent_match = re.search(r"(\d{3,4})\s*eur", normalized)
    date_match = re.search(r"\b(\d{1,2}\.\d{1,2}\.\d{4}|\d{4}-\d{2}-\d{2})\b", combined)

    has_party_terms = any(token in normalized for token in ("prenajimatel", "najomca", "tenant", "landlord"))
    has_property_terms = any(token in normalized for token in ("adresa", "byt", "apartment", "ulica"))
    has_rent = rent_match is not None or "najomne" in normalized or "rent" in normalized
    has_start = date_match is not None or "zacat" in normalized or "start" in normalized

    return {
        "rent_amount": f"{rent_match.group(1)} EUR" if rent_match else "850 EUR",
        "start_date": date_match.group(1) if date_match else "01.04.2026",
        "has_parties_and_property": has_party_terms and has_property_terms,
        "has_rent_and_start": has_rent and has_start,
    }


def _build_slovak_contract_draft(first_user_message: str, facts: dict[str, object]) -> str:
    duration = _extract_contract_duration(first_user_message)
    notice = _extract_notice_period(first_user_message)
    advance = _extract_advance_rent(first_user_message)
    rent_amount = str(facts.get("rent_amount", "850 EUR"))
    start_date = str(facts.get("start_date", "01.04.2026"))
    return (
        "Rozumiem. Tu je navrh najomnej zmluvy (byt):\n"
        "1) Zmluvne strany: Prenajimatel Jana Novotna, Najomca Tomas Hlavaty a manzelka.\n"
        "2) Predmet najmu: Byt na adrese Dunajska 12, Bratislava.\n"
        f"3) Doba najmu: Na dobu urcitu {duration}, od {start_date}.\n"
        f"4) Najomne: {rent_amount} mesacne, splatne do 5. dna v mesiaci.\n"
        f"5) Platba vopred: {advance}.\n"
        "6) Kaucia: 1 mesacne najomne, vratna po odovzdani bytu bez skod.\n"
        f"7) Ukoncenie: Vypovedna lehota {notice}, dorucenie pisomne aj emailom.\n"
        "8) Zaverecne ustanovenia: Datum podpisu, pocet vyhotoveni, podpisy oboch stran."
    )


def _extract_contract_duration(text: str) -> str:
    normalized = _normalize_text(text)
    if any(token in normalized for token in ("jeden rok", "1 rok", "12 mesiac", "na dobu urcitu jeden rok")):
        return "1 rok"
    return "podla dohody zmluvnych stran"


def _extract_notice_period(text: str) -> str:
    normalized = _normalize_text(text)
    if any(token in normalized for token in ("1 mesac", "jeden mesiac", "vypovednu dobu 1")):
        return "1 mesiac"
    return "podla dohody"


def _extract_advance_rent(text: str) -> str:
    normalized = _normalize_text(text)
    if any(token in normalized for token in ("2 mesacne najomne vopred", "dve mesacne najomne vopred", "2 mesiace vopred")):
        return "2 mesacne najomne vopred"
    return "1 mesacne najomne vopred"


def _is_pdf_request(text: str) -> bool:
    normalized = _normalize_text(text)
    return "pdf" in normalized and any(token in normalized for token in ("ano", "prosim", "yes", "chcem", "want"))


def _wants_slovak_rental_template(user_message: str) -> bool:
    text = _normalize_text(user_message)
    rental_markers = ("prenaj", "najom")
    template_markers = ("vzor", "sablon", "template", "zmluv")
    return any(marker in text for marker in rental_markers) and any(
        marker in text for marker in template_markers
    )


def _prefers_slovak(system_prompt: str, first_user_message: str, latest_user_message: str) -> bool:
    combined = _normalize_text(f"{system_prompt}\n{first_user_message}\n{latest_user_message}")
    slovak_markers = ("respond in slovak", "sk-sk", "slovak", "prosim", "dakujem", "zmluv", "prenaj")
    return any(marker in combined for marker in slovak_markers)


def _normalize_text(text: str) -> str:
    lowered = (text or "").lower()
    normalized = unicodedata.normalize("NFKD", lowered)
    return normalized.encode("ascii", "ignore").decode("ascii")
