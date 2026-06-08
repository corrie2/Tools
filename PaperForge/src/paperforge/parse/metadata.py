"""Metadata extraction from PDF — title, authors, DOI, language."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from langdetect import detect as _detect_lang
except ImportError:
    _detect_lang = None


DOI_RE = re.compile(r"(10\.\d{4,}/[^\s,;\\\]]+)")


def compute_pdf_sha256(pdf_path: Path) -> str:
    """Compute SHA-256 hash of a PDF file."""
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_doi(text: str) -> Optional[str]:
    """Extract DOI from text using regex."""
    match = DOI_RE.search(text)
    if match:
        doi = match.group(1).rstrip(".,;)]:")
        return doi
    return None


def detect_language(text: str) -> str:
    """Detect language of text, returns 'en', 'zh', or 'unknown'."""
    if not text or len(text.strip()) < 20:
        return "unknown"
    if _detect_lang is None:
        return "unknown"
    try:
        lang = _detect_lang(text[:2000])
        if lang.startswith("zh"):
            return "zh"
        elif lang.startswith("en"):
            return "en"
        return lang
    except Exception:
        return "unknown"


_HEADER_NOISE = re.compile(
    r"^(arXiv|arxiv|PREPRINT|Preprint|preprint|CORR|CoRR|corr|"
    r"IEEE|ACM|Proceedings|PROCEEDINGS|Journal|JOURNAL|"
    r"Volume|VOLUME|vol\.|No\.|Number|"
    r"Accepted|Submitted|Published|Manuscript|"
    r"\d{4}\s*(IEEE|ACM|Springer|Elsevier)|"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}|"
    r"©\s*\d{4}|"
    r"DOI|doi|https?://|www\.)",
    re.IGNORECASE,
)


def extract_title_from_pdf(pdf_path: Path) -> Optional[str]:
    """Extract title from first page using heuristic: largest font text block.

    Filters out common arXiv headers, journal headers, and other noise.
    """
    if fitz is None:
        return None
    try:
        doc = fitz.open(str(pdf_path))
        if doc.page_count == 0:
            return None
        page = doc[0]
        blocks = page.get_text("dict")["blocks"]
        # Find text blocks with largest font size
        candidates = []
        for block in blocks:
            if block.get("type") != 0:  # text block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    size = span.get("size", 0)
                    if text and len(text) > 3:
                        candidates.append((text, size))
        if not candidates:
            return None
        # Group by font size (within 0.5 tolerance) and pick the largest group
        candidates.sort(key=lambda x: -x[1])
        max_size = candidates[0][1]
        title_parts = []
        for text, size in candidates:
            if abs(size - max_size) < 0.5:
                title_parts.append(text)
            else:
                break
        # Filter out header noise from title parts
        filtered_parts = []
        for part in title_parts:
            if not _HEADER_NOISE.match(part.strip()):
                filtered_parts.append(part)
        # If all parts were noise, try without filtering
        if not filtered_parts:
            filtered_parts = title_parts
        title = " ".join(filtered_parts)
        # Clean up
        title = re.sub(r"\s+", " ", title).strip()
        return title if len(title) > 3 else None
    except Exception:
        return None


def _strip_affiliation_numbers(text: str) -> str:
    """Strip superscript numbers used for affiliations (e.g., 'Alice 1,2 Bob 3' -> 'Alice Bob')."""
    # Remove numbers/comma-separated digits at word boundaries that look like affiliation markers
    # Pattern: space followed by digits (possibly comma-separated) before comma/space/and/end
    text = re.sub(r"\s+[\d]+(?:,[\d]+)*(?=\s*[,;&]|\s+and\s+|\s+[A-Z]|\s*$)", "", text)
    # Also remove leading digits like "1 Department of..."
    text = re.sub(r"^\d[\d,*]+\s+", "", text)
    return text


def extract_authors_from_pdf(pdf_path: Path, title: Optional[str] = None) -> list:
    """Extract authors from first page — heuristic: text block just below the title.

    Strips affiliation numbers and common artifacts.
    """
    if fitz is None:
        return []
    try:
        doc = fitz.open(str(pdf_path))
        if doc.page_count == 0:
            return []
        page = doc[0]
        blocks = page.get_text("dict")["blocks"]
        text_blocks = []
        for block in blocks:
            if block.get("type") != 0:
                continue
            text = ""
            max_size = 0
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text += span.get("text", "")
                    max_size = max(max_size, span.get("size", 0))
            text = text.strip()
            if text:
                text_blocks.append({"text": text, "size": max_size, "bbox": block.get("bbox", (0, 0, 0, 0))})
        if len(text_blocks) < 2:
            return []
        # Sort by vertical position (bbox[1])
        text_blocks.sort(key=lambda b: b["bbox"][1])
        # The first large text is title; the next block is likely authors
        if text_blocks[0]["size"] > text_blocks[1]["size"]:
            author_text = text_blocks[1]["text"]
            # Strip affiliation numbers
            author_text = _strip_affiliation_numbers(author_text)
            # Split by comma or "and"
            parts = re.split(r",\s*|\s+and\s+", author_text)
            # Clean each author name
            authors = []
            for p in parts:
                name = re.sub(r"\d+", "", p).strip()
                name = re.sub(r"\s+", " ", name).strip()
                if name and len(name) > 1:
                    # Skip things that look like affiliations/emails
                    if "@" not in name and not name.startswith("(") and not name.startswith("*"):
                        authors.append(name)
            return authors
        return []
    except Exception:
        return []


def extract_metadata(pdf_path: Path, sha256: Optional[str] = None) -> dict:
    """Extract all metadata from a PDF file.

    Returns dict with: title, authors, doi, language, sha256, year
    """
    if sha256 is None:
        sha256 = compute_pdf_sha256(pdf_path)
    title = extract_title_from_pdf(pdf_path)
    authors = extract_authors_from_pdf(pdf_path, title=title)
    doi = None
    language = "unknown"
    year = None

    # Try to extract DOI and detect language from first few pages
    if fitz is not None:
        try:
            doc = fitz.open(str(pdf_path))
            text = ""
            for i in range(min(3, doc.page_count)):
                text += doc[i].get_text()
            doi = extract_doi(text)
            language = detect_language(text)

            # Extract year from PDF metadata dates
            pdf_meta = doc.metadata or {}
            for date_field in ('creationDate', 'modDate'):
                raw_date = pdf_meta.get(date_field, '') or ''
                if len(raw_date) >= 4:
                    m = re.search(r'(\d{4})', raw_date)
                    if m:
                        candidate = int(m.group(1))
                        if 1900 <= candidate <= 2099:
                            year = candidate
                            break

            # Fallback: look for year near title on first page
            if year is None and doc.page_count > 0:
                first_page_text = doc[0].get_text()[:500]
                year_matches = re.findall(r'\b(19\d{2}|20\d{2})\b', first_page_text)
                if year_matches:
                    for ym in year_matches:
                        candidate = int(ym)
                        if 1960 <= candidate <= 2099:
                            year = candidate
                            break
        except Exception:
            pass

    return {
        "title": title or "",
        "authors": authors,
        "doi": doi,
        "language": language,
        "sha256": sha256,
        "year": year,
    }
