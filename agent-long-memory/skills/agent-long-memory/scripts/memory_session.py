from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def _bootstrap_local_package() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    src_path = repo_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=_json_default))


def _write_result_payload(result: Any) -> dict[str, Any]:
    payload = {
        "project": result.project,
        "record": result.record,
        "embedding": None,
    }
    if result.embedding is not None:
        payload["embedding"] = {
            "id": result.embedding.id,
            "record_id": result.embedding.record_id,
            "embedding_model": result.embedding.embedding_model,
            "dimensions": len(result.embedding.embedding),
            "created_at": result.embedding.created_at,
        }
    return payload


def _load_runtime():
    _bootstrap_local_package()
    from agent_long_memory import load_memory_config, resolve_project_scope

    return load_memory_config, resolve_project_scope


def _status(args: argparse.Namespace) -> int:
    load_memory_config, resolve_project_scope = _load_runtime()
    workspace = Path(args.workspace).resolve()
    config = load_memory_config()
    scope = resolve_project_scope(workspace)
    _print_json(
        {
            "ok": True,
            "enabled": config.enabled and bool(config.database_url),
            "configured": {
                "vector_memory": config.enabled,
                "database_url": bool(config.database_url),
                "embedding_model": config.embedding_model,
            },
            "scope": asdict(scope),
        }
    )
    return 0


def _enable(args: argparse.Namespace) -> int:
    _bootstrap_local_package()
    from agent_long_memory import enable_long_memory_for_agent

    status = enable_long_memory_for_agent(
        Path(args.workspace),
        database_url=args.database_url,
        initialize_database=not args.skip_init_db,
        set_project_root_env=not args.no_project_root_env,
    )
    _print_json(
        {
            "ok": True,
            "enabled": status.enabled,
            "initialized": status.initialized,
            "configured": {
                "vector_memory": status.config.enabled,
                "database_url": bool(status.config.database_url),
                "embedding_model": status.config.embedding_model,
            },
            "scope": status.scope,
        }
    )
    return 0


def _search(args: argparse.Namespace) -> int:
    _bootstrap_local_package()
    from agent_long_memory import load_memory_config, search_semantic_memory

    workspace = Path(args.workspace).resolve()
    config = load_memory_config()
    if not config.enabled or not config.database_url:
        _print_json({"ok": True, "enabled": False, "results": []})
        return 0

    results = search_semantic_memory(
        workspace,
        args.query,
        config=config,
        memory_types=args.memory_type,
        limit=args.limit,
    )
    _print_json({"ok": True, "enabled": True, "results": results})
    return 0


def _write(args: argparse.Namespace) -> int:
    _bootstrap_local_package()
    from agent_long_memory import CreateMemoryRecordInput, load_memory_config, write_semantic_memory

    workspace = Path(args.workspace).resolve()
    config = load_memory_config()
    if not config.enabled or not config.database_url:
        _print_json({"ok": True, "enabled": False, "written": False})
        return 0

    result = write_semantic_memory(
        workspace,
        CreateMemoryRecordInput(
            memory_type=args.memory_type,
            title=args.title,
            content=args.content,
            source_type=args.source_type,
            source_ref=args.source_ref,
            module_path=args.module_path,
            tags=args.tag or [],
            importance=args.importance,
            confidence=args.confidence,
        ),
        config=config,
        create_embedding=not args.no_embedding,
    )
    _print_json({"ok": True, "enabled": True, "written": True, "result": _write_result_payload(result)})
    return 0


def _init_db(args: argparse.Namespace) -> int:
    _bootstrap_local_package()
    from agent_long_memory import initialize_memory_database, load_memory_config

    config = load_memory_config()
    if not config.database_url:
        _print_json({"ok": False, "enabled": config.enabled, "error": "PPT_AGENT_MEMORY_DATABASE_URL is required"})
        return 2

    initialize_memory_database(config=config)
    _print_json({"ok": True, "initialized": True})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project-scoped agent long-memory helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status")
    status.add_argument("--workspace", required=True)
    status.set_defaults(func=_status)

    enable = subparsers.add_parser("enable")
    enable.add_argument("--workspace", required=True)
    enable.add_argument("--database-url")
    enable.add_argument("--skip-init-db", action="store_true")
    enable.add_argument("--no-project-root-env", action="store_true")
    enable.set_defaults(func=_enable)

    search = subparsers.add_parser("search")
    search.add_argument("--workspace", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--memory-type", action="append")
    search.add_argument("--limit", type=int, default=8)
    search.set_defaults(func=_search)

    write = subparsers.add_parser("write")
    write.add_argument("--workspace", required=True)
    write.add_argument("--memory-type", required=True)
    write.add_argument("--title", required=True)
    write.add_argument("--content", required=True)
    write.add_argument("--source-type", default="agent")
    write.add_argument("--source-ref")
    write.add_argument("--module-path")
    write.add_argument("--tag", action="append")
    write.add_argument("--importance", type=float, default=0.5)
    write.add_argument("--confidence", type=float, default=0.5)
    write.add_argument("--no-embedding", action="store_true")
    write.set_defaults(func=_write)

    init_db = subparsers.add_parser("init-db")
    init_db.set_defaults(func=_init_db)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
