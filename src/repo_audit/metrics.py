"""Pure metric calculations, Git history extraction, and reconciliation checks."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .gitops import git_text
from .models import DeveloperConfig, PreparedRepository, Row, as_int


class MetricError(RuntimeError):
    """Raised when Git data cannot be reconciled deterministically."""


CANONICAL_DECIMAL_PLACES = 12
LOG_FORMAT = "%x1e%H%x1f%an%x1f%ae%x1f%aI"
# Flags that pin every diff and log setting a user or system Git config could change.
LOG_OPTIONS = (
    "--no-merges",
    "--root",
    "--numstat",
    "--no-renames",
    "--diff-algorithm=myers",
    "--no-ext-diff",
    "--no-textconv",
    "--no-color",
    "--no-mailmap",
    "--no-show-signature",
    "--encoding=UTF-8",
)
_NUMSTAT_LINE = re.compile(r"^(\d+|-)\t(\d+|-)\t")


@dataclass(frozen=True)
class CommitExtraction:
    commits: list[dict[str, object]]
    excluded_authors: list[dict[str, object]]
    parsed_commits: int
    excluded_commits: int
    expected_commits: int


def decimal_ratio(numerator: int, denominator: int, places: int = CANONICAL_DECIMAL_PLACES) -> str:
    quantum = Decimal(1).scaleb(-places)
    if denominator == 0:
        return format(Decimal(0).quantize(quantum), "f")
    with localcontext() as context:
        context.prec = 50
        value = Decimal(numerator) / Decimal(denominator)
        return format(value.quantize(quantum, rounding=ROUND_HALF_UP), "f")


def percentage(numerator: int, denominator: int) -> str:
    return decimal_ratio(numerator * 100, denominator)


def language_summary(
    repository_name: str,
    files: Sequence[Row],
) -> list[dict[str, object]]:
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "loc": 0})
    for row in files:
        language = str(row["Language"])
        totals[language]["files"] += 1
        totals[language]["loc"] += as_int(row["Lines of Code"])
    source_files = len(files)
    total_loc = sum(values["loc"] for values in totals.values())
    rows: list[dict[str, object]] = [
        {
            "Repository": repository_name,
            "Language": language,
            "Files": values["files"],
            "Lines of Code": values["loc"],
            "Percentage Files": percentage(values["files"], source_files),
            "Percentage LOC": percentage(values["loc"], total_loc),
        }
        for language, values in totals.items()
    ]
    return sorted(rows, key=lambda row: (-as_int(row["Lines of Code"]), str(row["Language"])))


def _parse_identity(identity: str) -> tuple[str, str]:
    match = re.fullmatch(r"(.+) <([^<>]+)>", identity.strip())
    if not match:
        raise MetricError(f"Invalid exact identity: {identity!r}")
    return match.group(1), match.group(2)


def canonical_identity(name: str, email: str, config: DeveloperConfig) -> tuple[str, str]:
    exact = f"{name} <{email}>"
    return _parse_identity(config.aliases.get(exact, exact))


def extract_commits(
    repository: PreparedRepository,
    developer_config: DeveloperConfig,
) -> CommitExtraction:
    revisions = repository.history_revisions
    raw = git_text(repository.git_path, "log", *LOG_OPTIONS, f"--format={LOG_FORMAT}", *revisions)
    exclusion_patterns = [re.compile(pattern) for pattern in developer_config.exclude_patterns]
    records: list[dict[str, object]] = []
    excluded: dict[tuple[str, str], tuple[str, int]] = {}
    parsed_commits = 0
    for block in raw.split("\x1e")[1:]:
        lines = block.replace("\r\n", "\n").split("\n")
        metadata = lines[0].split("\x1f", 3)
        if len(metadata) != 4:
            raise MetricError(f"Could not parse commit metadata in {repository.spec.name}")
        commit_sha, author_name, author_email, author_date = metadata
        parsed_commits += 1
        try:
            datetime.fromisoformat(author_date)
        except ValueError as error:
            raise MetricError(
                f"Invalid author date {author_date!r} in commit {commit_sha}"
            ) from error
        added = 0
        deleted = 0
        binary_files = 0
        for line in lines[1:]:
            if not line:
                continue
            match = _NUMSTAT_LINE.match(line)
            if match is None:
                raise MetricError(f"Unexpected numstat line in commit {commit_sha}: {line!r}")
            if match.group(1) == "-" or match.group(2) == "-":
                binary_files += 1
            else:
                added += int(match.group(1))
                deleted += int(match.group(2))
        identity = f"{author_name} <{author_email}>"
        matching_pattern = next(
            (pattern.pattern for pattern in exclusion_patterns if pattern.search(identity)),
            None,
        )
        if matching_pattern is not None:
            _, count = excluded.get((author_name, author_email), (matching_pattern, 0))
            excluded[(author_name, author_email)] = (matching_pattern, count + 1)
            continue
        canonical_name, canonical_email = canonical_identity(
            author_name, author_email, developer_config
        )
        records.append(
            {
                "Repository": repository.spec.name,
                "Commit SHA": commit_sha,
                "Author Name": canonical_name,
                "Author Email": canonical_email,
                "Original Author Name": author_name,
                "Original Author Email": author_email,
                "Author Date": author_date,
                "Lines Added": added,
                "Lines Deleted": deleted,
                "Net Lines": added - deleted,
                "Binary Files Excluded": binary_files,
            }
        )
    expected = int(
        git_text(repository.git_path, "rev-list", "--count", "--no-merges", *revisions).strip()
    )
    excluded_rows: list[dict[str, object]] = [
        {
            "Repository": repository.spec.name,
            "Developer": name,
            "Email": email,
            "Rule": rule,
            "Commits": count,
        }
        for (name, email), (rule, count) in sorted(excluded.items())
    ]
    records.sort(key=lambda row: (str(row["Author Date"]), str(row["Commit SHA"])))
    return CommitExtraction(
        commits=records,
        excluded_authors=excluded_rows,
        parsed_commits=parsed_commits,
        excluded_commits=sum(count for _, count in excluded.values()),
        expected_commits=expected,
    )


def author_periods(author_date: str) -> tuple[str, str, str, datetime]:
    value = datetime.fromisoformat(author_date)
    local_date = value.date()
    iso_year, iso_week, _ = local_date.isocalendar()
    return (
        local_date.isoformat(),
        f"{iso_year:04d}-W{iso_week:02d}",
        f"{local_date.year:04d}-{local_date.month:02d}",
        value.astimezone(UTC),
    )


def developer_outputs(
    repository_name: str,
    commits: Sequence[Row],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    identities: dict[tuple[str, str], list[Row]] = defaultdict(list)
    period_maps: list[dict[tuple[str, str, str], dict[str, int]]] = [
        defaultdict(lambda: {"commits": 0, "added": 0, "deleted": 0}) for _ in range(3)
    ]
    for commit in commits:
        identity = (str(commit["Author Name"]), str(commit["Author Email"]))
        identities[identity].append(commit)
        periods = author_periods(str(commit["Author Date"]))[:3]
        for target, period in zip(period_maps, periods, strict=True):
            values = target[(*identity, period)]
            values["commits"] += 1
            values["added"] += as_int(commit["Lines Added"])
            values["deleted"] += as_int(commit["Lines Deleted"])

    summaries: list[dict[str, object]] = []
    for (name, email), identity_commits in identities.items():
        ordered = sorted(
            identity_commits,
            key=lambda row: (author_periods(str(row["Author Date"]))[3], str(row["Commit SHA"])),
        )
        period_sets = [
            {author_periods(str(row["Author Date"]))[index] for row in ordered}
            for index in range(3)
        ]
        added = sum(as_int(row["Lines Added"]) for row in ordered)
        deleted = sum(as_int(row["Lines Deleted"]) for row in ordered)
        summaries.append(
            {
                "Repository": repository_name,
                "Developer": name,
                "Email": email,
                "First Commit": ordered[0]["Author Date"],
                "Last Commit": ordered[-1]["Author Date"],
                "Commits": len(ordered),
                "Lines Added": added,
                "Lines Deleted": deleted,
                "Net Lines": added - deleted,
                "Active Days": len(period_sets[0]),
                "Average LOC per Active Day": decimal_ratio(added, len(period_sets[0])),
                "Active Weeks": len(period_sets[1]),
                "Average LOC per Active Week": decimal_ratio(added, len(period_sets[1])),
                "Active Months": len(period_sets[2]),
                "Average LOC per Active Month": decimal_ratio(added, len(period_sets[2])),
            }
        )

    def series_rows(
        source: dict[tuple[str, str, str], dict[str, int]],
        field: str,
    ) -> list[dict[str, object]]:
        return [
            {
                "Repository": repository_name,
                "Developer": name,
                "Email": email,
                field: period,
                "Commits": values["commits"],
                "Lines Added": values["added"],
                "Lines Deleted": values["deleted"],
            }
            for (name, email, period), values in sorted(source.items())
        ]

    summaries.sort(
        key=lambda row: (-as_int(row["Lines Added"]), str(row["Developer"]), str(row["Email"]))
    )
    return (
        summaries,
        series_rows(period_maps[0], "Date"),
        series_rows(period_maps[1], "ISO Week"),
        series_rows(period_maps[2], "Month"),
    )


def global_developer_summary(
    commits: Sequence[Row],
) -> list[dict[str, object]]:
    identities: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for commit in commits:
        identities[(str(commit["Author Name"]), str(commit["Author Email"]))].append(commit)
    rows: list[dict[str, object]] = []
    for (name, email), identity_commits in identities.items():
        unique: dict[str, Row] = {}
        for row in sorted(
            identity_commits, key=lambda item: (str(item["Commit SHA"]), str(item["Repository"]))
        ):
            sha = str(row["Commit SHA"])
            if sha in unique:
                fields = (
                    "Author Name",
                    "Author Email",
                    "Author Date",
                    "Lines Added",
                    "Lines Deleted",
                )
                if any(unique[sha][field] != row[field] for field in fields):
                    raise MetricError(f"Commit {sha} has inconsistent metadata across repositories")
            else:
                unique[sha] = row
        records = list(unique.values())
        periods = [
            {author_periods(str(row["Author Date"]))[index] for row in records}
            for index in range(3)
        ]
        added = sum(as_int(row["Lines Added"]) for row in records)
        rows.append(
            {
                "Developer": name,
                "Email": email,
                "Repositories": "; ".join(
                    sorted({str(row["Repository"]) for row in identity_commits})
                ),
                "Commits": len(records),
                "Lines Added": added,
                "Active Days": len(periods[0]),
                "Average LOC per Active Day": decimal_ratio(added, len(periods[0])),
                "Active Weeks": len(periods[1]),
                "Average LOC per Active Week": decimal_ratio(added, len(periods[1])),
                "Active Months": len(periods[2]),
                "Average LOC per Active Month": decimal_ratio(added, len(periods[2])),
            }
        )
    return sorted(
        rows,
        key=lambda row: (-as_int(row["Lines Added"]), str(row["Developer"]), str(row["Email"])),
    )


def validate_developer_series(
    summaries: Sequence[Row],
    daily: Sequence[Row],
    weekly: Sequence[Row],
    monthly: Sequence[Row],
) -> list[dict[str, object]]:
    validations: list[dict[str, object]] = []
    definitions = (
        (daily, "Date", "Active Days", "Average LOC per Active Day", "Daily"),
        (weekly, "ISO Week", "Active Weeks", "Average LOC per Active Week", "Weekly"),
        (monthly, "Month", "Active Months", "Average LOC per Active Month", "Monthly"),
    )
    for summary in summaries:
        identity = (summary["Repository"], summary["Developer"], summary["Email"])
        scope = " | ".join(str(value) for value in identity)
        expected_added = as_int(summary["Lines Added"])
        for series, period_field, active_field, average_field, label in definitions:
            rows = [
                row
                for row in series
                if (row["Repository"], row["Developer"], row["Email"]) == identity
            ]
            checks = (
                (
                    f"Sum({label} Lines Added) = Developer Total Lines Added",
                    expected_added,
                    sum(as_int(row["Lines Added"]) for row in rows),
                ),
                (
                    f"Distinct {label} periods = {active_field}",
                    as_int(summary[active_field]),
                    len({row[period_field] for row in rows}),
                ),
                (
                    f"{label} average = Lines Added / active periods",
                    summary[average_field],
                    decimal_ratio(expected_added, as_int(summary[active_field])),
                ),
            )
            for check, expected, actual in checks:
                validations.append(
                    {
                        "Scope": scope,
                        "Check": check,
                        "Expected": expected,
                        "Actual": actual,
                        "Status": "PASS" if str(expected) == str(actual) else "FAIL",
                    }
                )
    return validations
