"""Bounded parsers for untrusted case uploads; no network or embedded execution."""
from __future__ import annotations

import importlib
import io
import zipfile
from typing import Any
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_IMAGE_PIXELS = 25_000_000
MAX_XML_BYTES = 40 * 1024 * 1024
TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv", ".html", ".xml"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def validate_upload(filename: str, payload: bytes) -> None:
    if not payload or len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("Upload must contain between 1 byte and 20 MiB.")
    suffix = Path(filename).suffix.lower()
    try:
        if suffix in TEXT_SUFFIXES:
            text = payload.decode("utf-8-sig")
            if "\x00" in text:
                raise ValueError("Binary content is not a text document.")
        elif suffix == ".docx":
            _word_xml(payload)
        elif suffix == ".pdf":
            from pypdf import PdfReader
            if not payload.startswith(b"%PDF-"):
                raise ValueError("Invalid PDF signature.")
            reader = PdfReader(io.BytesIO(payload))
            if reader.is_encrypted:
                raise ValueError("Password-protected PDFs are unsupported. Upload an unlocked copy.")
            if not 0 < len(reader.pages) <= MAX_PDF_PAGES:
                raise ValueError("PDF must contain 1 to 20 pages.")
        elif suffix in IMAGE_SUFFIXES:
            from PIL import Image
            with Image.open(io.BytesIO(payload)) as image:
                expected = "PNG" if suffix == ".png" else "JPEG"
                if image.format != expected or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image format mismatch or image exceeds 25 million pixels.")
                image.verify()
        else:
            raise ValueError("Unsupported format. Use PDF, DOCX, JPG, PNG or UTF-8 text.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Document is corrupt or cannot be read safely.") from exc


def _word_xml(payload: bytes) -> ET.Element:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if len(archive.infolist()) > 2000:
            raise ValueError("DOCX contains too many entries.")
        if sum(item.file_size for item in archive.infolist()) > MAX_XML_BYTES:
            raise ValueError("Expanded DOCX exceeds 40 MiB.")
        xml = archive.read("word/document.xml")
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("Document XML declarations are unsupported.")
    return ET.fromstring(xml)


def extract_docx(payload: bytes) -> str:
    root = _word_xml(payload)
    # XML document order preserves paragraphs inside table cells as well as prose.
    paragraphs = []
    for paragraph in root.iter(WORD_NS + "p"):
        value = "".join(
            element.text or "" if element.tag == WORD_NS + "t" else
            "\t" if element.tag == WORD_NS + "tab" else "\n"
            for element in paragraph.iter()
            if element.tag in {WORD_NS + "t", WORD_NS + "tab", WORD_NS + "br"}
        )
        paragraphs.append(value)
    return "\n\n".join(paragraphs).strip()


def extract_image(payload: bytes) -> str:
    from PIL import Image, ImageOps
    engine = importlib.import_module("rapidocr").RapidOCR()
    with Image.open(io.BytesIO(payload)) as image:
        return recognize_image(ImageOps.exif_transpose(image).convert("RGB"), engine)


def recognize_image(image: Any, engine: Any) -> str:
    np = importlib.import_module("numpy")
    array = np.array(image)
    # The orientation classifier can incorrectly rotate upright Slovak § lines.
    # Prefer the original orientation; compare confidence before using rotation.
    result = engine(array, use_cls=False, text_score=0.0)
    scores = list(getattr(result, "scores", None) or [])
    if scores and min(scores) < 0.85:
        rotated = engine(array, use_cls=True, text_score=0.0)
        alternate = list(getattr(rotated, "scores", None) or [])
        if len(alternate) == len(scores) and sum(alternate) > sum(scores):
            result, scores = rotated, alternate
    lines = list(getattr(result, "txts", None) or [])
    return "\n".join(("[NEISTÉ OCR – skontrolujte originál] " if index < len(scores) and scores[index] < 0.85 else "") + str(line)
                     for index, line in enumerate(lines))
