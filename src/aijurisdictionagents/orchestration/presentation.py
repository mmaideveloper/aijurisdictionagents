from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Literal, Mapping, Sequence, cast


RendererId = Literal[
    "result_card",
    "key_value_table",
    "data_table",
    "notice",
    "document_preview",
    "text",
    "sanitized_json",
    "action_link",
]

ResultShape = Literal["document", "mapping", "records", "notice", "text"]

_RENDERER_IDS = frozenset(
    {
        "result_card",
        "key_value_table",
        "data_table",
        "notice",
        "document_preview",
        "text",
        "sanitized_json",
        "action_link",
    }
)
_SENSITIVE_KEY = re.compile(
    r"(?:password|secret|token|credential|api[_-]?key|prompt|chain[_-]?of[_-]?thought|"
    r"internal[_-]?argument|connection[_-]?string|consent_event_id)",
    flags=re.IGNORECASE,
)


class PresentationPolicyError(ValueError):
    """Raised when a flow presentation policy is unsafe or malformed."""


@dataclass(frozen=True)
class PresentationRendererDefinition:
    renderer_id: RendererId
    version: int
    supported_shapes: tuple[ResultShape, ...]
    description: str

    def public_definition(self) -> dict[str, Any]:
        return {
            "renderer_id": self.renderer_id,
            "version": self.version,
            "supported_shapes": list(self.supported_shapes),
            "description": self.description,
        }


@dataclass(frozen=True)
class FlowPresentationPolicy:
    policy_id: str
    default_renderer: RendererId
    renderers: tuple[PresentationRendererDefinition, ...]
    user_overrides: tuple[RendererId, ...]
    max_items: int
    max_string_length: int
    max_payload_bytes: int


@dataclass(frozen=True)
class PresentationSelection:
    renderer: PresentationRendererDefinition
    reason_code: str
    explicit_user_request: bool
    model_proposal_accepted: bool


def builtin_presentation_renderers() -> tuple[PresentationRendererDefinition, ...]:
    return (
        PresentationRendererDefinition(
            "result_card", 1, ("document", "mapping", "records", "text"),
            "A concise result summary with bounded labelled items.",
        ),
        PresentationRendererDefinition(
            "key_value_table", 1, ("mapping",),
            "A two-column table for a single structured record.",
        ),
        PresentationRendererDefinition(
            "data_table", 1, ("records",),
            "A bounded semantic table for homogeneous records.",
        ),
        PresentationRendererDefinition(
            "notice", 1, ("notice", "text"),
            "A status, warning, limitation, or human-review notice.",
        ),
        PresentationRendererDefinition(
            "document_preview", 1, ("document",),
            "A trusted legal-document preview rendered by the client.",
        ),
        PresentationRendererDefinition(
            "text", 1, ("document", "mapping", "records", "notice", "text"),
            "Localized readable text used as the universal safe fallback.",
        ),
        PresentationRendererDefinition(
            "sanitized_json", 1, ("document", "mapping", "records", "notice", "text"),
            "Escaped JSON containing only bounded user-visible fields.",
        ),
        PresentationRendererDefinition(
            "action_link", 1, ("document", "mapping"),
            "An authorized application action; URLs are supplied by trusted application code.",
        ),
    )


