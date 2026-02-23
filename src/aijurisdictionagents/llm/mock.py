from __future__ import annotations

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
        if "lawyer" in agent_key:
            if _wants_slovak_rental_template(first_user_message) or _wants_slovak_rental_template(
                user_message
            ):
                return _slovak_rental_template_response(
                    first_user_message=first_user_message,
                    latest_user_message=user_message,
                )
            if prefers_slovak:
                return (
                    "Pravne posudenie: podla dostupnych faktov je poziadavka klienta obhajitelna. "
                    f"Hlavny kontext: {user_message}. Dostupne dokumenty: {doc_list}. "
                    "Dalsi krok: doplnte konkretne datumy, strany a zmluvne podmienky pre finalny navrh. "
                    "Chcete finalny vystup aj vo formate PDF?"
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
) -> str:
    detail_line = ""
    normalized_first = _normalize_text(first_user_message.strip())
    normalized_latest = _normalize_text(latest_user_message.strip())
    if normalized_latest and normalized_latest != normalized_first:
        detail_line = f"\nDoplnene fakty od klienta: {latest_user_message.strip()}"

    return (
        "Rozumiem. Tu je jednoduchy vzor najomnej zmluvy (byt):\n"
        "1) Zmluvne strany: Prenajimatel [meno, adresa] a Najomca [meno, adresa].\n"
        "2) Predmet najmu: Byt [adresa, cislo bytu, vymera].\n"
        "3) Doba najmu: [od datum] do [datum/na dobu neurcitu].\n"
        "4) Najomne a platby: Najomne [EUR/mesiac], splatne do [den], zalohy na energie [EUR].\n"
        "5) Kaucia: [EUR], podmienky vratenia po skonceni najmu.\n"
        "6) Prava a povinnosti: Udrzba, drobne opravy, uzivanie bytu, zakaz podnajmu bez suhlasu.\n"
        "7) Ukoncenie: Vypovedna lehota [x mesiacov], sposob dorucovania.\n"
        "8) Zaverecne ustanovenia: Pocet vyhotoveni, datum, podpisy."
        f"{detail_line}\n"
        "Ak chcete, doplnim to hned do kompletnej verzie na podpis s konkretnymi udajmi.\n"
        "Chcete finalny vystup aj vo formate PDF?"
    )


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
