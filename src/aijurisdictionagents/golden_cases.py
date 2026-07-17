"""Deterministic loading and comparison of JurisDigta golden-case exports."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
from typing import cast
import unicodedata
from zipfile import ZipFile


@dataclass(frozen=True)
class ComparisonResult:
    passed: bool
    similarity: float
    missing_required: tuple[str, ...]
    present_forbidden: tuple[str, ...]


@dataclass(frozen=True)
class GoldenCase:
    case_key: str
    prompts: tuple[str, ...]
    expected_answer: str
    expected_documents: tuple[str, ...]
    model_audit: tuple[dict[str, object], ...]
    warnings: tuple[dict[str, object], ...]


def canonical_text(value: str) -> str:
    """Normalize text for stable semantic-ish comparison without byte-matching PDFs."""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.casefold()).strip()


def compare_text(
    actual: str,
    expected: str,
    *,
    required: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
    similarity_min: float = 0.0,
) -> ComparisonResult:
    normalized_actual = canonical_text(actual)
    normalized_expected = canonical_text(expected)
    similarity = SequenceMatcher(None, normalized_actual, normalized_expected).ratio()
    missing = tuple(item for item in required if canonical_text(item) not in normalized_actual)
    present = tuple(item for item in forbidden if canonical_text(item) in normalized_actual)
    return ComparisonResult(
        passed=not missing and not present and similarity >= similarity_min,
        similarity=similarity,
        missing_required=missing,
        present_forbidden=present,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_golden_case(path: Path) -> GoldenCase:
    """Load either a native case-export v1 ZIP or the legacy scenario-01 seed ZIP."""
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        if "manifest.json" in names:
            return _load_native_export(archive)
        if "case-export.json" in names:
            return _load_legacy_export(archive)
    raise ValueError(f"Unsupported golden-case ZIP schema: {path}")


def _read_json(archive: ZipFile, name: str) -> dict[str, object]:
    value = json.loads(archive.read(name).decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {name}")
    return cast(dict[str, object], value)


def _object_list(payload: dict[str, object], key: str) -> tuple[dict[str, object], ...]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"Expected a list in field {key}")
    return tuple(cast(dict[str, object], item) for item in value if isinstance(item, dict))


def _load_legacy_export(archive: ZipFile) -> GoldenCase:
    metadata = _read_json(archive, "case-export.json")
    answer = archive.read("fixed-assistant-answer.txt").decode("utf-8-sig")
    document = archive.read("generated-document.txt").decode("utf-8-sig")
    return GoldenCase(
        case_key=str(metadata["case_key"]),
        prompts=(str(metadata["prompt"]),),
        expected_answer=answer,
        expected_documents=(document,),
        model_audit=(),
        warnings=(
            {
                "code": "legacy_fixture",
                "message": "Replace with a manually reviewed native JurisDigta case export.",
            },
        ),
    )


def _load_native_export(archive: ZipFile) -> GoldenCase:
    manifest = _read_json(archive, "manifest.json")
    messages = [
        json.loads(line)
        for line in archive.read("messages.jsonl").decode("utf-8-sig").splitlines()
        if line.strip()
    ]
    prompts = tuple(str(item["content"]) for item in messages if item.get("role") == "user")
    answers = [str(item["content"]) for item in messages if item.get("role") == "assistant"]
    documents: list[str] = []
    for item in _object_list(manifest, "documents"):
        if item.get("kind") != "generated_document":
            continue
        artifact = item.get("source_artifact")
        if isinstance(artifact, str) and artifact in archive.namelist():
            documents.append(archive.read(artifact).decode("utf-8-sig", errors="replace"))
    audit = _read_json(archive, "ai-model-audit.json") if "ai-model-audit.json" in archive.namelist() else {}
    warnings = _read_json(archive, "warnings.json") if "warnings.json" in archive.namelist() else {}
    return GoldenCase(
        case_key=str(manifest.get("case_id", manifest.get("case_title", "unknown"))),
        prompts=prompts,
        expected_answer="\n\n".join(answers),
        expected_documents=tuple(documents),
        model_audit=_object_list(audit, "entries"),
        warnings=_object_list(warnings, "items"),
    )
