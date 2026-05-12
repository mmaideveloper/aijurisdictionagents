from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from pathlib import Path
import os
import re
import shutil
import subprocess
import time
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

from .archive_storage import ArchiveObjectStore, build_archive_object_store
from .config import LawsCollectorConfig
from .domain import ArchiveImportAsset, CollectorImportState, CollectorProgress, LawSnapshot, SyncSummary
from .service import LawsCollectorService
from .slovlex_live_source import (
    _build_metadata_record,
    _normalize_date_value,
    _normalize_whitespace,
    _parse_h1,
    _parse_metadata_fields,
    _parse_pdf_url,
    _parse_provisions,
    _parse_relations,
    _strip_tags,
)

_EXPORT_INDEX_URL = "https://static.slov-lex.sk/static/exporty/index.portal"
_STATIC_ROOT = "https://static.slov-lex.sk"
_PUBLIC_ROOT = "https://www.slov-lex.sk"
_REQUEST_HEADERS = {"User-Agent": "aijurisdictionagents-slovlex-zip/1.0"}
_MONTHLY_RANGE_PATTERN = re.compile(
    r"Zmeny v zbierke od\s+(\d{2}\.\d{2}\.\d{4})\s+do\s+(\d{2}\.\d{2}\.\d{4})",
    re.IGNORECASE,
)
_ARCHIVE_DATE_PATTERN = re.compile(
    r"Kompletný archív zbierky zo dňa\s+(\d{2}\.\d{2}\.\d{4})",
    re.IGNORECASE,
)
_HREF_PATTERN = re.compile(r'href="([^"]+)"', re.IGNORECASE)
_LOGGER = logging.getLogger("laws-collector")


class ZipImportStateStore(Protocol):
    def get_import_state(self, *, country_code: str, import_key: str) -> CollectorImportState | None: ...

    def upsert_import_state(self, state: CollectorImportState) -> None: ...

    def upsert_archive_import_asset(self, asset: ArchiveImportAsset) -> None: ...

    def update_archive_import_assets_status(
        self,
        *,
        country_code: str,
        import_key: str,
        processing_status: str,
    ) -> None: ...

    def get_or_create_collector_progress(
        self,
        *,
        country_code: str,
        source_system: str,
        initial_year: int,
    ) -> CollectorProgress: ...

    def save_collector_progress(self, progress: CollectorProgress) -> None: ...


@dataclass(frozen=True)
class SlovLexArchiveExport:
    snapshot_date: str
    part_urls: tuple[str, ...]

    @property
    def import_key(self) -> str:
        return "slov-lex:zip:archive-seed"

    @property
    def import_label(self) -> str:
        return f"archive seed {self.snapshot_date}"


@dataclass(frozen=True)
class SlovLexMonthlyExport:
    range_start: str
    range_end: str
    zip_url: str

    @property
    def import_key(self) -> str:
        return f"slov-lex:zip:monthly:{self.range_start}_{self.range_end}"

    @property
    def import_label(self) -> str:
        return f"monthly {self.range_start}..{self.range_end}"


@dataclass(frozen=True)
class SlovLexExportIndex:
    archive_export: SlovLexArchiveExport | None
    monthly_export: SlovLexMonthlyExport | None


@dataclass(frozen=True)
class SlovLexZipImportSummary:
    phase: str
    import_key: str | None
    import_label: str | None
    entries_processed: int
    sync_summary: SyncSummary
    archive_completed: bool
    monthly_completed: bool
    last_processed_entry: str | None
    last_processed_law: str | None
    stopped_due_to_max_running_time: bool = False
    skipped_as_already_completed: bool = False


