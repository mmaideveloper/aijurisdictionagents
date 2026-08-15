from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import TypeAlias


ModelParameterValue: TypeAlias = bool | int | float | str | None
ModelParameters: TypeAlias = dict[str, ModelParameterValue]

_MAX_SERIALIZED_BYTES = 4096
_OPENAI_COMPATIBLE_PROVIDER_TYPES = {
    "azure",
    "azure_foundry",
    "azurefoundry",
    "local_llamacpp_openai",
    "local_lmstudio",
    "openai",
    "openai_compatible",
}
_OLLAMA_PROVIDER_TYPES = {"local_ollama", "ollama"}
_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}


def validate_model_parameters(
    parameters: Mapping[str, object] | None,
    *,
    provider_type: str,
) -> ModelParameters:
    """Return a normalized, safe provider request-parameter mapping.

    Only bounded scalar values are accepted. Credentials, endpoints, prompts, and
    arbitrary SDK kwargs therefore cannot be smuggled through model routing.
    """

    if parameters is None:
        return {}
    if not isinstance(parameters, Mapping):
        raise ValueError("model_parameters must be a JSON object")
    if not parameters:
        return {}

    normalized_provider = provider_type.strip().lower()
    allowed = _allowed_parameter_names(normalized_provider)
    normalized: ModelParameters = {}
    for raw_name, raw_value in parameters.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("model_parameters keys must be non-empty strings")
        name = raw_name.strip()
        if name not in allowed:
            raise ValueError(
                f'model parameter "{name}" is not allowed for provider type '
                f'"{normalized_provider or provider_type}"'
            )
        normalized[name] = None if raw_value is None else _validate_value(name, raw_value)

    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(payload.encode("utf-8")) > _MAX_SERIALIZED_BYTES:
        raise ValueError(f"model_parameters must not exceed {_MAX_SERIALIZED_BYTES} serialized bytes")
    return normalized


def merge_model_parameters(
    provider_parameters: Mapping[str, object] | None,
    profile_parameters: Mapping[str, object] | None,
    *,
    provider_type: str,
) -> ModelParameters:
    provider_defaults = validate_model_parameters(provider_parameters, provider_type=provider_type)
    profile_overrides = validate_model_parameters(profile_parameters, provider_type=provider_type)
    merged = dict(provider_defaults)
    for name, value in profile_overrides.items():
        if value is None:
            merged.pop(name, None)
        else:
            merged[name] = value
    return merged


def serialize_model_parameters(parameters: Mapping[str, object] | None, *, provider_type: str) -> str:
    normalized = validate_model_parameters(parameters, provider_type=provider_type)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def deserialize_model_parameters(value: object) -> ModelParameters:
    if value is None or str(value).strip() in {"", "{}"}:
        return {}
    loaded = json.loads(str(value))
    if not isinstance(loaded, dict):
        raise ValueError("stored model_parameters must be a JSON object")
    result: ModelParameters = {}
    for key, item in loaded.items():
        if not isinstance(key, str) or isinstance(item, (dict, list)):
            raise ValueError("stored model_parameters contain an invalid value")
        if item is not None and not isinstance(item, (bool, int, float, str)):
            raise ValueError("stored model_parameters contain an invalid scalar")
        result[key] = item
    return result


def _allowed_parameter_names(provider_type: str) -> set[str]:
    if provider_type in _OPENAI_COMPATIBLE_PROVIDER_TYPES:
        return {
            "frequency_penalty",
            "max_completion_tokens",
            "max_tokens",
            "parallel_tool_calls",
            "presence_penalty",
            "reasoning_effort",
            "seed",
            "store",
            "temperature",
            "top_p",
        }
    if provider_type in _OLLAMA_PROVIDER_TYPES:
        return {"max_tokens", "seed", "temperature", "top_p"}
    if not provider_type:
        raise ValueError("provider_type is required to validate model_parameters")
    raise ValueError(f'model_parameters are not supported for provider type "{provider_type}"')


def _validate_value(name: str, value: object) -> ModelParameterValue:
    if name in {"parallel_tool_calls", "store"}:
        if not isinstance(value, bool):
            raise ValueError(f'model parameter "{name}" must be a boolean')
        return value
    if name in {"max_completion_tokens", "max_tokens"}:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 2_000_000:
            raise ValueError(f'model parameter "{name}" must be an integer between 1 and 2000000')
        return value
    if name == "seed":
        if isinstance(value, bool) or not isinstance(value, int) or not -(2**31) <= value < 2**31:
            raise ValueError('model parameter "seed" must be a signed 32-bit integer')
        return value
    if name == "reasoning_effort":
        if not isinstance(value, str) or value.strip().lower() not in _REASONING_EFFORTS:
            allowed = ", ".join(sorted(_REASONING_EFFORTS))
            raise ValueError(f'model parameter "reasoning_effort" must be one of: {allowed}')
        return value.strip().lower()
    if name in {"temperature", "top_p", "frequency_penalty", "presence_penalty"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'model parameter "{name}" must be a finite number')
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f'model parameter "{name}" must be a finite number')
        lower, upper = {
            "temperature": (0.0, 2.0),
            "top_p": (0.0, 1.0),
            "frequency_penalty": (-2.0, 2.0),
            "presence_penalty": (-2.0, 2.0),
        }[name]
        if not lower <= number <= upper:
            raise ValueError(f'model parameter "{name}" must be between {lower:g} and {upper:g}')
        return number
    raise ValueError(f'unsupported model parameter "{name}"')
