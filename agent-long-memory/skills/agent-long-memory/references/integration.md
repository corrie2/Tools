# Agent Integration

## Environment

Install the package in the agent environment:

```bash
pip install -e E:\workspace\Tools\agent-long-memory
```

Set:

```bash
PPT_AGENT_VECTOR_MEMORY=1
PPT_AGENT_MEMORY_DATABASE_URL=postgresql://...
```

Optional:

```bash
PPT_AGENT_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
PPT_AGENT_MEMORY_PROJECT_ROOT=E:\workspace\Tools\agent-long-memory
PPT_AGENT_MEMORY_SCOPE_MODE=workspace
```

The default embedding model emits 384-dimensional vectors and matches the schema's `vector(384)`.
`PPT_AGENT_MEMORY_PROJECT_ROOT` overrides the workspace argument when an agent process runs outside the project root. `PPT_AGENT_MEMORY_SCOPE_MODE` defaults to `workspace`; use `git` only when the whole git root is one project.

## Agent Lifecycle

For Windows agents, prefer launching through the repository wrapper:

```powershell
.\scripts\start-agent-with-memory.ps1 -Workspace <project-root> -MemoryPython <project-python> -AgentExecutable <project-python> -AgentArgsJson '["-m", "my_agent"]'
```

Use `-AgentArgsBase64` with base64-encoded JSON when arguments contain shell-sensitive tokens.

The wrapper sets memory environment variables for the child agent process and fixes `PPT_AGENT_MEMORY_PROJECT_ROOT` to the supplied project root. Use it for one project per launched process.

If the agent should respond to natural language such as "start long-term memory", add an intent handler that calls:

```python
from pathlib import Path
from agent_long_memory import enable_long_memory_for_agent

status = enable_long_memory_for_agent(Path.cwd())
```

This enables memory inside the already-running process. A shell startup wrapper cannot change environment variables for a process that is already running. The in-process API sets `PPT_AGENT_MEMORY_PROJECT_ROOT` by default so normal `Path.cwd()` calls use the activated project. A multi-project agent should pass each target project workspace explicitly; explicit non-current workspaces override the default project root.

At process startup:

1. Load environment.
2. Run `memory_session.py init-db` during setup or deployment, not on every task.
3. Determine active workspace.
4. Run `memory_session.py status --workspace <workspace>`.
5. If enabled, continue.

At task start:

1. Run one search using the user's request.
2. Run additional focused searches only for relevant modules or decisions.
3. Add high-confidence results to the agent context with project/source metadata.

At task end:

1. Write durable memories only.
2. Use stable `memory_type` values such as `user_preference`, `project_convention`, `decision`, `implementation_note`, or `pitfall`.
3. Use concise titles and specific content.

## Isolation Contract

Do not expose a manual `project_id` setting in agent configuration. The workspace path, or the explicit `PPT_AGENT_MEMORY_PROJECT_ROOT`, is the only input used to resolve scope.

For custom database queries, first resolve the project using `resolve_project_scope(workspace)` and `ensure_memory_project(scope, config=config)`, then filter every query by that project's ID.

Never run global semantic searches across all projects. Cross-project retrieval is outside this skill's contract.

## Failure Behavior

Memory is optional. If environment variables, PostgreSQL, pgvector, or the embedding model are unavailable, continue the task without long-term memory and report the memory status only when relevant.
