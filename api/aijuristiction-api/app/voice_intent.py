from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


class VoiceIntentName(str, Enum):
    CREATE_CASE = "create_case"
    SEND_MESSAGE = "send_message"
    CONFIRM_YES = "confirm_yes"
    CONFIRM_NO = "confirm_no"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VoiceIntentDecision:
    intent: VoiceIntentName
    confidence: float
    slots: dict[str, str]
    requires_confirmation: bool
    clarification_question: str | None
    transcript_redaction_hint: str
    routing_strategy: str = "rules_v1"


_CASE_PREFIX_PATTERNS: tuple[tuple[str, ...], ...] = (
    ("create", "a", "new", "case"),
    ("create", "new", "case"),
    ("create", "a", "case"),
    ("create", "case"),
    ("open", "a", "new", "case"),
    ("open", "new", "case"),
    ("new", "case"),
    ("vytvor", "mi", "novy", "pripad"),
    ("vytvor", "mi", "pripad"),
    ("vytvor", "mi", "prosim", "novy", "pripad"),
    ("vytvor", "prosim", "novy", "pripad"),
    ("vytvor", "prosim", "pripad"),
    ("vytvor", "mi", "novy", "case"),
    ("vytvor", "mi", "case"),
    ("vytvor", "novy", "pripad"),
    ("vytvor", "novy", "case"),
    ("vytvor", "case"),
    ("vytvor", "pripad"),
    ("vytvorit", "novy", "pripad"),
    ("vytvorit", "novy", "case"),
    ("vytvorit", "pripad"),
    ("vytvorit", "case"),
    ("vytvor", "novy", "pripad", "prosim"),
    ("chcem", "zalozit", "novy", "pripad"),
    ("chcem", "zalozit", "pripad"),
    ("chcel", "by", "som", "vytvorit", "novy", "pripad"),
    ("chcel", "by", "som", "vytvorit", "pripad"),
    ("chcela", "by", "som", "vytvorit", "novy", "pripad"),
    ("chcela", "by", "som", "vytvorit", "pripad"),
    ("chcem", "vytvorit", "novy", "pripad"),
    ("chcem", "vytvorit", "novy", "case"),
    ("chcem", "vytvorit", "pripad"),
    ("chcem", "vytvorit", "case"),
    ("potrebujem", "vytvorit", "novy", "pripad"),
    ("potrebujem", "vytvorit", "novy", "case"),
    ("potrebujem", "vytvorit", "pripad"),
    ("potrebujem", "vytvorit", "case"),
    ("zaloz", "novy", "pripad"),
    ("zaloz", "novy", "case"),
    ("zaloz", "pripad"),
    ("zaloz", "case"),
    ("potrebujem", "zalozit", "novy", "pripad"),
    ("potrebujem", "zalozit", "novy", "case"),
    ("potrebujem", "zalozit", "pripad"),
    ("potrebujem", "zalozit", "case"),
)

_TITLE_INTRO_PATTERNS: tuple[tuple[str, ...], ...] = (
    ("with", "name"),
    ("named",),
    ("called",),
    ("titled",),
    ("s", "nazvom"),
    ("s", "nazovom"),
    ("s", "menom"),
    ("pod", "nazvom"),
    ("pod", "nazovom"),
    ("meno", "pripadu"),
    ("nazov", "pripadu"),
    ("nazov",),
    ("nazovom",),
    ("bude", "sa", "volat"),
    ("vola", "sa"),
    ("je",),
)

_SEND_PATTERNS: tuple[tuple[str, ...], ...] = (
    ("send",),
    ("send", "it"),
    ("send", "message"),
    ("send", "the", "message"),
    ("end",),
    ("submit",),
    ("submit", "message"),
    ("i", "am", "done"),
    ("im", "done"),
    ("this", "is", "end"),
    ("this", "is", "the", "end"),
    ("odosli",),
    ("odoslat",),
    ("odosli", "spravu"),
    ("koniec",),
    ("posli",),
    ("poslat",),
    ("posli", "spravu"),
    ("to", "je", "vsetko"),
    ("cakam", "na", "odpoved"),
)

_CONFIRM_YES_PATTERNS: tuple[tuple[str, ...], ...] = (
    ("yes",),
    ("yep",),
    ("yeah",),
    ("ano",),
)

_CONFIRM_NO_PATTERNS: tuple[tuple[str, ...], ...] = (
    ("no",),
    ("nope",),
    ("nie",),
)

_POLITE_PREFIXES = {
    "dobre",
    "hej",
    "ok",
    "okay",
    "poprosim",
    "please",
    "prosim",
    "ta",
    "vas",
    "bitte",
    "este",
    "raz",
}
_EDGE_CHARS = " \t\r\n-_,.?!;:\"'`()[]{}"


