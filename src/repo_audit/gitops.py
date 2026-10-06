"""Read-only Git source preparation, snapshot materialization, and invariants."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import IO

from .models import AuditConfig, PreparedRepository, RepositorySpec, SourceState, TreeEntry
from .process import CommandError, environment, run


class GitError(RuntimeError):
    """Raised when a repository cannot be prepared without ambiguity."""


# Never prompt for credentials and never take optional locks (for example the
# index refresh performed by `git status`) inside an analyzed repository.
GIT_ENVIRONMENT = {"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
NON_INTERACTIVE = ("-c", "credential.interactive=never")
REGULAR_FILE_MODES = {"100644", "100755"}
SYMLINK_MODE = "120000"
GITLINK_MODE = "160000"

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._+@=~-]*[A-Za-z0-9_+@=~-]$")
_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9_+-]+$")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{n}" for n in range(10)),
    *(f"LPT{n}" for n in range(10)),
}
_CHUNK_SIZE = 1024 * 1024


def git(git_path: Path, *arguments: str, text: bool = True) -> str | bytes:
    return run(("git", "-C", str(git_path), *arguments), text=text, env=GIT_ENVIRONMENT)


def git_text(git_path: Path, *arguments: str) -> str:
    return str(git(git_path, *arguments))


def source_state(git_path: Path) -> SourceState:
    bare = git_text(git_path, "rev-parse", "--is-bare-repository").strip() == "true"
    status = (
        None if bare else git_text(git_path, "status", "--porcelain=v1", "--untracked-files=all")
    )
    try:
        head = git_text(git_path, "rev-parse", "--verify", "--quiet", "HEAD^{commit}").strip()
    except CommandError:
        head = "(unborn)"
    refs = git_text(git_path, "for-each-ref", "--format=%(objectname) %(refname)")
    return SourceState(status=status, refs=f"{head} HEAD\n{refs}")


def state_digest(state: SourceState) -> str:
    payload = json.dumps({"status": state.status, "refs": state.refs}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_within(child: Path, parent: Path) -> bool:
    return child.resolve().is_relative_to(parent.resolve())


def validate_output_isolation(config: AuditConfig) -> None:
    for repository in config.repositories:
        if repository.path is None:
            continue
        for candidate, label in (
            (config.output_dir, "output_dir"),
            (config.workspace_dir, "workspace_dir"),
        ):
            if _is_within(candidate, repository.path):
                raise GitError(
                    f"{label} must be outside analyzed repository {repository.name}: {candidate}"
                )
            if _is_within(repository.path, candidate):
                raise GitError(
                    f"Analyzed repository {repository.name} must not be inside {label}: "
                    f"{repository.path}"
                )


def _prepare_source(spec: RepositorySpec, workspace: Path) -> Path:
    if spec.path is not None:
        if not spec.path.is_dir():
            raise GitError(f"Local repository does not exist: {spec.path}")
        try:
            git(spec.path, "rev-parse", "--git-dir")
        except CommandError as error:
            raise GitError(f"Not a Git repository: {spec.path}") from error
        if spec.fetch:
            git(spec.path, *NON_INTERACTIVE, "fetch", "--all", "--tags", "--prune")
        return spec.path

    mirrors = workspace / "mirrors"
    mirrors.mkdir(parents=True, exist_ok=True)
    mirror = mirrors / f"{spec.name}.git"
    if mirror.exists():
        if not (mirror / "HEAD").is_file():
            raise GitError(f"Mirror path exists but is not a bare repository: {mirror}")
        configured_url = git_text(mirror, "config", "--get", "remote.origin.url").strip()
        if configured_url != spec.url:
            raise GitError(
                f"Mirror {mirror} tracks {configured_url!r}, not {spec.url!r}. "
                "Remove the stale mirror or use a different repository name."
            )
        if spec.fetch:
            git(mirror, *NON_INTERACTIVE, "remote", "update", "--prune")
    else:
        run(
            ("git", *NON_INTERACTIVE, "clone", "--mirror", "--quiet", spec.url, str(mirror)),
            env=GIT_ENVIRONMENT,
        )
    return mirror


def _resolve_ref(git_path: Path, requested_ref: str) -> tuple[str, str]:
    candidates = [requested_ref]
    if not requested_ref.startswith("refs/") and requested_ref != "HEAD":
        candidates.extend(
            (
                f"refs/heads/{requested_ref}",
                f"refs/tags/{requested_ref}",
                f"refs/remotes/origin/{requested_ref}",
            )
        )
    for candidate in dict.fromkeys(candidates):
        try:
            sha = git_text(git_path, "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}")
        except CommandError:
            continue
        full_name = git_text(git_path, "rev-parse", "--symbolic-full-name", candidate).strip()
        return full_name if full_name.startswith("refs/") else candidate, sha.strip()
    raise GitError(f"Could not resolve Git ref {requested_ref!r} in {git_path}")


def read_tree(git_path: Path, commit_sha: str) -> tuple[TreeEntry, ...]:
    raw = git(git_path, "ls-tree", "-r", "-z", "--full-tree", commit_sha, text=False)
    assert isinstance(raw, bytes)
    entries: list[TreeEntry] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        if not separator:
            raise GitError(f"Could not parse tree entry in {commit_sha}")
        parts = metadata.decode("ascii").split()
        if len(parts) != 3:
            raise GitError(f"Unexpected tree metadata in {commit_sha}: {metadata!r}")
        path = raw_path.decode("utf-8", "replace")
        posix = PurePosixPath(path)
        if posix.is_absolute() or ".." in posix.parts or any(c in path for c in "\n\r\x00"):
            raise GitError(f"Unsupported tracked path in {commit_sha}: {path!r}")
        entries.append(
            TreeEntry(path=path, mode=parts[0], object_type=parts[1], object_id=parts[2])
        )
    if len({entry.path for entry in entries}) != len(entries):
        raise GitError(f"Tracked paths in {commit_sha} are not unique after UTF-8 decoding")
    return tuple(sorted(entries, key=lambda entry: entry.path))


def materialized_name(path: str) -> str:
    """Return a CSV-, JSON-, and filesystem-safe file name that keeps LOC detection intact.

    The LOC tool identifies languages by file name, extension, and content. Safe
    names are preserved verbatim; unsafe names keep only their safe suffixes.
    """
    name = PurePosixPath(path).name
    if _SAFE_NAME.fullmatch(name) and name.split(".")[0].upper() not in _WINDOWS_RESERVED:
        return name
    suffixes = PurePosixPath(name).suffixes
    safe_suffixes = [suffix for suffix in suffixes if _SAFE_SUFFIX.fullmatch(suffix)]
    if len(safe_suffixes) != len(suffixes):
        safe_suffixes = safe_suffixes[-1:]
    return "file" + "".join(safe_suffixes)


def _copy_exact(stream: IO[bytes], size: int, output: IO[bytes] | None) -> None:
    remaining = size
    while remaining:
        chunk = stream.read(min(remaining, _CHUNK_SIZE))
        if not chunk:
            raise GitError("Unexpected end of `git cat-file` output")
        if output is not None:
            output.write(chunk)
        remaining -= len(chunk)


def materialize_snapshot(
    git_path: Path,
    entries: tuple[TreeEntry, ...],
    target: Path,
) -> dict[str, Path]:
    """Write the exact blob bytes of every regular tracked file into ``target``.

    Blobs are read with `git cat-file --batch`, so no checkout, smudge/clean
    filter, text conversion, `export-ignore`, or `export-subst` attribute can
    change the analyzed content. Each file is placed in its own numbered
    directory, which keeps paths short and makes case-insensitive collisions
    impossible.
    """
    if target.exists():
        shutil.rmtree(target)
    files_root = target / "files"
    files_root.mkdir(parents=True)
    regular = [entry for entry in entries if entry.mode in REGULAR_FILE_MODES]
    materialized: dict[str, Path] = {}
    manifest: list[dict[str, str]] = []
    if regular:
        with subprocess.Popen(
            ("git", "-C", str(git_path), "cat-file", "--batch"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment(GIT_ENVIRONMENT),
        ) as process:
            assert process.stdin and process.stdout and process.stderr
            try:
                for index, entry in enumerate(regular, start=1):
                    process.stdin.write(entry.object_id.encode("ascii") + b"\n")
                    process.stdin.flush()
                    header = process.stdout.readline().decode("ascii", "replace").split()
                    if len(header) != 3 or header[0] != entry.object_id or header[1] != "blob":
                        raise GitError(
                            f"Unexpected `git cat-file` response for {entry.path}: {header}"
                        )
                    directory = files_root / str(index)
                    directory.mkdir()
                    destination = directory / materialized_name(entry.path)
                    with destination.open("wb") as output:
                        _copy_exact(process.stdout, int(header[2]), output)
                    _copy_exact(process.stdout, 1, None)
                    materialized[entry.path] = destination
                    manifest.append(
                        {
                            "path": entry.path,
                            "mode": entry.mode,
                            "object_id": entry.object_id,
                            "materialized": destination.relative_to(target).as_posix(),
                        }
                    )
                process.stdin.close()
                error_output = process.stderr.read().decode("utf-8", "replace").strip()
            except BaseException:
                process.kill()
                raise
            if process.wait() != 0:
                raise GitError(f"`git cat-file --batch` failed: {error_output}")
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return materialized


def history_revisions(scope: str, commit_sha: str) -> tuple[str, ...]:
    if scope == "all-refs":
        return ("--all",)
    return ("--branches", "--tags", "--remotes", commit_sha)


def prepare_repository(
    spec: RepositorySpec,
    workspace: Path,
    require_clean: bool,
    history_scope: str = "branches-and-tags",
) -> PreparedRepository:
    git_path = _prepare_source(spec, workspace)
    initial_state = source_state(git_path)
    if require_clean and initial_state.status:
        raise GitError(f"Repository {spec.name} is not clean:\n{initial_state.status}")
    resolved_ref, commit_sha = _resolve_ref(git_path, spec.ref)
    if spec.expected_sha and commit_sha.lower() != spec.expected_sha.lower():
        raise GitError(
            f"Repository {spec.name} ref {resolved_ref} resolved to {commit_sha}; "
            f"expected {spec.expected_sha}"
        )
    entries = read_tree(git_path, commit_sha)
    snapshot = workspace / "snapshots" / spec.name
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot_files = materialize_snapshot(git_path, entries, snapshot)
    return PreparedRepository(
        spec=spec,
        git_path=git_path,
        snapshot_path=snapshot,
        resolved_ref=resolved_ref,
        commit_sha=commit_sha,
        tracked_files=tuple(entry.path for entry in entries),
        file_modes={entry.path: entry.mode for entry in entries},
        snapshot_files=snapshot_files,
        history_revisions=history_revisions(history_scope, commit_sha),
        initial_state=initial_state,
    )


def verify_unchanged(repository: PreparedRepository) -> SourceState:
    final_state = source_state(repository.git_path)
    if final_state != repository.initial_state:
        raise GitError(
            f"Repository {repository.spec.name} changed during the audit. "
            f"Before: {repository.initial_state.describe()}; after: {final_state.describe()}"
        )
    return final_state
