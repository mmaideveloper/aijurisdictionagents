from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
import unicodedata


_MAX_QUERY_LENGTH = 400
_MAX_SEQUENCE_ITEMS = 12
_MAX_TERM_LENGTH = 100
_LEGACY_QUERY_KEY_DEFAULTS = {
    "payment_confirmation_legal_requirements": "potvrdenie",
}


class McpRetrievalPolicyError(ValueError):
    """Raised when an immutable flow retrieval policy is unsafe or incomplete."""


@dataclass(frozen=True)
class McpRetrievalRequest:
    query: str
    policy_id: str
    query_keys: tuple[str, ...]
    matched_fact_keys: tuple[str, ...]
    search_limit: int
    text_limit: int


def validate_mcp_retrieval_policy(
    policy: object,
    *,
    case_type_key: str,
    jurisdiction: str,
    strict: bool,
) -> None:
    if not isinstance(policy, Mapping):
        raise McpRetrievalPolicyError("mcp_retrieval_policy_missing")

    query_keys = _string_sequence(policy.get("query_keys", ()), field="query_keys")
    raw_default_query = policy.get("default_query")
    default_query = (
        _single_line(raw_default_query, field="default_query")
        if isinstance(raw_default_query, str)
        else ""
    )
    legacy_query_unavailable = not default_query and (
        not query_keys or not all(key in _LEGACY_QUERY_KEY_DEFAULTS for key in query_keys)
    )
    if strict and legacy_query_unavailable:
        raise McpRetrievalPolicyError("mcp_retrieval_default_query_missing")

    if strict:
        if policy.get("schema_version") != 1:
            raise McpRetrievalPolicyError("mcp_retrieval_schema_version_invalid")
        if not default_query:
            raise McpRetrievalPolicyError("mcp_retrieval_default_query_missing")
        policy_id = _single_line(policy.get("policy_id"), field="policy_id")
        if not policy_id:
            raise McpRetrievalPolicyError("mcp_retrieval_policy_id_missing")
        allowed_case_types = _string_sequence(
            policy.get("case_type_keys", ()), field="case_type_keys"
        )
        if case_type_key not in allowed_case_types:
            raise McpRetrievalPolicyError("mcp_retrieval_case_type_not_allowed")
        allowed_jurisdictions = {
            item.upper()
            for item in _string_sequence(
                policy.get("jurisdictions", ()), field="jurisdictions"
            )
        }
        if jurisdiction.strip().upper() not in allowed_jurisdictions:
            raise McpRetrievalPolicyError("mcp_retrieval_jurisdiction_not_allowed")

    _bounded_limit(policy.get("search_limit", 5), field="search_limit", maximum=20)
    _bounded_limit(policy.get("text_limit", 3), field="text_limit", maximum=10)
    _validate_fact_query_mappings(policy.get("fact_query_mappings", {}))


def build_mcp_retrieval_request(
    *,
    policy: object,
    case_type_key: str,
    jurisdiction: str,
    verified_facts: Mapping[str, str],
    strict: bool,
) -> McpRetrievalRequest:
    validate_mcp_retrieval_policy(
        policy,
        case_type_key=case_type_key,
        jurisdiction=jurisdiction,
        strict=strict,
    )
    assert isinstance(policy, Mapping)

    query_keys = _string_sequence(policy.get("query_keys", ()), field="query_keys")
    raw_default_query = policy.get("default_query")
    query = (
        _single_line(raw_default_query, field="default_query")
        if isinstance(raw_default_query, str)
        else ""
    )
    if not query and query_keys:
        query = _LEGACY_QUERY_KEY_DEFAULTS.get(query_keys[0], "")
    if not query and not strict:
        query = "potvrdenie"

    matched_fact_keys: list[str] = []
    raw_mappings = policy.get("fact_query_mappings", {})
    assert isinstance(raw_mappings, Mapping)
    for fact_key, raw_choices in raw_mappings.items():
        fact_value = verified_facts.get(str(fact_key), "").strip()
        if not fact_value or not isinstance(raw_choices, Mapping):
            continue
        normalized_value = _canonical_match_value(fact_value)
        for reviewed_term, raw_aliases in raw_choices.items():
            aliases = _string_sequence(raw_aliases, field=f"fact_query_mappings.{fact_key}")
            reviewed = _single_line(reviewed_term, field=f"fact_query_mappings.{fact_key}.query")
            candidates = (reviewed, *aliases)
            if not any(
                _contains_reviewed_alias(normalized_value, _canonical_match_value(item))
                for item in candidates
            ):
                continue
            query = reviewed
            matched_fact_keys.append(str(fact_key))
            break

    if len(query) > _MAX_QUERY_LENGTH:
        raise McpRetrievalPolicyError("mcp_retrieval_query_too_long")
    raw_policy_id = policy.get("policy_id")
    policy_id = (
        _single_line(raw_policy_id, field="policy_id")
        if isinstance(raw_policy_id, str) and raw_policy_id.strip()
        else "legacy:" + ",".join(query_keys)
    )
    return McpRetrievalRequest(
        query=query,
        policy_id=policy_id,
        query_keys=query_keys,
        matched_fact_keys=tuple(matched_fact_keys),
        search_limit=_bounded_limit(
            policy.get("search_limit", 5), field="search_limit", maximum=20
        ),
        text_limit=_bounded_limit(policy.get("text_limit", 3), field="text_limit", maximum=10),
    )


def _validate_fact_query_mappings(value: object) -> None:
    if not isinstance(value, Mapping):
        raise McpRetrievalPolicyError("mcp_retrieval_fact_query_mappings_invalid")
    for fact_key, raw_choices in value.items():
        _single_line(fact_key, field="fact_query_mappings.fact_key")
        if not isinstance(raw_choices, Mapping) or not raw_choices:
            raise McpRetrievalPolicyError("mcp_retrieval_fact_choices_invalid")
        for reviewed_term, raw_aliases in raw_choices.items():
            _single_line(reviewed_term, field="fact_query_mappings.reviewed_query")
            aliases = _string_sequence(raw_aliases, field="fact_query_mappings.aliases")
            if not aliases:
                raise McpRetrievalPolicyError("mcp_retrieval_fact_aliases_missing")


def _contains_reviewed_alias(value: str, alias: str) -> bool:
    if not alias:
        return False
    return re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", value) is not None


def _string_sequence(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise McpRetrievalPolicyError(f"mcp_retrieval_{field}_invalid")
    if len(value) > _MAX_SEQUENCE_ITEMS:
        raise McpRetrievalPolicyError(f"mcp_retrieval_{field}_too_many")
    return tuple(_single_line(item, field=field) for item in value)


def _single_line(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise McpRetrievalPolicyError(f"mcp_retrieval_{field}_invalid")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > _MAX_TERM_LENGTH:
        raise McpRetrievalPolicyError(f"mcp_retrieval_{field}_invalid")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise McpRetrievalPolicyError(f"mcp_retrieval_{field}_control_character")
    return normalized


def _bounded_limit(value: object, *, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        raise McpRetrievalPolicyError(f"mcp_retrieval_{field}_invalid")
    return value


def _canonical_match_value(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()
