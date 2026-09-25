from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from app.document_templates.source_ingestion import TemplateSourceIngestor, normalize_source_content
from app.document_templates.store import DocumentTemplateStore, DocumentTemplateStoreConfig


def _build_store(tmp_path: Path) -> DocumentTemplateStore:
    return DocumentTemplateStore(
        DocumentTemplateStoreConfig(db_option="sqlite", db_cloud="", sqlite_path=tmp_path / "templates.sqlite3")
    )


def test_capture_is_idempotent_per_template_and_avoids_filename_collisions(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    templates = [
        store.get(template_key="sk.employment.employment_contract", jurisdiction="SK"),
        store.get(template_key="sk.real_estate.lease_agreement", jurisdiction="SK"),
    ]
    payload = "<h1>Clánok I</h1><p>Review text</p>".encode("utf-8")
    payloads = {template.source_url: payload for template in templates}
    root = tmp_path / "template_sources"
    ingestor = TemplateSourceIngestor(store=store, storage_root=root, fetch_source=payloads.__getitem__)

    first = ingestor.capture(templates)
    second = ingestor.capture(templates)

    assert len({item.artifact_reference for item in first}) == 2
    assert [item.content_sha256 for item in first] == [item.content_sha256 for item in second]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 2
    assert "Review text" not in (root / "manifest.json").read_text(encoding="utf-8")
    for item in first:
        assert (root / item.artifact_reference).exists()
        assert (root / item.normalized_artifact_reference).exists()


def test_capture_records_failures_without_creating_artifacts(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    template = store.get(template_key="sk.employment.employment_contract", jurisdiction="SK")
    template = template.model_copy(update={"source_url": "file:///not-approved.html"})
    ingestor = TemplateSourceIngestor(store=store, storage_root=tmp_path / "sources")

    result = ingestor.capture([template])[0]

    assert result.capture_status == "failed"
    assert result.failure_code == "unsupported_url_scheme"
    assert not result.artifact_reference


def test_cleanup_removes_expired_runtime_bodies_but_keeps_metadata_audit(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    template = store.get(template_key="sk.employment.employment_contract", jurisdiction="SK")
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    root = tmp_path / "sources"
    ingestor = TemplateSourceIngestor(
        store=store,
        storage_root=root,
        fetch_source=lambda _: b"<p>Temporary review text</p>",
        now=lambda: now - timedelta(days=31),
    )
    captured = ingestor.capture([template])[0]

    deleted = TemplateSourceIngestor(store=store, storage_root=root, now=lambda: now).cleanup_expired(retention_days=30)

    assert sorted(deleted) == sorted([captured.artifact_reference, captured.normalized_artifact_reference])
    assert json.loads((root / "manifest.json").read_text(encoding="utf-8")) == []
    with store._connect() as connection:  # noqa: SLF001 - validates the metadata-only audit record.
        status = connection.execute(
            "SELECT capture_status FROM document_template_source_captures WHERE template_key = ?",
            (template.template_key,),
        ).fetchone()[0]
    assert status == "expired"


def test_profile_normalization_is_deterministic_and_does_not_execute_markup() -> None:
    source = "<style>hidden</style><h2>Článok I</h2><p> A  clause </p><script>alert(1)</script>".encode("utf-8")

    normalized = normalize_source_content(content=source, source_profile="law_firm_article_template")

    assert normalized == "Článok I\nA clause\n"
    assert "hidden" not in normalized
    assert "alert" not in normalized
