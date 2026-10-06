"""Immutable data structures shared across the audit pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

HISTORY_SCOPES = ("branches-and-tags", "all-refs")

Row = Mapping[str, object]
"""A canonical table row: CSV column name to integer, decimal string, or text value."""


def as_int(value: object) -> int:
    """Convert a canonical integer cell (``int`` or decimal string) to ``int``."""
    return value if isinstance(value, int) else int(str(value))


@dataclass(frozen=True)
class LocToolConfig:
    command: tuple[str, ...] = ("cloc",)
    expected_version: str = ""
    expected_sha256: str = ""


@dataclass(frozen=True)
class DeveloperConfig:
    exclude_patterns: tuple[str, ...] = ()
    aliases: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RepositorySpec:
    name: str
    ref: str = "HEAD"
    expected_sha: str = ""
    path: Path | None = None
    url: str = ""
    fetch: bool = True

    @property
    def is_remote(self) -> bool:
        return bool(self.url)


@dataclass(frozen=True)
class AuditConfig:
    config_path: Path
    title: str
    output_dir: Path
    workspace_dir: Path
    generate_pdf: bool
    require_clean: bool
    history_scope: str
    loc: LocToolConfig
    developer: DeveloperConfig
    repositories: tuple[RepositorySpec, ...]


@dataclass(frozen=True)
class TreeEntry:
    path: str
    mode: str
    object_type: str
    object_id: str


@dataclass(frozen=True)
class SourceState:
    """Fingerprint of a source repository used to prove it was not modified."""

    status: str | None
    refs: str

    def describe(self) -> str:
        status = (
            "bare" if self.status is None else f"{len(self.status.splitlines())} status line(s)"
        )
        return f"{status}; {len(self.refs.splitlines())} ref(s)"


@dataclass(frozen=True)
class PreparedRepository:
    spec: RepositorySpec
    git_path: Path
    snapshot_path: Path
    resolved_ref: str
    commit_sha: str
    tracked_files: tuple[str, ...]
    file_modes: dict[str, str]
    snapshot_files: dict[str, Path]
    history_revisions: tuple[str, ...]
    initial_state: SourceState