class SlovLexExportIndexLoader:
    def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
        request = Request(_EXPORT_INDEX_URL, headers=_REQUEST_HEADERS)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                html = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise RuntimeError(f"SlovLex export index failed: HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"SlovLex export index failed: {exc}") from exc
        return parse_export_index_html(html)


class SlovLexZipImportRunner:
    def __init__(
        self,
        *,
        config: LawsCollectorConfig,
        store: ZipImportStateStore,
        service: LawsCollectorService,
        export_index_loader: SlovLexExportIndexLoader | None = None,
        archive_object_store: ArchiveObjectStore | None = None,
        monotonic_time_provider=time.monotonic,
    ) -> None:
        self.config = config
        self.store = store
        self.service = service
        self.export_index_loader = export_index_loader or SlovLexExportIndexLoader()
        self.archive_object_store = archive_object_store or build_archive_object_store(config)
        self._monotonic_time = monotonic_time_provider

    def run(self, *, max_running_seconds: float = 0) -> SlovLexZipImportSummary:
        started_at = self._monotonic_time()
        index = self.export_index_loader.load()
        _log_zip(
            "index loaded "
            f"archive_snapshot={index.archive_export.snapshot_date if index.archive_export else ''} "
            f"monthly_range={_format_monthly_range(index.monthly_export)}"
        )
        archive_completed_state = self.store.get_import_state(
            country_code=self.config.country_code,
            import_key="slov-lex:zip:archive-seed",
        )
        archive_completed = archive_completed_state is not None and archive_completed_state.status == "completed"
        if archive_completed_state is not None:
            _log_zip(
                "archive state loaded "
                f"status={archive_completed_state.status} "
                f"last_processed_law={archive_completed_state.last_processed_law or ''} "
                f"archive_snapshot_date={_archive_snapshot_date(archive_completed_state) or ''}"
            )

        if not archive_completed and index.archive_export is not None:
            _log_zip(
                "archive import starting "
                f"snapshot_date={index.archive_export.snapshot_date} "
                f"parts={len(index.archive_export.part_urls)}"
            )
            summary = self._process_archive(
                export=index.archive_export,
                max_running_seconds=max_running_seconds,
                started_at=started_at,
            )
            if summary.stopped_due_to_max_running_time or not summary.archive_completed:
                _log_zip(
                    "archive import paused "
                    f"entries_processed={summary.entries_processed} "
                    f"last_processed_law={summary.last_processed_law or ''}"
                )
                return summary
            archive_completed_state = self.store.get_import_state(
                country_code=self.config.country_code,
                import_key=index.archive_export.import_key,
            )
            archive_completed = archive_completed_state is not None and archive_completed_state.status == "completed"
            _log_zip(
                "archive import completed "
                f"entries_processed={summary.entries_processed} "
                f"last_processed_law={summary.last_processed_law or ''}"
            )

        if index.monthly_export is None:
            _log_zip("no monthly export available")
            return SlovLexZipImportSummary(
                phase="idle",
                import_key=None,
                import_label=None,
                entries_processed=0,
                sync_summary=SyncSummary(),
                archive_completed=archive_completed,
                monthly_completed=False,
                last_processed_entry=None,
                last_processed_law=None,
            )

        archive_date = _archive_snapshot_date(archive_completed_state)
        if archive_date is not None and index.monthly_export.range_end <= archive_date:
            _log_zip(
                "monthly import skipped because archive already covers range "
                f"archive_snapshot_date={archive_date} "
                f"monthly_range={index.monthly_export.range_start}..{index.monthly_export.range_end}"
            )
            return SlovLexZipImportSummary(
                phase="monthly",
                import_key=index.monthly_export.import_key,
                import_label=index.monthly_export.import_label,
                entries_processed=0,
                sync_summary=SyncSummary(),
                archive_completed=archive_completed,
                monthly_completed=True,
                last_processed_entry=None,
                last_processed_law=None,
                skipped_as_already_completed=True,
            )

        monthly_state = self.store.get_import_state(
            country_code=self.config.country_code,
            import_key=index.monthly_export.import_key,
        )
        if monthly_state is not None and monthly_state.status == "completed":
            _log_zip(
                "monthly import skipped because the same monthly bundle was already completed "
                f"range={index.monthly_export.range_start}..{index.monthly_export.range_end} "
                f"last_processed_law={monthly_state.last_processed_law or ''}"
            )
            return SlovLexZipImportSummary(
                phase="monthly",
                import_key=index.monthly_export.import_key,
                import_label=index.monthly_export.import_label,
                entries_processed=0,
                sync_summary=SyncSummary(),
                archive_completed=archive_completed,
                monthly_completed=True,
                last_processed_entry=monthly_state.last_processed_entry,
                last_processed_law=monthly_state.last_processed_law,
                skipped_as_already_completed=True,
            )

        _log_zip(
            "monthly import starting "
            f"range={index.monthly_export.range_start}..{index.monthly_export.range_end}"
        )
        return self._process_monthly(
            export=index.monthly_export,
            max_running_seconds=max_running_seconds,
            started_at=started_at,
            archive_completed=archive_completed,
        )

    def _process_archive(
        self,
        *,
        export: SlovLexArchiveExport,
        max_running_seconds: float,
        started_at: float,
    ) -> SlovLexZipImportSummary:
        base_root = self.config.archive_root / "archive" / export.snapshot_date
        download_root = base_root / "download"
        extract_root = base_root / "extract"
        for url in export.part_urls:
            destination = download_root / Path(url).name
            _log_zip(f"archive download source={url} destination={destination}")
            _download_file(url=url, destination=destination)
            self._record_archive_asset(
                import_key=export.import_key,
                import_label=export.import_label,
                phase="archive",
                source_url=url,
                source_file=destination,
                metadata={"archive_snapshot_date": export.snapshot_date},
            )
        _extract_archive_bundle(download_root=download_root, extract_root=extract_root)
        return self._process_extracted_entries(
            import_key=export.import_key,
            import_label=export.import_label,
            source_url=",".join(export.part_urls),
            metadata={"archive_snapshot_date": export.snapshot_date, "phase": "archive"},
            extract_root=extract_root,
            max_running_seconds=max_running_seconds,
            started_at=started_at,
            archive_completed_on_success=True,
            archive_completed=False,
        )

    def _process_monthly(
        self,
        *,
        export: SlovLexMonthlyExport,
        max_running_seconds: float,
        started_at: float,
        archive_completed: bool,
    ) -> SlovLexZipImportSummary:
        base_root = self.config.archive_root / "monthly" / export.range_end
        download_root = base_root / "download"
        extract_root = base_root / "extract"
        destination = download_root / Path(export.zip_url).name
        _log_zip(f"monthly download source={export.zip_url} destination={destination}")
        _download_file(url=export.zip_url, destination=destination)
        self._record_archive_asset(
            import_key=export.import_key,
            import_label=export.import_label,
            phase="monthly",
            source_url=export.zip_url,
            source_file=destination,
            metadata={
                "monthly_range_start": export.range_start,
                "monthly_range_end": export.range_end,
            },
        )
        _extract_zip_archive(zip_path=destination, extract_root=extract_root)
        return self._process_extracted_entries(
            import_key=export.import_key,
            import_label=export.import_label,
            source_url=export.zip_url,
            metadata={
                "monthly_range_start": export.range_start,
                "monthly_range_end": export.range_end,
                "phase": "monthly",
            },
            extract_root=extract_root,
            max_running_seconds=max_running_seconds,
            started_at=started_at,
            archive_completed_on_success=False,
            archive_completed=archive_completed,
        )

    def _process_extracted_entries(
        self,
        *,
        import_key: str,
        import_label: str,
        source_url: str,
        metadata: dict[str, object],
        extract_root: Path,
        max_running_seconds: float,
        started_at: float,
        archive_completed_on_success: bool,
        archive_completed: bool,
    ) -> SlovLexZipImportSummary:
        entries = list(iter_slovlex_entry_files(extract_root))
        state = self.store.get_import_state(country_code=self.config.country_code, import_key=import_key)
        if state is None:
            state = CollectorImportState(
                country_code=self.config.country_code,
                source_system="slov-lex",
                import_key=import_key,
                import_label=import_label,
                source_url=source_url,
                status="in_progress",
                started_at=_now_iso(),
                last_processed_at=None,
                last_processed_entry=None,
                last_processed_law_year=None,
                last_processed_law_number=None,
                completed_at=None,
                metadata=metadata,
            )
            self.store.upsert_import_state(state)
            self.store.update_archive_import_assets_status(
                country_code=self.config.country_code,
                import_key=import_key,
                processing_status="in_progress",
            )
            _log_zip(
                "state initialized "
                f"phase={metadata.get('phase', 'zip')} import_key={import_key}"
            )
        elif state.status == "completed":
            self.store.update_archive_import_assets_status(
                country_code=self.config.country_code,
                import_key=import_key,
                processing_status="processed",
            )
            _log_zip(
                "state already completed "
                f"phase={metadata.get('phase', 'zip')} import_key={import_key} "
                f"last_processed_law={state.last_processed_law or ''}"
            )
            return SlovLexZipImportSummary(
                phase=str(metadata.get("phase", "zip")),
                import_key=import_key,
                import_label=import_label,
                entries_processed=0,
                sync_summary=SyncSummary(),
                archive_completed=archive_completed or archive_completed_on_success,
                monthly_completed=not archive_completed_on_success,
                last_processed_entry=state.last_processed_entry,
                last_processed_law=state.last_processed_law,
                skipped_as_already_completed=True,
            )

        sync_summary = SyncSummary()
        entries_processed = 0
        resume_entry = state.last_processed_entry
        resume_reached = resume_entry is None
        last_state = state
        collector_progress = self.store.get_or_create_collector_progress(
            country_code=self.config.country_code,
            source_system="slov-lex",
            initial_year=self.config.initial_import_from.year,
        )
        highest_processed_law = _highest_progress_key(collector_progress)
        if resume_entry is not None:
            _log_zip(
                "resuming import "
                f"phase={metadata.get('phase', 'zip')} import_key={import_key} "
                f"resume_after={resume_entry}"
            )

        for entry in entries:
            relative_entry = entry.relative_to(extract_root).as_posix()
            if not resume_reached:
                if relative_entry == resume_entry:
                    resume_reached = True
                continue
            if max_running_seconds > 0 and (self._monotonic_time() - started_at) >= max_running_seconds:
                _log_zip(
                    "max running time reached "
                    f"phase={metadata.get('phase', 'zip')} import_key={import_key} "
                    f"last_processed_law={last_state.last_processed_law or ''}"
                )
                return SlovLexZipImportSummary(
                    phase=str(metadata.get("phase", "zip")),
                    import_key=import_key,
                    import_label=import_label,
                    entries_processed=entries_processed,
                    sync_summary=sync_summary,
                    archive_completed=archive_completed,
                    monthly_completed=False,
                    last_processed_entry=last_state.last_processed_entry,
                    last_processed_law=last_state.last_processed_law,
                    stopped_due_to_max_running_time=True,
                )
            snapshot = load_snapshot_from_entry_file(entry)
            if snapshot.year < self.config.historical_import_from.year:
                entries_processed += 1
                last_state = last_state.evolve(
                    status="in_progress",
                    last_processed_at=_now_iso(),
                    last_processed_entry=relative_entry,
                    last_processed_law_year=snapshot.year,
                    last_processed_law_number=snapshot.number,
                    metadata=metadata,
                )
                self.store.upsert_import_state(last_state)
                continue
            sync_summary = sync_summary.merge(self.service.sync((snapshot,)))
            entries_processed += 1
            last_state = last_state.evolve(
                status="in_progress",
                last_processed_at=_now_iso(),
                last_processed_entry=relative_entry,
                last_processed_law_year=snapshot.year,
                last_processed_law_number=snapshot.number,
                metadata=metadata,
            )
            self.store.upsert_import_state(last_state)
            collector_progress = collector_progress.evolve(
                last_collector_run_at=last_state.last_processed_at,
                last_processed_at=last_state.last_processed_at,
            )
            current_law = (snapshot.year, snapshot.number)
            if current_law >= highest_processed_law:
                highest_processed_law = current_law
                collector_progress = collector_progress.evolve(
                    last_processed_law_year=snapshot.year,
                    last_processed_law_number=snapshot.number,
                    next_probe_law_year=snapshot.year,
                    next_probe_law_number=snapshot.number + 1,
                )
            self.store.save_collector_progress(collector_progress)

        completed_state = last_state.evolve(
            status="completed",
            completed_at=_now_iso(),
            metadata=metadata,
        )
        self.store.upsert_import_state(completed_state)
        self.store.update_archive_import_assets_status(
            country_code=self.config.country_code,
            import_key=import_key,
            processing_status="processed",
        )
        _log_zip(
            "state completed "
            f"phase={metadata.get('phase', 'zip')} import_key={import_key} "
            f"entries_processed={entries_processed} "
            f"last_processed_law={completed_state.last_processed_law or ''}"
        )
        return SlovLexZipImportSummary(
            phase=str(metadata.get("phase", "zip")),
            import_key=import_key,
            import_label=import_label,
            entries_processed=entries_processed,
            sync_summary=sync_summary,
            archive_completed=archive_completed or archive_completed_on_success,
            monthly_completed=not archive_completed_on_success,
            last_processed_entry=completed_state.last_processed_entry,
            last_processed_law=completed_state.last_processed_law,
        )

    def _record_archive_asset(
        self,
        *,
        import_key: str,
        import_label: str,
        phase: str,
        source_url: str,
        source_file: Path,
        metadata: dict[str, object],
    ) -> None:
        relative_storage_path = _build_archive_storage_relative_path(
            country_code=self.config.country_code,
            archive_root=self.config.archive_root,
            source_file=source_file,
        )
        stored_object = self.archive_object_store.persist_file(
            source_path=source_file,
            relative_path=relative_storage_path,
        )
        self.store.upsert_archive_import_asset(
            ArchiveImportAsset(
                country_code=self.config.country_code,
                source_system="slov-lex",
                import_key=import_key,
                import_label=import_label,
                phase=phase,
                asset_name=source_file.name,
                source_url=source_url,
                storage_backend=stored_object.storage_backend,
                storage_path=stored_object.storage_path,
                checksum=_hash_file(source_file),
                file_size_bytes=source_file.stat().st_size,
                processing_status="downloaded",
                downloaded_at=_now_iso(),
                metadata=metadata,
            )
        )
        _log_zip(
            "asset stored "
            f"phase={phase} import_key={import_key} asset_name={source_file.name} "
            f"storage_backend={stored_object.storage_backend} storage_path={stored_object.storage_path}"
        )


def parse_export_index_html(html: str) -> SlovLexExportIndex:
    monthly_match = _MONTHLY_RANGE_PATTERN.search(html)
    archive_match = _ARCHIVE_DATE_PATTERN.search(html)
    hrefs = tuple(_HREF_PATTERN.findall(html))

    archive_urls = sorted(
        url
        for url in hrefs
        if Path(url).name.startswith("export.z") or Path(url).name == "export.zip"
    )
    monthly_url = next((url for url in hrefs if Path(url).name == "exportZmeny.zip"), None)

    archive_export = None
    if archive_match and archive_urls:
        archive_export = SlovLexArchiveExport(
            snapshot_date=_to_iso_date(archive_match.group(1)),
            part_urls=tuple(archive_urls),
        )

    monthly_export = None
    if monthly_match and monthly_url:
        monthly_export = SlovLexMonthlyExport(
            range_start=_to_iso_date(monthly_match.group(1)),
            range_end=_to_iso_date(monthly_match.group(2)),
            zip_url=monthly_url,
        )

    return SlovLexExportIndex(
        archive_export=archive_export,
        monthly_export=monthly_export,
    )


def iter_slovlex_entry_files(extract_root: Path) -> tuple[Path, ...]:
    entries: list[Path] = []
    for candidate in sorted(extract_root.rglob("*")):
        if not candidate.is_file():
            continue
        parsed = _parse_entry_path(candidate, extract_root=extract_root)
        if parsed is None:
            continue
        entries.append(candidate)
    return tuple(entries)


def load_snapshot_from_entry_file(entry_file: Path) -> LawSnapshot:
    parsed = _parse_entry_path(entry_file)
    if parsed is None:
        raise ValueError(f"Unsupported SlovLex entry path: {entry_file}")
    year, number, version_token = parsed
    html_bytes = entry_file.read_bytes()
    html = html_bytes.decode("utf-8", errors="ignore")
    metadata_fields = _parse_metadata_fields(html)
    publication_date = _normalize_date_value(metadata_fields.get("datum vyhlasenia", ""))
    effective_from = _normalize_date_value(metadata_fields.get("datum ucinnosti od", "")) or _date_from_token(version_token)
    if not effective_from:
        effective_from = publication_date
    official_name = metadata_fields.get("nazov", "").strip() or (_parse_h1(html) or f"{number}/{year}")
    metadata_record = _build_metadata_record(
        metadata_fields=metadata_fields,
        title=official_name,
        default_publication_date=publication_date or effective_from,
        default_effective_from=effective_from,
    )
    relations = _parse_relations(html)
    provisions = _parse_provisions(html)
    text_content = "\n\n".join(record.text for record in provisions if record.text).strip()
    if not text_content:
        text_content = _normalize_whitespace(_strip_tags(html))
    try:
        pdf_url = _parse_pdf_url(html=html, year=year, number=number)
    except RuntimeError:
        pdf_url = ""
    return LawSnapshot(
        source_system="slov-lex",
        country_code="SK",
        collection_code="ZZ",
        year=year,
        number=number,
        official_name=official_name,
        lawyer_title=official_name,
        publication_date=publication_date or effective_from,
        effective_from=effective_from,
        version_token=version_token,
        source_url=f"{_PUBLIC_ROOT}/pravne-predpisy/SK/ZZ/{year}/{number}/",
        html_url=_build_html_url(year=year, number=number, version_token=version_token, suffix=entry_file.suffix),
        pdf_url=pdf_url,
        html_content=text_content,
        html_source_content=html_bytes,
        pdf_content=b"",
        provisions=provisions,
        metadata=metadata_record,
        relations=relations,
    )


def _parse_entry_path(path: Path, *, extract_root: Path | None = None) -> tuple[int, int, str] | None:
    if extract_root is None:
        relative = path
    else:
        try:
            relative = path.relative_to(extract_root)
        except ValueError:
            relative = path
    parts = relative.parts
    for index in range(len(parts) - 4):
        if parts[index] != "SK" or parts[index + 1] != "ZZ":
            continue
        if len(parts) != index + 5:
            return None
        year_text = parts[index + 2]
        number_text = parts[index + 3]
        filename = parts[index + 4]
        if not year_text.isdigit() or not number_text.isdigit():
            return None
        candidate = Path(filename)
        if candidate.suffix.lower() not in {".html", ".portal"}:
            return None
        version_token = candidate.stem
        if version_token == "index" or version_token.endswith(".print"):
            return None
        return int(year_text), int(number_text), version_token
    return None


def _build_html_url(*, year: int, number: int, version_token: str, suffix: str) -> str:
    return f"{_STATIC_ROOT}/static/SK/ZZ/{year}/{number}/{version_token}{suffix}"


def _download_file(*, url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return
    temporary_path = destination.with_suffix(f"{destination.suffix}.part")
    request = Request(url, headers=_REQUEST_HEADERS)
    try:
        with urlopen(request, timeout=120) as response, temporary_path.open("wb") as output:  # noqa: S310
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
    except HTTPError as exc:
        raise RuntimeError(f"SlovLex download failed for {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"SlovLex download failed for {url}: {exc}") from exc
    temporary_path.replace(destination)


def _build_archive_storage_relative_path(
    *,
    country_code: str,
    archive_root: Path,
    source_file: Path,
) -> str:
    relative_local_path = source_file.relative_to(archive_root).as_posix()
    return f"{country_code.lower()}/{relative_local_path}"


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _reset_extract_root(extract_root: Path) -> None:
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)


def _extract_marker_matches(*, marker: Path, expected_signature: dict[str, object]) -> bool:
    if not marker.exists():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("signature") == expected_signature


def _write_extract_marker(*, marker: Path, signature: dict[str, object]) -> None:
    marker.write_text(
        json.dumps({"completed_at": _now_iso(), "signature": signature}, ensure_ascii=True, sort_keys=True),
        encoding="utf-8",
    )


def _extract_zip_archive(*, zip_path: Path, extract_root: Path) -> None:
    marker = extract_root / ".extract.complete"
    signature = {"mode": "single", "files": [{"name": zip_path.name, "checksum": _hash_file(zip_path)}]}
    if _extract_marker_matches(marker=marker, expected_signature=signature):
        _log_zip(f"extract skipped marker={marker}")
        return
    _reset_extract_root(extract_root)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_root)
    _write_extract_marker(marker=marker, signature=signature)


def _extract_archive_bundle(*, download_root: Path, extract_root: Path) -> None:
    marker = extract_root / ".extract.complete"
    final_zip = download_root / "export.zip"
    split_parts = tuple(
        path for path in sorted(download_root.glob("export.z*"))
        if path.name.lower() != "export.zip"
    )
    signature = {
        "mode": "split" if split_parts else "single",
        "files": [
            {"name": path.name, "checksum": _hash_file(path)}
            for path in (*split_parts, final_zip)
            if path.exists()
        ],
    }
    if _extract_marker_matches(marker=marker, expected_signature=signature):
        _log_zip(f"extract skipped marker={marker}")
        return
    _reset_extract_root(extract_root)
    if final_zip.exists() and not split_parts:
        _log_zip(f"extract single zip source={final_zip} destination={extract_root}")
        _extract_zip_archive(zip_path=final_zip, extract_root=extract_root)
        return
    command = _resolve_7zip_command()
    if command is None:
        combined_zip = _combine_split_zip_archive(
            download_root=download_root,
            split_parts=split_parts,
            final_zip=final_zip,
        )
        _log_zip(
            f"extract combined split archive source={combined_zip} destination={extract_root}"
        )
        with zipfile.ZipFile(combined_zip) as archive:
            archive.extractall(extract_root)
        _write_extract_marker(marker=marker, signature=signature)
        return
    _log_zip(
        f"extract split archive source={final_zip} destination={extract_root} tool={command[0]}"
    )
    completed = subprocess.run(
        [*command, "x", "-y", f"-o{extract_root}", str(final_zip)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Split SlovLex archive extraction failed: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    _write_extract_marker(marker=marker, signature=signature)


def _resolve_7zip_command() -> list[str] | None:
    for name in ("7z", "7zz", "7za"):
        resolved = shutil.which(name)
        if resolved:
            return [resolved]
    if os.name == "nt":
        default_windows_path = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "7-Zip" / "7z.exe"
        if default_windows_path.exists():
            return [str(default_windows_path)]
    return None


def _combine_split_zip_archive(*, download_root: Path, split_parts: tuple[Path, ...], final_zip: Path) -> Path:
    if not final_zip.exists():
        raise RuntimeError(f"Split SlovLex archive final ZIP part was not found: {final_zip}")
    if not split_parts:
        raise RuntimeError("Split SlovLex archive has no split parts to combine.")

    combined_zip = download_root / "export-combined.zip"
    temporary_path = combined_zip.with_suffix(".zip.part")
    with temporary_path.open("wb") as output:
        for path in (*split_parts, final_zip):
            with path.open("rb") as input_file:
                shutil.copyfileobj(input_file, output, length=1024 * 1024)
    temporary_path.replace(combined_zip)
    return combined_zip


def _archive_snapshot_date(state: CollectorImportState | None) -> str | None:
    if state is None:
        return None
    value = state.metadata.get("archive_snapshot_date")
    if isinstance(value, str):
        return value
    return None


def _format_monthly_range(export: SlovLexMonthlyExport | None) -> str:
    if export is None:
        return ""
    return f"{export.range_start}..{export.range_end}"


def _highest_progress_key(progress: CollectorProgress) -> tuple[int, int]:
    if progress.last_processed_law_year is None or progress.last_processed_law_number is None:
        return (progress.next_probe_law_year, max(0, progress.next_probe_law_number - 1))
    return (progress.last_processed_law_year, progress.last_processed_law_number)


def _log_zip(message: str) -> None:
    _LOGGER.info("[laws-collector] zip-import %s", message)


def _to_iso_date(value: str) -> str:
    day, month, year = value.split(".")
    return f"{year}-{month}-{day}"


def _date_from_token(token: str) -> str:
    if re.fullmatch(r"\d{8}", token):
        return f"{token[0:4]}-{token[4:6]}-{token[6:8]}"
    return ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
