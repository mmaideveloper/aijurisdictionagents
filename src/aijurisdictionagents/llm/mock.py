from __future__ import annotations

import re
import unicodedata
import logging
from pathlib import Path
from typing import Sequence

from .base import log_llm_request, log_llm_response
from .base import LLMClient
from ..schemas import Document, Message

logger = logging.getLogger(__name__)


class MockLLMClient:
    def complete(
        self,
        agent_name: str,
        system_prompt: str,
        conversation: Sequence[Message],
        documents: Sequence[Document],
    ) -> str:
        request_payload = [
            {"role": "system", "content": system_prompt},
            *(
                [{"role": "system", "content": _render_documents_for_log(documents)}]
                if documents
                else []
            ),
            *[
                {
                    "role": message.role,
                    "content": f"{message.agent_name}: {message.content}",
                }
                for message in conversation
            ],
        ]
        log_llm_request(
            logger,
            provider="mock",
            agent_name=agent_name,
            request_payload=request_payload,
            message_count=len(conversation),
            document_count=len(documents),
        )
        user_message = _latest_user_message(conversation)
        first_user_message = _first_user_message(conversation)
        prefers_slovak = _prefers_slovak(system_prompt, first_user_message, user_message)

        doc_list = ", ".join(Path(doc.path).name for doc in documents[:3])
        if not doc_list:
            doc_list = "no documents"

        agent_key = agent_name.lower()
        if "aiusersimulatoragent" in agent_key:
            response = _simulate_user_answer(user_message, prefers_slovak, conversation)
            log_llm_response(
                logger,
                provider="mock",
                agent_name=agent_name,
                raw_response=response,
            )
            return response

        if "lawyer" in agent_key:
            if documents and _is_document_summary_request(user_message):
                response = _document_summary_response(documents, prefers_slovak)
                log_llm_response(
                    logger,
                    provider="mock",
                    agent_name=agent_name,
                    raw_response=response,
                )
                return response
            if documents and _is_document_update_request(user_message):
                response = _document_update_response(documents, prefers_slovak)
                log_llm_response(
                    logger,
                    provider="mock",
                    agent_name=agent_name,
                    raw_response=response,
                )
                return response
            if _wants_slovak_rental_template(first_user_message) or _wants_slovak_rental_template(
                user_message
            ):
                response = _slovak_rental_template_response(
                    first_user_message=first_user_message,
                    latest_user_message=user_message,
                    conversation=conversation,
                )
                log_llm_response(
                    logger,
                    provider="mock",
                    agent_name=agent_name,
                    raw_response=response,
                )
                return response
            if prefers_slovak:
                if not _has_answered_lawyer_question(conversation):
                    response = (
                        "Aby som mohol pripravit presny navrh, potrebujem doplnit klucove udaje: "
                        "kedy vznikol spor, ake su hlavne datumy a co je vas hlavny ciel?"
                    )
                    log_llm_response(
                        logger,
                        provider="mock",
                        agent_name=agent_name,
                        raw_response=response,
                    )
                    return response
                response = (
                    "Pravne posudenie: podla dostupnych faktov je poziadavka klienta obhajitelna. "
                    f"Hlavny kontext: {user_message}. Dostupne dokumenty: {doc_list}. "
                    "Dalsi krok: doplnte konkretne datumy, strany a zmluvne podmienky pre finalny navrh. "
                    "Chcete finalny vystup aj vo formate PDF?"
                )
                log_llm_response(
                    logger,
                    provider="mock",
                    agent_name=agent_name,
                    raw_response=response,
                )
                return response
            if not _has_answered_lawyer_question(conversation):
                response = (
                    "To prepare an accurate draft, I need key details first: "
                    "when the dispute started, the main dates, and your concrete target outcome?"
                )
                log_llm_response(
                    logger,
                    provider="mock",
                    agent_name=agent_name,
                    raw_response=response,
                )
                return response
            response = (
                "Legal assessment: based on the provided facts, the user's requested outcome is supportable. "
                f"Primary context: {user_message}. Available documents: {doc_list}. "
                "Next step: provide concrete dates, party names, and contract terms so I can draft an actionable response. "
                "Do you want the final result in PDF format?"
            )
            log_llm_response(
                logger,
                provider="mock",
                agent_name=agent_name,
                raw_response=response,
            )
            return response

        if "judge" in agent_key:
            if prefers_slovak:
                response = (
                    "Pohlad sudcu: argumenty a dokazy hodnotim nestranne. "
                    "Spresnujuca otazka: Ake rozhodne pravo alebo jurisdikcia sa uplatni? "
                    f"Fokus pouzivatela: {user_message}"
                )
                log_llm_response(
                    logger,
                    provider="mock",
                    agent_name=agent_name,
                    raw_response=response,
                )
                return response
            response = (
                "Judicial view: I weigh the arguments and evidence neutrally. "
                "Clarifying question: What jurisdiction or governing law applies? "
                f"User focus: {user_message}"
            )
            log_llm_response(
                logger,
                provider="mock",
                agent_name=agent_name,
                raw_response=response,
            )
            return response

        if "finalsummary" in agent_key:
            if _wants_slovak_rental_template(first_user_message) or _wants_slovak_rental_template(
                user_message
            ):
                response = (
                    "Recommendation: Pripravit a pouzit pisomny vzor najomnej zmluvy s konkretnymi udajmi o stranach, "
                    "predmete, platbach a ukonceni.\n"
                    "Rationale: Diskusia potvrdila, ze vzor najomnej zmluvy je poziadovany a vhodny vystup."
                )
                log_llm_response(
                    logger,
                    provider="mock",
                    agent_name=agent_name,
                    raw_response=response,
                )
                return response
            if prefers_slovak:
                response = (
                    "Recommendation: Pokracovat podla poziadavky klienta s doplnenim chybanucich skutocnosti.\n"
                    "Rationale: Diskusia poskytla dostatocny zaklad pre dalsi postup."
                )
                log_llm_response(
                    logger,
                    provider="mock",
                    agent_name=agent_name,
                    raw_response=response,
                )
                return response
            response = (
                "Recommendation: Proceed with the user's requested position.\n"
                "Rationale: The discussion supports the user's arguments based on the provided facts."
            )
            log_llm_response(
                logger,
                provider="mock",
                agent_name=agent_name,
                raw_response=response,
            )
            return response

        response = f"Response prepared for {agent_name}. User focus: {user_message}"
        log_llm_response(
            logger,
            provider="mock",
            agent_name=agent_name,
            raw_response=response,
        )
        return response


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
    slovak_markers = (
        "respond in slovak",
        "respond in sk",
        "sk-sk",
        "slovak",
        "language: sk",
        "prosim",
        "dakujem",
        "zmluv",
        "prenaj",
    )
    return any(marker in combined for marker in slovak_markers)


