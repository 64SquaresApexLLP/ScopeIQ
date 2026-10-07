"""Text-layer PDF reading (RFDS and MA/SA exports have real text). Uses pypdf's layout mode so table columns
stay separated by runs of spaces; scanned / vector-outline PDFs go through extract/ocr.py instead."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from scopeiq.common.errors import ExtractionError


def pdf_pages_text(path: Path) -> list[str]:
    try:
        reader = PdfReader(str(path))
        return [p.extract_text(extraction_mode="layout") or "" for p in reader.pages]
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"PDF {Path(path).name} could not be opened: {exc}", cause=exc) from exc


def has_text_layer(path: Path, min_chars: int = 40) -> bool:
    return sum(len(t.strip()) for t in pdf_pages_text(path)) >= min_chars
