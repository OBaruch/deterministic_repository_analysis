"""Independent, read-only verification of a completed audit output directory.

Every derived table is recomputed from the canonical per-file and per-commit CSV
files and compared with what the audit wrote. Nothing in the output directory
is modified.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .metrics import developer_outputs, language_summary
from .models import Row
from .pipeline import OUTPUT_FORMAT, OUTPUT_MARKER, check, derived_tables
from .reporting import CSV_SCHEMAS, DEVELOPER_CHARTS, GLOBAL_CHARTS, read_csv, slug

REQUIRED_DOCUMENTS = (
    "metadata.json",
    "audit-data.json",
    "REPORT.md",
    "METHODOLOGY.md",
    "reports/global-summary.md",
)


def _project(rows: Iterable[Row], fields: Sequence[str]) -> list[tuple[str, ...]]:
    return [tuple(str(row.get(field, "")) for field in fields) for row in rows]


def _compare(
    scope: str, name: str, expected: Iterable[Row], actual: Iterable[Row], table: str
) -> dict[str, object]:
    fields = CSV_SCHEMAS[table]
    expected_rows = _project(expected, fields)
    actual_rows = _project(actual, fields)
    mismatches = sum(
        1 for left, right in zip(expected_rows, actual_rows, strict=False) if left != right
    )
    mismatches += abs(len(expected_rows) - len(actual_rows))
    return check(scope, name, "0 differing rows", f"{mismatches} differing rows")


def _header(path: Path) -> tuple[str, ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return tuple(next(csv.reader(handle), ()))


def _artifact_checks(output: Path) -> tuple[list[dict[str, object]], bool]:
    rows: list[dict[str, object]] = []
    marker = output / OUTPUT_MARKER
    marker_format = ""
    if marker.is_file():
        try:
            marker_format = str(json.loads(marker.read_text(encoding="utf-8")).get("format", ""))
        except (ValueError, AttributeError):
            marker_format = "invalid"
    rows.append(
        check("Artifacts", "Output marker format", OUTPUT_FORMAT, marker_format or "missing")
    )
    complete = True
    for name in (*CSV_SCHEMAS, *REQUIRED_DOCUMENTS):
        present = (output / name).is_file()
        complete = complete and present
        rows.append(check("Artifacts", f"{name} present", True, present))
    if complete:
        for name, fields in CSV_SCHEMAS.items():
            rows.append(
                check(
                    "Artifacts",
                    f"{name} header",
                    ",".join(fields),
                    ",".join(_header(output / name)),
                )
            )
    return rows, complete


def _repository_checks(
    output: Path,
    tables: dict[str, list[dict[str, str]]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for summary in tables["repository_summary.csv"]:
        name = summary["Repository"]

        def own(table: str, repository: str = name) -> list[dict[str, str]]:
            return [row for row in tables[table] if row["Repository"] == repository]

        files = own("files.csv")
        languages = own("languages.csv")
        commits = own("commits.csv")
        loc = sum(int(row["Lines of Code"]) for row in files)
        rows.extend(
            (
                check(name, "Repository LOC = Sum(LOC by file)", summary["Lines of Code"], loc),
                check(name, "Source files = File rows", summary["Source Files"], len(files)),
                check(name, "Languages = Language rows", summary["Languages"], len(languages)),
                check(
                    name,
                    "Tracked files = File rows + excluded file rows",
                    summary["Total Files"],
                    len(files) + len(own("excluded_files.csv")),
                ),
                check(
                    name,
                    f"reports/{name}.md present",
                    True,
                    (output / "reports" / f"{name}.md").is_file(),
                ),
            )
        )
        rows.append(
            _compare(
                name,
                "languages.csv matches recomputation from files.csv",
                language_summary(name, files),
                languages,
                "languages.csv",
            )
        )
        developers, daily, weekly, monthly = developer_outputs(name, commits)
        for table, recomputed in (
            ("developer_summary.csv", developers),
            ("developer_daily.csv", daily),
            ("developer_weekly.csv", weekly),
            ("developer_monthly.csv", monthly),
        ):
            rows.append(
                _compare(
                    name,
                    f"{table} matches recomputation from commits.csv",
                    recomputed,
                    own(table),
                    table,
                )
            )
        missing_charts = [
            filename
            for _, filename, _, _ in DEVELOPER_CHARTS
            if not (output / "charts" / f"{slug(name)}-{filename}.svg").is_file()
        ]
        rows.append(check(name, "Developer charts present", 0, len(missing_charts)))
    return rows


def _global_checks(
    output: Path,
    tables: dict[str, list[dict[str, str]]],
    metadata: dict[str, Any],
    audit_data: dict[str, Any],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    recomputed = derived_tables(
        tables["repository_summary.csv"],
        tables["files.csv"],
        tables["languages.csv"],
        tables["commits.csv"],
    )
    for table, values in recomputed.items():
        rows.append(
            _compare("Global", f"{table} matches recomputation", values, tables[table], table)
        )
    recorded = {
        (str(item.get("name")), str(item.get("commit_sha")), str(item.get("resolved_ref")))
        for item in metadata.get("repositories", [])
    }
    summarized = {
        (row["Repository"], row["Commit SHA"], row["Resolved Ref"])
        for row in tables["repository_summary.csv"]
    }
    rows.append(
        check(
            "Global",
            "metadata.json snapshots = repository_summary.csv snapshots",
            sorted(summarized),
            sorted(recorded),
        )
    )
    embedded = audit_data.get("tables", {})
    for table in CSV_SCHEMAS:
        rows.append(
            _compare(
                "Global",
                f"audit-data.json {table} = CSV",
                tables[table],
                embedded.get(table, []),
                table,
            )
        )
    missing_charts = [name for _, name in GLOBAL_CHARTS if not (output / "charts" / name).is_file()]
    rows.append(check("Global", "Global charts present", 0, len(missing_charts)))
    recorded_validations = tables["validation.csv"]
    passed = sum(row["Status"] == "PASS" for row in recorded_validations)
    rows.append(
        check(
            "Global",
            "Recorded validation.csv checks passed",
            len(recorded_validations) or "at least one check",
            passed,
        )
    )
    return rows


def verify_output(output: Path) -> list[dict[str, object]]:
    """Return verification rows (Scope, Check, Expected, Actual, Status) for ``output``."""
    output = output.resolve()
    rows, complete = _artifact_checks(output)
    if not complete:
        return rows
    tables = {name: read_csv(output / name) for name in CSV_SCHEMAS}
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    audit_data = json.loads((output / "audit-data.json").read_text(encoding="utf-8"))
    rows.extend(_repository_checks(output, tables))
    rows.extend(_global_checks(output, tables, metadata, audit_data))
    return rows
