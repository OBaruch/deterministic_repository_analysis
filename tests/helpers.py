"""Shared helpers for building throwaway Git repositories and audit configs in tests."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from repo_audit.models import LocToolConfig

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FAKE_CLOC = FIXTURES / "fake_cloc.py"
GIT_ENVIRONMENT = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_AUTHOR_NAME": "Example Developer",
    "GIT_AUTHOR_EMAIL": "developer@example.com",
    "GIT_COMMITTER_NAME": "Example Developer",
    "GIT_COMMITTER_EMAIL": "developer@example.com",
}


def command(*arguments: str, cwd: Path, env: Mapping[str, str] | None = None) -> str:
    return subprocess.run(
        arguments,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, **GIT_ENVIRONMENT, **(env or {})},
    ).stdout.strip()


def commit_files(
    repository: Path,
    files: Mapping[str, str | bytes],
    message: str = "change",
    *,
    author: str = "Example Developer <developer@example.com>",
    date: str = "2026-01-15T10:00:00+00:00",
) -> str:
    for relative, content in files.items():
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    command("git", "add", "--all", cwd=repository)
    name, email = author[:-1].split(" <")
    command(
        "git",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        message,
        cwd=repository,
        env={
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_DATE": date,
        },
    )
    return command("git", "rev-parse", "HEAD", cwd=repository)


def create_repository(
    root: Path, files: Mapping[str, str | bytes], name: str = "source"
) -> tuple[Path, str]:
    repository = root / name
    repository.mkdir(parents=True)
    command("git", "init", "--quiet", "-b", "main", cwd=repository)
    command("git", "config", "core.autocrlf", "false", cwd=repository)
    return repository, commit_files(repository, files, "initial")


def fake_loc_config() -> LocToolConfig:
    return LocToolConfig(command=(sys.executable, str(FAKE_CLOC)), expected_version="test-cloc-1")


def write_config(
    root: Path,
    repositories: str,
    *,
    extra: str = "",
    output: str = "output",
    workspace: str = "workspace",
) -> Path:
    path = root / "audit.toml"
    path.write_text(
        f"""
schema_version = 1
title = "Test Audit"
output_dir = "{(root / output).as_posix()}"
workspace_dir = "{(root / workspace).as_posix()}"
{extra}

[loc]
command = ["{Path(sys.executable).as_posix()}", "{FAKE_CLOC.as_posix()}"]
expected_version = "test-cloc-1"

{repositories}
""",
        encoding="utf-8",
    )
    return path


def local_repository_entry(name: str, path: Path, sha: str = "", ref: str = "main") -> str:
    return f"""
[[repositories]]
name = "{name}"
path = "{path.as_posix()}"
ref = "{ref}"
expected_sha = "{sha}"
fetch = false
"""
