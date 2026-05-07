from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_long_memory.memory_config import MemoryConfig, load_memory_config
from agent_long_memory.memory_db import (
    CreateMemoryRecordInput,
    MemoryEmbedding,
    MemoryProject,
    MemoryRecord,
    MemorySearchResult,
    create_memory_record,
    ensure_memory_project,
    search_memory_records_by_embedding,
    upsert_memory_embedding,
)
from agent_long_memory.memory_scope import resolve_project_scope


@dataclass(frozen=True)
class SemanticMemoryWriteResult:
    project: MemoryProject
    record: MemoryRecord
    embedding: MemoryEmbedding | None


def create_semantic_memory_record(
    project: MemoryProject,
    record: CreateMemoryRecordInput,
    *,
    config: MemoryConfig,
) -> SemanticMemoryWriteResult:
    created = create_memory_record(project, record, config=config)
    text = _embedding_text(created)

    from agent_long_memory.embeddings import embed_text

    embedding = embed_text(text, model_name=config.embedding_model)
    stored_embedding = upsert_memory_embedding(
        created.id,
        embedding_model=config.embedding_model,
        embedding=embedding,
        config=config,
    )
    return SemanticMemoryWriteResult(project=project, record=created, embedding=stored_embedding)


def write_semantic_memory(
    workspace: Path,
    record: CreateMemoryRecordInput,
    *,
    config: MemoryConfig | None = None,
    create_embedding: bool = True,
) -> SemanticMemoryWriteResult:
    resolved_config = config or load_memory_config()
    if not resolved_config.database_url:
        raise ValueError("PPT_AGENT_MEMORY_DATABASE_URL is required")

    scope = resolve_project_scope(workspace)
    project = ensure_memory_project(scope, config=resolved_config)
    created_record = create_memory_record(project, record, config=resolved_config)
    if not create_embedding:
        return SemanticMemoryWriteResult(project=project, record=created_record, embedding=None)

    embedding_text = "\n".join((record.memory_type, record.title, record.content))

    from agent_long_memory.embeddings import embed_text

    vector = embed_text(embedding_text, model_name=resolved_config.embedding_model)
    embedding = upsert_memory_embedding(
        created_record.id,
        embedding_model=resolved_config.embedding_model,
        embedding=vector,
        config=resolved_config,
    )
    return SemanticMemoryWriteResult(project=project, record=created_record, embedding=embedding)


def search_semantic_memory(
    workspace: Path,
    query: str,
    *,
    config: MemoryConfig | None = None,
    memory_types: list[str] | None = None,
    limit: int = 8,
) -> list[MemorySearchResult]:
    if not query.strip():
        raise ValueError("query must be non-empty")
    resolved_config = config or load_memory_config()
    if not resolved_config.database_url:
        raise ValueError("PPT_AGENT_MEMORY_DATABASE_URL is required")

    scope = resolve_project_scope(workspace)
    project = ensure_memory_project(scope, config=resolved_config)

    from agent_long_memory.embeddings import embed_text

    vector = embed_text(query, model_name=resolved_config.embedding_model)
    return search_memory_records_by_embedding(
        project,
        query_embedding=vector,
        embedding_model=resolved_config.embedding_model,
        memory_types=memory_types,
        limit=limit,
        config=resolved_config,
    )


def _embedding_text(record: MemoryRecord) -> str:
    return "\n".join(part for part in (record.title, record.content) if part)

