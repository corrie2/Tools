from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from agent_long_memory.access_config import (
    add_registered_workspace,
    allowed_workspaces,
    describe_workspace_access,
    list_registered_workspaces,
    normalize_workspace,
    remove_registered_workspace,
    resolve_access_workspace,
    workspace_allowed,
)
from agent_long_memory.harness import format_memory_context, load_memory_context
from agent_long_memory.memory_config import load_memory_config
from agent_long_memory.memory_db import (
    CreateMemoryRecordInput,
    ensure_memory_project,
    initialize_memory_database,
    list_memory_records,
)
from agent_long_memory.memory_scope import resolve_project_scope
from agent_long_memory.semantic_memory import search_semantic_memory, write_semantic_memory


def _workspace_path(workspace: str) -> Path:
    return resolve_access_workspace(workspace or ".")


def _allowed_workspaces() -> list[Path]:
    return allowed_workspaces()


def _workspace_allowed(workspace: Path) -> bool:
    return workspace_allowed(workspace)


def _not_allowed_payload(workspace: Path) -> dict[str, Any]:
    return {
        "ok": True,
        "enabled": False,
        "workspace": str(workspace),
        "reason": "workspace_not_allowed",
        "allowed_workspaces": [str(path) for path in _allowed_workspaces()],
        "access": describe_workspace_access(workspace),
    }


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    return value


def _config_status() -> dict[str, Any]:
    config = load_memory_config()
    return {
        "vector_memory": config.enabled,
        "database_url_set": bool(config.database_url),
        "embedding_model": config.embedding_model,
        "pool_min": config.min_pool_size,
        "pool_max": config.max_pool_size,
    }


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _mcp_embedding_env() -> dict[str, str]:
    return {
        "AGENT_LONG_MEMORY_EMBEDDING_SUBPROCESS": "1",
        "AGENT_LONG_MEMORY_EMBEDDING_QUIET": "1",
        "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        "TOKENIZERS_PARALLELISM": "false",
    }


def _call_with_env(func: Any, *args: Any, env: dict[str, str] | None = None, **kwargs: Any) -> Any:
    previous: dict[str, str | None] = {}
    try:
        for key, value in (env or {}).items():
            previous[key] = os.environ.get(key)
            os.environ[key] = value
        return func(*args, **kwargs)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _search_result_payload(results: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "record": _to_jsonable(result.record),
            "similarity": result.similarity,
            "embedding_model": result.embedding_model,
        }
        for result in results
    ]


def memory_status(workspace: str = ".") -> dict[str, Any]:
    """Return configuration and resolved project scope for the memory backend."""
    input_workspace = normalize_workspace(workspace or ".")
    resolved_workspace = _workspace_path(workspace)
    config = load_memory_config()
    scope = resolve_project_scope(resolved_workspace)
    allowed = _workspace_allowed(input_workspace)
    payload = {
        "ok": True,
        "enabled": allowed and config.enabled and bool(config.database_url),
        "allowed": allowed,
        "allowed_workspaces": [str(path) for path in _allowed_workspaces()],
        "input_workspace": str(input_workspace),
        "access": list_registered_workspaces(),
        "resolved_access": describe_workspace_access(input_workspace),
        "configured": _config_status(),
        "workspace": str(resolved_workspace),
        "scope": _to_jsonable(scope),
    }
    return payload


def memory_access_list() -> dict[str, Any]:
    """List dynamically registered memory workspaces."""
    return {"ok": True, **list_registered_workspaces()}


def memory_access_add(workspace: str) -> dict[str, Any]:
    """Allow a workspace to use the memory backend without restarting MCP."""
    return {"ok": True, **add_registered_workspace(workspace)}


def memory_access_remove(workspace: str) -> dict[str, Any]:
    """Remove a workspace from the dynamic memory allowlist."""
    return {"ok": True, **remove_registered_workspace(workspace)}


def memory_access_resolve(workspace: str) -> dict[str, Any]:
    """Resolve a path to the registered memory project that would be used."""
    return {"ok": True, **describe_workspace_access(workspace)}


