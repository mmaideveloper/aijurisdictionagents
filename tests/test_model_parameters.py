import pytest

from aijurisdictionagents.model_parameters import (
    deserialize_model_parameters,
    merge_model_parameters,
    serialize_model_parameters,
    validate_model_parameters,
)


def test_profile_parameters_override_provider_defaults() -> None:
    merged = merge_model_parameters(
        {"temperature": 0.2, "top_p": 0.8},
        {"temperature": None},
        provider_type="azurefoundry",
    )

    assert merged == {"top_p": 0.8}


def test_empty_parameters_are_supported_for_every_provider() -> None:
    assert validate_model_parameters({}, provider_type="custom") == {}


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"api_key": "secret"}, "not allowed"),
        ({"temperature": 2.1}, "between 0 and 2"),
        ({"max_tokens": True}, "integer"),
        ({"reasoning_effort": "unbounded"}, "must be one of"),
        ({"response_format": {"type": "json_object"}}, "not allowed"),
    ],
)
def test_invalid_or_secret_like_parameters_are_rejected(
    parameters: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_model_parameters(parameters, provider_type="azurefoundry")


def test_serialization_is_stable_and_round_trips() -> None:
    serialized = serialize_model_parameters(
        {"top_p": 0.75, "max_completion_tokens": 512},
        provider_type="openai",
    )

    assert serialized == '{"max_completion_tokens":512,"top_p":0.75}'
    assert deserialize_model_parameters(serialized) == {
        "max_completion_tokens": 512,
        "top_p": 0.75,
    }
