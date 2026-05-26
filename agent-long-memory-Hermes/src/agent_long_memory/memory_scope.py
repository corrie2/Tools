from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MemoryScope:
    name: str
    root_path: Path
    git_remote: str | None


ProjectScope = MemoryScope


def resolve_git_root(workspace: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return workspace.resolve()

    root = result.stdout.strip() if result.returncode == 0 else ""
    if not root:
        return workspace.resolve()
    return Path(root).resolve()


def resolve_git_remote(root_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root_path), "remote", "get-url", "origin"],
            capture_output=True,
            check=False,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    remote = result.stdout.strip() if result.returncode == 0 else ""
    return remote or None


def resolve_memory_scope(workspace: Path) -> MemoryScope:
    root_path = resolve_git_root(workspace)
    return MemoryScope(
        name=root_path.name,
        root_path=root_path,
        git_remote=resolve_git_remote(root_path),
    )


resolve_project_scope = resolve_memory_scope