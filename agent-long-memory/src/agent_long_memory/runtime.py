from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agent_long_memory.memory_config import MemoryConfig, load_memory_config
from agent_long_memory.memory_db import initialize_memory_database
from agent_long_memory.memory_scope import ProjectScope, resolve_project_scope


DEFAULT_DATABASE_URL = "postgresql://ppt_agent:ppt_agent@127.0.0.1:54329/ppt_agent_memory"


@dataclass(frozen=True)
class LongMemoryRuntimeStatus:
    enabled: bool
    initialized: bool
    config: MemoryConfig
    scope: ProjectScope


def enable_long_memory_for_agent(
    workspace: Path,
    *,
    database_url: str | None = None,
    initialize_database: bool = True,
    set_project_root_env: bool = True,
) -> LongMemoryRuntimeStatus:
    resolved_workspace = Path(workspace).resolve()
    resolved_database_url = database_url or os.environ.get("PPT_AGENT_MEMORY_DATABASE_URL") or DEFAULT_DATABASE_URL

    os.environ["PPT_AGENT_VECTOR_MEMORY"] = "1"
    os.environ["PPT_AGENT_MEMORY_DATABASE_URL"] = resolved_database_url
    os.environ["PPT_AGENT_MEMORY_SCOPE_MODE"] = "workspace"
    if set_project_root_env:
        os.environ["PPT_AGENT_MEMORY_PROJECT_ROOT"] = str(resolved_workspace)
    else:
        os.environ.pop("PPT_AGENT_MEMORY_PROJECT_ROOT", None)

    config = load_memory_config()
    initialized = False
    if initialize_database:
        initialize_memory_database(config=config)
        initialized = True

    return LongMemoryRuntimeStatus(
        enabled=config.enabled and bool(config.database_url),
        initialized=initialized,
        config=config,
        scope=resolve_project_scope(resolved_workspace),
    )
