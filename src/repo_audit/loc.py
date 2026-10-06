"""LOC tool verification, invocation, and result parsing."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .gitops import GITLINK_MODE, SYMLINK_MODE
from .models import LocToolConfig, PreparedRepository, as_int
from .process import run


class LocError(RuntimeError):
    """Raised when LOC tooling is unavailable or produces inconsistent output."""


# Options that make cloc independent of the machine it runs on:
# - an explicit empty options file disables ~/.config/cloc/options.txt;
# - --skip-uniqueness counts every tracked file, including identical copies;
# - --timeout=0 removes the speed-dependent per-file processing time limit;
# - --hide-rate removes elapsed-time data from the raw report.
DETERMINISTIC_OPTIONS = ("--skip-uniqueness", "--timeout=0", "--hide-rate")

BINARY_EXTENSIONS = frozenset(
    {
        ".7z", ".a", ".avi", ".bin", ".bmp", ".class", ".dll", ".dylib", ".eot", ".exe",
        ".gif", ".gz", ".ico", ".jar", ".jpeg", ".jpg", ".lib", ".mov", ".mp3", ".mp4",
        ".o", ".obj", ".otf", ".pdf", ".png", ".pyc", ".so", ".tar", ".tgz", ".ttf",
        ".wasm", ".webp", ".woff", ".woff2", ".xls", ".xlsx", ".zip",
    }
)  # fmt: skip
DATA_EXTENSIONS = frozenset({".db", ".parquet", ".sqlite", ".sqlite3"})


@dataclass(frozen=True)
class LocTool:
    command: tuple[str, ...]
    version: str
    sha256: str


@dataclass(frozen=True)
class LocResult:
    files: list[dict[str, object]]
    exclusions: list[dict[str, object]]
    reported_code: int
    reported_files: int


def resolve_loc_tool(config: LocToolConfig) -> LocTool:
    executable = config.command[0]
    resolved = Path(executable).expanduser()
    if not resolved.is_file():
        found = shutil.which(executable)
        if not found:
            raise LocError(
                f"LOC tool not found: {executable}. "
                "Install cloc or run `repo-audit bootstrap-cloc`."
            )
        resolved = Path(found)
    resolved = resolved.resolve()
    command = (str(resolved), *config.command[1:])
    version = str(run((*command, "--version"))).strip()
    if config.expected_version and version != config.expected_version:
        raise LocError(
            f"LOC tool version mismatch: expected {config.expected_version}, got {version}"
        )
    hash_target = resolved
    for token in reversed(command[1:]):
        candidate = Path(token).expanduser()
        if candidate.is_file():
            hash_target = candidate.resolve()
            break
    digest = hashlib.sha256(hash_target.read_bytes()).hexdigest()
    if config.expected_sha256 and digest != config.expected_sha256:
        raise LocError(
            f"LOC tool SHA-256 mismatch for {hash_target}: expected "
            f"{config.expected_sha256}, got {digest}"
        )
    return LocTool(command=command, version=version, sha256=digest)


def exclusion_reason(repository: PreparedRepository, path: str) -> str:
    mode = repository.file_modes[path]
    if mode == SYMLINK_MODE:
        return "Git symbolic link"
    if mode == GITLINK_MODE:
        return "Git submodule reference"
    snapshot_file = repository.snapshot_files.get(path)
    if snapshot_file is None:
        return "Tracked object is not a regular file"
    if snapshot_file.stat().st_size == 0:
        return "Empty tracked file"
    suffix = Path(path).suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return "Binary, compiled, archive, font, or media extension"
    if suffix in DATA_EXTENSIONS:
        return "Data file extension not recognized as source"
    return "Not recognized as source by LOC tool"


def _integer(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LocError(f"LOC report contains an invalid {context}: {value!r}")
    return value


def analyze_snapshot(tool: LocTool, repository: PreparedRepository, raw_dir: Path) -> LocResult:
    raw_dir.mkdir(parents=True, exist_ok=True)
    name = repository.spec.name
    list_path = raw_dir / f"{name}-loc-input.txt"
    options_path = raw_dir / f"{name}-loc-options.txt"
    report_path = raw_dir / f"{name}-loc-by-file.json"
    by_materialized = {
        str(materialized.resolve()): tracked
        for tracked, materialized in repository.snapshot_files.items()
    }
    list_path.write_text(
        "".join(f"{path}\n" for path in by_materialized), encoding="utf-8", newline="\n"
    )
    options_path.write_text("", encoding="utf-8")
    if by_materialized:
        run(
            (
                *tool.command,
                f"--config={options_path}",
                "--by-file",
                "--json",
                "--quiet",
                *DETERMINISTIC_OPTIONS,
                f"--list-file={list_path}",
                f"--out={report_path}",
            )
        )
    else:
        report_path.write_text("{}\n", encoding="utf-8", newline="\n")
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LocError(f"Could not parse LOC report {report_path}: {error}") from error
    if not isinstance(payload, dict):
        raise LocError(f"LOC report {report_path} is not a JSON object")

    files: list[dict[str, object]] = []
    for key, value in payload.items():
        if key in {"header", "SUM"}:
            continue
        tracked = by_materialized.get(str(Path(key).resolve()))
        if tracked is None:
            raise LocError(f"LOC tool reported a file outside the snapshot input: {key}")
        if not isinstance(value, dict) or not isinstance(value.get("language"), str):
            raise LocError(f"LOC report entry for {tracked} is malformed")
        files.append(
            {
                "Repository": name,
                "File": tracked,
                "Language": value["language"],
                "Lines of Code": _integer(value.get("code"), f"code count for {tracked}"),
            }
        )
    files.sort(key=lambda item: (-as_int(item["Lines of Code"]), str(item["File"])))
    summary = payload.get("SUM", {"code": 0, "nFiles": 0})
    if not isinstance(summary, dict):
        raise LocError(f"LOC report {report_path} has a malformed SUM entry")
    analyzed = {str(row["File"]) for row in files}
    exclusions: list[dict[str, object]] = [
        {"Repository": name, "File": path, "Reason": exclusion_reason(repository, path)}
        for path in repository.tracked_files
        if path not in analyzed
    ]
    return LocResult(
        files=files,
        exclusions=exclusions,
        reported_code=_integer(summary.get("code"), "SUM code count"),
        reported_files=_integer(summary.get("nFiles"), "SUM file count"),
    )
