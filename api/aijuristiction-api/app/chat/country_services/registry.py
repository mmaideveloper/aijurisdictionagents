from __future__ import annotations

from collections.abc import Callable

from app.chat.country_services.base import DirectReplyPreparation
from app.chat.country_services.slovakia import prepare_slovakia_direct_reply
from app.chat.models import Message, Session


def prepare_country_direct_reply(
    *,
    session: Session,
    messages: list[Message],
    current_content: str,
    prior_messages: list[Message],
    normalize_document_lines: Callable[[str], list[str]],
    extract_document_facts: Callable[[list[str]], dict[str, str]],
    current_turn_confirms_document_generation: Callable[[str, list[Message]], bool],
    build_share_transfer_lines: Callable[[dict[str, str]], list[str]],
) -> DirectReplyPreparation:
    country_code = session.country.strip().upper()
    if country_code == "SK":
        return prepare_slovakia_direct_reply(
            session=session,
            messages=messages,
            current_content=current_content,
            prior_messages=prior_messages,
            normalize_document_lines=normalize_document_lines,
            extract_document_facts=extract_document_facts,
            current_turn_confirms_document_generation=current_turn_confirms_document_generation,
            build_share_transfer_lines=build_share_transfer_lines,
        )
    return DirectReplyPreparation(supplemental_documents=[])
