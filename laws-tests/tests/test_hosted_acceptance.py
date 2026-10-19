"""Hosted launcher trust boundaries and real child-process cleanup."""

import importlib.util
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "hosted_acceptance", Path(__file__).with_name("run_hosted_acceptance.py")
)
hosted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosted)


def valid():
    return {
        "E2E_AZURE_FOUNDRY_ENDPOINT": "https://synthetic.invalid",
        "E2E_AZURE_FOUNDRY_API_VERSION": "v1",
        "E2E_AZURE_FOUNDRY_DEPLOYMENT": "gpt-5-mini",
        "E2E_AZURE_FOUNDRY_API_KEY": "synthetic-private-key",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("ENDPOINT", "http://synthetic.invalid"),
        ("ENDPOINT", "https://user:private@synthetic.invalid"),
        ("ENDPOINT", "https://synthetic.invalid?key=private"),
        ("DEPLOYMENT", "mock"),
        ("API_KEY", "unknown-variable"),
        ("API_KEY", "private\nvalue"),
    ],
)
def test_hosted_model_config_refuses_unsafe_or_missing_values(field, value):
    settings = valid()
    settings["E2E_AZURE_FOUNDRY_" + field] = value
    with pytest.raises(ValueError) as error:
        hosted.model_settings(settings)
    assert value not in str(error.value)


def test_hosted_refuses_local_execution_without_overwriting_configuration(tmp_path, monkeypatch):
    config = tmp_path / ".env"
    config.write_text("private existing configuration")
    monkeypatch.setattr(hosted, "ROOT", tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(ValueError, match="GitHub-hosted"):
        hosted.prepare(5440, [])
    assert config.read_text() == "private existing configuration"


def test_real_child_is_terminated_when_acceptance_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(hosted, "LOGS", tmp_path)
    with (
        pytest.raises(RuntimeError, match="synthetic failure"),
        hosted.services(
            [("sleep", [sys.executable, "-c", "import time; time.sleep(60)"], tmp_path, {})]
        ) as processes,
    ):
        assert processes[0].poll() is None
        raise RuntimeError("synthetic failure")
    assert processes[0].poll() is not None
