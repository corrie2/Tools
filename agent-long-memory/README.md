# Agent Long Memory

Reusable workspace-scoped PostgreSQL/pgvector semantic memory for local agents.

## Features

- Workspace/project-isolated semantic memory
- PostgreSQL + pgvector storage
- Local `sentence-transformers` embeddings
- Connection pooling with `psycopg_pool`
- Batch write/search APIs
- Schema initialization helper
- Local runtime enablement for agent processes
- Lightweight harness helpers for memory context loading
- Local MCP server for Codex and other MCP clients
- Optional FastAPI monitor

## Install In A Project

Clone this repository on the host that will run the agent:

```powershell
git clone <agent-long-memory-repo-url> E:\workspace\Tools\agent-long-memory
```

Install this package into the target project's own virtual environment:

```powershell
E:\workspace\MyProject\.venv\Scripts\python.exe -m pip install -e E:\workspace\Tools\agent-long-memory
```

If the target project uses another virtual environment path, use that environment's Python. The agent process must be able to `import agent_long_memory` from its own runtime environment.

## Database

Start PostgreSQL with pgvector, for example with Docker:

```powershell
docker run -d `
  --name ppt-agent-memory-db `
  -e POSTGRES_DB=ppt_agent_memory `
  -e POSTGRES_USER=ppt_agent `
  -e POSTGRES_PASSWORD=ppt_agent `
  -p 54329:5432 `
  pgvector/pgvector:pg16
```

Default database URL:

```text
postgresql://ppt_agent:ppt_agent@127.0.0.1:54329/ppt_agent_memory
```

## Enable From An Agent

For an already-running agent, handle a user request like "start long-term memory" by calling:

```python
from pathlib import Path
from agent_long_memory import enable_long_memory_for_agent

status = enable_long_memory_for_agent(Path.cwd())
```

This sets the memory access environment for the current process, initializes the database schema by default, and sets `PPT_AGENT_MEMORY_PROJECT_ROOT` to the supplied workspace. Default `Path.cwd()` calls use the activated project. A multi-project agent can still pass another project workspace explicitly to search/write calls.

If the database is not at the default URL, pass it explicitly:

```python
status = enable_long_memory_for_agent(
    Path.cwd(),
    database_url="postgresql://user:password@host:port/dbname",
)
```

## Search And Write

Use a workspace path to resolve workspace scope before writing or searching memory:

```python
from pathlib import Path

from agent_long_memory import CreateMemoryRecordInput, search_semantic_memory, write_semantic_memory

workspace = Path.cwd()
results = search_semantic_memory(workspace, "technical slide style")

write_semantic_memory(
    workspace,
    CreateMemoryRecordInput(
        memory_type="user_preference",
        title="Style preference",
        content="Use concise technical slides in this project.",
        source_type="agent",
    ),
)
```

## Batch Operations

```python
from pathlib import Path

from agent_long_memory import (
    CreateMemoryRecordInput,
    search_semantic_memory_batch,
    write_semantic_memory_batch,
)

workspace = Path.cwd()

records = [
    CreateMemoryRecordInput(
        memory_type="user_preference",
        title="Style",
        content="Use concise technical slides.",
    ),
    CreateMemoryRecordInput(
        memory_type="project_fact",
        title="Color system",
        content="Use the professional color scheme from the existing deck.",
    ),
]
write_results = write_semantic_memory_batch(workspace, records)

queries = ["technical slides", "color scheme"]
search_results = search_semantic_memory_batch(workspace, queries)
```

## Harness Helpers

Use the harness layer when wiring memory into an agent startup or request loop:

```python
from pathlib import Path
from agent_long_memory import format_memory_context, load_memory_context

context = load_memory_context(Path.cwd(), "current user request")
prompt_context = format_memory_context(context)
```

`load_memory_context()` is safe to call opportunistically. It returns an empty disabled context when memory is not enabled or no database URL is configured.

## MCP Server

Run the local MCP server over stdio:

```powershell
agent-long-memory-mcp
```

Or run it from source:

```powershell
python -m agent_long_memory.mcp_server
```

The server exposes these tools:

```text
memory_status(workspace)
memory_access_list()
memory_access_add(workspace)
memory_access_remove(workspace)
memory_access_resolve(workspace)
memory_init_schema()
memory_search(workspace, query, memory_types?, limit?)
memory_write(workspace, memory_type, title, content, source_type?, source_ref?, module_path?, tags?, importance?, confidence?)
memory_list_recent(workspace, memory_types?, limit?)
memory_load_context(workspace, user_request, memory_types?, limit?, max_content_chars?)
```