def memory_init_schema() -> dict[str, Any]:
    """Initialize the PostgreSQL/pgvector schema."""
    config = load_memory_config()
    if not config.database_url:
        return {
            "ok": False,
            "error": "PPT_AGENT_MEMORY_DATABASE_URL is required",
            "configured": _config_status(),
        }
    try:
        initialize_memory_database(config=config)
    except Exception as exc:
        return {
            "ok": False,
            "initialized": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "configured": _config_status(),
        }
    return {"ok": True, "initialized": True, "configured": _config_status()}


def memory_search(
    workspace: str,
    query: str,
    memory_types: list[str] | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    """Search semantic memories scoped to a workspace/project."""
    resolved_workspace = _workspace_path(workspace)
    if not _workspace_allowed(resolved_workspace):
        payload = _not_allowed_payload(resolved_workspace)
        payload["results"] = []
        return payload
    config = load_memory_config()
    if not config.enabled or not config.database_url:
        return {"ok": True, "enabled": False, "results": []}
    try:
        results = search_semantic_memory(
            resolved_workspace,
            query,
            config=config,
            memory_types=memory_types,
            limit=limit,
        )
    except Exception as exc:
        return {"ok": False, "enabled": True, "error": str(exc), "error_type": type(exc).__name__, "results": []}
    return {
        "ok": True,
        "enabled": True,
        "results": _search_result_payload(results),
    }


def memory_write(
    workspace: str,
    memory_type: str,
    title: str,
    content: str,
    source_type: str = "codex",
    source_ref: str | None = None,
    module_path: str | None = None,
    tags: list[str] | None = None,
    importance: float = 0.5,
    confidence: float = 0.7,
    create_embedding: bool = True,
) -> dict[str, Any]:
    """Write one durable memory scoped to a workspace/project."""
    resolved_workspace = _workspace_path(workspace)
    if not _workspace_allowed(resolved_workspace):
        payload = _not_allowed_payload(resolved_workspace)
        payload["written"] = False
        return payload
    config = load_memory_config()
    if not config.enabled or not config.database_url:
        return {"ok": True, "enabled": False, "written": False}

    try:
        result = write_semantic_memory(
            resolved_workspace,
            CreateMemoryRecordInput(
                memory_type=memory_type,
                title=title,
                content=content,
                source_type=source_type,
                source_ref=source_ref,
                module_path=module_path,
                tags=tags or [],
                importance=importance,
                confidence=confidence,
            ),
            config=config,
            create_embedding=create_embedding,
        )
    except Exception as exc:
        return {"ok": False, "enabled": True, "written": False, "error": str(exc), "error_type": type(exc).__name__}
    payload = {
        "project": _to_jsonable(result.project),
        "record": _to_jsonable(result.record),
        "embedding": None,
    }
    if result.embedding is not None:
        payload["embedding"] = {
            "id": result.embedding.id,
            "record_id": result.embedding.record_id,
            "embedding_model": result.embedding.embedding_model,
            "dimensions": len(result.embedding.embedding),
            "created_at": _to_jsonable(result.embedding.created_at),
        }
    return {"ok": True, "enabled": True, "written": True, "result": payload}


def memory_list_recent(
    workspace: str,
    memory_types: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List recent memories scoped to a workspace/project."""
    resolved_workspace = _workspace_path(workspace)
    if not _workspace_allowed(resolved_workspace):
        payload = _not_allowed_payload(resolved_workspace)
        payload["records"] = []
        return payload
    config = load_memory_config()
    if not config.enabled or not config.database_url:
        return {"ok": True, "enabled": False, "records": []}
    try:
        scope = resolve_project_scope(resolved_workspace)
        project = ensure_memory_project(scope, config=config)
        records = list_memory_records(project, memory_types=memory_types, limit=limit, config=config)
    except Exception as exc:
        return {"ok": False, "enabled": True, "error": str(exc), "error_type": type(exc).__name__, "records": []}
    return {
        "ok": True,
        "enabled": True,
        "project": _to_jsonable(project),
        "records": _to_jsonable(records),
    }


def memory_load_context(
    workspace: str,
    user_request: str,
    memory_types: list[str] | None = None,
    limit: int = 8,
    max_content_chars: int = 800,
) -> dict[str, Any]:
    """Load and format project memory context for a user request."""
    resolved_workspace = _workspace_path(workspace)
    if not _workspace_allowed(resolved_workspace):
        payload = _not_allowed_payload(resolved_workspace)
        payload["context_text"] = ""
        payload["results"] = []
        return payload
    try:
        context = load_memory_context(
            resolved_workspace,
            user_request,
            memory_types=memory_types,
            limit=limit,
        )
    except Exception as exc:
        return {
            "ok": False,
            "enabled": True,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "context_text": "",
            "results": [],
        }
    return {
        "ok": True,
        "enabled": context.enabled,
        "workspace": str(context.workspace),
        "query": context.query,
        "context_text": format_memory_context(context, max_content_chars=max_content_chars),
        "results": _search_result_payload(context.results),
    }


def create_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install MCP support with: pip install -e .") from exc

    server = FastMCP("agent-long-memory")

    @server.tool(name="memory_status")
    async def memory_status_tool(workspace: str = ".") -> str:
        """Return configuration and resolved project scope for the memory backend."""
        return _json_text(memory_status(workspace))

    @server.tool(name="memory_init_schema")
    async def memory_init_schema_tool() -> str:
        """Initialize the PostgreSQL/pgvector schema."""
        return _json_text(memory_init_schema())

    @server.tool(name="memory_access_list")
    async def memory_access_list_tool() -> str:
        """List dynamically registered memory workspaces."""
        return _json_text(memory_access_list())

    @server.tool(name="memory_access_add")
    async def memory_access_add_tool(workspace: str) -> str:
        """Allow a workspace to use the memory backend without restarting MCP."""
        return _json_text(memory_access_add(workspace))

    @server.tool(name="memory_access_remove")
    async def memory_access_remove_tool(workspace: str) -> str:
        """Remove a workspace from the dynamic memory allowlist."""
        return _json_text(memory_access_remove(workspace))

    @server.tool(name="memory_access_resolve")
    async def memory_access_resolve_tool(workspace: str) -> str:
        """Resolve a path to the registered memory project that would be used."""
        return _json_text(memory_access_resolve(workspace))

    @server.tool(name="memory_search")
    async def memory_search_tool(
        workspace: str,
        query: str,
        memory_types: list[str] | None = None,
        limit: int = 8,
    ) -> str:
        """Search semantic memories scoped to a workspace/project."""
        payload = await asyncio.to_thread(
            _call_with_env,
            memory_search,
            workspace,
            query,
            memory_types,
            limit,
            env=_mcp_embedding_env(),
        )
        return _json_text(payload)

    @server.tool(name="memory_write")
    async def memory_write_tool(
        workspace: str,
        memory_type: str,
        title: str,
        content: str,
        source_type: str = "codex",
        source_ref: str | None = None,
        module_path: str | None = None,
        tags: list[str] | None = None,
        importance: float = 0.5,
        confidence: float = 0.7,
        create_embedding: bool = True,
    ) -> str:
        """Write one durable memory scoped to a workspace/project."""
        payload = await asyncio.to_thread(
            _call_with_env,
            memory_write,
            env=_mcp_embedding_env(),
            workspace=workspace,
            memory_type=memory_type,
            title=title,
            content=content,
            source_type=source_type,
            source_ref=source_ref,
            module_path=module_path,
            tags=tags,
            importance=importance,
            confidence=confidence,
            create_embedding=create_embedding,
        )
        return _json_text(payload)

    @server.tool(name="memory_list_recent")
    async def memory_list_recent_tool(
        workspace: str,
        memory_types: list[str] | None = None,
        limit: int = 20,
    ) -> str:
        """List recent memories scoped to a workspace/project."""
        payload = await asyncio.to_thread(memory_list_recent, workspace, memory_types, limit)
        return _json_text(payload)

    @server.tool(name="memory_load_context")
    async def memory_load_context_tool(
        workspace: str,
        user_request: str,
        memory_types: list[str] | None = None,
        limit: int = 8,
        max_content_chars: int = 800,
    ) -> str:
        """Load and format project memory context for a user request."""
        payload = await asyncio.to_thread(
            _call_with_env,
            memory_load_context,
            workspace,
            user_request,
            memory_types,
            limit,
            max_content_chars,
            env=_mcp_embedding_env(),
        )
        return _json_text(payload)

    return server


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