def classify_voice_intent(transcript: str, *, language_code: str | None = None) -> VoiceIntentDecision:
    normalized_transcript = transcript.strip()
    if not normalized_transcript:
        return _unknown_decision("empty transcript")

    tokens = _tokenize(normalized_transcript)
    normalized_tokens = [_normalize_token(token) for token in tokens]
    start = _skip_polite_prefixes(normalized_tokens)
    filtered_tokens = normalized_tokens[start:]

    if _matches_any(filtered_tokens, _CONFIRM_YES_PATTERNS):
        return VoiceIntentDecision(
            intent=VoiceIntentName.CONFIRM_YES,
            confidence=0.96,
            slots={},
            requires_confirmation=False,
            clarification_question=None,
            transcript_redaction_hint="transcript_not_stored",
        )

    if _matches_any(filtered_tokens, _CONFIRM_NO_PATTERNS):
        return VoiceIntentDecision(
            intent=VoiceIntentName.CONFIRM_NO,
            confidence=0.96,
            slots={},
            requires_confirmation=False,
            clarification_question=None,
            transcript_redaction_hint="transcript_not_stored",
        )

    if _matches_any(filtered_tokens, _SEND_PATTERNS):
        return VoiceIntentDecision(
            intent=VoiceIntentName.SEND_MESSAGE,
            confidence=0.86,
            slots={},
            requires_confirmation=False,
            clarification_question=None,
            transcript_redaction_hint="transcript_not_stored",
        )

    case_prefix_length = _match_prefix(filtered_tokens, _CASE_PREFIX_PATTERNS)
    if case_prefix_length is not None:
        title_start = start + case_prefix_length
        while title_start < len(tokens):
            next_index = _skip_title_intro(normalized_tokens, title_start)
            if next_index == title_start:
                break
            title_start = next_index
        title = _extract_title(tokens[title_start:])
        if title:
            return VoiceIntentDecision(
                intent=VoiceIntentName.CREATE_CASE,
                confidence=0.93,
                slots={"title": title},
                requires_confirmation=False,
                clarification_question=None,
                transcript_redaction_hint="store_title_only",
            )
        return VoiceIntentDecision(
            intent=VoiceIntentName.CREATE_CASE,
            confidence=0.72,
            slots={},
            requires_confirmation=False,
            clarification_question=_clarification_question(language_code),
            transcript_redaction_hint="transcript_not_stored",
        )

    return _unknown_decision("no intent matched", language_code=language_code)


def _unknown_decision(reason: str, *, language_code: str | None = None) -> VoiceIntentDecision:
    return VoiceIntentDecision(
        intent=VoiceIntentName.UNKNOWN,
        confidence=0.18,
        slots={"reason": reason},
        requires_confirmation=False,
        clarification_question=_clarification_question(language_code),
        transcript_redaction_hint="transcript_not_stored",
    )


def _clarification_question(language_code: str | None) -> str:
    normalized = (language_code or "").strip().upper()
    if normalized == "SK":
        return "Čo mám urobiť s touto správou?"
    if normalized in {"DE", "GE"}:
        return "Was soll ich mit dieser Nachricht tun?"
    return "What should I do with this message?"


def _tokenize(value: str) -> list[str]:
    return [
        token.strip()
        for token in re.sub(r"[,!?;:\"()]", " ", value).split()
        if token.strip()
    ]


def _normalize_token(token: str) -> str:
    trimmed = token.strip(_EDGE_CHARS).casefold()
    decomposed = unicodedata.normalize("NFKD", trimmed)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _skip_polite_prefixes(tokens: list[str]) -> int:
    index = 0
    while index < len(tokens) and tokens[index] in _POLITE_PREFIXES:
        index += 1
    return index


def _matches_any(tokens: list[str], patterns: tuple[tuple[str, ...], ...]) -> bool:
    return any(tuple(tokens) == pattern for pattern in patterns)


def _match_prefix(tokens: list[str], patterns: tuple[tuple[str, ...], ...]) -> int | None:
    for pattern in patterns:
        if len(tokens) >= len(pattern) and tuple(tokens[: len(pattern)]) == pattern:
            return len(pattern)
    return None


def _skip_title_intro(tokens: list[str], start_index: int) -> int:
    for pattern in _TITLE_INTRO_PATTERNS:
        if tuple(tokens[start_index : start_index + len(pattern)]) == pattern:
            return start_index + len(pattern)
    return start_index


def _extract_title(tokens: list[str]) -> str | None:
    sanitized = [token.strip(_EDGE_CHARS) for token in tokens]
    sanitized = [token for token in sanitized if token]
    normalized = [_normalize_token(token) for token in sanitized]
    suffix_length = _trailing_send_suffix_length(normalized)
    if suffix_length:
        sanitized = sanitized[: -suffix_length]
    title = " ".join(sanitized).strip()
    return title or None


def _trailing_send_suffix_length(tokens: list[str]) -> int | None:
    sorted_patterns = sorted(_SEND_PATTERNS, key=len, reverse=True)
    for pattern in sorted_patterns:
        if len(tokens) >= len(pattern) and tuple(tokens[-len(pattern) :]) == pattern:
            suffix_length = len(pattern)
            prefix_index = len(tokens) - suffix_length - 1
            if prefix_index >= 0 and tokens[prefix_index] in _POLITE_PREFIXES:
                suffix_length += 1
            return suffix_length
    return None
