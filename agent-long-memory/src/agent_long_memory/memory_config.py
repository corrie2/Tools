from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass(frozen=True)
class MemoryConfig:
    enabled: bool
    database_url: str | None
    embedding_model: str
    min_pool_size: int = 2
    max_pool_size: int = 10
    connect_timeout_seconds: int = 5
    use_pool: bool = True


def load_memory_config() -> MemoryConfig:
    enabled = os.environ.get("PPT_AGENT_VECTOR_MEMORY") == "1"
    database_url = os.environ.get("PPT_AGENT_MEMORY_DATABASE_URL") or None
    embedding_model = os.environ.get("PPT_AGENT_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
    min_pool_size = int(os.environ.get("PPT_AGENT_MEMORY_POOL_MIN", "2"))
    max_pool_size = int(os.environ.get("PPT_AGENT_MEMORY_POOL_MAX", "10"))
    connect_timeout_seconds = int(os.environ.get("PPT_AGENT_MEMORY_CONNECT_TIMEOUT", "5"))
    use_pool = os.environ.get("PPT_AGENT_MEMORY_USE_POOL", "1") != "0"
    return MemoryConfig(
        enabled=enabled,
        database_url=database_url,
        embedding_model=embedding_model,
        min_pool_size=min_pool_size,
        max_pool_size=max_pool_size,
        connect_timeout_seconds=connect_timeout_seconds,
        use_pool=use_pool,
    )
