from pathlib import Path
import json
import pytest
from scripts.env_config import (
    audit,
    bootstrap,
    inspect_non_secret_values,
    inspectable_non_secret_keys,
    merge,
    profiles,
)


def profile_file(tmp_path: Path) -> Path:
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps(
            {
                "inspectable_non_secret": ["DB_OPTION"],
                "profiles": {"local-core": {"required": ["DB_OPTION"]}},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_audit_blocks_unknown_without_exposing_values(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DB_OPTION=unknown-variable\nSECRET=do-not-print\n", encoding="utf-8")
    example = tmp_path / ".env.example"
    example.write_text("DB_OPTION=local\n# SECRET=your-secret\n", encoding="utf-8")
    result = audit(env, example, profiles(profile_file(tmp_path))["local-core"])
    assert result["profile_ready"] is False
    assert result["unresolved_required"] == ["DB_OPTION"]
    assert "do-not-print" not in json.dumps(result)


def test_audit_detects_duplicate_malformed_and_extra(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DB_OPTION=local\nDB_OPTION=local\ninvalid\nEXTRA=yes\n", encoding="utf-8")
    example = tmp_path / ".env.example"
    example.write_text("DB_OPTION=local\n", encoding="utf-8")
    result = audit(env, example, profiles(profile_file(tmp_path))["local-core"])
    assert result["duplicate_keys"] == ["DB_OPTION"]
    assert result["malformed_line_numbers"] == [3]
    assert result["extra_keys"] == ["EXTRA"]


def test_bootstrap_is_idempotent_and_preserves_values(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "DB_OPTION=postgres\nPORT=unknown-variable\nSECRET=unknown-variable\n", encoding="utf-8"
    )
    example = tmp_path / ".env.example"
    example.write_text(
        "DB_OPTION=local\nPORT=8080\n# SECRET=your-secret\nNEW_PATH=./runs/data\n", encoding="utf-8"
    )
    first = bootstrap(env, example)
    second = bootstrap(env, example)
    content = env.read_text(encoding="utf-8")
    assert (
        "DB_OPTION=postgres" in content
        and "PORT=8080" in content
        and "SECRET=unknown-variable" in content
    )
    assert first["repaired"] == ["PORT"] and second == {"added": [], "repaired": []}


def test_merge_reports_names_only_and_rejects_bad_source(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("KEEP=local\nREPLACE=old\n", encoding="utf-8")
    source = tmp_path / "source.env"
    source.write_text("REPLACE=secret-one\nNEW=secret-two\n", encoding="utf-8")
    result = merge(env, source)
    assert result == {"added": ["NEW"], "updated": ["REPLACE"]}
    assert "secret-one" not in json.dumps(result)
    source.write_text("bad line\n", encoding="utf-8")
    with pytest.raises(ValueError):
        merge(env, source)


def test_inspection_returns_only_explicitly_allowed_non_secret_values(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DB_OPTION=local\nSECRET=do-not-print\n", encoding="utf-8")

    result = inspect_non_secret_values(env, allowed_keys={"DB_OPTION"})

    assert result == {"DB_OPTION": "local"}
    assert "do-not-print" not in json.dumps(result)


def test_inspection_denies_unknown_and_secret_like_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DB_OPTION=local\nAPI_KEY=do-not-print\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not approved"):
        inspect_non_secret_values(
            env,
            allowed_keys={"DB_OPTION"},
            requested_keys={"API_KEY"},
        )
    with pytest.raises(ValueError, match="Sensitive key"):
        inspect_non_secret_values(env, allowed_keys={"API_KEY"})


def test_inspection_fails_closed_for_sensitive_looking_value(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DB_LOCAL=postgresql://user:password@db/app\n", encoding="utf-8")

    with pytest.raises(ValueError, match="resembles sensitive"):
        inspect_non_secret_values(env, allowed_keys={"DB_LOCAL"})


def test_inspectable_allowlist_rejects_sensitive_key_names(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps({"inspectable_non_secret": ["API_KEY"], "profiles": {}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sensitive key"):
        inspectable_non_secret_keys(path)
