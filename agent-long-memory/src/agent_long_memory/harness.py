from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_long_memory.memory_config import MemoryConfig, load_memory_config
from agent_long_memory.memory_db import CreateMemoryRecordInput, MemorySearchResult
from agent_long_memory.semantic_memory import (
    SemanticMemoryWriteResult,
    search_semantic_memory,
    write_semantic_memory,
)


@dataclass(frozen=True)
class LoadedMemoryContext:
    workspace: Path
    query: str
    enabled: bool
    results: list[MemorySearchResult]


def load_memory_context(
    workspace: Path,
    user_request: str,
    *,
    config: MemoryConfig | None = None,
    memory_types: list[str] | None = None,
    limit: int = 8,
) -> LoadedMemoryContext:
    """Search project memory for context relevant to the current request."""
    resolved_config = config or load_memory_config()
    resolved_workspace = Path(workspace).resolve()
    if not resolved_config.enabled or not resolved_config.database_url or not user_request.strip():
        return LoadedMemoryContext(
            workspace=resolved_workspace,
            query=user_request,
            enabled=False,
            results=[],
        )

    results = search_semantic_memory(
        resolved_workspace,
        user_request,
        config=resolved_config,
        memory_types=memory_types,
        limit=limit,
    )
    return LoadedMemoryContext(
        workspace=resolved_workspace,
        query=user_request,
        enabled=True,
        results=results,
    )


def format_memory_context(context: LoadedMemoryContext, *, max_content_chars: int = 800) -> str:
    """Format retrieved memories as compact context for an agent prompt."""
    if not context.enabled:
        return ""
    if not context.results:
        return "Long-term memory: enabled, no relevant project memories found."

    lines = ["Long-term memory context:"]
    for index, result in enumerate(context.results, start=1):
        record = result.record
        content = record.content.strip()
        if len(content) > max_content_chars:
            content = content[: max_content_chars - 3].rstrip() + "..."
        tags = ", ".join(record.tags)
        parts = [
            f"{index}. [{record.memory_type}] {record.title}",
            f"similarity={result.similarity:.3f}",
            f"importance={record.importance:.2f}",
            f"confidence={record.confidence:.2f}",
        ]
        if record.module_path:
            parts.append(f"module={record.module_path}")
        if tags:
            parts.append(f"tags={tags}")
        lines.append(" | ".join(parts))
        lines.append(content)
    return "\n".join(lines)


def write_harness_memory(
    workspace: Path,
    *,
    memory_type: str,
    title: str,
    content: str,
    source_type: str = "agent",
    source_ref: str | None = None,
    module_path: str | None = None,
    tags: list[str] | None = None,
    importance: float = 0.5,
    confidence: float = 0.7,
    config: MemoryConfig | None = None,
    create_embedding: bool = True,
) -> SemanticMemoryWriteResult | None:
    """Write one durable memory when memory is enabled.

    Return None when the memory backend is disabled so callers can use this
    function opportunistically in startup/shutdown hooks.
    """
    resolved_config = config or load_memory_config()
    if not resolved_config.enabled or not resolved_config.database_url:
        return None

    return write_semantic_memory(
        Path(workspace).resolve(),
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
        config=resolved_config,
        create_embedding=create_embedding,
    )
