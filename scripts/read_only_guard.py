"""PreToolUse hook that keeps audited repositories read-only during agent-led audits.

Usage::

    python scripts/read_only_guard.py [--strict] [--config PATH]

The hook reads one tool-call payload (JSON) from standard input. Allowed calls
exit 0 without output. Denied calls write the reason to standard error and exit
with code 2, the blocking convention shared by Claude Code, Codex, GitHub
Copilot CLI, and the VS Code agent harness. A malformed payload is denied too
(fail closed).

Protected locations come from the audit configuration: every local source
repository, the external workspace (mirrors and snapshots), and the output
directory, whose generated data must never be edited by hand. In ``--strict``
mode, used by the audit agents, any mutating Git command is denied wherever it
targets.

This is a guardrail for cooperative agents, not a sandbox. Combine it with
operating-system permissions for high-assurance use.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11: refuse to guess which paths are protected.
    tomllib = None  # type: ignore[assignment]

DENY_EXIT_CODE = 2
# Same defaults as the toolkit's configuration loader.
DEFAULT_DIRECTORIES = (
    ("workspace_dir", "../repo-audit-workspace", "audit workspace"),
    ("output_dir", "../repo-audit-output", "audit output"),
)
SHELL_TOOLS = frozenset(
    {
        "bash",
        "exec_command",
        "local_shell",
        "powershell",
        "run_in_terminal",
        "runinterminal",
        "shell",
        "terminal",
    }
)
EDIT_TOOL_MARKERS = ("edit", "write", "create", "delete", "replace", "patch", "rename", "move")
PATH_KEYS = (
    "file_path",
    "filePath",
    "notebook_path",
    "notebookPath",
    "path",
    "paths",
    "files",
    "target_file",
    "targetFile",
    "destination",
    "new_path",
    "old_path",
    "uri",
)
PATCH_HEADER = re.compile(r"(?m)^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$")

GIT_READ_ONLY = frozenset(
    {
        "annotate", "archive", "blame", "cat-file", "check-attr", "check-ignore",
        "check-mailmap", "check-ref-format", "cherry", "count-objects", "describe", "diff",
        "diff-files", "diff-index", "diff-tree", "for-each-ref", "grep", "help", "log",
        "ls-files", "ls-remote", "ls-tree", "merge-base", "name-rev", "range-diff",
        "rev-list", "rev-parse", "shortlog", "show", "show-branch", "show-ref", "status",
        "var", "verify-commit", "verify-tag", "version", "whatchanged",
    }
)  # fmt: skip
GIT_OPTIONS_WITH_VALUE = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
)
BRANCH_WRITE = frozenset(
    {
        "-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-f", "--force",
        "-u", "--set-upstream-to", "--unset-upstream", "--edit-description", "-t", "--track",
        "--create-reflog",
    }
)  # fmt: skip
BRANCH_LIST = frozenset(
    {
        "-l", "--list", "-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose",
        "--show-current", "--contains", "--no-contains", "--merged", "--no-merged",
        "--points-at", "--format", "--sort", "--column", "--no-column", "--color",
        "--no-color", "--abbrev", "--no-abbrev", "-i", "--ignore-case", "--omit-empty",
    }
)  # fmt: skip
TAG_WRITE = frozenset(
    {
        "-a", "--annotate", "-s", "--sign", "-u", "--local-user", "-f", "--force", "-d",
        "--delete", "-m", "--message", "-F", "--file", "-e", "--edit",
    }
)  # fmt: skip
TAG_LIST = frozenset(
    {
        "-l", "--list", "-n", "--contains", "--no-contains", "--merged", "--no-merged",
        "--points-at", "--sort", "--format", "--column", "--no-column", "--color", "-i",
        "--ignore-case", "--omit-empty", "-v", "--verify",
    }
)  # fmt: skip
CONFIG_WRITE = frozenset(
    {
        "--add", "--unset", "--unset-all", "--replace-all", "--rename-section",
        "--remove-section", "-e", "--edit", "set", "unset", "rename-section",
        "remove-section", "edit",
    }
)  # fmt: skip
CONFIG_READ = frozenset(
    {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "-l", "--list", "get", "list"}
)
CONFIG_OPTIONS_WITH_VALUE = frozenset(
    {"-f", "--file", "--blob", "--type", "--default", "--comment"}
)
READ_ONLY_SUBCOMMANDS = {
    "stash": {"list", "show"},
    "notes": {"", "list", "show"},
    "worktree": {"list"},
    "remote": {"", "show", "get-url"},
    "submodule": {"", "status", "summary"},
    "lfs": {"env", "ls-files", "status", "version"},
    "sparse-checkout": {"list"},
}

MUTATING_PROGRAMS = frozenset(
    {
        "ac", "add-content", "attrib", "chgrp", "chmod", "chown", "clc", "clear-content",
        "copy", "copy-item", "cp", "cpi", "dd", "del", "erase", "install", "ln", "md",
        "mi", "mkdir", "mklink", "move", "move-item", "mv", "new-item", "ni", "out-file",
        "patch", "rd", "ren", "rename", "rename-item", "remove-item", "ri", "rm", "rmdir", "rni",
        "robocopy", "rsync", "sc", "set-content", "shred", "tee", "touch", "truncate",
        "unlink", "xcopy",
    }
)  # fmt: skip
IN_PLACE_EDITORS = {"sed": ("-i", "--in-place"), "perl": ("-i", "-pi")}
COMMAND_PREFIXES = frozenset({"builtin", "command", "env", "exec", "nice", "nohup", "sudo", "time"})
CHANGE_DIRECTORY = frozenset({"cd", "chdir", "pushd", "set-location", "sl"})
NULL_DEVICES = frozenset({"/dev/null", "nul", "$null"})

_TOKEN = re.compile(
    r"""(?P<op>\n|&&|\|\||[;&|()])"""
    r"""|(?P<redirect>\d*>>?(?:&\d+|&-)?|<)"""
    r"""|(?P<word>(?:[^\s;&|()<>"'`]|"(?:[^"\\]|\\.)*"|'[^']*'|`[^`]*`)+)"""
)


@dataclass(frozen=True)
class ProtectedRoot:
    path: Path
    kind: str


def _absolute(value: str, base: Path) -> Path:
    # Treat both separators alike so Windows-style paths are recognized on every platform.
    path = Path(value.removeprefix("file://").replace("\\", "/")).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def _inside(path: Path, roots: Iterable[ProtectedRoot]) -> ProtectedRoot | None:
    for root in roots:
        try:
            if path.resolve().is_relative_to(root.path):
                return root
        except (OSError, ValueError):
            continue
    return None


class UnreadableConfigError(RuntimeError):
    """Raised when an existing audit configuration cannot be parsed."""


def protected_roots(config_path: Path) -> tuple[ProtectedRoot, ...]:
    if not config_path.is_file():
        return ()
    if tomllib is None:
        raise UnreadableConfigError("Python 3.11 or newer is required to read audit.toml")
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise UnreadableConfigError(f"cannot read {config_path}: {error}") from error
    base = config_path.parent
    roots: list[ProtectedRoot] = []
    for repository in payload.get("repositories", []):
        path = repository.get("path") if isinstance(repository, dict) else None
        if isinstance(path, str) and path.strip():
            roots.append(ProtectedRoot(_absolute(path.strip(), base), "source repository"))
    for key, default, kind in DEFAULT_DIRECTORIES:
        value = payload.get(key, default)
        if isinstance(value, str) and value.strip():
            roots.append(ProtectedRoot(_absolute(value.strip(), base), kind))
    return tuple(roots)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            item for key in ("path", "filePath", "file_path") for item in _strings(value.get(key))
        ]
    if isinstance(value, list):
        return [item for element in value for item in _strings(element)]
    return []


def _edit_paths(tool_input: Any, cwd: Path) -> list[Path]:
    if not isinstance(tool_input, dict):
        return []
    values = [item for key in PATH_KEYS for item in _strings(tool_input.get(key))]
    for key in ("command", "input", "patch"):
        text = tool_input.get(key)
        if isinstance(text, list):
            text = "\n".join(str(item) for item in text)
        if isinstance(text, str):
            values.extend(match.strip() for match in PATCH_HEADER.findall(text))
    return [_absolute(value, cwd) for value in values if value.strip()]


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        token = token[1:-1]
    return re.sub(r"""(?<!\\)["']""", "", token)


def tokenize(command: str) -> list[list[tuple[str, str]]]:
    """Split a shell command into simple-command segments of (kind, text) tokens."""
    segments: list[list[tuple[str, str]]] = [[]]
    for match in _TOKEN.finditer(command):
        kind = match.lastgroup or "word"
        text = match.group(kind)
        if kind == "op":
            segments.append([])
        else:
            segments[-1].append((kind, _unquote(text) if kind == "word" else text))
    return [segment for segment in segments if segment]


def _program(word: str) -> str:
    name = re.split(r"[\\/]", word)[-1].casefold()
    return name.removesuffix(".exe")


def _positionals(arguments: Sequence[str], options_with_value: frozenset[str]) -> list[str]:
    values: list[str] = []
    skip = False
    for argument in arguments:
        if skip:
            skip = False
        elif argument in options_with_value:
            skip = True
        elif not argument.startswith("-"):
            values.append(argument)
    return values


def git_mutates(subcommand: str, arguments: Sequence[str]) -> bool:
    """Return whether a Git subcommand may modify a repository, failing closed on unknowns."""
    flags = {argument.split("=", 1)[0] for argument in arguments if argument.startswith("-")}
    positionals = _positionals(arguments, frozenset())
    first = positionals[0] if positionals else ""
    if subcommand in GIT_READ_ONLY:
        return False
    if subcommand == "fsck":
        return "--lost-found" in flags
    if subcommand == "branch":
        return bool(flags & BRANCH_WRITE) or (bool(positionals) and not flags & BRANCH_LIST)
    if subcommand == "tag":
        return bool(flags & TAG_WRITE) or (bool(positionals) and not flags & TAG_LIST)
    if subcommand == "config":
        if flags & CONFIG_WRITE or (positionals and positionals[0] in CONFIG_WRITE):
            return True
        if flags & CONFIG_READ or (positionals and positionals[0] in CONFIG_READ):
            return False
        return len(_positionals(arguments, CONFIG_OPTIONS_WITH_VALUE)) != 1
    if subcommand == "reflog":
        return first in {"expire", "delete", "drop"}
    if subcommand == "symbolic-ref":
        return (
            bool(flags & {"-d", "--delete"}) or len(_positionals(arguments, frozenset({"-m"}))) > 1
        )
    if subcommand in READ_ONLY_SUBCOMMANDS:
        return first not in READ_ONLY_SUBCOMMANDS[subcommand]
    return True


def _git_invocation(arguments: Sequence[str], cwd: Path) -> tuple[str, list[str], list[Path]]:
    """Return the subcommand, its arguments, and repository locations named by global options."""
    locations: list[Path] = []
    base = cwd
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        name, _, inline = argument.partition("=")
        if name in GIT_OPTIONS_WITH_VALUE:
            value = (
                inline if inline else (arguments[index + 1] if index + 1 < len(arguments) else "")
            )
            index += 1 if inline else 2
            if name == "-C" and value:
                base = _absolute(value, base)
                locations.append(base)
            elif name in {"--git-dir", "--work-tree"} and value:
                locations.append(_absolute(value, base))
            continue
        if argument.startswith("-"):
            index += 1
            continue
        return argument.casefold(), list(arguments[index + 1 :]), locations or [base]
    return "", [], locations or [base]


def _shell_reason(
    command: str,
    cwd: Path,
    roots: Sequence[ProtectedRoot],
    strict: bool,
) -> str | None:
    for segment in tokenize(command):
        words = [text for kind, text in segment if kind == "word"]
        for index, (kind, text) in enumerate(segment):
            if kind != "redirect" or "&" in text or text == "<":
                continue
            target = segment[index + 1][1] if index + 1 < len(segment) else ""
            if target and target.casefold() not in NULL_DEVICES:
                root = _inside(_absolute(target, cwd), roots)
                if root is not None:
                    return (
                        "Read-only audit policy blocks shell output redirected into the "
                        f"{root.kind}: {root.path}"
                    )
        while words and (
            words[0] in COMMAND_PREFIXES or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0])
        ):
            words = words[1:]
        if not words:
            continue
        program, arguments = _program(words[0]), words[1:]
        if program in CHANGE_DIRECTORY and arguments:
            cwd = _absolute(arguments[-1], cwd)
            continue
        if program == "git":
            subcommand, git_arguments, locations = _git_invocation(arguments, cwd)
            if not subcommand or not git_mutates(subcommand, git_arguments):
                continue
            if strict:
                return f"Read-only audit policy blocks `git {subcommand}` during an audit session"
            repository = locations[-1]
            targets = [
                *locations,
                *(
                    _absolute(value, repository)
                    for value in git_arguments
                    if not value.startswith("-")
                ),
            ]
            root = next(
                (found for found in map(lambda path: _inside(path, roots), targets) if found), None
            )
            if root is not None:
                return (
                    f"Read-only audit policy blocks `git {subcommand}` targeting the "
                    f"{root.kind}: {root.path}"
                )
            continue
        in_place = IN_PLACE_EDITORS.get(program)
        mutating = program in MUTATING_PROGRAMS or (
            in_place is not None and any(argument.startswith(in_place) for argument in arguments)
        )
        if not mutating:
            continue
        targets = [
            _absolute(value, cwd) for value in arguments if value and not value.startswith("-")
        ]
        root = next(
            (found for found in map(lambda path: _inside(path, roots), targets) if found), None
        )
        if root is not None:
            return (
                f"Read-only audit policy blocks `{program}` targeting the {root.kind}: {root.path}"
            )
    return None


