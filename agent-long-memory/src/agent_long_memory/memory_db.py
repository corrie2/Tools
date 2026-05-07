from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_long_memory.memory_config import MemoryConfig, load_memory_config
from agent_long_memory.memory_scope import ProjectScope


class MemoryDbError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemoryProject:
    id: str
    name: str
    root_path: str
    git_remote: str | None


@dataclass(frozen=True)
class CreateMemoryRecordInput:
    memory_type: str
    title: str
    content: str
    source_type: str | None = None
    source_ref: str | None = None
    module_path: str | None = None
    tags: list[str] | None = None
    importance: float = 0.5
    confidence: float = 0.5


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    project_id: str
    memory_type: str
    title: str
    content: str
    source_type: str | None
    source_ref: str | None
    module_path: str | None
    tags: list[str]
    importance: float
    confidence: float


@dataclass(frozen=True)
class MemoryEmbedding:
    id: str
    record_id: str
    embedding_model: str
    embedding: list[float]
    created_at: object | None = None


@dataclass(frozen=True)
class MemorySearchResult:
    record: MemoryRecord
    similarity: float
    embedding_model: str


class PostgresMemoryStore:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        self.database_url = database_url

    @classmethod
    def from_config(cls, config: MemoryConfig | None = None) -> "PostgresMemoryStore":
        resolved = config or load_memory_config()
        if not resolved.database_url:
            raise MemoryDbError("PPT_AGENT_MEMORY_DATABASE_URL is not set")
        return cls(resolved.database_url)

    def upsert_project(self, scope: ProjectScope) -> str:
        config = MemoryConfig(enabled=True, database_url=self.database_url, embedding_model="")
        return ensure_memory_project(scope, config=config).id

    def add_record(self, project_id: str, record: CreateMemoryRecordInput) -> str:
        config = MemoryConfig(enabled=True, database_url=self.database_url, embedding_model="")
        project = MemoryProject(id=project_id, name="", root_path="", git_remote=None)
        return create_memory_record(project, record, config=config).id

    def add_embedding(self, record_id: str, embedding_model: str, embedding: list[float]) -> None:
        config = MemoryConfig(enabled=True, database_url=self.database_url, embedding_model="")
        upsert_memory_embedding(record_id, embedding_model=embedding_model, embedding=embedding, config=config)

    def search_by_embedding(
        self,
        *,
        project_id: str,
        embedding: list[float],
        memory_type: str | None = None,
        limit: int = 10,
    ) -> list[MemorySearchResult]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        params: list[Any] = [_format_pgvector_literal(embedding), project_id]
        memory_type_filter = ""
        if memory_type is not None:
            memory_type_filter = "AND r.memory_type = %s"
            params.append(memory_type)
        params.extend([_format_pgvector_literal(embedding), limit])
        query = f"""
            SELECT
                r.id,
                r.project_id,
                r.memory_type,
                r.title,
                r.content,
                r.source_type,
                r.source_ref,
                r.module_path,
                r.tags,
                r.importance,
                r.confidence,
                1 - (e.embedding <=> %s::vector) AS similarity,
                e.embedding_model
            FROM memory_records r
            JOIN memory_embeddings e ON e.record_id = r.id
            WHERE r.project_id = %s
              {memory_type_filter}
              AND r.superseded_by IS NULL
              AND (r.valid_until IS NULL OR r.valid_until > now())
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
        """
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [
            MemorySearchResult(record=_record_from_row(row), similarity=float(row[11]), embedding_model=row[12])
            for row in rows
        ]

    def _connect(self):
        config = MemoryConfig(enabled=True, database_url=self.database_url, embedding_model="")
        try:
            return connect_memory_db(config)
        except RuntimeError as exc:
            raise MemoryDbError(str(exc)) from exc


def connect_memory_db(config: MemoryConfig):
    if not config.database_url:
        raise ValueError("PPT_AGENT_MEMORY_DATABASE_URL is required")

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('psycopg is not installed. Install the memory extra first: pip install -e ".[memory]"') from exc

    return psycopg.connect(config.database_url)


