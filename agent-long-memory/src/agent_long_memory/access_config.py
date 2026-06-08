from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECTS_FILE_ENV = "PPT_AGENT_MEMORY_PROJECTS_FILE"
ALLOWED_WORKSPACES_ENV = "PPT_AGENT_MEMORY_ALLOWED_WORKSPACES"
DEFAULT_PROJECTS_FILENAME = "agent-long-memory-projects.json"


def default_projects_file() -> Path:
    configured = os.environ.get(PROJECTS_FILE_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    codex_home = os.environ.get("CODEX_HOME", "").strip()
    if codex_home:
        return Path(codex_home).expanduser().resolve() / DEFAULT_PROJECTS_FILENAME

    return Path.home() / ".codex" / DEFAULT_PROJECTS_FILENAME


def normalize_workspace(workspace: str | Path) -> Path:
    return Path(workspace or ".").expanduser().resolve()


def _paths_from_env() -> list[Path]:
    raw = os.environ.get(ALLOWED_WORKSPACES_ENV, "").strip()
    if not raw:
        return []
    return [normalize_workspace(part) for part in raw.split(";") if part.strip()]


def _read_projects_file(path: Path | None = None) -> dict[str, Any]:
    projects_file = path or default_projects_file()
    if not projects_file.exists():
        return {"allowed_workspaces": []}

    try:
        data = json.loads(projects_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"allowed_workspaces": []}

    if not isinstance(data, dict):
        return {"allowed_workspaces": []}
    allowed = data.get("allowed_workspaces", [])
    if not isinstance(allowed, list):
        allowed = []
    return {**data, "allowed_workspaces": [str(item) for item in allowed if str(item).strip()]}


def _write_projects_file(data: dict[str, Any], path: Path | None = None) -> Path:
    projects_file = path or default_projects_file()
    projects_file.parent.mkdir(parents=True, exist_ok=True)
    normalized = {
        **data,
        "allowed_workspaces": [
            str(normalize_workspace(item))
            for item in data.get("allowed_workspaces", [])
            if str(item).strip()
        ],
    }
    projects_file.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return projects_file


def allowed_workspaces() -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()

    for path in [*_paths_from_env(), *[normalize_workspace(item) for item in _read_projects_file().get("allowed_workspaces", [])]]:
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            paths.append(path)

    return paths


def workspace_allowed(workspace: str | Path) -> bool:
    resolved_workspace = normalize_workspace(workspace)
    allowed = allowed_workspaces()
    if not allowed:
        return True
    return any(resolved_workspace == root or root in resolved_workspace.parents for root in allowed)


def registered_workspace_for(workspace: str | Path) -> Path | None:
    resolved_workspace = normalize_workspace(workspace)
    matches = [
        root
        for root in allowed_workspaces()
        if resolved_workspace == root or root in resolved_workspace.parents
    ]
    if not matches:
        return None
    return max(matches, key=lambda path: len(path.parts))


def resolve_access_workspace(workspace: str | Path) -> Path:
    resolved_workspace = normalize_workspace(workspace)
    return registered_workspace_for(resolved_workspace) or resolved_workspace


def describe_workspace_access(workspace: str | Path) -> dict[str, Any]:
    resolved_workspace = normalize_workspace(workspace)
    matched = registered_workspace_for(resolved_workspace)
    return {
        "workspace": str(resolved_workspace),
        "allowed": workspace_allowed(resolved_workspace),
        "matched_project": str(matched) if matched else None,
        "effective_workspace": str(matched or resolved_workspace),
        "registered_projects": [str(path) for path in allowed_workspaces()],
    }


def list_registered_workspaces() -> dict[str, Any]:
    projects_file = default_projects_file()
    file_data = _read_projects_file(projects_file)
    file_paths = [normalize_workspace(item) for item in file_data.get("allowed_workspaces", [])]
    env_paths = _paths_from_env()

    return {
        "projects_file": str(projects_file),
        "allowlist_enabled": bool(file_paths or env_paths),
        "allowed_workspaces": [str(path) for path in allowed_workspaces()],
        "file_workspaces": [str(path) for path in file_paths],
        "env_workspaces": [str(path) for path in env_paths],
    }


def add_registered_workspace(workspace: str | Path) -> dict[str, Any]:
    projects_file = default_projects_file()
    data = _read_projects_file(projects_file)
    workspace_path = normalize_workspace(workspace)
    existing = [normalize_workspace(item) for item in data.get("allowed_workspaces", [])]
    key = os.path.normcase(str(workspace_path))
    changed = key not in {os.path.normcase(str(path)) for path in existing}
    if changed:
        existing.append(workspace_path)
        data["allowed_workspaces"] = [str(path) for path in existing]
        _write_projects_file(data, projects_file)

    return {
        "projects_file": str(projects_file),
        "workspace": str(workspace_path),
        "added": changed,
        "allowed_workspaces": [str(path) for path in allowed_workspaces()],
    }


def remove_registered_workspace(workspace: str | Path) -> dict[str, Any]:
    projects_file = default_projects_file()
    data = _read_projects_file(projects_file)
    workspace_path = normalize_workspace(workspace)
    target_key = os.path.normcase(str(workspace_path))
    existing = [normalize_workspace(item) for item in data.get("allowed_workspaces", [])]
    remaining = [path for path in existing if os.path.normcase(str(path)) != target_key]
    changed = len(remaining) != len(existing)
    if changed:
        data["allowed_workspaces"] = [str(path) for path in remaining]
        _write_projects_file(data, projects_file)

    return {
        "projects_file": str(projects_file),
        "workspace": str(workspace_path),
        "removed": changed,
        "allowed_workspaces": [str(path) for path in allowed_workspaces()],
    }
