"""记忆库监控面板后端API"""

import os
from datetime import datetime
from typing import Optional
from pathlib import Path

# 加载 .env 文件
def _load_dotenv(env_path: Path):
    """简单加载 .env 文件"""
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

_load_dotenv(Path(__file__).parent.parent.parent / ".env")

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from agent_long_memory.memory_config import load_memory_config
from agent_long_memory.memory_db import (
    connect_memory_db,
    release_connection,
    MemoryConfig,
)

app = FastAPI(title="Memory Monitor", description="Agent Long Memory 监控面板")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_config() -> MemoryConfig:
    """获取配置"""
    return load_memory_config()


def execute_query(query: str, params: tuple = ()) -> list:
    """执行查询"""
    config = get_config()
    conn = connect_memory_db(config)
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return rows
    finally:
        release_connection(conn, config)


@app.get("/api/stats")
async def get_stats():
    """获取统计信息"""
    # 总记录数
    total_query = "SELECT COUNT(*) FROM memory_records"
    total = execute_query(total_query)[0][0]
    
    # 各类型记录数
    type_query = """
        SELECT memory_type, COUNT(*) as count
        FROM memory_records
        GROUP BY memory_type
        ORDER BY count DESC
    """
    type_rows = execute_query(type_query)
    types = {row[0]: row[1] for row in type_rows}
    
    # 项目数
    project_query = "SELECT COUNT(*) FROM memory_projects"
    projects = execute_query(project_query)[0][0]
    
    # 嵌入数
    embedding_query = "SELECT COUNT(*) FROM memory_embeddings"
    embeddings = execute_query(embedding_query)[0][0]
    
    # 最近24小时新增记录
    recent_query = """
        SELECT COUNT(*) FROM memory_records 
        WHERE created_at > NOW() - INTERVAL '24 hours'
    """
    recent = execute_query(recent_query)[0][0]
    
    return {
        "total_records": total,
        "types": types,
        "projects": projects,
        "embeddings": embeddings,
        "recent_24h": recent,
    }


@app.get("/api/records")
async def get_records(
    memory_type: Optional[str] = Query(None, description="按类型筛选"),
    keyword: Optional[str] = Query(None, description="按关键词搜索"),
    limit: int = Query(20, description="返回数量"),
):
    """获取记录列表"""
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
            p.name as project_name
        FROM memory_records r
        LEFT JOIN memory_projects p ON p.id = r.project_id
        WHERE 1=1
    """
    params = []
    
    if memory_type:
        query += " AND r.memory_type = %s"
        params.append(memory_type)
    
    if keyword:
        query += " AND (r.title ILIKE %s OR r.content ILIKE %s)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    
    query += " ORDER BY r.created_at DESC LIMIT %s"
    params.append(limit)
    
    rows = execute_query(query, tuple(params))
    
    records = []
    for row in rows:
        records.append({
            "id": str(row[0]),
            "memory_type": row[1],
            "title": row[2],
            "content": row[3][:200] if row[3] else "",
            "source_type": row[4],
            "importance": float(row[5]) if row[5] else 0,
            "confidence": float(row[6]) if row[6] else 0,
            "created_at": row[7].isoformat() if row[7] else None,
            "project_name": row[8],
        })
    
    return {"records": records, "count": len(records)}


@app.get("/api/types")
async def get_types():
    """获取所有类型"""
    query = """
        SELECT DISTINCT memory_type 
        FROM memory_records 
        ORDER BY memory_type
    """
    rows = execute_query(query)
    return {"types": [row[0] for row in rows]}


@app.get("/api/projects")
async def get_projects():
    """获取所有项目"""
    query = """
        SELECT 
            p.id,
            p.name,
            p.root_path,
            p.git_remote,
            p.created_at,
            COUNT(r.id) as record_count
        FROM memory_projects p
        LEFT JOIN memory_records r ON r.project_id = p.id
        GROUP BY p.id, p.name, p.root_path, p.git_remote, p.created_at
        ORDER BY p.created_at DESC
    """
    rows = execute_query(query)
    
    projects = []
    for row in rows:
        projects.append({
            "id": str(row[0]),
            "name": row[1],
            "root_path": row[2],
            "git_remote": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
            "record_count": row[5],
        })
    
    return {"projects": projects}


@app.get("/api/timeline")
async def get_timeline(days: int = Query(7, description="天数")):
    """获取时间线数据"""
    query = """
        SELECT 
            DATE(created_at) as date,
            memory_type,
            COUNT(*) as count
        FROM memory_records
        WHERE created_at > NOW() - INTERVAL '%s days'
        GROUP BY DATE(created_at), memory_type
        ORDER BY date DESC
    """
    rows = execute_query(query, (days,))
    
    timeline = {}
    for row in rows:
        date_str = row[0].isoformat() if row[0] else "unknown"
        if date_str not in timeline:
            timeline[date_str] = {}
        timeline[date_str][row[1]] = row[2]
    
    return {"timeline": timeline, "days": days}


@app.get("/", response_class=HTMLResponse)
async def root():
    """返回监控面板页面"""
    html_path = Path(__file__).parent / "monitor.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>Monitor page not found</h1>"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