def _is_document_summary_request(user_message: str) -> bool:
    normalized = _normalize_text(user_message)
    summary_terms = (
        "summary",
        "summar",
        "summarize",
        "summarise",
        "short summary",
        "sumar",
        "sumariz",
        "sumarizovanie",
        "zhrn",
        "zhrnut",
        "zusammenfass",
    )
    document_terms = (
        "document",
        "documents",
        "uploaded",
        "pdf",
        "dokument",
        "dokumenty",
        "dokumente",
        "zmluv",
        "vertrag",
    )
    return any(term in normalized for term in summary_terms) and any(
        term in normalized for term in document_terms
    )


def _document_summary_response(
    documents: Sequence[Document],
    prefers_slovak: bool,
) -> str:
    primary = documents[0]
    normalized_text = " ".join(primary.content.split())
    sentences = _split_sentences(normalized_text)
    snippet_sentences = sentences[:3]
    snippet = " ".join(snippet_sentences).strip()
    filename = Path(primary.path).name
    additional_count = max(0, len(documents) - 1)

    if prefers_slovak:
        lines = [
            f"Dokument {filename} som zhrnul v kratkej forme.",
            snippet or "Text dokumentu je kratky alebo slabo citatelny, preto viem potvrdit len zakladny obsah bez detailov.",
        ]
        if additional_count > 0:
            lines.append(
                f"V pripade su este {additional_count} dalsie nahrane dokumenty, ktore mozem zhrnut podrobnejsie na poziadanie."
            )
        lines.append(
            "Ak chcete, v dalsom kroku vypisem aj hlavne pravne rizika alebo chybajuce casti."
        )
        return " ".join(lines[:4])

    lines = [
        f"I prepared a short summary of {filename}.",
        snippet or "The extracted text is short or low quality, so I can confirm only the basic document context without reliable detail.",
    ]
    if additional_count > 0:
        lines.append(
            f"The case also includes {additional_count} additional uploaded document(s) that I can summarize separately if needed."
        )
    lines.append(
        "If you want, I can next list the main legal risks, contradictions, or missing parts."
    )
    return " ".join(lines[:4])


def _is_document_update_request(user_message: str) -> bool:
    normalized = _normalize_text(user_message)
    document_terms = (
        "document",
        "documents",
        "pdf",
        "dokument",
        "dokumenty",
        "zmluv",
        "vertrag",
    )
    update_terms = (
        "prepare",
        "generate",
        "create",
        "review",
        "revise",
        "update",
        "amend",
        "fix",
        "correct",
        "pozri",
        "skontroluj",
        "oprav",
        "uprav",
        "aktualizuj",
        "zmen",
        "zmien",
        "zakon",
        "zakona",
        "zakonov",
        "law",
        "laws",
        "change",
        "changes",
    )
    return any(term in normalized for term in document_terms) and any(
        term in normalized for term in update_terms
    )


def _document_update_response(
    documents: Sequence[Document],
    prefers_slovak: bool,
) -> str:
    primary = documents[0]
    filename = Path(primary.path).name
    normalized_text = " ".join(primary.content.split())
    sentences = _split_sentences(normalized_text)
    basis = " ".join(sentences[:2]).strip()
    if prefers_slovak:
        lines = [
            f"Pripravil som aktualizovane znenie dokumentu {filename} podla poslednych zmien zakonov.",
            basis
            or "Vychadzal som z nahraneho dokumentu a jeho extrahovaneho textu.",
            "Doplnil som potrebne upravy a finalny dokument je pripraveny na export do PDF.",
        ]
        return " ".join(lines)

    lines = [
        f"I prepared an updated version of {filename} based on the latest legal changes.",
        basis or "I used the uploaded document and its extracted text as the starting point.",
        "The final revised document is ready for PDF export.",
    ]
    return " ".join(lines)


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    cleaned = [part.strip() for part in parts if part.strip()]
    if cleaned:
        return cleaned
    return [text.strip()] if text.strip() else []


def _normalize_text(text: str) -> str:
    lowered = (text or "").lower()
    normalized = unicodedata.normalize("NFKD", lowered)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _render_documents_for_log(documents: Sequence[Document], max_chars: int = 4000) -> str:
    chunks = ["Context documents:"]
    total = 0
    for doc in documents:
        header = f"[{Path(doc.path).name}]"
        body = doc.content.strip().replace("\n", " ")
        snippet = body[:800]
        entry = f"{header} {snippet}"
        total += len(entry)
        if total > max_chars:
            break
        chunks.append(entry)
    return "\n".join(chunks)
