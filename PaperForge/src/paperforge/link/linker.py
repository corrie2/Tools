"""Generate bidirectional citation links between papers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from paperforge.store import db

logger = logging.getLogger(__name__)


def process_references(
    paper_id: str,
    references: List[dict],
    conn,
    config=None,
) -> dict:
    """Process extracted references: match and create citation edges.

    Args:
        paper_id: Source paper ID.
        references: List of structured reference dicts.
        conn: SQLite connection.
        config: Config object.

    Returns:
        Summary dict with counts: total, confirmed, pending, unmatched.
    """
    from paperforge.link.matcher import match_reference, normalize_title

    stats = {"total": len(references), "confirmed": 0, "pending": 0, "unmatched": 0, "errors": 0}

    for idx, ref in enumerate(references):
        try:
            raw_text = ref.get("_raw", ref.get("title", ""))
            parsed_title = ref.get("title", "")
            parsed_authors = ref.get("authors", [])
            parsed_year = ref.get("year")
            parsed_venue = ref.get("venue")
            parsed_doi = ref.get("doi")
            norm_title = normalize_title(parsed_title) if parsed_title else ""

            # Insert raw reference
            ref_id = uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            import json as _json
            conn.execute(
                """INSERT OR IGNORE INTO references_raw
                   (id, source_paper_id, raw_text, parsed_authors, parsed_title,
                    normalized_title, parsed_year, parsed_venue, parsed_doi,
                    sequence_num, extraction_method, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ref_id, paper_id, raw_text,
                    _json.dumps(parsed_authors) if parsed_authors else None,
                    parsed_title or None,
                    norm_title or None,
                    parsed_year,
                    parsed_venue,
                    parsed_doi,
                    idx + 1,
                    "llm",
                    now,
                ),
            )

            # Try matching
            result = match_reference(ref, conn, config.citation if config else None)

            # Insert candidate
            candidate_id = uuid4().hex
            conn.execute(
                """INSERT INTO reference_candidates
                   (id, source_paper_id, raw_reference_id, title, normalized_title,
                    authors, year, venue, doi, matched_paper_id,
                    match_method, confidence, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    candidate_id, paper_id, ref_id,
                    parsed_title, norm_title,
                    _json.dumps(parsed_authors) if parsed_authors else None,
                    parsed_year, parsed_venue, parsed_doi,
                    result.paper_id,
                    result.match_method,
                    result.confidence,
                    result.status,
                    now, now,
                ),
            )

            # Create citation edge for confirmed matches
            if result.status == "confirmed" and result.paper_id:
                conn.execute(
                    """INSERT OR REPLACE INTO citation_edges
                       (source_paper_id, target_paper_id, raw_reference_id,
                        match_method, confidence, confirmed, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        paper_id, result.paper_id, ref_id,
                        result.match_method, result.confidence, 1,
                        now, now,
                    ),
                )
                stats["confirmed"] += 1
            elif result.status == "pending":
                stats["pending"] += 1
            else:
                stats["unmatched"] += 1

        except Exception as e:
            logger.error("Error processing reference %d: %s", idx, e)
            stats["errors"] += 1

    conn.commit()
    return stats


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
    """
    from paperforge.store.writer import write_index_md

    paper_id = paper["id"]
    year = paper.get("year", 2026)
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


def update_cited_papers_index(vault: Path, paper_id: str, conn) -> List[Path]:
    """Update index.md for all papers that this paper cites.

    Returns:
        List of updated index.md paths.
    """
    updated = []
    rows = conn.execute(
        """SELECT p.* FROM citation_edges ce
           JOIN papers p ON p.id = ce.target_paper_id
           WHERE ce.source_paper_id = ?""",
        (paper_id,),
    ).fetchall()

    for row in rows:
        paper = dict(row)
        try:
            path = update_index_md(vault, paper, conn)
            updated.append(path)
        except Exception as e:
            logger.error("Failed to update index for cited paper %s: %s", paper.get("slug"), e)

    return updated


def update_citing_papers_index(vault: Path, paper_id: str, conn) -> List[Path]:
    """Update index.md for all papers that cite this paper.

    Returns:
        List of updated index.md paths.
    """
    updated = []
    rows = conn.execute(
        """SELECT p.* FROM citation_edges ce
           JOIN papers p ON p.id = ce.source_paper_id
           WHERE ce.target_paper_id = ?""",
        (paper_id,),
    ).fetchall()

    for row in rows:
        paper = dict(row)
        try:
            path = update_index_md(vault, paper, conn)
            updated.append(path)
        except Exception as e:
            logger.error("Failed to update index for citing paper %s: %s", paper.get("slug"), e)

    return updated
