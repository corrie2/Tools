---
name: agent-long-memory
description: "Project-scoped long-term semantic memory for Codex using the local agent_long_memory MCP tools. Use when Codex is working in a project and may benefit from prior project context: at the start of substantial coding, debugging, design, review, documentation, research, or multi-step work; when the user asks to remember, recall, continue, use history, check prior decisions, or preserve project knowledge; before editing unfamiliar code; and after work that creates durable preferences, decisions, implementation notes, pitfalls, or session summaries. Do not use for tiny one-off answers, secrets, credentials, transient logs, or cross-project/global memory sharing."
---

# Agent Long Memory

Use the local `agent_long_memory` MCP server as a project-scoped long-term memory layer. The memory database is shared, but every read and write must pass the active workspace path so records stay isolated by project.

## Decision Policy

Before substantial project work, decide whether memory would likely help. Prefer checking memory when the task involves code changes, debugging, architecture, tests, documentation, research notes, project conventions, user preferences, or continuation from earlier sessions.

Skip memory for tiny questions, pure chit-chat, throwaway commands, requests with all needed context in the prompt, or anything where a memory lookup would add noise.

When unsure and the task is project-specific, do one lightweight `memory_load_context` call. Treat an empty result as normal and continue.

## Read Workflow

Use MCP tools when available:

```text
memory_status(workspace)
memory_access_list()
memory_access_add(workspace)
memory_access_remove(workspace)
memory_access_resolve(workspace)
memory_load_context(workspace, user_request, memory_types?, limit?)
memory_search(workspace, query, memory_types?, limit?)
memory_list_recent(workspace, memory_types?, limit?)
```

First decide the active memory project. Use only a registered project root, not a Codex temporary conversation folder. If the current working directory is inside a registered project, use the matched registered project root. If the user explicitly names a registered project path, use that project. If neither is true, skip memory and ask which registered project to use when memory is necessary.

For most tasks after resolving a registered project, start with:

```text
memory_load_context(workspace=<active workspace>, user_request=<current user request>, limit=5)
```

Use focused `memory_search` calls when the first result is empty or the task mentions a specific module, decision, convention, error, or prior discussion.

Only use retrieved memories when they are clearly relevant to the current workspace and task. If memory conflicts with the current repository, user message, or observed files, trust the current evidence and mention the mismatch only if it matters.

## Write Workflow

Use `memory_write` only for durable information that should help future sessions in the same project:

```text
memory_write(workspace, memory_type, title, content, source_type?, source_ref?, module_path?, tags?, importance?, confidence?)
```

Good memory types:

```text
user_preference
project_fact
decision
implementation_note
pitfall
session_summary
```

Write directly when the user says "记住", "remember", "以后", or explicitly asks to save something. Otherwise, write sparingly after meaningful work, using a concise summary rather than raw chat.

Do not store secrets, credentials, private tokens, raw logs, full chat transcripts, temporary errors, or facts that are likely to become stale quickly. Do not write cross-project memories.

## Project Isolation

Always use the registered project workspace path. Never invent or reuse a `project_id`. Treat different registered workspace directories as separate projects even when they share the same database.

Do not use `C:\Users\<user>\Documents\Codex\...` temporary conversation directories as memory projects unless the user explicitly registers that directory as a project.

If there is no clear registered project, skip memory unless the user explicitly asks to use a specific registered project path.

When the user asks to enable or disable memory for a project, use the access tools if available:

```text
memory_access_add(workspace)
memory_access_remove(workspace)
memory_access_list()
memory_access_resolve(workspace)
```

If those tools are not available in the current session, update the configured projects file directly. The default file is `%CODEX_HOME%\agent-long-memory-projects.json`, falling back to `%USERPROFILE%\.codex\agent-long-memory-projects.json`.