def validate_presentation_policy(
    raw_policy: Any,
    *,
    registry_definitions: Sequence[PresentationRendererDefinition] | None = None,
    strict: bool,
) -> FlowPresentationPolicy | None:
    if raw_policy is None and not strict:
        return None
    if not isinstance(raw_policy, Mapping):
        raise PresentationPolicyError("invalid_presentation_policy_schema")
    if raw_policy.get("schema_version") != 1:
        raise PresentationPolicyError("unsupported_presentation_policy_schema_version")

    policy_id = _required_text(raw_policy, "policy_id")
    definitions = {
        (item.renderer_id, item.version): item
        for item in (registry_definitions or builtin_presentation_renderers())
    }
    raw_renderers = raw_policy.get("renderers")
    if not isinstance(raw_renderers, list) or not raw_renderers:
        raise PresentationPolicyError("invalid_presentation_policy_renderers")
    renderers: list[PresentationRendererDefinition] = []
    seen: set[RendererId] = set()
    for raw_renderer in raw_renderers:
        if not isinstance(raw_renderer, Mapping):
            raise PresentationPolicyError("invalid_presentation_renderer_entry")
        renderer_id = _renderer_id(raw_renderer.get("renderer_id"))
        version = raw_renderer.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise PresentationPolicyError("invalid_presentation_renderer_version")
        definition = definitions.get((renderer_id, version))
        if definition is None:
            raise PresentationPolicyError("unregistered_presentation_renderer")
        if renderer_id in seen:
            raise PresentationPolicyError("duplicate_presentation_renderer")
        renderers.append(definition)
        seen.add(renderer_id)

    default_renderer = _renderer_id(raw_policy.get("default_renderer"))
    if default_renderer not in seen:
        raise PresentationPolicyError("default_presentation_renderer_not_assigned")
    raw_overrides = raw_policy.get("user_overrides", [])
    if not isinstance(raw_overrides, list):
        raise PresentationPolicyError("invalid_presentation_user_overrides")
    overrides = tuple(_renderer_id(item) for item in raw_overrides)
    if len(set(overrides)) != len(overrides):
        raise PresentationPolicyError("duplicate_presentation_user_override")
    if set(overrides) - seen:
        raise PresentationPolicyError("unassigned_presentation_user_override")
    if "text" not in seen:
        raise PresentationPolicyError("presentation_text_fallback_required")

    return FlowPresentationPolicy(
        policy_id=policy_id,
        default_renderer=default_renderer,
        renderers=tuple(renderers),
        user_overrides=overrides,
        max_items=_bounded_int(raw_policy, "max_items", default=20, minimum=1, maximum=100),
        max_string_length=_bounded_int(
            raw_policy, "max_string_length", default=4_000, minimum=64, maximum=12_000
        ),
        max_payload_bytes=_bounded_int(
            raw_policy, "max_payload_bytes", default=64_000, minimum=1_024, maximum=256_000
        ),
    )


def presentation_result_shape(
    *,
    final_answer: str,
    tool_results: Sequence[Mapping[str, Any]],
    artifacts: Sequence[Mapping[str, Any]],
    status: str,
) -> ResultShape:
    if any(str(item.get("artifact_type", "")).endswith("document_draft") for item in artifacts):
        return "document"
    if len(tool_results) > 1:
        return "records"
    if len(tool_results) == 1:
        return "mapping"
    if status in {"blocked", "human_review_required", "waiting_for_user"}:
        return "notice"
    return "text" if final_answer.strip() else "notice"


def eligible_presentation_definitions(
    policy: FlowPresentationPolicy, *, result_shape: ResultShape
) -> tuple[dict[str, Any], ...]:
    return tuple(
        definition.public_definition()
        for definition in policy.renderers
        if result_shape in definition.supported_shapes
    )


def requested_renderer(request_text: str) -> RendererId | None:
    normalized = " ".join(request_text.casefold().split())
    patterns: tuple[tuple[RendererId, tuple[str, ...]], ...] = (
        ("sanitized_json", ("json", "raw data", "surové dáta", "surove data")),
        ("data_table", ("table", "tabuľ", "tabul", "tabelle")),
        ("result_card", ("card", "karta", "html", "web format", "webový formát")),
        ("document_preview", ("document preview", "náhľad dokumentu", "nahlad dokumentu")),
        ("notice", ("notice", "upozornenie", "warning")),
        ("text", ("plain text", "raw text", "obyčajný text", "obycajny text")),
    )
    for renderer_id, markers in patterns:
        if any(marker in normalized for marker in markers):
            return renderer_id
    return None


def select_presentation_renderer(
    policy: FlowPresentationPolicy,
    *,
    request_text: str,
    result_shape: ResultShape,
    proposed_renderer: str | None = None,
    client_capabilities: Sequence[str] | None = None,
) -> PresentationSelection:
    by_id = {item.renderer_id: item for item in policy.renderers}
    supported = set(client_capabilities) if client_capabilities is not None else set(by_id)
    explicit = requested_renderer(request_text)
    if explicit is not None and explicit in policy.user_overrides:
        definition = by_id.get(explicit)
        if (
            definition is not None
            and explicit in supported
            and result_shape in definition.supported_shapes
        ):
            return PresentationSelection(definition, "explicit_user_format", True, False)
        return PresentationSelection(by_id["text"], "explicit_format_safe_fallback", True, False)

    proposed = proposed_renderer.strip() if isinstance(proposed_renderer, str) else ""
    proposed_definition = by_id.get(cast(RendererId, proposed))
    if (
        proposed_definition is not None
        and proposed in supported
        and result_shape in proposed_definition.supported_shapes
    ):
        return PresentationSelection(proposed_definition, "model_proposal_validated", False, True)

    default = by_id[policy.default_renderer]
    if policy.default_renderer in supported and result_shape in default.supported_shapes:
        reason = "flow_default" if not proposed else "invalid_model_proposal_flow_default"
        return PresentationSelection(default, reason, False, False)
    return PresentationSelection(by_id["text"], "capability_safe_fallback", False, False)


