"""Semantic Scholar API integration for reference enrichment."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://api.semanticscholar.org/graph/v1"

# Rate limiting: 100 requests per 5 minutes (no API key)
# With API key: 1 request per second
_last_request_time = 0.0
_min_interval = 3.0  # 3 seconds between requests (conservative for no API key)


def _rate_limit():
    """Simple rate limiter."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _min_interval:
        time.sleep(_min_interval - elapsed)
    _last_request_time = time.time()


def _api_get(url: str, timeout: int = 30) -> Optional[dict]:
    """Make a GET request to Semantic Scholar API.

    Returns parsed JSON or None on failure.
    """
    _rate_limit()

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            logger.warning("Semantic Scholar rate limited, waiting 60s...")
            time.sleep(60)
            # Retry once
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e2:
                logger.error("Semantic Scholar retry failed: %s", e2)
                return None
        elif e.code == 404:
            logger.debug("Not found on Semantic Scholar: %s", url)
            return None
        else:
            logger.error("Semantic Scholar HTTP error %d: %s", e.code, url)
            return None
    except Exception as e:
        logger.error("Semantic Scholar request failed: %s", e)
        return None


def search_by_title(title: str) -> Optional[dict]:
    """Search Semantic Scholar for a paper by title.

    Args:
        title: Paper title to search for.

    Returns:
        Dict with keys: title, authors, year, venue, doi, paperId
        or None if not found.
    """
    if not title or len(title.strip()) < 5:
        return None

    encoded = urllib.parse.quote(title.strip())
    fields = "title,authors,year,venue,externalIds,paperId"
    url = f"{BASE_URL}/paper/search?query={encoded}&limit=1&fields={fields}"

    data = _api_get(url)
    if not data:
        return None

    papers = data.get("data", [])
    if not papers:
        return None

    paper = papers[0]
    return _normalize_result(paper)


def get_paper_by_doi(doi: str) -> Optional[dict]:
    """Get paper metadata from Semantic Scholar by DOI.

    Args:
        doi: DOI string.

    Returns:
        Dict with keys: title, authors, year, venue, doi, paperId
        or None if not found.
    """
    if not doi:
        return None

    # Clean DOI
    import re
    doi = re.sub(r"^(https?://doi\.org/|https?://dx\.doi\.org/|doi:)\s*", "", doi, flags=re.IGNORECASE)
    doi = doi.strip()

    fields = "title,authors,year,venue,externalIds,paperId"
    url = f"{BASE_URL}/paper/DOI:{doi}?fields={fields}"

    data = _api_get(url)
    if not data:
        return None

    return _normalize_result(data)


def get_references(paper_id: str) -> List[dict]:
    """Get references of a paper from Semantic Scholar.

    Args:
        paper_id: Semantic Scholar paper ID.

    Returns:
        List of dicts with keys: title, authors, year, venue, doi, paperId
    """
    fields = "title,authors,year,venue,externalIds,paperId"
    url = f"{BASE_URL}/paper/{paper_id}/references?fields={fields}&limit=100"

    data = _api_get(url)
    if not data:
        return []

    results = []
    for ref in data.get("data", []):
        cited_paper = ref.get("citedPaper")
        if cited_paper and cited_paper.get("title"):
            results.append(_normalize_result(cited_paper))

    return results


def _normalize_result(paper: dict) -> dict:
    """Normalize Semantic Scholar API response to standard format."""
    ext_ids = paper.get("externalIds", {}) or {}
    authors_raw = paper.get("authors", []) or []

    return {
        "title": paper.get("title", ""),
        "authors": [a.get("name", "") for a in authors_raw if a.get("name")],
        "year": paper.get("year"),
        "venue": paper.get("venue", "") or "",
        "doi": ext_ids.get("DOI"),
        "paperId": paper.get("paperId", ""),
        "abstract": paper.get("abstract", "") or "",
    }


def enrich_metadata(
    doi: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[dict]:
    """Try to enrich paper metadata via Semantic Scholar, with Crossref fallback.

    Strategy:
    1. If DOI provided, query S2 by DOI (most reliable)
    2. If no DOI or DOI not found, query S2 by title
    3. If S2 fails (429, etc.), fall back to Crossref

    Returns normalized dict or None.
    """
    # Try Semantic Scholar first
    s2_result = _try_semantic_scholar(doi, title)
    if s2_result:
        return s2_result

    # Fall back to Crossref
    logger.info("Semantic Scholar unavailable, trying Crossref fallback...")
    return _try_crossref(doi, title)


def _try_semantic_scholar(
    doi: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[dict]:
    """Try Semantic Scholar API."""
    # Try DOI first
    if doi:
        result = get_paper_by_doi(doi)
        if result and result.get("title"):
            logger.info("Semantic Scholar found by DOI: %s", result.get("title"))
            return result

    # Try title
    if title and len(title.strip()) > 5:
        result = search_by_title(title)
        if result and result.get("title"):
            logger.info("Semantic Scholar found by title: %s", result.get("title"))
            return result

    return None


def _try_crossref(
    doi: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[dict]:
    """Try Crossref API as fallback."""
    from paperforge.link.crossref import get_paper_by_doi as crossref_by_doi
    from paperforge.link.crossref import search_by_title as crossref_by_title

    # Try DOI first
    if doi:
        result = crossref_by_doi(doi)
        if result and result.get("title"):
            logger.info("Crossref found by DOI: %s", result.get("title"))
            return result

    # Try title
    if title and len(title.strip()) > 5:
        result = crossref_by_title(title)
        if result and result.get("title"):
            logger.info("Crossref found by title: %s", result.get("title"))
            return result

    return None


def resolve_reference_doi(title: str) -> Optional[str]:
    """Try to find DOI for a reference by searching Semantic Scholar by title.

    Returns DOI string or None.
    """
    if not title or len(title.strip()) < 10:
        return None

    result = search_by_title(title)
    if result and result.get("doi"):
        return result["doi"]
    return None
