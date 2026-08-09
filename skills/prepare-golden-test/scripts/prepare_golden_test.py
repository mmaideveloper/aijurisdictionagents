#!/usr/bin/env python3
"""Safely validate and promote native JurisDigta golden-case exports."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable
import unicodedata
from zipfile import BadZipFile, ZipFile, ZipInfo

import pymupdf
from pypdf import PdfReader


REQUIRED_FILES = {
    "manifest.json",
    "case.json",
    "messages.jsonl",
    "ai-model-audit.json",
    "citations.json",
    "warnings.json",
    "sha256sums.txt",
}
REQUIRED_MARKERS = {
    "document_title",
    "parties",
    "operative_statement",
    "signature_block",
    "limited_claim_scope",
    "human_review_disclosure",
}
TEXT_SUFFIXES = {".json", ".jsonl", ".txt", ".md", ".html", ".htm", ".csv", ".xml"}
EXECUTABLE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".jar",
    ".js",
    ".msi",
    ".ps1",
    ".scr",
    ".sh",
    ".vbs",
}
MAX_MEMBERS = 512
MAX_MEMBER_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
SYNTHETIC_TERMS = ("synthetic", "syntetick", "fiktiv", "testovac")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|github_pat|sk-proj|sk-live|sk-test)_[A-Za-z0-9_-]{12,}\b"),
    re.compile(
        r'(?i)["\'](?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|client[_-]?secret)'
        r'["\']\s*:\s*["\'](?!unknown|redacted)[^"\']{6,}["\']'
    ),
)


class ValidationFailure(RuntimeError):
    """Raised after a redacted validation report has been written."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


