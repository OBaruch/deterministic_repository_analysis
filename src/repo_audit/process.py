"""Subprocess execution with uniform error reporting."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


class CommandError(RuntimeError):
    """Raised when an external command fails."""


def environment(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    merged = dict(os.environ)
    if overrides:
        merged.update(overrides)
    return merged


def run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    text: bool = True,
    env: Mapping[str, str] | None = None,
) -> str | bytes:
    """Run a command and return its standard output.

    Text output is always decoded as UTF-8 so that results do not depend on the
    platform locale. Undecodable bytes are replaced deterministically.
    """
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            check=True,
            capture_output=True,
            env=environment(env) if env is not None else None,
        )
    except FileNotFoundError as error:
        raise CommandError(f"Command not found: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or b"").decode("utf-8", "replace").strip()
        raise CommandError(
            f"Command failed with exit code {error.returncode}: {' '.join(command)}"
            + (f"\n{detail}" if detail else "")
        ) from error
    return result.stdout.decode("utf-8", "replace") if text else result.stdout
