"""End-to-end audit orchestration, derived tables, and validation."""

from __future__ import annotations

import hashlib
import json
import platform
import shlex
import shutil
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .gitops import (
    git_text,
    prepare_repository,
    source_state,
    state_digest,
    validate_output_isolation,
    verify_unchanged,
)
from .loc import DETERMINISTIC_OPTIONS, LocTool, analyze_snapshot, resolve_loc_tool
from .metrics import (
    developer_outputs,
    extract_commits,
    global_developer_summary,
    language_summary,
    percentage,
    validate_developer_series,
)
from .models import AuditConfig, PreparedRepository, Row, as_int
from .process import run
from .reporting import CSV_SCHEMAS, generate_charts, generate_reports, write_canonical_csvs

OUTPUT_MARKER = ".repo-audit-output.json"
OUTPUT_FORMAT = "deterministic-repository-audit"
SOURCE_UNCHANGED_CHECK = "Source repository unchanged"


class ValidationError(RuntimeError):
    """Raised when one or more reconciliation checks fail."""


def _prepare_output(output: Path, force: bool) -> None:
    if output.exists() and any(output.iterdir()):
        marker = output / OUTPUT_MARKER
        if not force:
            raise RuntimeError(
                f"Output directory is not empty: {output}. "
                "Use --force only to replace a previous audit output."
            )
        if not marker.is_file():
            raise RuntimeError(
                f"Refusing to replace unmarked directory: {output}. "
                f"Expected marker {OUTPUT_MARKER}."
            )
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / OUTPUT_MARKER).write_text(
        json.dumps({"format": OUTPUT_FORMAT, "schema_version": 1}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def check(scope: str, name: str, expected: object, actual: object) -> dict[str, object]:
    return {
        "Scope": scope,
        "Check": name,
        "Expected": expected,
        "Actual": actual,
        "Status": "PASS" if str(expected) == str(actual) else "FAIL",
    }


def _integer_sum(rows: Sequence[Row], field: str) -> int:
    return sum(as_int(row[field]) for row in rows)


def derived_tables(
    repository_rows: Sequence[Row],
    files: Sequence[Row],
    languages: Sequence[Row],
    commits: Sequence[Row],
) -> dict[str, list[dict[str, object]]]:
    global_languages: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "loc": 0})
    for row in languages:
        values = global_languages[str(row["Language"])]
        values["files"] += as_int(row["Files"])
        values["loc"] += as_int(row["Lines of Code"])
    global_loc = sum(values["loc"] for values in global_languages.values())
    global_language_rows: list[dict[str, object]] = [
        {
            "Language": language,
            "Files": values["files"],
            "Lines of Code": values["loc"],
            "Percentage Global LOC": percentage(values["loc"], global_loc),
        }
        for language, values in global_languages.items()
    ]
    global_language_rows.sort(key=lambda row: (-as_int(row["Lines of Code"]), str(row["Language"])))

    total_files = _integer_sum(repository_rows, "Total Files")
    total_commits = _integer_sum(repository_rows, "Unique Commits")
    repository_percentages: list[dict[str, object]] = [
        {
            "Repository": row["Repository"],
            "Lines of Code": row["Lines of Code"],
            "Percentage Total LOC": percentage(as_int(row["Lines of Code"]), global_loc),
            "Files": row["Total Files"],
            "Percentage Total Files": percentage(as_int(row["Total Files"]), total_files),
            "Unique Commits": row["Unique Commits"],
            "Percentage Sum Repository Commits": percentage(
                as_int(row["Unique Commits"]), total_commits
            ),
        }
        for row in repository_rows
    ]
    top = sorted(
        files,
        key=lambda row: (-as_int(row["Lines of Code"]), str(row["Repository"]), str(row["File"])),
    )[:20]
    top_rows: list[dict[str, object]] = [
        {"Rank": index, **row} for index, row in enumerate(top, start=1)
    ]
    return {
        "global_languages.csv": global_language_rows,
        "repository_percentages.csv": repository_percentages,
        "top_20_files.csv": top_rows,
        "developer_global_summary.csv": global_developer_summary(commits),
    }


