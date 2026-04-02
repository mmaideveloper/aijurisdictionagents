from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from io import BytesIO
from pathlib import PurePosixPath
import re
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from pypdf import PdfReader

from .domain import LawSnapshot, ProvisionRecord
from .import_planner import ImportTarget

_STATIC_ROOT = "https://static.slov-lex.sk"
_PUBLIC_ROOT = "https://www.slov-lex.sk"
_REQUEST_HEADERS = {"User-Agent": "aijurisdictionagents-slovlex-loader/1.0"}
_META_ROW_PATTERN = re.compile(
    r'<tr><td class="title(?:_po)?">(.*?)</td><td class="value(?:_bold)?">(.*?)</td></tr>',
    re.IGNORECASE | re.DOTALL,
)
_HISTORY_ROW_PATTERN = re.compile(
    r'<tr class="effectivenessHistoryItem"[^>]*data-iri="([^"]+)"[^>]*data-vyhlasene="([^"]+)"'
    r'[^>]*data-ucinnostod="([^"]*)"[^>]*data-ucinnostdo="([^"]*)"',
    re.IGNORECASE | re.DOTALL,
)
_TEXT_BLOCK_PATTERN = re.compile(
    r'<div class="text" id="([^"]+)">(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_H1_PATTERN = re.compile(r"<h1>(.*?)</h1>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class FetchedResource:
    url: str
    body: bytes
    etag: str
    last_modified: str

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="ignore")


@dataclass(frozen=True)
class SlovLexHistoryItem:
    token: str
    effective_from: str | None
    effective_to: str | None
    is_published: bool


class SlovLexLiveSnapshotLoader:
    def load_snapshot(self, *, target: ImportTarget, timeout_seconds: float = 12.0) -> LawSnapshot:
        published_html_url = (
            f"{_STATIC_ROOT}/static/{target.target_country_code}/ZZ/{target.year}/{target.number}/vyhlasene_znenie.html"
        )
        published_html = _fetch_resource(url=published_html_url, timeout_seconds=timeout_seconds)
        metadata = _parse_metadata(published_html.text)
        history = _parse_history(published_html.text)

        effective_entry = next((item for item in history if not item.is_published and item.effective_from), None)
        version_token = effective_entry.token if effective_entry else "vyhlasene_znenie"
        html_url = (
            published_html_url
            if version_token == "vyhlasene_znenie"
            else f"{_STATIC_ROOT}/static/{target.target_country_code}/ZZ/{target.year}/{target.number}/{version_token}.html"
        )
        effective_html = (
            published_html
            if html_url == published_html_url
            else _fetch_resource(url=html_url, timeout_seconds=timeout_seconds)
        )

        pdf_url = _parse_pdf_url(
            html=published_html.text,
            year=target.year,
            number=target.number,
        )
        pdf_resource = _fetch_resource(url=pdf_url, timeout_seconds=timeout_seconds)

        provisions = _parse_provisions(effective_html.text)
        text_content = "\n\n".join(record.text for record in provisions if record.text).strip()
        if not text_content:
            text_content = _extract_pdf_text(pdf_resource.body)

        official_name = metadata.get("nazov", "").strip()
        if not official_name:
            official_name = _parse_h1(effective_html.text) or target.law_id

        publication_date = _normalize_date_value(metadata.get("datum vyhlasenia", ""))
        effective_from = (
            effective_entry.effective_from
            if effective_entry and effective_entry.effective_from
            else publication_date
        )

        return LawSnapshot(
            source_system="slov-lex",
            country_code=target.target_country_code,
            collection_code="ZZ",
            year=target.year,
            number=target.number,
            official_name=official_name,
            lawyer_title=official_name,
            publication_date=publication_date,
            effective_from=effective_from,
            version_token=version_token,
            source_url=target.url,
            html_url=html_url,
            pdf_url=pdf_url,
            html_content=text_content,
            pdf_content=pdf_resource.body,
            provisions=provisions,
            http_etag=effective_html.etag or pdf_resource.etag,
            http_last_modified=effective_html.last_modified or pdf_resource.last_modified,
        )


def _fetch_resource(*, url: str, timeout_seconds: float) -> FetchedResource:
    request = Request(url, headers=_REQUEST_HEADERS)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - controlled HTTPS URL
            return FetchedResource(
                url=url,
                body=response.read(),
                etag=response.headers.get("ETag", "").strip(),
                last_modified=response.headers.get("Last-Modified", "").strip(),
            )
    except HTTPError as exc:
        raise RuntimeError(f"SlovLex fetch failed for {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"SlovLex fetch failed for {url}: {exc}") from exc


def _parse_metadata(html: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for raw_title, raw_value in _META_ROW_PATTERN.findall(html):
        label = _normalize_label(_strip_tags(raw_title))
        value = _normalize_whitespace(_strip_tags(raw_value))
        if label and value and label not in metadata:
            metadata[label] = value
    return metadata


def _parse_history(html: str) -> list[SlovLexHistoryItem]:
    history: list[SlovLexHistoryItem] = []
    for iri, is_published, effective_from, effective_to in _HISTORY_ROW_PATTERN.findall(html):
        history.append(
            SlovLexHistoryItem(
                token=PurePosixPath(iri).name,
                effective_from=effective_from or None,
                effective_to=effective_to or None,
                is_published=is_published == "1",
            )
        )
    return history


def _parse_provisions(html: str) -> tuple[ProvisionRecord, ...]:
    provisions: list[ProvisionRecord] = []
    for anchor, raw_text in _TEXT_BLOCK_PATTERN.findall(html):
        text = _normalize_whitespace(_strip_tags(raw_text))
        if text:
            provisions.append(ProvisionRecord(anchor=anchor, heading="", text=text))
    return tuple(provisions)


def _parse_pdf_url(*, html: str, year: int, number: int) -> str:
    preferred_relative = f"/static/pdf/SK/ZZ/{year}/{number}/ZZ_{year}_{number}.pdf"
    if preferred_relative in html:
        return _normalize_pdf_url(preferred_relative)

    matches = re.findall(r'href="([^"]*?/static/pdf/[^"]+\.pdf)"', html, re.IGNORECASE)
    if not matches:
        raise RuntimeError(f"No PDF link found for SlovLex law {number}/{year}.")
    return _normalize_pdf_url(matches[0])


def _extract_pdf_text(pdf_content: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_content))
    parts = [page.extract_text() or "" for page in reader.pages]
    return _normalize_whitespace("\n\n".join(parts))


def _parse_h1(html: str) -> str | None:
    match = _H1_PATTERN.search(html)
    if not match:
        return None
    value = _normalize_whitespace(_strip_tags(match.group(1)))
    return value or None


def _strip_tags(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value, flags=re.DOTALL)
    return unescape(without_tags)


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    return _normalize_whitespace(ascii_only).strip(": ").lower()


def _normalize_date_value(value: str) -> str:
    cleaned = _normalize_whitespace(value)
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", cleaned)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return cleaned


def _normalize_pdf_url(relative_url: str) -> str:
    if relative_url.startswith("/static/pdf/"):
        return urljoin(_STATIC_ROOT, relative_url[len("/static") :])
    return urljoin(_PUBLIC_ROOT, relative_url)
