from __future__ import annotations

import logging
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
    create_memory_records_batch,
    ensure_memory_project,
    search_memory_records_by_embedding,
    upsert_memory_embedding,
    upsert_memory_embeddings_batch,
)
from agent_long_memory.memory_scope import resolve_project_scope

# 审计日志
logger = logging.getLogger("agent_long_memory")


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
    from agent_long_memory.embeddings import embed_text

    text = _embedding_text_input(record)
    embedding = embed_text(text, model_name=config.embedding_model)
    created = create_memory_record(project, record, config=config)
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

    logger.debug(f"Writing semantic memory: type={record.memory_type}, title={record.title[:50]}")

    scope = resolve_project_scope(workspace)
    project = ensure_memory_project(scope, config=resolved_config)
    if not create_embedding:
        created_record = create_memory_record(project, record, config=resolved_config)
        return SemanticMemoryWriteResult(project=project, record=created_record, embedding=None)

    from agent_long_memory.embeddings import embed_text

    embedding_text = _embedding_text_input(record)
    vector = embed_text(embedding_text, model_name=resolved_config.embedding_model)
    created_record = create_memory_record(project, record, config=resolved_config)
    embedding = upsert_memory_embedding(
        created_record.id,
        embedding_model=resolved_config.embedding_model,
        embedding=vector,
        config=resolved_config,
    )

    logger.debug(f"Wrote semantic memory: record={created_record.id}")
    return SemanticMemoryWriteResult(project=project, record=created_record, embedding=embedding)


def write_semantic_memory_batch(
    workspace: Path,
    records: list[CreateMemoryRecordInput],
    *,
    config: MemoryConfig | None = None,
    create_embeddings: bool = True,
) -> list[SemanticMemoryWriteResult]:
    """批量写入语义记忆"""
    if not records:
        return []

    resolved_config = config or load_memory_config()
    if not resolved_config.database_url:
        raise ValueError("PPT_AGENT_MEMORY_DATABASE_URL is required")

    logger.debug(f"Writing {len(records)} semantic memories in batch")

    scope = resolve_project_scope(workspace)
    project = ensure_memory_project(scope, config=resolved_config)

    # 批量创建记录
    if not create_embeddings:
        created_records = create_memory_records_batch(project, records, config=resolved_config)
        return [
            SemanticMemoryWriteResult(project=project, record=record, embedding=None)
            for record in created_records
        ]

    # 批量生成嵌入
    from agent_long_memory.embeddings import embed_texts

    embedding_texts = [
        _embedding_text_input(record)
        for record in records
    ]
    vectors = embed_texts(embedding_texts, model_name=resolved_config.embedding_model)
    created_records = create_memory_records_batch(project, records, config=resolved_config)

    # 批量存储嵌入
    embeddings_input = [
        (record.id, resolved_config.embedding_model, vector)
        for record, vector in zip(created_records, vectors)
    ]
    stored_embeddings = upsert_memory_embeddings_batch(embeddings_input, config=resolved_config)

    # 组装结果
    results = []
    for i, record in enumerate(created_records):
        embedding = stored_embeddings[i] if i < len(stored_embeddings) else None
        results.append(SemanticMemoryWriteResult(project=project, record=record, embedding=embedding))

    logger.debug(f"Wrote {len(results)} semantic memories in batch")
    return results


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

    logger.debug(f"Searching semantic memory: query={query[:50]}")

    scope = resolve_project_scope(workspace)
    project = ensure_memory_project(scope, config=resolved_config)

    from agent_long_memory.embeddings import embed_text

    vector = embed_text(query, model_name=resolved_config.embedding_model)
    results = search_memory_records_by_embedding(
        project,
        query_embedding=vector,
        embedding_model=resolved_config.embedding_model,
        memory_types=memory_types,
        limit=limit,
        config=resolved_config,
    )

    logger.debug(f"Found {len(results)} semantic memories")
    return results


def search_semantic_memory_batch(
    workspace: Path,
    queries: list[str],
    *,
    config: MemoryConfig | None = None,
    memory_types: list[str] | None = None,
    limit: int = 8,
) -> list[list[MemorySearchResult]]:
    """批量搜索语义记忆"""
    if not queries:
        return []

    resolved_config = config or load_memory_config()
    if not resolved_config.database_url:
        raise ValueError("PPT_AGENT_MEMORY_DATABASE_URL is required")

    logger.debug(f"Searching semantic memory in batch: {len(queries)} queries")

    scope = resolve_project_scope(workspace)
    project = ensure_memory_project(scope, config=resolved_config)

    from agent_long_memory.embeddings import embed_texts

    vectors = embed_texts(queries, model_name=resolved_config.embedding_model)

    results = []
    for vector in vectors:
        search_results = search_memory_records_by_embedding(
            project,
            query_embedding=vector,
            embedding_model=resolved_config.embedding_model,
            memory_types=memory_types,
            limit=limit,
            config=resolved_config,
        )
        results.append(search_results)

    logger.debug(f"Found semantic memories for {len(results)} queries in batch")
    return results


def _embedding_text(record: MemoryRecord) -> str:
    return "\n".join(part for part in (record.title, record.content) if part)


def _embedding_text_input(record: CreateMemoryRecordInput) -> str:
    return "\n".join((record.memory_type, record.title, record.content))
