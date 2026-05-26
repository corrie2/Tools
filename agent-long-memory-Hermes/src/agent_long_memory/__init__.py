"""Workspace-scoped agent long memory primitives."""

import logging

from agent_long_memory.memory_config import DEFAULT_EMBEDDING_MODEL, MemoryConfig, load_memory_config
from agent_long_memory.memory_db import (
    CreateMemoryRecordInput,
    MemoryEmbedding,
    MemoryProject,
    MemoryRecord,
    MemoryNotFoundError,
    MemorySearchResult,
    MemoryValidationError,
    connect_memory_db,
    close_pool,
    create_memory_record,
    create_memory_records_batch,
    ensure_memory_project,
    get_memory_embedding,
    get_memory_record,
    list_memory_records,
    search_memory_records_by_embedding,
    upsert_memory_embedding,
    upsert_memory_embeddings_batch,
)
from agent_long_memory.memory_scope import MemoryScope, ProjectScope, resolve_memory_scope, resolve_project_scope
from agent_long_memory.semantic_memory import (
    SemanticMemoryWriteResult,
    search_semantic_memory,
    search_semantic_memory_batch,
    write_semantic_memory,
    write_semantic_memory_batch,
)

# 配置日志
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

__all__ = [
    "CreateMemoryRecordInput",
    "DEFAULT_EMBEDDING_MODEL",
    "MemoryConfig",
    "MemoryEmbedding",
    "MemoryNotFoundError",
    "MemoryProject",
    "MemoryRecord",
    "MemoryScope",
    "MemorySearchResult",
    "MemoryValidationError",
    "ProjectScope",
    "SemanticMemoryWriteResult",
    "close_pool",
    "connect_memory_db",
    "create_memory_record",
    "create_memory_records_batch",
    "ensure_memory_project",
    "get_memory_embedding",
    "get_memory_record",
    "list_memory_records",
    "load_memory_config",
    "resolve_memory_scope",
    "resolve_project_scope",
    "search_memory_records_by_embedding",
    "search_semantic_memory",
    "search_semantic_memory_batch",
    "upsert_memory_embedding",
    "upsert_memory_embeddings_batch",
    "write_semantic_memory",
    "write_semantic_memory_batch",
]
