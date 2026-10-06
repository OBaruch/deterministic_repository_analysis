"""Command-line interface for humans, CI pipelines, and agents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .bootstrap import bootstrap_cloc
from .config import ConfigError, load_config
from .pipeline import run_audit

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2

CONFIG_TEMPLATE = """\
schema_version = 1
title = "Engineering Repository Audit"
output_dir = "../repo-audit-output"
workspace_dir = "../repo-audit-workspace"
generate_pdf = false
require_clean = true
# "branches-and-tags" (default) or "all-refs".
history_scope = "branches-and-tags"

[loc]
# Paste the command and SHA-256 printed by `repo-audit bootstrap-cloc`.
command = ["cloc"]
expected_version = ""
expected_sha256 = ""

[developer]
# Regular expressions matched against "Name <email>"; matching authors are excluded.
exclude_patterns = []

[developer.aliases]
# "Alias Name <alias@example.com>" = "Canonical Name <canonical@example.com>"

[[repositories]]
name = "service-a"
url = "https://git.example.com/example-org/service-a.git"
ref = "main"
expected_sha = ""
fetch = true

[[repositories]]
name = "local-library"
path = "../local-library"
ref = "HEAD"
expected_sha = ""
fetch = false
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-audit",
        description="Deterministic, read-only quantitative audits for Git repositories.",
        epilog=(
            "Exit codes: 0 success, 1 audit or verification failure, "
            "2 usage or configuration error."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create an audit.toml template")
    init.add_argument("path", nargs="?", default="audit.toml", type=Path)

    validate = commands.add_parser("validate-config", help="Parse and validate a TOML config")
    validate.add_argument("--config", default="audit.toml", type=Path)

    audit = commands.add_parser("audit", help="Run the deterministic audit pipeline")
    audit.add_argument("--config", default="audit.toml", type=Path)
    audit.add_argument("--force", action="store_true", help="Replace a prior marked audit output")
    pdf_group = audit.add_mutually_exclusive_group()
    pdf_group.add_argument("--pdf", action="store_true", help="Also render HTML and PDF reports")
    pdf_group.add_argument("--no-pdf", action="store_true", help="Disable PDF even if configured")

    verify = commands.add_parser(
        "verify", help="Independently recompute and verify a completed audit output"
    )
    target = verify.add_mutually_exclusive_group()
    target.add_argument("--output", type=Path, help="Audit output directory to verify")
    target.add_argument("--config", type=Path, help="Verify the output_dir of this config")
    verify.add_argument("--json", action="store_true", help="Print every check as JSON")

    bootstrap = commands.add_parser("bootstrap-cloc", help="Download and verify pinned cloc 2.10")
    bootstrap.add_argument("--directory", default=Path(".repo-audit-tools"), type=Path)
    return parser


def _init(path: Path) -> int:
    path = path.resolve()
    if path.exists():
        raise ConfigError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CONFIG_TEMPLATE, encoding="utf-8", newline="\n")
    print(f"Created {path}")
    return EXIT_SUCCESS


def _validate(path: Path) -> int:
    config = load_config(path)
    summary = {
        "config": str(config.config_path),
        "repositories": [repository.name for repository in config.repositories],
        "output_dir": str(config.output_dir),
        "workspace_dir": str(config.workspace_dir),
        "history_scope": config.history_scope,
    }
    print(json.dumps(summary, indent=2))
    return EXIT_SUCCESS


def _verify(output: Path | None, config_path: Path | None, as_json: bool) -> int:
    from .verify import verify_output

    if output is None:
        output = load_config(config_path or Path("audit.toml")).output_dir
    rows = verify_output(output)
    failures = [row for row in rows if row["Status"] != "PASS"]
    if as_json:
        print(json.dumps({"output": str(output.resolve()), "checks": rows}, indent=2, default=str))
    else:
        for row in failures:
            print(
                f"FAIL [{row['Scope']}] {row['Check']}: "
                f"expected {row['Expected']}, got {row['Actual']}"
            )
        outcome = "failed" if failures else "passed"
        passed = len(rows) - len(failures)
        print(f"Verification {outcome}: {passed}/{len(rows)} checks passed")
    return EXIT_FAILURE if failures else EXIT_SUCCESS


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        if args.command == "init":
            return _init(args.path)
        if args.command == "validate-config":
            return _validate(args.config)
        if args.command == "verify":
            return _verify(args.output, args.config, args.json)
        if args.command == "bootstrap-cloc":
            target, command, digest = bootstrap_cloc(args.directory.resolve())
            print(f"Installed: {target}")
            print(f"SHA-256: {digest}")
            print("TOML command: " + json.dumps(list(command)))
            return EXIT_SUCCESS
        config = load_config(args.config)
        pdf_override = True if args.pdf else False if args.no_pdf else None
        output = run_audit(config, force=args.force, generate_pdf=pdf_override)
        print(f"Audit completed: {output / 'REPORT.md'}")
        return EXIT_SUCCESS
    except ConfigError as error:
        print(f"repo-audit: configuration error: {error}", file=sys.stderr)
        return EXIT_USAGE
    except (RuntimeError, OSError) as error:
        print(f"repo-audit: error: {error}", file=sys.stderr)
        for note in getattr(error, "__notes__", ()):
            print(f"repo-audit: note: {note}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
