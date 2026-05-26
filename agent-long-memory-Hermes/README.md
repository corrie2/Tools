# Agent Long Memory

Reusable workspace-scoped PostgreSQL/pgvector semantic memory with connection pooling and batch operations.

## Features

- **Connection Pooling**: Reuse database connections for better performance
- **Batch Operations**: Create/search multiple records in a single operation
- **Audit Logging**: Track all memory operations
- **Error Handling**: Custom exceptions with clear error messages
- **Project Isolation**: Memories are isolated by workspace/project

## Install

```bash
pip install -e /path/to/agent-long-memory
```

## Usage

### Basic Usage

```python
from pathlib import Path
from agent_long_memory import CreateMemoryRecordInput, search_semantic_memory, write_semantic_memory

workspace = Path.cwd()

# Write memory
write_semantic_memory(
    workspace,
    CreateMemoryRecordInput(
        memory_type="user_preference",
        title="Style preference",
        content="Use concise technical slides in this project.",
    ),
)

# Search memory
results = search_semantic_memory(workspace, "technical slide style")
```

### Batch Operations

```python
from pathlib import Path
from agent_long_memory import (
    CreateMemoryRecordInput,
    search_semantic_memory_batch,
    write_semantic_memory_batch,
)

workspace = Path.cwd()

# Batch write
records = [
    CreateMemoryRecordInput(
        memory_type="user_preference",
        title="Style 1",
        content="Use concise technical slides.",
    ),
    CreateMemoryRecordInput(
        memory_type="user_preference",
        title="Style 2",
        content="Use professional color scheme.",
    ),
]
results = write_semantic_memory_batch(workspace, records)

# Batch search
queries = ["technical slides", "color scheme"]
search_results = search_semantic_memory_batch(workspace, queries)
```

### Connection Pool Management

```python
from agent_long_memory import close_pool

# Close connection pool when done
close_pool()
```

## Configuration

Set environment variables:

```bash
export PPT_AGENT_VECTOR_MEMORY=1
export PPT_AGENT_MEMORY_DATABASE_URL="postgresql://user:pass@localhost/dbname"
export PPT_AGENT_EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"  # Optional
export PPT_AGENT_MEMORY_POOL_MIN=2  # Optional, default: 2
export PPT_AGENT_MEMORY_POOL_MAX=10  # Optional, default: 10
```

## Error Handling

```python
from agent_long_memory import (
    MemoryDbError,
    MemoryNotFoundError,
    MemoryValidationError,
)

try:
    write_semantic_memory(workspace, record)
except MemoryValidationError as e:
    print(f"Validation error: {e}")
except MemoryDbError as e:
    print(f"Database error: {e}")
```

## Changelog

### v0.2.0

- Added connection pooling with `psycopg_pool`
- Added batch operations: `write_semantic_memory_batch`, `search_semantic_memory_batch`
- Added custom exceptions: `MemoryNotFoundError`, `MemoryValidationError`
- Added audit logging
- Added connection pool management: `close_pool()`
