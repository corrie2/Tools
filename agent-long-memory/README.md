# Agent Long Memory

Reusable workspace-scoped PostgreSQL/pgvector semantic memory.

Install this tool package from the workspace:

```bash
pip install -e E:\workspace\tools\agent-long-memory
```

Use a workspace path to resolve workspace scope before writing or searching memory:

```python
from pathlib import Path

from agent_long_memory import CreateMemoryRecordInput, search_semantic_memory, write_semantic_memory

workspace = Path.cwd()
write_semantic_memory(
    workspace,
    CreateMemoryRecordInput(
        memory_type="user_preference",
        title="Style preference",
        content="Use concise technical slides in this project.",
    ),
)
results = search_semantic_memory(workspace, "technical slide style")
```

Set `PPT_AGENT_VECTOR_MEMORY=1` and `PPT_AGENT_MEMORY_DATABASE_URL` to enable PostgreSQL access. Records are isolated by the resolved workspace scope, and searches filter by `project_id`.




