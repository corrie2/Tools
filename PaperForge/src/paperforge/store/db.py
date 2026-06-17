"""SQLite database initialization and CRUD operations."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    normalized_title TEXT,
    authors TEXT,
    year INTEGER,
    venue TEXT,
    doi TEXT UNIQUE,
    language TEXT,
    pdf_path TEXT,
    pdf_sha256 TEXT,
    vault_path TEXT,
    paper_dir TEXT,
    parser TEXT,
    parse_quality TEXT,
    fallback_used INTEGER DEFAULT 0,
    processed_at TEXT,
    updated_at TEXT,
    status TEXT DEFAULT 'completed',
    external_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_papers_slug ON papers(slug);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_pdf_sha256 ON papers(pdf_sha256);
CREATE INDEX IF NOT EXISTS idx_papers_normalized_title ON papers(normalized_title);
CREATE INDEX IF NOT EXISTS idx_papers_external_id ON papers(external_id);

CREATE TABLE IF NOT EXISTS paper_tasks (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    input_hash TEXT,
    output_path TEXT,
    error TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_paper ON paper_tasks(paper_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON paper_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_type ON paper_tasks(task_type);

CREATE TABLE IF NOT EXISTS references_raw (
    id TEXT PRIMARY KEY,
    source_paper_id TEXT NOT NULL REFERENCES papers(id),
    raw_text TEXT NOT NULL,
    parsed_authors TEXT,
    parsed_title TEXT,
    normalized_title TEXT,
    parsed_year INTEGER,
    parsed_venue TEXT,
    parsed_doi TEXT,
    sequence_num INTEGER,
    extraction_method TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_refs_source ON references_raw(source_paper_id);
CREATE INDEX IF NOT EXISTS idx_refs_doi ON references_raw(parsed_doi);
CREATE INDEX IF NOT EXISTS idx_refs_normalized_title ON references_raw(normalized_title);

CREATE TABLE IF NOT EXISTS reference_candidates (
    id TEXT PRIMARY KEY,
    source_paper_id TEXT NOT NULL REFERENCES papers(id),
    raw_reference_id TEXT NOT NULL REFERENCES references_raw(id),
    title TEXT,
    normalized_title TEXT,
    authors TEXT,
    year INTEGER,
    venue TEXT,
    doi TEXT,
    external_id TEXT,
    matched_paper_id TEXT REFERENCES papers(id),
    match_method TEXT,
    confidence REAL,
    status TEXT DEFAULT 'unmatched',
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_candidates_source ON reference_candidates(source_paper_id);
CREATE INDEX IF NOT EXISTS idx_candidates_doi ON reference_candidates(doi);
CREATE INDEX IF NOT EXISTS idx_candidates_matched ON reference_candidates(matched_paper_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON reference_candidates(status);

CREATE TABLE IF NOT EXISTS citation_edges (
    source_paper_id TEXT NOT NULL REFERENCES papers(id),
    target_paper_id TEXT NOT NULL REFERENCES papers(id),
    raw_reference_id TEXT REFERENCES references_raw(id),
    match_method TEXT,
    confidence REAL,
    confirmed INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    PRIMARY KEY (source_paper_id, target_paper_id)
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON citation_edges(source_paper_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON citation_edges(target_paper_id);
CREATE INDEX IF NOT EXISTS idx_edges_confirmed ON citation_edges(confirmed);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Get a SQLite connection, creating parent dirs and tables if needed."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize database with schema."""
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


# --- Paper CRUD ---

# Valid column names for each table (used for SQL injection prevention)
_VALID_COLUMNS = {
    "papers": {
        "id", "slug", "title", "normalized_title", "authors", "year", "venue",
        "doi", "language", "pdf_path", "pdf_sha256", "vault_path", "paper_dir",
        "parser", "parse_quality", "fallback_used", "processed_at", "updated_at",
        "status", "external_id",
    },
    "references_raw": {
        "id", "source_paper_id", "raw_text", "parsed_authors", "parsed_title",
        "normalized_title", "parsed_year", "parsed_venue", "parsed_doi",
        "sequence_num", "extraction_method", "created_at",
    },
    "reference_candidates": {
        "id", "source_paper_id", "raw_reference_id", "title", "normalized_title",
        "authors", "year", "venue", "doi", "external_id", "matched_paper_id",
        "match_method", "confidence", "status", "created_at", "updated_at",
    },
}


def _validate_columns(data: dict, table: str) -> dict:
    """Filter dict to only include valid columns for the given table."""
    valid = _VALID_COLUMNS.get(table)
    if valid is None:
        return data  # No validation defined
    return {k: v for k, v in data.items() if k in valid}