def build_presentation_block(
    *,
    policy: FlowPresentationPolicy,
    selection: PresentationSelection,
    final_answer: str,
    tool_results: Sequence[Mapping[str, Any]] = (),
    artifacts: Sequence[Mapping[str, Any]] = (),
    citations: Sequence[str] = (),
    notices: Sequence[str] = (),
    title: str = "Result",
) -> dict[str, Any]:
    fallback = final_answer.strip()[: policy.max_string_length]
    safe_tools = _sanitize_value(list(tool_results), policy=policy)
    safe_artifacts = _sanitize_value(list(artifacts), policy=policy)
    renderer_id = selection.renderer.renderer_id
    if renderer_id == "sanitized_json":
        data: Any = {
            "answer": fallback,
            "tool_results": safe_tools,
            "artifacts": safe_artifacts,
        }
    elif renderer_id == "data_table":
        records = safe_tools if isinstance(safe_tools, list) else []
        scalar_records = [item for item in records if isinstance(item, dict)]
        columns = list(dict.fromkeys(key for row in scalar_records for key in row))[:12]
        data = {"columns": columns, "rows": scalar_records[: policy.max_items]}
    elif renderer_id == "key_value_table":
        first = safe_tools[0] if isinstance(safe_tools, list) and safe_tools else {}
        data = {"items": first if isinstance(first, dict) else {}}
    elif renderer_id == "document_preview":
        data = {"title": title[:200], "body": fallback, "human_review_required": True}
    elif renderer_id == "notice":
        data = {"severity": "warning", "title": title[:200], "body": fallback}
    elif renderer_id == "text":
        data = {"text": fallback}
    elif renderer_id == "action_link":
        data = {"label": title[:200], "href": ""}
    else:
        data = {
            "title": title[:200],
            "summary": fallback,
            "items": safe_tools if isinstance(safe_tools, list) else [],
        }

    block = {
        "schema_version": 1,
        "renderer_id": renderer_id,
        "renderer_version": selection.renderer.version,
        "data": data,
        "fallback_text": fallback,
        "citations": [str(item)[:500] for item in citations[: policy.max_items] if str(item).strip()],
        "notices": [str(item)[:500] for item in notices[: policy.max_items] if str(item).strip()],
        "selection": {
            "policy_id": policy.policy_id,
            "reason_code": selection.reason_code,
            "explicit_user_request": selection.explicit_user_request,
            "model_proposal_accepted": selection.model_proposal_accepted,
        },
    }
    encoded = json.dumps(block, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > policy.max_payload_bytes:
        return {
            "schema_version": 1,
            "renderer_id": "text",
            "renderer_version": 1,
            "data": {"text": fallback},
            "fallback_text": fallback,
            "citations": [],
            "notices": [],
            "selection": {
                "policy_id": policy.policy_id,
                "reason_code": "payload_limit_safe_fallback",
                "explicit_user_request": selection.explicit_user_request,
                "model_proposal_accepted": False,
            },
        }
    return block


def _sanitize_value(value: Any, *, policy: FlowPresentationPolicy, depth: int = 0) -> Any:
    if depth >= 4:
        return "[bounded]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[: policy.max_string_length]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, nested in list(value.items())[: policy.max_items]:
            normalized_key = str(key)[:100]
            if _SENSITIVE_KEY.search(normalized_key):
                continue
            result[normalized_key] = _sanitize_value(nested, policy=policy, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _sanitize_value(item, policy=policy, depth=depth + 1)
            for item in list(value)[: policy.max_items]
        ]
    return str(value)[: policy.max_string_length]


def _renderer_id(value: Any) -> RendererId:
    normalized = str(value).strip()
    if normalized not in _RENDERER_IDS:
        raise PresentationPolicyError("unknown_presentation_renderer")
    return cast(RendererId, normalized)


def _required_text(value: Mapping[str, Any], key: str) -> str:
    result = str(value.get(key, "")).strip()
    if not result or len(result) > 200:
        raise PresentationPolicyError(f"invalid_presentation_policy_{key}")
    return result


def _bounded_int(
    value: Mapping[str, Any], key: str, *, default: int, minimum: int, maximum: int
) -> int:
    raw = value.get(key, default)
    if not isinstance(raw, int) or isinstance(raw, bool) or not minimum <= raw <= maximum:
        raise PresentationPolicyError(f"invalid_presentation_policy_{key}")
    return raw
