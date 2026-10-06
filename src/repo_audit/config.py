"""Strict TOML configuration loading and validation."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .models import HISTORY_SCOPES, AuditConfig, DeveloperConfig, LocToolConfig, RepositorySpec


class ConfigError(ValueError):
    """Raised when audit configuration is invalid or ambiguous."""


SCHEMA_VERSION = 1
DEFAULT_TITLE = "Deterministic Repository Audit"

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY_PATTERN = re.compile(r"^.+ <[^<>]+>$")

_TOP_LEVEL_KEYS = {
    "schema_version",
    "title",
    "output_dir",
    "workspace_dir",
    "generate_pdf",
    "require_clean",
    "history_scope",
    "loc",
    "developer",
    "repositories",
}
_REPOSITORY_KEYS = {"name", "path", "url", "ref", "expected_sha", "fetch"}


def _reject_unknown(table: dict[str, Any], allowed: Iterable[str], context: str) -> None:
    unknown = sorted(set(table) - set(allowed))
    if unknown:
        raise ConfigError(f"Unknown {context} key(s): {', '.join(unknown)}")


def _string(value: Any, context: str, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError(f"{context} must be a string")
    return value.strip()


def _boolean(value: Any, context: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"{context} must be true or false")
    return value


def _table(value: Any, context: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{context} must be a TOML table")
    return value


def _resolve(base: Path, value: Any, context: str) -> Path:
    text = _string(value, context)
    if not text:
        raise ConfigError(f"{context} cannot be empty")
    path = Path(text).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def _nested(first: Path, second: Path) -> bool:
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


def _command(value: Any) -> tuple[str, ...]:
    if value is None:
        return ("cloc",)
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if (
        isinstance(value, list)
        and value
        and all(isinstance(item, str) and item.strip() for item in value)
    ):
        return tuple(item.strip() for item in value)
    raise ConfigError("loc.command must be a non-empty string or array of strings")


def _loc(payload: dict[str, Any]) -> LocToolConfig:
    _reject_unknown(payload, {"command", "expected_version", "expected_sha256"}, "loc")
    loc = LocToolConfig(
        command=_command(payload.get("command")),
        expected_version=_string(payload.get("expected_version"), "loc.expected_version"),
        expected_sha256=_string(payload.get("expected_sha256"), "loc.expected_sha256").lower(),
    )
    if loc.expected_sha256 and not _SHA256_PATTERN.fullmatch(loc.expected_sha256):
        raise ConfigError("loc.expected_sha256 must contain exactly 64 hexadecimal characters")
    return loc


def _developer(payload: dict[str, Any]) -> DeveloperConfig:
    _reject_unknown(payload, {"exclude_patterns", "aliases"}, "developer")
    patterns = payload.get("exclude_patterns", [])
    if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
        raise ConfigError("developer.exclude_patterns must be an array of regex strings")
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as error:
            raise ConfigError(f"Invalid developer exclusion regex {pattern!r}: {error}") from error
    aliases = payload.get("aliases", {})
    if not isinstance(aliases, dict) or not all(
        isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip()
        for key, value in aliases.items()
    ):
        raise ConfigError(
            "developer.aliases must map exact identity strings to canonical identity strings"
        )
    normalized = {key.strip(): value.strip() for key, value in aliases.items()}
    invalid = [
        identity
        for pair in normalized.items()
        for identity in pair
        if not _IDENTITY_PATTERN.fullmatch(identity)
    ]
    if invalid:
        raise ConfigError(
            "developer.aliases keys and values must use 'Name <email>' format: "
            + ", ".join(repr(value) for value in invalid)
        )
    chained = sorted(set(normalized) & set(normalized.values()))
    if chained:
        raise ConfigError(
            "developer.aliases must map directly to a canonical identity; chained aliases: "
            + ", ".join(repr(value) for value in chained)
        )
    return DeveloperConfig(exclude_patterns=tuple(patterns), aliases=normalized)


def _repository(item: Any, index: int, base: Path) -> RepositorySpec:
    context = f"repositories[{index}]"
    if not isinstance(item, dict):
        raise ConfigError(f"{context} must be a TOML table")
    _reject_unknown(item, _REPOSITORY_KEYS, context)
    name = _string(item.get("name"), f"{context}.name")
    if not _NAME_PATTERN.fullmatch(name):
        raise ConfigError(f"{context}.name must match {_NAME_PATTERN.pattern}; got {name!r}")
    raw_path = _string(item.get("path"), f"{context}.path")
    url = _string(item.get("url"), f"{context}.url")
    if bool(raw_path) == bool(url):
        raise ConfigError(f"{context} must define exactly one of path or url")
    if url and urlsplit(url).password:
        raise ConfigError(
            f"{context}.url must not embed credentials; use a Git credential helper instead"
        )
    expected_sha = _string(item.get("expected_sha"), f"{context}.expected_sha").lower()
    if expected_sha and not _SHA_PATTERN.fullmatch(expected_sha):
        raise ConfigError(f"{context}.expected_sha must be a full 40- or 64-character commit SHA")
    return RepositorySpec(
        name=name,
        path=_resolve(base, raw_path, f"{context}.path") if raw_path else None,
        url=url,
        ref=_string(item.get("ref"), f"{context}.ref", "HEAD") or "HEAD",
        expected_sha=expected_sha,
        fetch=_boolean(item.get("fetch"), f"{context}.fetch", bool(url)),
    )


def load_config(path: str | Path) -> AuditConfig:
    config_path = Path(path).expanduser().resolve()
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Could not read TOML config {config_path}: {error}") from error

    _reject_unknown(payload, _TOP_LEVEL_KEYS, "top-level")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ConfigError(f"schema_version must be {SCHEMA_VERSION}")

    base = config_path.parent
    output_dir = _resolve(base, payload.get("output_dir", "../repo-audit-output"), "output_dir")
    workspace_dir = _resolve(
        base, payload.get("workspace_dir", "../repo-audit-workspace"), "workspace_dir"
    )
    if _nested(output_dir, workspace_dir):
        raise ConfigError("output_dir and workspace_dir must be distinct, non-nested directories")

    history_scope = _string(payload.get("history_scope"), "history_scope", HISTORY_SCOPES[0])
    if history_scope not in HISTORY_SCOPES:
        raise ConfigError(f"history_scope must be one of: {', '.join(HISTORY_SCOPES)}")

    repository_payloads = payload.get("repositories")
    if not isinstance(repository_payloads, list) or not repository_payloads:
        raise ConfigError("At least one [[repositories]] table is required")
    repositories: list[RepositorySpec] = []
    names: set[str] = set()
    for index, item in enumerate(repository_payloads, start=1):
        repository = _repository(item, index, base)
        if repository.name.casefold() in names:
            raise ConfigError(f"Duplicate repository name: {repository.name}")
        names.add(repository.name.casefold())
        repositories.append(repository)

    return AuditConfig(
        config_path=config_path,
        title=_string(payload.get("title"), "title", DEFAULT_TITLE) or DEFAULT_TITLE,
        output_dir=output_dir,
        workspace_dir=workspace_dir,
        generate_pdf=_boolean(payload.get("generate_pdf"), "generate_pdf", False),
        require_clean=_boolean(payload.get("require_clean"), "require_clean", True),
        history_scope=history_scope,
        loc=_loc(_table(payload.get("loc"), "loc")),
        developer=_developer(_table(payload.get("developer"), "developer")),
        repositories=tuple(repositories),
    )