Always pass a registered project workspace path when possible. If a path inside a registered project is passed, the MCP tools resolve it back to the registered project root before reading or writing. This keeps temporary Codex conversation folders and project subdirectories from becoming accidental memory projects.

## Manual Configuration

Set environment variables when configuring manually:

```powershell
$env:PPT_AGENT_VECTOR_MEMORY = "1"
$env:PPT_AGENT_MEMORY_DATABASE_URL = "postgresql://ppt_agent:ppt_agent@127.0.0.1:54329/ppt_agent_memory"
$env:PPT_AGENT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
$env:PPT_AGENT_MEMORY_POOL_MIN = "2"
$env:PPT_AGENT_MEMORY_POOL_MAX = "10"
$env:PPT_AGENT_MEMORY_CONNECT_TIMEOUT = "5"
$env:PPT_AGENT_MEMORY_USE_POOL = "1"
$env:PPT_AGENT_MEMORY_PROJECTS_FILE = "C:\Users\22834\.codex\agent-long-memory-projects.json"
$env:PPT_AGENT_MEMORY_ALLOWED_WORKSPACES = "E:\workspace\Tools;E:\workspace\AnotherProject"
```

Records are isolated by the resolved workspace scope, and searches filter by `project_id`.

By default, the resolved workspace scope is the workspace path passed by the agent. This keeps different project directories isolated even when they live under the same parent git repository. Set `PPT_AGENT_MEMORY_PROJECT_ROOT` to force a specific project root, or set `PPT_AGENT_MEMORY_SCOPE_MODE=git` if you intentionally want the git root to be the project scope.

Use `PPT_AGENT_MEMORY_PROJECTS_FILE` for dynamic project access. The file is read on every access check, so adding or removing a workspace takes effect without restarting the MCP server:

```json
{
  "allowed_workspaces": [
    "E:\\workspace\\Tools",
    "E:\\workspace\\AnotherProject"
  ]
}
```

If `PPT_AGENT_MEMORY_PROJECTS_FILE` is not set, the default is `%CODEX_HOME%\agent-long-memory-projects.json`, falling back to `%USERPROFILE%\.codex\agent-long-memory-projects.json`. `PPT_AGENT_MEMORY_ALLOWED_WORKSPACES` remains supported as a semicolon-separated environment allowlist. If both the JSON file and environment variable are empty, all workspaces may use the memory backend.

## Monitor

Run the local monitor from the package directory:

```powershell
python .\run_monitor.py
```

The monitor serves the FastAPI dashboard from `agent_long_memory.monitor_api`.

On Windows, use the bundled startup script to set the memory environment automatically:

```powershell
E:\workspace\Tools\agent-long-memory\scripts\start-monitor.ps1
```

To show or allow multiple projects in the monitor:

```powershell
E:\workspace\Tools\agent-long-memory\scripts\start-monitor.ps1 `
  -ProjectsFile "C:\Users\22834\.codex\agent-long-memory-projects.json"
```

Then open:

```text
http://127.0.0.1:8081
```

## Startup Wrapper

Start an agent with memory enabled from the Windows startup wrapper:

```powershell
.\scripts\start-agent-with-memory.ps1 `
  -Workspace E:\workspace\MyProject `
  -MemoryPython E:\workspace\MyProject\.venv\Scripts\python.exe `
  -AgentExecutable E:\workspace\MyProject\.venv\Scripts\python.exe `
  -AgentArgsJson '["-m", "my_agent"]'
```

When arguments contain PowerShell-sensitive tokens, pass base64-encoded JSON instead:

```powershell
$argsJson = '["-m", "my_agent"]'
$argsBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($argsJson))
.\scripts\start-agent-with-memory.ps1 -Workspace E:\workspace\MyProject -AgentExecutable E:\workspace\MyProject\.venv\Scripts\python.exe -AgentArgsBase64 $argsBase64
```

The wrapper sets `PPT_AGENT_VECTOR_MEMORY`, `PPT_AGENT_MEMORY_DATABASE_URL`, `PPT_AGENT_MEMORY_PROJECT_ROOT`, and `PPT_AGENT_MEMORY_SCOPE_MODE` before launching the agent. Pass each agent's own workspace to keep memory isolated per project.

Call `close_pool()` when a long-running process shuts down and you want to close pooled database connections explicitly.
