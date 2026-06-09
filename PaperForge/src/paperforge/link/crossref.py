"""Crossref API integration for reference enrichment (fallback)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://api.crossref.org"


def _api_get(url: str, timeout: int = 30) -> Optional[dict]:
    """Make a GET request to Crossref API.

    Returns parsed JSON or None on failure.
    """
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "PaperForge/0.1 (mailto:paperforge@example.com)",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.debug("Not found on Crossref: %s", url)
            return None
        elif e.code == 429:
            logger.warning("Crossref rate limited")
            return None
        else:
            logger.error("Crossref HTTP error %d: %s", e.code, url)
            return None
    except Exception as e:
        logger.error("Crossref request failed: %s", e)
        return None


def search_by_title(title: str) -> Optional[dict]:
    """Search Crossref for a paper by title.

    Args:
        title: Paper title to search for.

    Returns:
        Dict with keys: title, authors, year, venue, doi
        or None if not found.
    """
    if not title or len(title.strip()) < 5:
        return None

    encoded = urllib.parse.quote(title.strip())
    url = f"{BASE_URL}/works?query={encoded}&rows=1&select=DOI,title,author,published-print,container-title"

    data = _api_get(url)
    if not data:
        return None

    items = data.get("message", {}).get("items", [])
    if not items:
        return None

    return _normalize_result(items[0])


def get_paper_by_doi(doi: str) -> Optional[dict]:
    """Get paper metadata from Crossref by DOI.

    Args:
        doi: DOI string.

    Returns:
        Dict with keys: title, authors, year, venue, doi
        or None if not found.
    """
    if not doi:
        return None

    # Clean DOI
    from paperforge.models.paper import normalize_doi
    doi = normalize_doi(doi)

    url = f"{BASE_URL}/works/{urllib.parse.quote(doi, safe='')}"

    data = _api_get(url)
    if not data:
        return None

    item = data.get("message", {})
    if not item.get("title"):
        return None

    return _normalize_result(item)


def _normalize_result(item: dict) -> dict:
    """Normalize Crossref API response to standard format."""
    # Extract title (Crossref returns as list)
    title_raw = item.get("title", [])
    title = title_raw[0] if isinstance(title_raw, list) and title_raw else str(title_raw)

    # Extract authors
    authors_raw = item.get("author", [])
    authors = []
    for a in authors_raw:
        name_parts = []
        if a.get("given"):
            name_parts.append(a["given"])
        if a.get("family"):
            name_parts.append(a["family"])
        if name_parts:
            authors.append(" ".join(name_parts))

    # Extract year from published-print or published-online
    year = None
    for date_field in ["published-print", "published-online", "created"]:
        date_info = item.get(date_field, {})
        date_parts = date_info.get("date-parts", [[]])
        if date_parts and date_parts[0] and date_parts[0][0]:
            year = date_parts[0][0]
            break

    # Extract venue/journal
    container = item.get("container-title", [])
    venue = container[0] if isinstance(container, list) and container else str(container)

    # Extract DOI
    doi = item.get("DOI", "")

    return {
        "title": title.strip(),
        "authors": authors,
        "year": year,
        "venue": venue.strip() if venue else "",
        "doi": doi,
        "paperId": "",  # Crossref doesn't have paperId
        "abstract": "",  # Crossref abstracts require special handling
    }
