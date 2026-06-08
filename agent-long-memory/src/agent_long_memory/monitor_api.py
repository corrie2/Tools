"""FastAPI monitor for Agent Long Memory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from agent_long_memory.access_config import allowed_workspaces, list_registered_workspaces
from agent_long_memory.memory_config import MemoryConfig, load_memory_config
from agent_long_memory.memory_db import connect_memory_db, release_connection


def _load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(Path(__file__).resolve().parents[2] / ".env")

app = FastAPI(title="Memory Monitor", description="Agent Long Memory monitor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_config() -> MemoryConfig:
    return load_memory_config()


def execute_query(query: str, params: tuple = ()) -> list:
    config = get_config()
    conn = connect_memory_db(config)
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
    finally:
        release_connection(conn, config)


def _allowed_workspaces() -> list[str]:
    return [str(path) for path in allowed_workspaces()]


@app.get("/api/stats")
async def get_stats():
    total = execute_query("SELECT COUNT(*) FROM memory_records")[0][0]
    type_rows = execute_query(
        """
        SELECT memory_type, COUNT(*) AS count
        FROM memory_records
        GROUP BY memory_type
        ORDER BY count DESC
        """
    )
    projects = execute_query("SELECT COUNT(*) FROM memory_projects")[0][0]
    embeddings = execute_query("SELECT COUNT(*) FROM memory_embeddings")[0][0]
    recent = execute_query(
        """
        SELECT COUNT(*)
        FROM memory_records
        WHERE created_at > NOW() - INTERVAL '24 hours'
        """
    )[0][0]
    return {
        "total_records": total,
        "types": {row[0]: row[1] for row in type_rows},
        "projects": projects,
        "embeddings": embeddings,
        "recent_24h": recent,
    }


@app.get("/api/access")
async def get_access():
    config = get_config()
    allowed = _allowed_workspaces()
    access = list_registered_workspaces()
    project_rows = execute_query(
        """
        SELECT
            p.id,
            p.name,
            p.root_path,
            p.git_remote,
            p.created_at,
            COUNT(r.id) AS record_count
        FROM memory_projects p
        LEFT JOIN memory_records r ON r.project_id = p.id
        GROUP BY p.id, p.name, p.root_path, p.git_remote, p.created_at
        ORDER BY p.created_at DESC
        """
    )
    projects = [
        {
            "id": str(row[0]),
            "name": row[1],
            "root_path": row[2],
            "git_remote": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
            "record_count": row[5],
            "allowed": not allowed or any(Path(row[2]).resolve() == Path(path) for path in allowed),
        }
        for row in project_rows
    ]
    known_roots = {project["root_path"] for project in projects}
    allowed_entries = [
        {
            "root_path": path,
            "registered": path in known_roots,
        }
        for path in allowed
    ]
    return {
        "enabled": config.enabled and bool(config.database_url),
        "allowlist_enabled": bool(allowed),
        "projects_file": access["projects_file"],
        "file_workspaces": access["file_workspaces"],
        "env_workspaces": access["env_workspaces"],
        "allowed_workspaces": allowed_entries,
        "projects": projects,
    }


@app.get("/api/records")
async def get_records(
    memory_type: str | None = Query(None, description="Filter by memory type"),
    keyword: str | None = Query(None, description="Search title and content"),
    limit: int = Query(20, ge=1, le=200, description="Maximum records to return"),
):
    query = """
        SELECT
            r.id,
            r.memory_type,
            r.title,
            r.content,
            r.source_type,
            r.importance,
            r.confidence,
            r.created_at,
            p.name AS project_name
        FROM memory_records r
        LEFT JOIN memory_projects p ON p.id = r.project_id
        WHERE 1 = 1
    """
    params: list[object] = []
    if memory_type:
        query += " AND r.memory_type = %s"
        params.append(memory_type)
    if keyword:
        query += " AND (r.title ILIKE %s OR r.content ILIKE %s)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    query += " ORDER BY r.created_at DESC LIMIT %s"
    params.append(limit)

    rows = execute_query(query, tuple(params))
    records = [
        {
            "id": str(row[0]),
            "memory_type": row[1],
            "title": row[2],
            "content": row[3][:200] if row[3] else "",
            "source_type": row[4],
            "importance": float(row[5]) if row[5] is not None else 0,
            "confidence": float(row[6]) if row[6] is not None else 0,
            "created_at": row[7].isoformat() if row[7] else None,
            "project_name": row[8],
        }
        for row in rows
    ]
    return {"records": records, "count": len(records)}


@app.get("/api/types")
async def get_types():
    rows = execute_query(
        """
        SELECT DISTINCT memory_type
        FROM memory_records
        ORDER BY memory_type
        """
    )
    return {"types": [row[0] for row in rows]}


@app.get("/api/projects")
async def get_projects():
    rows = execute_query(
        """
        SELECT
            p.id,
            p.name,
            p.root_path,
            p.git_remote,
            p.created_at,
            COUNT(r.id) AS record_count
        FROM memory_projects p
        LEFT JOIN memory_records r ON r.project_id = p.id
        GROUP BY p.id, p.name, p.root_path, p.git_remote, p.created_at
        ORDER BY p.created_at DESC
        """
    )
    projects = [
        {
            "id": str(row[0]),
            "name": row[1],
            "root_path": row[2],
            "git_remote": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
            "record_count": row[5],
        }
        for row in rows
    ]
    return {"projects": projects}


@app.get("/api/timeline")
async def get_timeline(days: int = Query(7, ge=1, le=365, description="Number of days")):
    rows = execute_query(
        """
        SELECT
            DATE(created_at) AS date,
            memory_type,
            COUNT(*) AS count
        FROM memory_records
        WHERE created_at > NOW() - (%s * INTERVAL '1 day')
        GROUP BY DATE(created_at), memory_type
        ORDER BY date DESC
        """,
        (days,),
    )
    timeline: dict[str, dict[str, int]] = {}
    for row in rows:
        date_key = row[0].isoformat() if row[0] else "unknown"
        timeline.setdefault(date_key, {})[row[1]] = row[2]
    return {"timeline": timeline, "days": days}


@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "monitor.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>Monitor page not found</h1>"