def _canonical(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", plain.casefold()).strip()


def _route_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _read_json_path(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationFailure((f"invalid_json_file:{path}:{exc}",)) from exc
    if not isinstance(value, dict):
        raise ValidationFailure((f"expected_json_object:{path}",))
    return value


def _read_json_member(archive: ZipFile, name: str) -> dict[str, Any]:
    try:
        value = json.loads(archive.read(name).decode("utf-8-sig"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationFailure((f"invalid_json_member:{name}:{exc}",)) from exc
    if not isinstance(value, dict):
        raise ValidationFailure((f"expected_json_object:{name}",))
    return value


def _object_list(payload: dict[str, Any], key: str, source: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValidationFailure((f"expected_object_list:{source}:{key}",))
    return value


def _safe_member(info: ZipInfo) -> str | None:
    name = info.filename
    if "\\" in name or "\x00" in name:
        return f"unsafe_archive_path:{name!r}"
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return f"unsafe_archive_path:{name!r}"
    if re.match(r"^[A-Za-z]:", name):
        return f"unsafe_archive_path:{name!r}"
    if path.suffix.casefold() in EXECUTABLE_SUFFIXES:
        return f"unexpected_executable:{name}"
    if info.file_size > MAX_MEMBER_BYTES:
        return f"archive_member_too_large:{name}"
    ratio = info.file_size / max(info.compress_size, 1)
    if ratio > MAX_COMPRESSION_RATIO and info.file_size > 1024 * 1024:
        return f"archive_compression_ratio_exceeded:{name}"
    return None


def _luhn_valid(candidate: str) -> bool:
    digits = [int(char) for char in candidate if char.isdigit()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _scan_sensitive_text(text: str, issue_body: str) -> list[str]:
    errors: list[str] = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            errors.append("secret_or_token_pattern_detected")
    if IBAN_RE.search(text):
        errors.append("payment_iban_detected")
    if any(_luhn_valid(match.group()) for match in CARD_RE.finditer(text)):
        errors.append("payment_card_number_detected")
    issue_emails = {item.casefold() for item in EMAIL_RE.findall(issue_body)}
    for email in EMAIL_RE.findall(text):
        normalized = email.casefold()
        if normalized not in issue_emails and not normalized.endswith((".test", "@example.com")):
            errors.append("email_not_declared_by_source_issue")
            break
    return errors


def _fetch_issue(issue: int, repo: str, issue_json: Path | None) -> dict[str, Any]:
    if issue_json is not None:
        payload = _read_json_path(issue_json)
    else:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                str(issue),
                "--repo",
                repo,
                "--json",
                "number,title,body,url",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise ValidationFailure((f"source_issue_fetch_failed:{result.stderr.strip()}",))
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValidationFailure(("source_issue_fetch_invalid_json",)) from exc
    if int(payload.get("number", -1)) != issue:
        raise ValidationFailure(("source_issue_number_mismatch",))
    body = str(payload.get("body") or "")
    if not body.strip():
        raise ValidationFailure(("source_issue_body_missing",))
    if not any(term in _canonical(body) for term in SYNTHETIC_TERMS):
        raise ValidationFailure(("source_issue_missing_synthetic_data_declaration",))
    payload.setdefault("url", f"https://github.com/{repo}/issues/{issue}")
    return payload


def _validate_assertions(assertions: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("case_key", "scenario_id", "language", "country", "category", "fixture_purpose"):
        if not str(assertions.get(key) or "").strip():
            errors.append(f"assertions.{key}_missing")
    for key in ("case_key", "scenario_id"):
        value = str(assertions.get(key) or "")
        if value and not SLUG_RE.fullmatch(value):
            errors.append(f"assertions.{key}_must_be_slug")
    facts = assertions.get("source_facts")
    if not isinstance(facts, list) or not facts or any(not str(item).strip() for item in facts):
        errors.append("assertions.source_facts_missing")
    for output_name in ("answer", "document"):
        output = assertions.get(output_name)
        if not isinstance(output, dict):
            errors.append(f"assertions.{output_name}_missing")
            continue
        required = output.get("must_contain")
        forbidden = output.get("must_not_contain")
        if not isinstance(required, list) or not required:
            errors.append(f"assertions.{output_name}.must_contain_missing")
        if not isinstance(forbidden, list):
            errors.append(f"assertions.{output_name}.must_not_contain_missing")
        threshold = output.get("similarity_min")
        if not isinstance(threshold, (int, float)) or not 0.0 <= float(threshold) <= 1.0:
            errors.append(f"assertions.{output_name}.similarity_min_invalid")
    document = assertions.get("document")
    if isinstance(document, dict):
        if not str(document.get("type") or "").strip():
            errors.append("assertions.document.type_missing")
        markers = document.get("marker_phrases")
        if not isinstance(markers, dict):
            errors.append("assertions.document.marker_phrases_missing")
        else:
            missing = REQUIRED_MARKERS.difference(markers)
            errors.extend(f"assertions.document.marker_missing:{item}" for item in sorted(missing))
            for marker, phrases in markers.items():
                if marker in REQUIRED_MARKERS and (
                    not isinstance(phrases, list)
                    or not phrases
                    or any(not str(item).strip() for item in phrases)
                ):
                    errors.append(f"assertions.document.marker_phrases_empty:{marker}")
    return errors


def _parse_checksums(payload: str) -> tuple[dict[str, str], list[str]]:
    checksums: dict[str, str] = {}
    errors: list[str] = []
    for line_number, line in enumerate(payload.splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-fA-F]{64})  ([^\r\n]+)", line)
        if not match:
            errors.append(f"invalid_checksum_line:{line_number}")
            continue
        name = match.group(2)
        if name in checksums:
            errors.append(f"duplicate_checksum_path:{name}")
        checksums[name] = match.group(1).upper()
    return checksums, errors


def _render_pdf_evidence(
    payload: bytes, evidence_root: Path, ordinal: int
) -> tuple[str, list[str]]:
    errors: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(payload), strict=True)
        if not reader.pages:
            return "", [f"pdf_has_no_pages:{ordinal}"]
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:  # pypdf intentionally exposes many parser exception types
        return "", [f"invalid_pdf_structure:{ordinal}:{type(exc).__name__}"]
    if not text:
        errors.append(f"pdf_text_empty:{ordinal}")
    try:
        document = pymupdf.open(stream=payload, filetype="pdf")
        pixmap = document[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
        (evidence_root / f"document-{ordinal:02d}-first-page.png").write_bytes(
            pixmap.tobytes("png")
        )
        document.close()
    except Exception as exc:
        errors.append(f"pdf_first_page_render_failed:{ordinal}:{type(exc).__name__}")
    (evidence_root / f"document-{ordinal:02d}.pdf").write_bytes(payload)
    (evidence_root / f"document-{ordinal:02d}-extracted.txt").write_text(text, encoding="utf-8")
    return text, errors


def _validate_export(
    *,
    zip_path: Path,
    issue_payload: dict[str, Any],
    assertions: dict[str, Any],
    expected_route: str,
    expected_scenario_id: str | None,
    evidence_root: Path,
    require_native_provenance: bool,
) -> tuple[dict[str, Any], list[str]]:
    errors = _validate_assertions(assertions)
    issue_body = str(issue_payload["body"])
    if expected_scenario_id and assertions.get("scenario_id") != expected_scenario_id:
        errors.append("expected_scenario_id_mismatch")
    evidence_root.mkdir(parents=True, exist_ok=True)
    try:
        archive = ZipFile(zip_path)
    except (OSError, BadZipFile) as exc:
        raise ValidationFailure((f"invalid_zip:{type(exc).__name__}",)) from exc

    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos if not info.is_dir()]
        if len(infos) > MAX_MEMBERS:
            errors.append("archive_member_limit_exceeded")
        if len(names) != len(set(names)):
            errors.append("duplicate_archive_member")
        if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
            errors.append("archive_uncompressed_size_exceeded")
        errors.extend(error for info in infos if (error := _safe_member(info)) is not None)
        missing_files = REQUIRED_FILES.difference(names)
        errors.extend(f"required_file_missing:{name}" for name in sorted(missing_files))
        if missing_files or any(error.startswith("unsafe_archive_path") for error in errors):
            return {}, sorted(set(errors))

        manifest = _read_json_member(archive, "manifest.json")
        case = _read_json_member(archive, "case.json")
        audit_payload = _read_json_member(archive, "ai-model-audit.json")
        citations_payload = _read_json_member(archive, "citations.json")
        warnings_payload = _read_json_member(archive, "warnings.json")
        if manifest.get("schema") != "jurisdigta.case-export.v1":
            errors.append("native_manifest_schema_invalid")
        if case.get("schema") != "jurisdigta.case-export.case.v1":
            errors.append("case_schema_invalid")
        case_id = str(manifest.get("case_id") or "")
        if not case_id or str(case.get("case_id") or "") != case_id:
            errors.append("manifest_case_id_mismatch")
        if manifest.get("user_id") != case.get("user_id"):
            errors.append("manifest_user_id_mismatch")
        if manifest.get("artifact_count") != len(names):
            errors.append("manifest_artifact_count_mismatch")

        checksums, checksum_errors = _parse_checksums(
            archive.read("sha256sums.txt").decode("utf-8-sig")
        )
        errors.extend(checksum_errors)
        expected_checksum_names = set(names).difference({"sha256sums.txt"})
        if set(checksums) != expected_checksum_names:
            errors.append("internal_checksum_member_set_mismatch")
        for name, expected in checksums.items():
            if name in names and _sha256_bytes(archive.read(name)) != expected:
                errors.append(f"internal_checksum_mismatch:{name}")

        try:
            message_lines = [
                json.loads(line)
                for line in archive.read("messages.jsonl").decode("utf-8-sig").splitlines()
                if line.strip()
            ]
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationFailure((f"messages_jsonl_invalid:{exc}",)) from exc
        if any(not isinstance(item, dict) for item in message_lines):
            errors.append("messages_jsonl_object_required")
            messages: list[dict[str, Any]] = []
        else:
            messages = message_lines
        roles = Counter(str(item.get("role") or "") for item in messages)
        if not roles["user"] or not roles["assistant"]:
            errors.append("transcript_requires_user_and_assistant")
        if manifest.get("message_count") != len(messages):
            errors.append("manifest_message_count_mismatch")
        assistant_text = "\n".join(
            str(item.get("content") or "") for item in messages if item.get("role") == "assistant"
        )

        audit_entries = _object_list(audit_payload, "entries", "ai-model-audit.json")
        if not audit_entries:
            errors.append("model_audit_missing")
        route_fields = ("provider", "model", "route_type", "status")
        for index, entry in enumerate(audit_entries):
            for field in route_fields:
                if (
                    not str(entry.get(field) or "").strip()
                    or _route_key(entry.get(field)) == "unknown"
                ):
                    errors.append(f"model_audit[{index}].{field}_missing")
            if entry.get("case_id") not in (None, "", case_id):
                errors.append(f"model_audit[{index}].case_id_mismatch")
        actual_routes = sorted(
            {
                (
                    str(entry.get("provider") or ""),
                    str(entry.get("model") or ""),
                    str(entry.get("route_type") or ""),
                    str(entry.get("status") or ""),
                )
                for entry in audit_entries
            }
        )
        expected_key = _route_key(expected_route)
        if expected_key and not any(
            expected_key in {_route_key(provider), _route_key(route_type)}
            for provider, _, route_type, _ in actual_routes
        ):
            errors.append("persisted_model_route_does_not_match_expected_route")
        manifest_routes = {
            (
                str(item.get("provider") or ""),
                str(item.get("model") or ""),
                str(item.get("route_type") or ""),
                str(item.get("status") or ""),
            )
            for item in manifest.get("models_used", [])
            if isinstance(item, dict)
        }
        if set(actual_routes) != manifest_routes:
            errors.append("manifest_models_used_mismatch")
        if manifest.get("ai_model_audit_count") != len(audit_entries):
            errors.append("manifest_model_audit_count_mismatch")

        citations = _object_list(citations_payload, "items", "citations.json")
        warnings = _object_list(warnings_payload, "items", "warnings.json")
        if manifest.get("citation_count") != len(citations):
            errors.append("manifest_citation_count_mismatch")
        if any(not str(item.get("code") or "").strip() for item in warnings):
            errors.append("warning_code_missing")

        documents = manifest.get("documents")
        if not isinstance(documents, list) or any(not isinstance(item, dict) for item in documents):
            errors.append("manifest_documents_invalid")
            document_entries: list[dict[str, Any]] = []
        else:
            document_entries = documents
        if manifest.get("document_count") != len(document_entries):
            errors.append("manifest_document_count_mismatch")
        document_texts: list[str] = []
        generated_count = 0
        pdf_count = 0
        for index, document in enumerate(document_entries, start=1):
            source = str(document.get("source_artifact") or "")
            if not source or source not in names:
                errors.append(f"document_source_missing:{index}")
            elif PurePosixPath(source).suffix.casefold() in TEXT_SUFFIXES:
                document_texts.append(archive.read(source).decode("utf-8-sig", errors="replace"))
            if document.get("kind") != "generated_document":
                continue
            generated_count += 1
            rendered = str(document.get("rendered_pdf_artifact") or "")
            if (
                not rendered
                or rendered not in names
                or PurePosixPath(rendered).suffix.casefold() != ".pdf"
            ):
                errors.append(f"generated_document_pdf_missing:{index}")
                continue
            pdf_count += 1
            pdf_text, pdf_errors = _render_pdf_evidence(
                archive.read(rendered), evidence_root, pdf_count
            )
            document_texts.append(pdf_text)
            errors.extend(pdf_errors)
        if generated_count == 0:
            errors.append("generated_document_missing")

        combined_output = "\n".join([assistant_text, *document_texts])
        issue_normalized = _canonical(issue_body)
        output_normalized = _canonical(combined_output)
        for fact in assertions.get("source_facts", []):
            normalized = _canonical(str(fact))
            if normalized not in issue_normalized:
                errors.append(f"source_fact_not_in_issue:{fact}")
            if normalized not in output_normalized:
                errors.append(f"source_fact_not_in_output:{fact}")

        for output_name, output_text in (
            ("answer", assistant_text),
            ("document", "\n".join(document_texts)),
        ):
            rules = assertions.get(output_name, {})
            normalized_output = _canonical(output_text)
            for required in rules.get("must_contain", []):
                if _canonical(str(required)) not in normalized_output:
                    errors.append(f"{output_name}_required_content_missing:{required}")
            for forbidden in rules.get("must_not_contain", []):
                if _canonical(str(forbidden)) in normalized_output:
                    errors.append(f"{output_name}_forbidden_content_present:{forbidden}")
        markers = assertions.get("document", {}).get("marker_phrases", {})
        normalized_documents = _canonical("\n".join(document_texts))
        for marker in REQUIRED_MARKERS:
            phrases = markers.get(marker, []) if isinstance(markers, dict) else []
            if phrases and not any(
                _canonical(str(phrase)) in normalized_documents for phrase in phrases
            ):
                errors.append(f"legal_document_marker_missing:{marker}")

        scan_texts: list[str] = [issue_body, assistant_text, *document_texts]
        for info in infos:
            if info.is_dir() or PurePosixPath(info.filename).suffix.casefold() not in TEXT_SUFFIXES:
                continue
            if info.file_size <= 2 * 1024 * 1024:
                scan_texts.append(archive.read(info.filename).decode("utf-8-sig", errors="replace"))
        for text in scan_texts:
            errors.extend(_scan_sensitive_text(text, issue_body))

        exported_by = str(manifest.get("exported_by") or "")
        correlation_id = str(manifest.get("correlation_id") or "")
        generated_at = str(manifest.get("generated_at") or "")
        native_provenance = bool(
            (exported_by == "case-owner" or exported_by.startswith("admin:"))
            and correlation_id
            and generated_at
            and not checksum_errors
        )
        if require_native_provenance and not native_provenance:
            errors.append("native_production_export_provenance_missing")

        metadata = {
            "case_id": case_id,
            "actual_audited_routes": [
                {
                    "provider": provider,
                    "model": model,
                    "route_type": route_type,
                    "status": status,
                }
                for provider, model, route_type, status in actual_routes
            ],
            "document_count": len(document_entries),
            "generated_document_count": generated_count,
            "rendered_pdf_count": pdf_count,
            "citation_count": len(citations),
            "citation_sources": sorted(
                {
                    str(item.get("source_type") or item.get("type") or "unknown")
                    for item in citations
                }
            ),
            "warning_count": len(warnings),
            "native_production_export_provenance": native_provenance,
            "exported_by": exported_by,
        }
        return metadata, sorted(set(errors))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _run_directory(root: Path, issue: int, run_id: str) -> Path:
    path = root / f"issue-{issue}" / run_id
    path.mkdir(parents=True, exist_ok=False)
    return path


def _default_run_id(zip_sha: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{zip_sha[:12].lower()}"


def _registry_entry(
    *,
    assertions: dict[str, Any],
    issue_payload: dict[str, Any],
    fixture_name: str,
    fixture_sha: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    document_rules = dict(assertions["document"])
    document_rules["legal_document_markers"] = sorted(REQUIRED_MARKERS)
    return {
        "case_key": assertions["case_key"],
        "scenario_id": assertions["scenario_id"],
        "fixture_status": "technical_reviewed",
        "zip_path": f"cases/{fixture_name}",
        "sha256": fixture_sha,
        "source_issue": issue_payload["url"],
        "language": assertions["language"],
        "country": assertions["country"],
        "category": assertions["category"],
        "data_classification": "synthetic_test_fixture",
        "fixture_purpose": assertions["fixture_purpose"],
        "actual_audited_routes": metadata["actual_audited_routes"],
        "production_path_evidence": {
            "native_export_claim_present": metadata["native_production_export_provenance"],
            "exported_by": metadata["exported_by"],
            "human_confirmation_required": True,
        },
        "review": {
            "state": "technical_reviewed",
            "technical_reviewed_at": now,
            "native_review_requires_human_approval": True,
        },
        "source_facts": assertions["source_facts"],
        "documents": {
            "type": assertions["document"]["type"],
            "count": metadata["document_count"],
            "generated_count": metadata["generated_document_count"],
            "rendered_pdf_count": metadata["rendered_pdf_count"],
        },
        "citations": {
            "count": metadata["citation_count"],
            "source_types": metadata["citation_sources"],
        },
        "warnings_count": metadata["warning_count"],
        "expected_outputs": {
            "answer": assertions["answer"],
            "document": document_rules,
        },
    }


def _load_registry(path: Path) -> dict[str, Any]:
    registry = _read_json_path(path)
    if registry.get("schema_version") != "jurisdigta.models-testing.index.v1":
        raise ValidationFailure(("registry_schema_invalid",))
    if not isinstance(registry.get("cases"), list):
        raise ValidationFailure(("registry_cases_invalid",))
    return registry


def _prepare(args: argparse.Namespace) -> int:
    source_zip = args.zip.resolve()
    if not source_zip.is_file():
        raise ValidationFailure((f"source_zip_missing:{source_zip}",))
    fixture_sha = _sha256_file(source_zip)
    run_id = args.run_id or _default_run_id(fixture_sha)
    run_root = _run_directory(args.quarantine_root, args.issue, run_id)
    quarantined_zip = run_root / "original-case-export.zip"
    shutil.copyfile(source_zip, quarantined_zip)
    if _sha256_file(quarantined_zip) != fixture_sha:
        raise ValidationFailure(("quarantine_copy_checksum_mismatch",))

    report_path = run_root / "validation-report.json"
    report: dict[str, Any] = {
        "schema": "jurisdigta.golden-preparation-report.v1",
        "source_issue": args.issue,
        "run_id": run_id,
        "fixture_sha256": fixture_sha,
        "review_state": "technical_reviewed",
        "quarantine_only": True,
        "retention_delete_by": (datetime.now(timezone.utc) + timedelta(days=args.retention_days))
        .isoformat()
        .replace("+00:00", "Z"),
        "passed": False,
        "errors": [],
    }
    try:
        issue_payload = _fetch_issue(args.issue, args.repo, args.issue_json)
        assertions = _read_json_path(args.assertions_json)
        metadata, errors = _validate_export(
            zip_path=quarantined_zip,
            issue_payload=issue_payload,
            assertions=assertions,
            expected_route=args.expected_production_route,
            expected_scenario_id=args.expected_scenario_id,
            evidence_root=run_root / "evidence",
            require_native_provenance=False,
        )
        report["checks"] = metadata
        report["errors"] = errors
        if errors:
            raise ValidationFailure(errors)

        stable_name = args.stable_name or f"{assertions['case_key']}-case-export.zip"
        if not stable_name.endswith(".zip"):
            stable_name += ".zip"
        if not SLUG_RE.fullmatch(stable_name[:-4]):
            raise ValidationFailure(("stable_name_must_be_lowercase_slug_zip",))
        registry = _load_registry(args.registry)
        cases: list[dict[str, Any]] = registry["cases"]
        case_key = assertions["case_key"]
        conflicts = [item for item in cases if item.get("case_key") == case_key]
        if conflicts and any(item.get("sha256") != fixture_sha for item in conflicts):
            raise ValidationFailure(("case_key_already_registered_with_different_fixture",))
        if conflicts and any(item.get("fixture_status") == "native_reviewed" for item in conflicts):
            raise ValidationFailure(("cannot_downgrade_native_reviewed_fixture",))
        entry = _registry_entry(
            assertions=assertions,
            issue_payload=issue_payload,
            fixture_name=stable_name,
            fixture_sha=fixture_sha,
            metadata=metadata,
        )
        registry["cases"] = sorted(
            [item for item in cases if item.get("case_key") != case_key] + [entry],
            key=lambda item: str(item.get("case_key") or ""),
        )
        fixture_path = args.fixture_root / "cases" / stable_name
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        if fixture_path.exists() and _sha256_file(fixture_path) != fixture_sha:
            raise ValidationFailure(("fixture_destination_exists_with_different_checksum",))
        shutil.copyfile(quarantined_zip, fixture_path)
        _write_json_atomic(args.registry, registry)
        report["passed"] = True
        report["quarantine_only"] = False
        report["promoted_fixture"] = str(fixture_path)
        report["registry_case_key"] = case_key
        _write_json_atomic(report_path, report)
        print(f"Prepared technical_reviewed fixture: {fixture_path}")
        print(f"Validation report: {report_path}")
        return 0
    except ValidationFailure as exc:
        report["errors"] = list(exc.errors)
        _write_json_atomic(report_path, report)
        raise


def _approval(path: Path) -> dict[str, Any]:
    approval = _read_json_path(path)
    errors: list[str] = []
    if not str(approval.get("reviewer") or "").strip():
        errors.append("human_approval_reviewer_missing")
    reference = str(approval.get("approval_reference") or "")
    if not re.match(r"^https://github\.com/[^/]+/[^/]+/pull/\d+", reference):
        errors.append("human_approval_reference_invalid")
    approved_at = str(approval.get("approved_at") or "")
    try:
        parsed = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            errors.append("human_approval_timestamp_requires_timezone")
    except ValueError:
        errors.append("human_approval_timestamp_invalid")
    if approval.get("production_path_confirmed") is not True:
        errors.append("human_approval_must_confirm_production_path")
    if errors:
        raise ValidationFailure(errors)
    return approval


def _promote(args: argparse.Namespace) -> int:
    registry = _load_registry(args.registry)
    cases: list[dict[str, Any]] = registry["cases"]
    matches = [item for item in cases if item.get("case_key") == args.case_key]
    if len(matches) != 1:
        raise ValidationFailure(("registered_case_key_not_found_or_ambiguous",))
    entry = matches[0]
    if entry.get("fixture_status") != "technical_reviewed":
        raise ValidationFailure(("promotion_requires_technical_reviewed_state",))
    approval = _approval(args.human_approval_json)
    fixture_path = args.fixture_root / str(entry["zip_path"])
    if not fixture_path.is_file() or _sha256_file(fixture_path) != entry.get("sha256"):
        raise ValidationFailure(("registered_fixture_checksum_mismatch",))
    issue_payload = _fetch_issue(args.issue, args.repo, args.issue_json)
    source_issue = str(entry.get("source_issue") or "")
    if not source_issue.endswith(f"/issues/{args.issue}"):
        raise ValidationFailure(("promotion_source_issue_mismatch",))
    document_rules = dict(entry["expected_outputs"]["document"])
    document_rules.pop("legal_document_markers", None)
    assertions = {
        "case_key": entry["case_key"],
        "scenario_id": entry["scenario_id"],
        "language": entry["language"],
        "country": entry["country"],
        "category": entry["category"],
        "fixture_purpose": entry["fixture_purpose"],
        "source_facts": entry["source_facts"],
        "answer": entry["expected_outputs"]["answer"],
        "document": document_rules,
    }
    expected_route = str(entry["actual_audited_routes"][0]["provider"])
    run_id = args.run_id or _default_run_id(str(entry["sha256"]))
    run_root = _run_directory(args.quarantine_root, args.issue, f"promotion-{run_id}")
    metadata, errors = _validate_export(
        zip_path=fixture_path,
        issue_payload=issue_payload,
        assertions=assertions,
        expected_route=expected_route,
        expected_scenario_id=str(entry["scenario_id"]),
        evidence_root=run_root / "evidence",
        require_native_provenance=True,
    )
    if errors:
        _write_json_atomic(
            run_root / "validation-report.json",
            {"passed": False, "review_state": "technical_reviewed", "errors": errors},
        )
        raise ValidationFailure(errors)
    entry["fixture_status"] = "native_reviewed"
    entry["review"] = {
        **entry.get("review", {}),
        "state": "native_reviewed",
        "native_reviewed_at": approval["approved_at"],
        "human_reviewer": approval["reviewer"],
        "approval_reference": approval["approval_reference"],
        "production_path_confirmed": True,
    }
    entry["production_path_evidence"] = {
        **entry.get("production_path_evidence", {}),
        "human_confirmation_required": False,
        "human_confirmation_reference": approval["approval_reference"],
    }
    _write_json_atomic(args.registry, registry)
    report_path = run_root / "validation-report.json"
    _write_json_atomic(
        report_path,
        {
            "schema": "jurisdigta.golden-preparation-report.v1",
            "passed": True,
            "review_state": "native_reviewed",
            "fixture_sha256": entry["sha256"],
            "checks": metadata,
            "approval_reference": approval["approval_reference"],
        },
    )
    print(f"Promoted {args.case_key} to native_reviewed.")
    print(f"Validation report: {report_path}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--issue", type=int, required=True)
        subparser.add_argument("--repo", default="mmaideveloper/aijurisdictionagents")
        subparser.add_argument("--issue-json", type=Path)
        subparser.add_argument(
            "--registry", type=Path, default=Path("tests/modelsTesting/index.json")
        )
        subparser.add_argument("--fixture-root", type=Path, default=Path("tests/modelsTesting"))
        subparser.add_argument(
            "--quarantine-root", type=Path, default=Path("runs/model-validation")
        )
        subparser.add_argument("--run-id")

    prepare = subparsers.add_parser("prepare", help="Validate and register technical_reviewed")
    common(prepare)
    prepare.add_argument("--zip", type=Path, required=True)
    prepare.add_argument("--assertions-json", type=Path, required=True)
    prepare.add_argument("--expected-scenario-id")
    prepare.add_argument("--expected-production-route", default="azurefoundry")
    prepare.add_argument("--stable-name")
    prepare.add_argument("--retention-days", type=int, default=7)
    prepare.set_defaults(handler=_prepare)

    promote = subparsers.add_parser("promote", help="Promote after explicit human approval")
    common(promote)
    promote.add_argument("--case-key", required=True)
    promote.add_argument("--human-approval-json", type=Path, required=True)
    promote.set_defaults(handler=_promote)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if getattr(args, "retention_days", 1) < 1:
        print("ERROR: retention_days_must_be_positive", file=sys.stderr)
        return 2
    try:
        return int(args.handler(args))
    except ValidationFailure as exc:
        for error in exc.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