def _metadata(
    config: AuditConfig,
    tool: LocTool,
    repositories: Sequence[PreparedRepository],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "toolkit_version": __version__,
        "title": config.title,
        "config_sha256": hashlib.sha256(config.config_path.read_bytes()).hexdigest(),
        "history_scope": config.history_scope,
        "git_version": str(run(("git", "--version"))).strip(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "loc_tool": {
            "command": shlex.join(tool.command),
            "options": list(DETERMINISTIC_OPTIONS),
            "version": tool.version,
            "sha256": tool.sha256,
        },
        "repositories": [
            {
                "name": repository.spec.name,
                "source_type": "remote" if repository.spec.is_remote else "local",
                "requested_ref": repository.spec.ref,
                "resolved_ref": repository.resolved_ref,
                "commit_sha": repository.commit_sha,
                "history_revisions": list(repository.history_revisions),
            }
            for repository in repositories
        ],
    }


def _analyze_repository(
    config: AuditConfig,
    repository: PreparedRepository,
    tool: LocTool,
    tables: dict[str, list[dict[str, object]]],
) -> None:
    name = repository.spec.name
    loc = analyze_snapshot(tool, repository, config.output_dir / "raw")
    languages = language_summary(name, loc.files)
    extraction = extract_commits(repository, config.developer)
    developers, daily, weekly, monthly = developer_outputs(name, extraction.commits)
    unique_commits = int(
        git_text(repository.git_path, "rev-list", "--count", *repository.history_revisions).strip()
    )
    repository_loc = _integer_sum(loc.files, "Lines of Code")
    tables["repository_summary.csv"].append(
        {
            "Repository": name,
            "Requested Ref": repository.spec.ref,
            "Resolved Ref": repository.resolved_ref,
            "Commit SHA": repository.commit_sha,
            "Total Files": len(repository.tracked_files),
            "Source Files": len(loc.files),
            "Languages": len(languages),
            "Lines of Code": repository_loc,
            "Unique Commits": unique_commits,
        }
    )
    tables["files.csv"].extend(loc.files)
    tables["languages.csv"].extend(languages)
    tables["commits.csv"].extend(extraction.commits)
    tables["developer_summary.csv"].extend(developers)
    tables["developer_daily.csv"].extend(daily)
    tables["developer_weekly.csv"].extend(weekly)
    tables["developer_monthly.csv"].extend(monthly)
    tables["excluded_files.csv"].extend(loc.exclusions)
    tables["excluded_authors.csv"].extend(extraction.excluded_authors)
    tables["validation.csv"].extend(
        (
            check(name, "LOC tool SUM(code) = Sum(LOC by file)", loc.reported_code, repository_loc),
            check(name, "LOC tool SUM(nFiles) = Source files", loc.reported_files, len(loc.files)),
            check(
                name,
                "Sum(LOC by language) = Repository LOC",
                repository_loc,
                _integer_sum(languages, "Lines of Code"),
            ),
            check(
                name,
                "Sum(files by language) = Source files",
                len(loc.files),
                _integer_sum(languages, "Files"),
            ),
            check(
                name,
                "Source files + excluded files = Tracked files",
                len(repository.tracked_files),
                len(loc.files) + len(loc.exclusions),
            ),
            check(
                name,
                "Parsed non-merge commits = git rev-list --no-merges --count",
                extraction.expected_commits,
                extraction.parsed_commits,
            ),
            check(
                name,
                "Attributed + excluded-author commits = Parsed non-merge commits",
                extraction.parsed_commits,
                len(extraction.commits) + extraction.excluded_commits,
            ),
            check(
                name,
                "Sum(developer commits) = Attributed commits",
                len(extraction.commits),
                _integer_sum(developers, "Commits"),
            ),
        )
    )


def _global_checks(tables: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    repositories = tables["repository_summary.csv"]
    return [
        check(
            "Global",
            "Sum(LOC by repository) = Sum(LOC by file)",
            _integer_sum(repositories, "Lines of Code"),
            _integer_sum(tables["files.csv"], "Lines of Code"),
        ),
        check(
            "Global",
            "Sum(LOC by global language) = Sum(LOC by file)",
            _integer_sum(tables["global_languages.csv"], "Lines of Code"),
            _integer_sum(tables["files.csv"], "Lines of Code"),
        ),
        check(
            "Global",
            "Sum(tracked files by repository) = Source files + excluded files",
            _integer_sum(repositories, "Total Files"),
            len(tables["files.csv"]) + len(tables["excluded_files.csv"]),
        ),
    ]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run_audit(
    config: AuditConfig,
    *,
    force: bool = False,
    generate_pdf: bool | None = None,
) -> Path:
    validate_output_isolation(config)
    tool = resolve_loc_tool(config.loc)
    _prepare_output(config.output_dir, force)
    config.workspace_dir.mkdir(parents=True, exist_ok=True)
    prepared: list[PreparedRepository] = []
    tables: dict[str, list[dict[str, object]]] = {filename: [] for filename in CSV_SCHEMAS}

    try:
        for spec in config.repositories:
            repository = prepare_repository(
                spec, config.workspace_dir, config.require_clean, config.history_scope
            )
            prepared.append(repository)
            _analyze_repository(config, repository, tool, tables)

        tables.update(
            derived_tables(
                tables["repository_summary.csv"],
                tables["files.csv"],
                tables["languages.csv"],
                tables["commits.csv"],
            )
        )
        tables["validation.csv"].extend(
            validate_developer_series(
                tables["developer_summary.csv"],
                tables["developer_daily.csv"],
                tables["developer_weekly.csv"],
                tables["developer_monthly.csv"],
            )
        )
        tables["validation.csv"].extend(_global_checks(tables))
        tables["validation.csv"].extend(
            check(
                repository.spec.name,
                SOURCE_UNCHANGED_CHECK,
                state_digest(repository.initial_state),
                state_digest(source_state(repository.git_path)),
            )
            for repository in prepared
        )
    except BaseException as error:
        for repository in prepared:
            try:
                verify_unchanged(repository)
            except Exception as invariant_error:
                error.add_note(str(invariant_error))
        raise

    write_canonical_csvs(config.output_dir, tables)
    failures = [row for row in tables["validation.csv"] if row["Status"] != "PASS"]
    if failures:
        evidence = config.output_dir / "validation.csv"
        raise ValidationError(f"{len(failures)} validation check(s) failed; see {evidence}")
    metadata = _metadata(config, tool, prepared)
    _write_json(config.output_dir / "metadata.json", metadata)
    _write_json(config.output_dir / "audit-data.json", {"metadata": metadata, "tables": tables})
    generate_charts(config.output_dir)
    generate_reports(config.output_dir, config.title)
    should_generate_pdf = config.generate_pdf if generate_pdf is None else generate_pdf
    if should_generate_pdf:
        from .pdf import build_pdf

        build_pdf(config.output_dir, config.title)
    return config.output_dir
