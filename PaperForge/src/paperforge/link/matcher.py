"""Three-layer citation matching against the local library."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from paperforge.models.paper import normalize_title, normalize_doi

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of matching a reference against the local library."""
    paper_id: Optional[str] = None
    match_method: Optional[str] = None  # doi | title_fuzzy | title_exact
    confidence: float = 0.0
    status: str = "unmatched"  # confirmed | pending | unmatched


def match_by_doi(doi: str, conn) -> Optional[str]:
    """Try exact DOI match against papers table.

    Args:
        doi: DOI string to match.
        conn: SQLite connection.

    Returns:
        paper_id if found, else None.
    """
    if not doi:
        return None

    doi = normalize_doi(doi)

    row = conn.execute(
        "SELECT id FROM papers WHERE LOWER(doi) = ?",
        (doi,),
    ).fetchone()
    return row["id"] if row else None


def match_by_title(
    title: str,
    year: Optional[int],
    conn,
    auto_threshold: float = 95.0,
    pending_threshold: float = 85.0,
    require_year: bool = True,
) -> Optional[MatchResult]:
    """Fuzzy title match using rapidfuzz.

    Args:
        title: Title to match.
        year: Year of the reference (for validation).
        conn: SQLite connection.
        auto_threshold: Minimum score for auto-confirmation (>= 95).
        pending_threshold: Minimum score for pending status (>= 85).
        require_year: Whether to require year match.

    Returns:
        MatchResult or None if no candidate above pending_threshold.
    """
    if not title:
        return None

    try:
        from rapidfuzz import fuzz
    except ImportError:
        logger.warning("rapidfuzz not installed, skipping title matching")
        return None

    norm_title = normalize_title(title)
    if len(norm_title) < 5:
        return None

    # Normalize year to int (LLM may return str)
    if year is not None:
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = None

    # Get all papers from DB
    rows = conn.execute(
        "SELECT id, normalized_title, year FROM papers WHERE normalized_title IS NOT NULL"
    ).fetchall()

    best_id = None
    best_score = 0.0
    best_year = None

    for row in rows:
        db_title = row["normalized_title"]
        if not db_title:
            continue

        score = fuzz.ratio(norm_title, db_title)
        if score > best_score:
            best_score = score
            best_id = row["id"]
            best_year = row["year"]

    if best_score < pending_threshold:
        return None

    # Year check
    if require_year and year and best_year:
        if year != best_year:
            # Allow +/- 1 year tolerance
            if abs(year - best_year) > 1:
                logger.debug(
                    "Title match but year mismatch: ref_year=%d, db_year=%d, score=%.1f",
                    year, best_year, best_score,
                )
                return None

    result = MatchResult(
        paper_id=best_id,
        match_method="title_fuzzy",
        confidence=best_score / 100.0,
        status="confirmed" if best_score >= auto_threshold else "pending",
    )

    logger.debug(
        "Title match: score=%.1f, method=%s, status=%s",
        best_score, result.match_method, result.status,
    )
    return result


def match_reference(
    ref_dict: dict,
    conn,
    config=None,
) -> MatchResult:
    """Match a structured reference against the local library.

    Uses three-layer matching:
    1. DOI exact match -> confirmed, confidence=1.0
    2. Title fuzzy >= auto_threshold AND year OK -> confirmed
    3. Title fuzzy >= pending_threshold -> pending
    4. Below threshold -> unmatched

    Args:
        ref_dict: Structured reference dict with keys: title, year, doi, ...
        conn: SQLite connection.
        config: CitationConfig (optional).

    Returns:
        MatchResult.
    """
    from paperforge.config import CitationConfig

    if config is None:
        config = CitationConfig()

    doi = ref_dict.get("doi")
    title = ref_dict.get("title", "")
    year = ref_dict.get("year")

    # Layer 1: DOI exact match
    if doi and config.auto_confirm_doi:
        paper_id = match_by_doi(doi, conn)
        if paper_id:
            logger.debug("DOI match found for: %s", doi)
            return MatchResult(
                paper_id=paper_id,
                match_method="doi",
                confidence=1.0,
                status="confirmed",
            )

    # Layer 2: Title fuzzy match
    if title:
        result = match_by_title(
            title=title,
            year=year,
            conn=conn,
            auto_threshold=config.auto_confirm_title_threshold,
            pending_threshold=config.pending_title_threshold,
            require_year=config.require_year_match_for_title,
        )
        if result:
            return result

    # Layer 3: No match
    return MatchResult(status="unmatched")