_ALLOWED_TABLES = frozenset({
    'papers', 'paper_tasks', 'references_raw', 'reference_candidates', 'citation_edges',
})


def _insert_record(conn: sqlite3.Connection, table: str, data: dict, or_ignore: bool = True, or_replace: bool = False) -> None:
    """Insert a record into any table with column validation."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f'Invalid table: {table}')
    data = _validate_columns(data, table)
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    if or_replace:
        conflict = "OR REPLACE"
    elif or_ignore:
        conflict = "OR IGNORE"
    else:
        conflict = ""
    sql = f"INSERT {conflict} INTO {table} ({cols}) VALUES ({placeholders})"
    conn.execute(sql, list(data.values()))
    conn.commit()


def insert_paper(conn: sqlite3.Connection, paper: dict) -> None:
    """Insert a paper record. authors should be a list, will be JSON-serialized."""
    authors = paper.get("authors", [])
    if isinstance(authors, list):
        authors = json.dumps(authors)
    paper = {**paper, "authors": authors}
    now = datetime.now(timezone.utc).isoformat()
    paper.setdefault("processed_at", now)
    paper.setdefault("updated_at", now)
    _insert_record(conn, "papers", paper, or_ignore=False, or_replace=True)


def _get_paper_by(conn: sqlite3.Connection, column: str, value) -> Optional[dict]:
    """Look up a paper by a single column value."""
    # Validate column name to prevent SQL injection
    allowed = {"id", "slug", "doi", "pdf_sha256"}
    if column not in allowed:
        raise ValueError(f"Invalid column for paper lookup: {column}")
    row = conn.execute(f"SELECT * FROM papers WHERE {column} = ?", (value,)).fetchone()
    return _row_to_dict(row) if row else None


def get_paper_by_id(conn: sqlite3.Connection, paper_id: str) -> Optional[dict]:
    return _get_paper_by(conn, "id", paper_id)


def get_paper_by_slug(conn: sqlite3.Connection, slug: str) -> Optional[dict]:
    return _get_paper_by(conn, "slug", slug)


def get_paper_by_doi(conn: sqlite3.Connection, doi: str) -> Optional[dict]:
    return _get_paper_by(conn, "doi", doi)


def get_paper_by_sha256(conn: sqlite3.Connection, sha256: str) -> Optional[dict]:
    return _get_paper_by(conn, "pdf_sha256", sha256)


def list_papers(conn: sqlite3.Connection) -> List[dict]:
    rows = conn.execute("SELECT * FROM papers ORDER BY year DESC, slug").fetchall()
    return [_row_to_dict(r) for r in rows]


def update_paper_status(conn: sqlite3.Connection, paper_id: str, status: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE papers SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, paper_id),
    )
    conn.commit()


# --- Paper Tasks ---

def insert_task(conn: sqlite3.Connection, paper_id: str, task_type: str) -> str:
    task_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO paper_tasks (id, paper_id, task_type, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (task_id, paper_id, task_type, "pending", now),
    )
    conn.commit()
    return task_id


def update_task_status(
    conn: sqlite3.Connection,
    task_id: str,
    status: str,
    error: Optional[str] = None,
    output_path: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    if status == "running":
        conn.execute(
            "UPDATE paper_tasks SET status = ?, started_at = ? WHERE id = ?",
            (status, now, task_id),
        )
    elif status in ("completed", "failed", "skipped"):
        conn.execute(
            "UPDATE paper_tasks SET status = ?, finished_at = ?, error = ?, output_path = ? WHERE id = ?",
            (status, now, error, output_path, task_id),
        )
    else:
        conn.execute("UPDATE paper_tasks SET status = ? WHERE id = ?", (status, task_id))
    conn.commit()


def get_tasks_for_paper(conn: sqlite3.Connection, paper_id: str) -> List[dict]:
    rows = conn.execute(
        "SELECT * FROM paper_tasks WHERE paper_id = ? ORDER BY created_at",
        (paper_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if "authors" in d and isinstance(d["authors"], str):
        try:
            d["authors"] = json.loads(d["authors"])
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse authors JSON: %s", d["authors"][:100])
    return d


# --- References Raw CRUD ---

def insert_reference_raw(conn: sqlite3.Connection, ref: dict) -> None:
    """Insert a raw reference record."""
    _insert_record(conn, "references_raw", ref)


def get_references_for_paper(conn: sqlite3.Connection, paper_id: str) -> List[dict]:
    """Get all raw references for a paper."""
    rows = conn.execute(
        "SELECT * FROM references_raw WHERE source_paper_id = ? ORDER BY sequence_num",
        (paper_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# --- Reference Candidates CRUD ---

def insert_reference_candidate(conn: sqlite3.Connection, candidate: dict) -> None:
    """Insert a reference candidate record."""
    _insert_record(conn, "reference_candidates", candidate, or_ignore=False)


def get_candidates_for_paper(conn: sqlite3.Connection, paper_id: str) -> List[dict]:
    """Get all reference candidates for a paper."""
    rows = conn.execute(
        "SELECT * FROM reference_candidates WHERE source_paper_id = ? ORDER BY created_at",
        (paper_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_pending_candidates(conn: sqlite3.Connection) -> List[dict]:
    """Get all pending reference candidates."""
    rows = conn.execute(
        "SELECT * FROM reference_candidates WHERE status = 'pending' ORDER BY created_at",
    ).fetchall()
    return [dict(r) for r in rows]


def update_candidate_status(conn: sqlite3.Connection, candidate_id: str, status: str) -> None:
    """Update the status of a reference candidate."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE reference_candidates SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, candidate_id),
    )
    conn.commit()