def ensure_memory_project(scope: ProjectScope, *, config: MemoryConfig) -> MemoryProject:
    query = """
        INSERT INTO memory_projects (name, root_path, git_remote)
        VALUES (%s, %s, %s)
        ON CONFLICT (root_path)
        DO UPDATE SET name = EXCLUDED.name,
                      git_remote = EXCLUDED.git_remote,
                      updated_at = now()
        RETURNING id, name, root_path, git_remote
    """
    with connect_memory_db(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (scope.name, str(scope.root_path), scope.git_remote))
            row = cursor.fetchone()
        conn.commit()
    if not row:
        raise MemoryDbError("ensure_memory_project did not return a project")
    return MemoryProject(id=str(row[0]), name=row[1], root_path=row[2], git_remote=row[3])


def create_memory_record(
    project: MemoryProject,
    record: CreateMemoryRecordInput,
    *,
    config: MemoryConfig,
) -> MemoryRecord:
    _validate_record_input(record)
    query = """
        INSERT INTO memory_records (
            project_id,
            memory_type,
            title,
            content,
            source_type,
            source_ref,
            module_path,
            tags,
            importance,
            confidence
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id,
                  project_id,
                  memory_type,
                  title,
                  content,
                  source_type,
                  source_ref,
                  module_path,
                  tags,
                  importance,
                  confidence
    """
    params = (
        project.id,
        record.memory_type,
        record.title,
        record.content,
        record.source_type,
        record.source_ref,
        record.module_path,
        record.tags or [],
        record.importance,
        record.confidence,
    )
    with connect_memory_db(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        conn.commit()
    if not row:
        raise MemoryDbError("create_memory_record did not return a record")
    return _record_from_row(row)


def get_memory_record(record_id: str, *, project_id: str, config: MemoryConfig) -> MemoryRecord | None:
    if not str(project_id).strip():
        raise ValueError("project_id must be non-empty")
    query = """
        SELECT id,
               project_id,
               memory_type,
               title,
               content,
               source_type,
               source_ref,
               module_path,
               tags,
               importance,
               confidence
        FROM memory_records
        WHERE id = %s
          AND project_id = %s
    """
    with connect_memory_db(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (record_id, project_id))
            row = cursor.fetchone()
    if not row:
        return None
    return _record_from_row(row)


def list_memory_records(
    project: MemoryProject,
    *,
    memory_types: list[str] | None = None,
    limit: int = 20,
    config: MemoryConfig,
) -> list[MemoryRecord]:
    resolved_limit = min(max(limit, 1), 100)
    params: list[Any] = [project.id]
    memory_type_filter = ""
    if memory_types:
        memory_type_filter = "AND memory_type = ANY(%s)"
        params.append(memory_types)
    params.append(resolved_limit)
    query = f"""
        SELECT id,
               project_id,
               memory_type,
               title,
               content,
               source_type,
               source_ref,
               module_path,
               tags,
               importance,
               confidence
        FROM memory_records
        WHERE project_id = %s
          {memory_type_filter}
          AND superseded_by IS NULL
          AND (valid_until IS NULL OR valid_until > now())
        ORDER BY created_at DESC
        LIMIT %s
    """
    with connect_memory_db(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
    return [_record_from_row(row) for row in rows]


def upsert_memory_embedding(
    record_id: str,
    *,
    embedding_model: str,
    embedding: list[float],
    config: MemoryConfig,
) -> MemoryEmbedding:
    _validate_embedding_input(record_id, embedding_model=embedding_model, embedding=embedding)
    query = """
        INSERT INTO memory_embeddings (record_id, embedding_model, embedding)
        VALUES (%s, %s, %s::vector)
        ON CONFLICT (record_id, embedding_model) DO UPDATE
        SET embedding = EXCLUDED.embedding
        RETURNING id, record_id, embedding_model, embedding, created_at
    """
    embedding_literal = _format_pgvector_literal(embedding)
    with connect_memory_db(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (record_id, embedding_model, embedding_literal))
            row = cursor.fetchone()
        conn.commit()
    if not row:
        raise MemoryDbError("upsert_memory_embedding did not return an embedding")
    return _embedding_from_row(row)


def get_memory_embedding(
    record_id: str,
    *,
    embedding_model: str,
    project_id: str,
    config: MemoryConfig,
) -> MemoryEmbedding | None:
    if not str(record_id).strip():
        raise ValueError("record_id must be non-empty")
    if not embedding_model.strip():
        raise ValueError("embedding_model must be non-empty")
    if not str(project_id).strip():
        raise ValueError("project_id must be non-empty")
    query = """
        SELECT e.id, e.record_id, e.embedding_model, e.embedding, e.created_at
        FROM memory_embeddings e
        JOIN memory_records r ON r.id = e.record_id
        WHERE e.record_id = %s
          AND e.embedding_model = %s
          AND r.project_id = %s
    """
    with connect_memory_db(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (record_id, embedding_model, project_id))
            row = cursor.fetchone()
    if not row:
        return None
    return _embedding_from_row(row)


def search_memory_records_by_embedding(
    project: MemoryProject,
    *,
    query_embedding: list[float],
    embedding_model: str,
    memory_types: list[str] | None = None,
    limit: int = 8,
    config: MemoryConfig,
) -> list[MemorySearchResult]:
    if not project.id:
        raise ValueError("project.id must be non-empty")
    if not query_embedding:
        raise ValueError("query_embedding must be non-empty")
    if len(query_embedding) != 384:
        raise ValueError("query_embedding must contain exactly 384 values")
    if not embedding_model.strip():
        raise ValueError("embedding_model must be non-empty")

    resolved_limit = min(max(limit, 1), 20)
    query_vector = _format_pgvector_literal(query_embedding)
    params: list[Any] = [query_vector, project.id, embedding_model]
    memory_type_filter = ""
    if memory_types:
        memory_type_filter = "AND r.memory_type = ANY(%s)"
        params.append(memory_types)
    params.extend([query_vector, resolved_limit])
    query = f"""
        SELECT
            r.id,
            r.project_id,
            r.memory_type,
            r.title,
            r.content,
            r.source_type,
            r.source_ref,
            r.module_path,
            r.tags,
            r.importance,
            r.confidence,
            1 - (e.embedding <=> %s::vector) AS similarity,
            e.embedding_model
        FROM memory_records r
        JOIN memory_embeddings e ON e.record_id = r.id
        WHERE r.project_id = %s
          AND e.embedding_model = %s
          {memory_type_filter}
          AND r.superseded_by IS NULL
          AND (r.valid_until IS NULL OR r.valid_until > now())
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
    """
    with connect_memory_db(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
    return [
        MemorySearchResult(
            record=_record_from_row(row),
            similarity=float(row[11]),
            embedding_model=row[12],
        )
        for row in rows
    ]


def _validate_record_input(record: CreateMemoryRecordInput) -> None:
    if not record.memory_type.strip():
        raise ValueError("memory_type must be non-empty")
    if not record.title.strip():
        raise ValueError("title must be non-empty")
    if not record.content.strip():
        raise ValueError("content must be non-empty")
    if not 0 <= record.importance <= 1:
        raise ValueError("importance must be between 0 and 1")
    if not 0 <= record.confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")


def _validate_embedding_input(record_id: str, *, embedding_model: str, embedding: list[float]) -> None:
    if not str(record_id).strip():
        raise ValueError("record_id must be non-empty")
    if not embedding_model.strip():
        raise ValueError("embedding_model must be non-empty")
    if not embedding:
        raise ValueError("embedding must be non-empty")
    if len(embedding) != 384:
        raise ValueError("embedding must contain exactly 384 values")


def _format_pgvector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in embedding) + "]"


def _vector_literal(values: list[float]) -> str:
    return _format_pgvector_literal(values)


def _record_from_row(row: tuple[Any, ...]) -> MemoryRecord:
    return MemoryRecord(
        id=str(row[0]),
        project_id=str(row[1]),
        memory_type=row[2],
        title=row[3],
        content=row[4],
        source_type=row[5],
        source_ref=row[6],
        module_path=row[7],
        tags=list(row[8] or []),
        importance=float(row[9]),
        confidence=float(row[10]),
    )


def _embedding_from_row(row: tuple[Any, ...]) -> MemoryEmbedding:
    return MemoryEmbedding(
        id=str(row[0]),
        record_id=str(row[1]),
        embedding_model=row[2],
        embedding=_coerce_embedding(row[3]),
        created_at=row[4],
    )


def _coerce_embedding(value: Any) -> list[float]:
    if isinstance(value, str):
        stripped = value.strip().removeprefix("[").removesuffix("]")
        if not stripped:
            return []
        return [float(part.strip()) for part in stripped.split(",")]
    return [float(part) for part in value]