def evaluate(
    payload: dict[str, Any],
    *,
    config_path: Path,
    strict: bool,
) -> str | None:
    """Return a denial reason for the tool call in ``payload``, or ``None`` to allow it."""
    tool_name = str(payload.get("tool_name") or payload.get("toolName") or "").casefold()
    tool_input = (
        payload.get("tool_input")
        or payload.get("toolInput")
        or payload.get("toolArgs")
        or payload.get("input")
        or {}
    )
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except ValueError:
            tool_input = {"command": tool_input}
    cwd = Path(str(payload.get("cwd") or Path.cwd())).resolve()
    try:
        roots = protected_roots(config_path)
    except UnreadableConfigError as error:
        if strict:
            return f"Read-only audit policy cannot identify protected paths: {error}"
        print(f"read_only_guard: warning: {error}; path protection is inactive", file=sys.stderr)
        roots = ()

    if tool_name in SHELL_TOOLS:
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if isinstance(command, list):
            command = " ".join(str(item) for item in command)
        if not isinstance(command, str):
            return "Read-only audit policy could not inspect the shell command"
        return _shell_reason(command, cwd, roots, strict)

    if any(marker in tool_name for marker in EDIT_TOOL_MARKERS):
        for path in _edit_paths(tool_input, cwd):
            root = _inside(path, roots)
            if root is not None:
                return f"Read-only audit policy blocks edits inside the {root.kind}: {path}"
    return None


def _deny(reason: str) -> int:
    print(reason, file=sys.stderr)
    return DENY_EXIT_CODE


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only PreToolUse guard for repository audits")
    parser.add_argument("--strict", action="store_true", help="Deny every mutating Git command")
    parser.add_argument(
        "--config", help="Audit config path (default: $REPO_AUDIT_CONFIG or audit.toml)"
    )
    args = parser.parse_args(arguments)
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        return _deny(f"Read-only guard received invalid hook JSON: {error}")
    if not isinstance(payload, dict):
        return _deny("Read-only guard expected a JSON object")
    config_path = Path(
        args.config or os.environ.get("REPO_AUDIT_CONFIG") or "audit.toml"
    ).expanduser()
    if not config_path.is_absolute():
        project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or Path.cwd()
        config_path = Path(str(project)) / config_path
    strict = args.strict or os.environ.get("REPO_AUDIT_STRICT_SESSION", "").casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
    reason = evaluate(payload, config_path=config_path.resolve(), strict=strict)
    return _deny(reason) if reason else 0


if __name__ == "__main__":
    raise SystemExit(main())