# --- Citation Edges CRUD ---

def insert_citation_edge(
    conn: sqlite3.Connection,
    source_paper_id: str,
    target_paper_id: str,
    match_method: str = None,
    confidence: float = None,
    raw_reference_id: str = None,
) -> None:
    """Insert a citation edge (source cites target)."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR IGNORE INTO citation_edges
           (source_paper_id, target_paper_id, raw_reference_id,
            match_method, confidence, confirmed, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (source_paper_id, target_paper_id, raw_reference_id,
         match_method, confidence, 1, now, now),
    )
    conn.commit()


def get_citing_papers(conn: sqlite3.Connection, paper_id: str) -> List[dict]:
    """Get papers that this paper cites (source -> target)."""
    rows = conn.execute(
        """SELECT ce.*, p.slug, p.title
           FROM citation_edges ce
           JOIN papers p ON p.id = ce.target_paper_id
           WHERE ce.source_paper_id = ?
           ORDER BY ce.confidence DESC""",
        (paper_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_cited_by_papers(conn: sqlite3.Connection, paper_id: str) -> List[dict]:
    """Get papers that cite this paper (target <- source)."""
    rows = conn.execute(
        """SELECT ce.*, p.slug, p.title
           FROM citation_edges ce
           JOIN papers p ON p.id = ce.source_paper_id
           WHERE ce.target_paper_id = ?
           ORDER BY p.year DESC""",
        (paper_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_citation_edge(
    conn: sqlite3.Connection,
    source_paper_id: str,
    target_paper_id: str,
) -> Optional[dict]:
    """Get a specific citation edge."""
    row = conn.execute(
        "SELECT * FROM citation_edges WHERE source_paper_id = ? AND target_paper_id = ?",
        (source_paper_id, target_paper_id),
    ).fetchone()
    return dict(row) if row else None


def update_citation_confirmed(
    conn: sqlite3.Connection,
    source_paper_id: str,
    target_paper_id: str,
    confirmed: bool,
) -> None:
    """Update the confirmed status of a citation edge."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE citation_edges SET confirmed = ?, updated_at = ?
           WHERE source_paper_id = ? AND target_paper_id = ?""",
        (1 if confirmed else 0, now, source_paper_id, target_paper_id),
    )
    conn.commit()


def delete_citation_edge(
    conn: sqlite3.Connection,
    source_paper_id: str,
    target_paper_id: str,
) -> None:
    """Delete a citation edge."""
    conn.execute(
        "DELETE FROM citation_edges WHERE source_paper_id = ? AND target_paper_id = ?",
        (source_paper_id, target_paper_id),
    )
    conn.commit()


def delete_paper(conn: sqlite3.Connection, paper_id: str) -> None:
    """Delete a paper and all related records (tasks, refs, candidates, edges)."""
    conn.execute(
        "DELETE FROM citation_edges WHERE source_paper_id = ? OR target_paper_id = ?",
        (paper_id, paper_id),
    )
    conn.execute(
        "DELETE FROM reference_candidates WHERE source_paper_id = ?",
        (paper_id,),
    )
    conn.execute(
        "DELETE FROM references_raw WHERE source_paper_id = ?",
        (paper_id,),
    )
    conn.execute(
        "DELETE FROM paper_tasks WHERE paper_id = ?",
        (paper_id,),
    )
    conn.execute(
        "DELETE FROM papers WHERE id = ?",
        (paper_id,),
    )
    conn.commit()
