"""Explicit, privacy-safe capture of reviewed third-party template sources.

This module intentionally never promotes fetched content into a canonical template body.
It creates temporary runtime review artifacts and metadata-only manifests instead.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import html
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.document_templates.models import DocumentTemplateDefinition
from app.document_templates.store import DocumentTemplateStore


FetchSource = Callable[[str], bytes]

_MANIFEST_FILENAME = "manifest.json"
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_TAG_PATTERN = re.compile(r"<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"[ \t\r\f\v]+")
_BLOCK_TAG_PATTERN = re.compile(r"</?(?:article|div|h[1-6]|li|p|section|table|tr|ul|ol)[^>]*>", re.IGNORECASE)
_STRIP_TAG_PATTERN = re.compile(r"<(?:script|style|noscript)[^>]*>.*?</(?:script|style|noscript)>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class SourceIngestionResult:
    template_key: str
    source_url: str
    source_profile: str
    captured_at: str
    content_sha256: str
    artifact_reference: str
    normalized_artifact_reference: str
    capture_status: str
    failure_code: str = ""


class TemplateSourceIngestor:
    """Captures approved source URLs into runtime-only review storage."""

    def __init__(
        self,
        *,
        store: DocumentTemplateStore,
        storage_root: Path,
        fetch_source: FetchSource | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._storage_root = storage_root
        self._fetch_source = fetch_source or _fetch_source
        self._now = now or (lambda: datetime.now(timezone.utc))

    def capture(self, templates: list[DocumentTemplateDefinition]) -> list[SourceIngestionResult]:
        """Capture each template's primary approved source URL once per template."""
        results: list[SourceIngestionResult] = []
        for template in templates:
            results.append(self._capture_template(template))
        self._write_manifest(results)
        return results

    def cleanup_expired(self, *, retention_days: int) -> list[str]:
        """Remove runtime source artifacts past the approved review window."""
        if retention_days < 1:
            raise ValueError("retention_days must be at least one day")
        manifest_path = self._storage_root / _MANIFEST_FILENAME
        entries = _read_manifest(manifest_path)
        threshold = self._now() - timedelta(days=retention_days)
        retained: list[dict[str, str]] = []
        deleted: list[str] = []
        for entry in entries:
            captured_at = _parse_timestamp(entry.get("captured_at", ""))
            if captured_at is None or captured_at >= threshold:
                retained.append(entry)
                continue
            for key in ("artifact_reference", "normalized_artifact_reference"):
                candidate = _runtime_path(self._storage_root, entry.get(key, ""))
                if candidate is not None and candidate.exists():
                    candidate.unlink()
                    deleted.append(candidate.relative_to(self._storage_root).as_posix())
            self._store.upsert_source_capture_manifest(
                template_key=entry.get("template_key", ""),
                source_url=entry.get("source_url", ""),
                content_sha256=entry.get("content_sha256", ""),
                capture_status="expired",
            )
        self._write_manifest_entries(retained)
        return deleted

    def _capture_template(self, template: DocumentTemplateDefinition) -> SourceIngestionResult:
        captured_at = self._now().astimezone(timezone.utc).isoformat()
        source_url = template.source_url.strip()
        profile = template.source_profile.strip() or "unclassified"
        if not _is_allowed_source_url(source_url):
            return self._record_failure(template.template_key, source_url, profile, captured_at, "unsupported_url_scheme")
        try:
            content = self._fetch_source(source_url)
            digest = sha256(content).hexdigest()
            artifact_path, normalized_path = _artifact_paths(
                storage_root=self._storage_root,
                template_key=template.template_key,
                source_url=source_url,
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(content)
            normalized_path.write_text(
                normalize_source_content(content=content, source_profile=profile), encoding="utf-8"
            )
            result = SourceIngestionResult(
                template_key=template.template_key,
                source_url=source_url,
                source_profile=profile,
                captured_at=captured_at,
                content_sha256=digest,
                artifact_reference=artifact_path.relative_to(self._storage_root).as_posix(),
                normalized_artifact_reference=normalized_path.relative_to(self._storage_root).as_posix(),
                capture_status="captured",
            )
            self._store.upsert_source_capture_manifest(
                template_key=result.template_key,
                source_url=result.source_url,
                content_sha256=result.content_sha256,
                artifact_reference=result.artifact_reference,
                capture_status=result.capture_status,
            )
            return result
        except (OSError, ValueError, UnicodeError) as error:
            return self._record_failure(template.template_key, source_url, profile, captured_at, _failure_code(error))

    def _record_failure(
        self, template_key: str, source_url: str, profile: str, captured_at: str, failure_code: str
    ) -> SourceIngestionResult:
        result = SourceIngestionResult(
            template_key=template_key,
            source_url=source_url,
            source_profile=profile,
            captured_at=captured_at,
            content_sha256="",
            artifact_reference="",
            normalized_artifact_reference="",
            capture_status="failed",
            failure_code=failure_code,
        )
        self._store.upsert_source_capture_manifest(
            template_key=template_key,
            source_url=source_url,
            capture_status="failed",
            failure_code=failure_code,
        )
        return result

    def _write_manifest(self, results: list[SourceIngestionResult]) -> None:
        existing = {
            (entry.get("template_key", ""), entry.get("source_url", "")): entry
            for entry in _read_manifest(self._storage_root / _MANIFEST_FILENAME)
        }
        for result in results:
            existing[(result.template_key, result.source_url)] = asdict(result)
        self._write_manifest_entries(list(existing.values()))

    def _write_manifest_entries(self, entries: list[dict[str, str]]) -> None:
        self._storage_root.mkdir(parents=True, exist_ok=True)
        target = self._storage_root / _MANIFEST_FILENAME
        target.write_text(
            json.dumps(sorted(entries, key=lambda item: (item.get("template_key", ""), item.get("source_url", ""))), indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )


def normalize_source_content(*, content: bytes, source_profile: str) -> str:
    """Normalize review artifacts while preserving the source-derived structure for humans."""
    decoded = content.decode("utf-8", errors="replace")
    profile = source_profile.strip().lower()
    if profile in {"law_firm_article_template", "interactive_form_template", "official_governed_form", "official_form_index"}:
        decoded = _STRIP_TAG_PATTERN.sub("", decoded)
        decoded = _BLOCK_TAG_PATTERN.sub("\n", decoded)
        decoded = html.unescape(_TAG_PATTERN.sub("", decoded))
    lines = [_WHITESPACE_PATTERN.sub(" ", line).strip() for line in decoded.splitlines()]
    lines = [line for line in lines if line]
    if profile == "law_firm_article_template":
        return "\n".join(_promote_article_headings(lines)) + "\n"
    if profile == "interactive_form_template":
        return "\n".join(_deduplicate_lines(lines)) + "\n"
    return "\n".join(lines) + "\n"


def _fetch_source(source_url: str) -> bytes:
    request = Request(source_url, headers={"User-Agent": "JurisDigta-template-source-review/1.0"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - URL scheme is validated before this call.
        return bytes(response.read())


def _artifact_paths(*, storage_root: Path, template_key: str, source_url: str) -> tuple[Path, Path]:
    parsed = urlparse(source_url)
    extension = Path(parsed.path).suffix.lower() or ".html"
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", extension):
        extension = ".bin"
    key_slug = re.sub(r"[^a-z0-9._-]+", "-", template_key.lower()).strip("-") or "template"
    url_digest = sha256(source_url.encode("utf-8")).hexdigest()[:16]
    raw = storage_root / key_slug / f"{url_digest}{extension}"
    return raw, raw.with_suffix(raw.suffix + ".normalized.txt")


def _is_allowed_source_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    return parsed.scheme.lower() in _ALLOWED_SCHEMES and bool(parsed.netloc)


def _read_manifest(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [entry for entry in loaded if isinstance(entry, dict)] if isinstance(loaded, list) else []


def _runtime_path(storage_root: Path, reference: str) -> Path | None:
    if not reference:
        return None
    candidate = (storage_root / reference).resolve()
    try:
        candidate.relative_to(storage_root.resolve())
    except ValueError:
        return None
    return candidate


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return None


def _failure_code(error: Exception) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", type(error).__name__.lower()).strip("_")[:128] or "capture_failed"


def _deduplicate_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        if not result or result[-1] != line:
            result.append(line)
    return result


def _promote_article_headings(lines: list[str]) -> list[str]:
    return [line if re.match(r"^(Článok|Čl\.)\s", line, re.IGNORECASE) else line for line in lines]
