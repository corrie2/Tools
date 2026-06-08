"""Generate bidirectional citation links between papers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from paperforge.store import db

logger = logging.getLogger(__name__)


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


def update_cited_papers_index(vault: Path, paper_id: str, conn) -> List[Path]:
    """Update index.md for all papers that this paper cites.

    Returns:
        List of updated index.md paths.
    """
    updated = []
    rows = conn.execute(
        """SELECT p.* FROM citation_edges ce
           JOIN papers p ON p.id = ce.target_paper_id
           WHERE ce.source_paper_id = ?
             AND ce.target_paper_id != ce.source_paper_id""",
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
           WHERE ce.target_paper_id = ?
             AND ce.source_paper_id != ce.target_paper_id""",
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
