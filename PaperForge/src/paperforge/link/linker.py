"""Generate bidirectional citation links between papers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from uuid import uuid4

from paperforge.models.paper import normalize_title
from paperforge.link.matcher import match_reference

logger = logging.getLogger(__name__)


def process_single_reference(
    conn,
    paper_id: str,
    raw_text: str,
    ref_dict: dict,
    config=None,
    extraction_method: str = "llm",
    sequence_num: int | None = None,
    extra_candidate_fields: dict | None = None,
) -> dict:
    """Process a single reference: insert raw ref, match, insert candidate, create edge.

    Args:
        conn: SQLite connection.
        paper_id: Source paper ID.
        raw_text: Raw reference text.
        ref_dict: Dict with title, year, doi for matching.
        config: CitationConfig for matching thresholds.
        extraction_method: How the reference was extracted (e.g. "llm", "relink").
        sequence_num: Reference sequence number.
        extra_candidate_fields: Additional fields for the candidate row.

    Returns:
        Dict with keys: ref_id, candidate_id, match_result, status.
    """
    from paperforge.store import db as store_db

    now = datetime.now(timezone.utc).isoformat()
    ref_id = uuid4().hex
    parsed_title = ref_dict.get("title", "")
    parsed_authors = ref_dict.get("authors", [])
    parsed_year = ref_dict.get("year")
    parsed_venue = ref_dict.get("venue")
    parsed_doi = ref_dict.get("doi")
    norm_title = normalize_title(parsed_title) if parsed_title else ""

    # Insert raw reference
    store_db.insert_reference_raw(conn, {
        "id": ref_id,
        "source_paper_id": paper_id,
        "raw_text": raw_text,
        "parsed_authors": json.dumps(parsed_authors) if parsed_authors else None,
        "parsed_title": parsed_title or None,
        "normalized_title": norm_title or None,
        "parsed_year": parsed_year,
        "parsed_venue": parsed_venue,
        "parsed_doi": parsed_doi,
        "sequence_num": sequence_num,
        "extraction_method": extraction_method,
        "created_at": now,
    })

    # Match
    result = match_reference(ref_dict, conn, config)

    # Build candidate data
    candidate_data = {
        "id": uuid4().hex,
        "source_paper_id": paper_id,
        "raw_reference_id": ref_id,
        "title": parsed_title,
        "normalized_title": norm_title,
        "match_method": result.match_method,
        "confidence": result.confidence,
        "status": result.status,
        "created_at": now,
        "updated_at": now,
    }
    if parsed_authors:
        candidate_data["authors"] = json.dumps(parsed_authors)
    if parsed_year:
        candidate_data["year"] = parsed_year
    if parsed_venue:
        candidate_data["venue"] = parsed_venue
    if parsed_doi:
        candidate_data["doi"] = parsed_doi
    if result.paper_id:
        candidate_data["matched_paper_id"] = result.paper_id
    if extra_candidate_fields:
        candidate_data.update(extra_candidate_fields)

    store_db.insert_reference_candidate(conn, candidate_data)

    # Create edge for confirmed
    if result.status == "confirmed" and result.paper_id:
        store_db.insert_citation_edge(
            conn, paper_id, result.paper_id,
            match_method=result.match_method,
            confidence=result.confidence,
            raw_reference_id=ref_id,
        )

    return {
        "ref_id": ref_id,
        "candidate_id": candidate_data["id"],
        "match_result": result,
        "status": result.status,
    }


def generate_citation_section(paper_id: str, conn) -> dict:
    """Query citation edges for a paper.

    Returns:
        {
            "citing_papers": [{"paper_id", "slug", "title", "confidence", "method"}],
            "cited_by_papers": [{"paper_id", "slug", "title"}],
            "pending_refs": [{"title", "year", "confidence", "candidate_id"}],
        }
    """
    result = {
        "citing_papers": [],
        "cited_by_papers": [],
        "pending_refs": [],
    }

    # Papers that this paper CITES (source -> target)
    rows = conn.execute(
        """SELECT ce.target_paper_id, ce.confidence, ce.match_method,
                  p.slug, p.title
           FROM citation_edges ce
           JOIN papers p ON p.id = ce.target_paper_id
           WHERE ce.source_paper_id = ?
           ORDER BY ce.confidence DESC""",
        (paper_id,),
    ).fetchall()
    for r in rows:
        result["citing_papers"].append({
            "paper_id": r["target_paper_id"],
            "slug": r["slug"],
            "title": r["title"],
            "confidence": round(r["confidence"], 2) if r["confidence"] else 0,
            "method": r["match_method"],
        })

    # Papers that CITE this paper (target -> source)
    rows = conn.execute(
        """SELECT ce.source_paper_id, p.slug, p.title
           FROM citation_edges ce
           JOIN papers p ON p.id = ce.source_paper_id
           WHERE ce.target_paper_id = ?
           ORDER BY p.year DESC""",
        (paper_id,),
    ).fetchall()
    for r in rows:
        result["cited_by_papers"].append({
            "paper_id": r["source_paper_id"],
            "slug": r["slug"],
            "title": r["title"],
        })

    # Pending references
    rows = conn.execute(
        """SELECT rc.id, rc.title, rc.year, rc.confidence
           FROM reference_candidates rc
           WHERE rc.source_paper_id = ? AND rc.status = 'pending'
           ORDER BY rc.confidence DESC""",
        (paper_id,),
    ).fetchall()
    for r in rows:
        result["pending_refs"].append({
            "title": r["title"] or "Unknown",
            "year": r["year"],
            "confidence": round(r["confidence"], 2) if r["confidence"] else 0,
            "candidate_id": r["id"],
        })

    return result


def update_index_md(vault: Path, paper: dict, conn) -> Path:
    """Regenerate index.md with citation sections for a paper.

    Args:
        vault: Vault root path.
        paper: Paper dict.
        conn: SQLite connection.

    Returns:
        Path to updated index.md.

    Note: pending_review.md rendering is not yet implemented.
          Low-confidence references are shown in the pending_refs section of index.md.
    """
    from paperforge.store.writer import write_index_md

    paper_id = paper["id"]
    year = paper.get("year") or "unknown"
    slug = paper["slug"]

    citation_data = generate_citation_section(paper_id, conn)

    path = write_index_md(
        vault=vault,
        year=year,
        slug=slug,
        paper=paper,
        citing_papers=citation_data["citing_papers"],
        cited_by_papers=citation_data["cited_by_papers"],
        pending_refs=citation_data["pending_refs"],
    )
    return path


def _update_related_papers_index(vault: Path, paper_id: str, conn, direction: str) -> List[Path]:
    """Update index.md for papers related to this paper via citations.

    Args:
        direction: "cited" = papers this paper cites (target),
                   "citing" = papers that cite this paper (source).
    """
    if direction == "cited":
        join_col = "target_paper_id"
        where_col = "source_paper_id"
    else:
        join_col = "source_paper_id"
        where_col = "target_paper_id"

    updated = []
    rows = conn.execute(
        f"""SELECT p.* FROM citation_edges ce
           JOIN papers p ON p.id = ce.{join_col}
           WHERE ce.{where_col} = ?
             AND ce.source_paper_id != ce.target_paper_id""",
        (paper_id,),
    ).fetchall()

    for row in rows:
        paper = dict(row)
        try:
            path = update_index_md(vault, paper, conn)
            updated.append(path)
        except Exception as e:
            logger.error("Failed to update index for %s paper %s: %s", direction, paper.get("slug"), e)

    return updated


def update_cited_papers_index(vault: Path, paper_id: str, conn) -> List[Path]:
    """Update index.md for all papers that this paper cites."""
    return _update_related_papers_index(vault, paper_id, conn, "cited")


def update_citing_papers_index(vault: Path, paper_id: str, conn) -> List[Path]:
    """Update index.md for all papers that cite this paper."""
    return _update_related_papers_index(vault, paper_id, conn, "citing")
