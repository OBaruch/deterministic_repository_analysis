"""Canonical CSV output, Markdown reports, and SVG charts."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from pathlib import Path

CSV_SCHEMAS: dict[str, tuple[str, ...]] = {
    "repository_summary.csv": (
        "Repository",
        "Requested Ref",
        "Resolved Ref",
        "Commit SHA",
        "Total Files",
        "Source Files",
        "Languages",
        "Lines of Code",
        "Unique Commits",
    ),
    "files.csv": ("Repository", "File", "Language", "Lines of Code"),
    "languages.csv": (
        "Repository",
        "Language",
        "Files",
        "Lines of Code",
        "Percentage Files",
        "Percentage LOC",
    ),
    "commits.csv": (
        "Repository",
        "Commit SHA",
        "Author Name",
        "Author Email",
        "Original Author Name",
        "Original Author Email",
        "Author Date",
        "Lines Added",
        "Lines Deleted",
        "Net Lines",
        "Binary Files Excluded",
    ),
    "developer_summary.csv": (
        "Repository",
        "Developer",
        "Email",
        "First Commit",
        "Last Commit",
        "Commits",
        "Lines Added",
        "Lines Deleted",
        "Net Lines",
        "Active Days",
        "Average LOC per Active Day",
        "Active Weeks",
        "Average LOC per Active Week",
        "Active Months",
        "Average LOC per Active Month",
    ),
    "developer_daily.csv": (
        "Repository",
        "Developer",
        "Email",
        "Date",
        "Commits",
        "Lines Added",
        "Lines Deleted",
    ),
    "developer_weekly.csv": (
        "Repository",
        "Developer",
        "Email",
        "ISO Week",
        "Commits",
        "Lines Added",
        "Lines Deleted",
    ),
    "developer_monthly.csv": (
        "Repository",
        "Developer",
        "Email",
        "Month",
        "Commits",
        "Lines Added",
        "Lines Deleted",
    ),
    "developer_global_summary.csv": (
        "Developer",
        "Email",
        "Repositories",
        "Commits",
        "Lines Added",
        "Active Days",
        "Average LOC per Active Day",
        "Active Weeks",
        "Average LOC per Active Week",
        "Active Months",
        "Average LOC per Active Month",
    ),
    "excluded_files.csv": ("Repository", "File", "Reason"),
    "excluded_authors.csv": ("Repository", "Developer", "Email", "Rule", "Commits"),
    "global_languages.csv": ("Language", "Files", "Lines of Code", "Percentage Global LOC"),
    "repository_percentages.csv": (
        "Repository",
        "Lines of Code",
        "Percentage Total LOC",
        "Files",
        "Percentage Total Files",
        "Unique Commits",
        "Percentage Sum Repository Commits",
    ),
    "top_20_files.csv": ("Rank", "Repository", "File", "Language", "Lines of Code"),
    "validation.csv": ("Scope", "Check", "Expected", "Actual", "Status"),
}


SVG_STYLE = (
    "text{font-family:Segoe UI,Arial,sans-serif;fill:#17212b}"
    ".title{font-size:24px;font-weight:700}"
    ".label{font-size:13px}"
    ".value{font-size:13px;font-weight:600}"
    ".grid{stroke:#d8dee4;stroke-width:1}"
)
DEVELOPER_CHARTS = (
    ("Lines Added", "lines-added", "Total lines added", "integer"),
    (
        "Average LOC per Active Day",
        "average-loc-active-day",
        "Average LOC added per active day",
        "decimal",
    ),
    (
        "Average LOC per Active Week",
        "average-loc-active-week",
        "Average LOC added per active week",
        "decimal",
    ),
    (
        "Average LOC per Active Month",
        "average-loc-active-month",
        "Average LOC added per active month",
        "decimal",
    ),
)
GLOBAL_CHARTS = (
    ("LOC by repository", "loc-by-repository.svg"),
    ("Files by repository", "files-by-repository.svg"),
    ("Commits by repository", "commits-by-repository.svg"),
    ("Percentage of LOC", "loc-percentage-by-repository.svg"),
    ("LOC by language", "loc-by-language.svg"),
    ("Files by language", "files-by-language.svg"),
)
HISTORY_SCOPE_DESCRIPTIONS = {
    "branches-and-tags": (
        "branches, tags, and remote-tracking branches plus the snapshot commit "
        "(hosting-internal refs such as pull-request refs, notes, and stashes are excluded)"
    ),
    "all-refs": "every ref (`--all`), including hosting-internal refs, notes, and stashes",
}


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_canonical_csvs(
    output: Path,
    tables: Mapping[str, Sequence[Mapping[str, object]]],
) -> None:
    for filename, fields in CSV_SCHEMAS.items():
        if filename not in tables:
            raise ValueError(f"Missing canonical table: {filename}")
        write_csv(output / filename, fields, tables[filename])


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def display_integer(value: str | int) -> str:
    return f"{int(value):,}"


def display_decimal(value: str | Decimal, suffix: str = "") -> str:
    decimal_value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{decimal_value:,.2f}{suffix}"


def slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in value).strip(
        "-"
    )


_MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]<>|~$&])")


def markdown_text(value: object) -> str:
    """Escape data so Markdown renderers display it literally."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", str(value)).replace("\r", " ").replace("\n", " ")


def code_span(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    fence = "`" * (max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    padding = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{padding}{text}{padding}{fence}"


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(markdown_text(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def write_bar_chart(
    path: Path,
    title: str,
    rows: Sequence[tuple[str, Decimal]],
    value_kind: str = "integer",
) -> None:
    width = 1200
    left = 420
    right = 150
    top = 80
    row_height = 30
    height = max(260, top + len(rows) * row_height + 60)
    plot_width = width - left - right
    maximum = max((value for _, value in rows), default=Decimal(0))
    palette = ("#0b6e75", "#c8553d", "#5b5f97", "#2f7d32", "#9c6b19")
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f"<style>{SVG_STYLE}</style>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text class="title" x="24" y="40">{escape(title)}</text>',
        f'<line class="grid" x1="{left}" y1="{top - 12}" x2="{left}" y2="{height - 35}"/>',
    ]
    for index, (label, value) in enumerate(rows):
        y = top + index * row_height
        bar_width = Decimal(0) if maximum == 0 else value * Decimal(plot_width) / maximum
        clipped = label if len(label) <= 55 else f"{label[:52]}..."
        if value_kind == "integer":
            shown = display_integer(int(value))
        elif value_kind == "percentage":
            shown = display_decimal(value, "%")
        else:
            shown = display_decimal(value)
        color = palette[index % len(palette)]
        svg.extend(
            (
                f'<text class="label" x="{left - 12}" y="{y + 16}" text-anchor="end">'
                f"<title>{escape(label)}</title>{escape(clipped)}</text>",
                f'<rect x="{left}" y="{y}" width="{bar_width:.3f}" height="20" fill="{color}"/>',
                f'<text class="value" x="{left + float(bar_width) + 8:.3f}" y="{y + 16}">'
                f"{escape(shown)}</text>",
            )
        )
    svg.append("</svg>")
    path.write_text("\n".join(svg) + "\n", encoding="utf-8", newline="\n")


def generate_charts(output: Path) -> None:
    charts = output / "charts"
    charts.mkdir(exist_ok=True)
    repositories = read_csv(output / "repository_summary.csv")
    percentages = read_csv(output / "repository_percentages.csv")
    languages = read_csv(output / "global_languages.csv")
    developers = read_csv(output / "developer_summary.csv")
    global_specs = (
        (
            "loc-by-repository.svg",
            "Lines of code by repository",
            "Lines of Code",
            "integer",
            repositories,
        ),
        (
            "files-by-repository.svg",
            "Tracked files by repository",
            "Total Files",
            "integer",
            repositories,
        ),
        (
            "commits-by-repository.svg",
            "Unique commits by repository",
            "Unique Commits",
            "integer",
            repositories,
        ),
        (
            "loc-percentage-by-repository.svg",
            "Percentage of total LOC by repository",
            "Percentage Total LOC",
            "percentage",
            percentages,
        ),
    )
    for filename, title, field, kind, source in global_specs:
        write_bar_chart(
            charts / filename,
            title,
            [(row["Repository"], Decimal(row[field])) for row in source],
            kind,
        )
    write_bar_chart(
        charts / "loc-by-language.svg",
        "Global lines of code by language",
        [(row["Language"], Decimal(row["Lines of Code"])) for row in languages],
    )
    write_bar_chart(
        charts / "files-by-language.svg",
        "Global source files by language",
        [(row["Language"], Decimal(row["Files"])) for row in languages],
    )
    for repository in repositories:
        name = repository["Repository"]
        repository_developers = [row for row in developers if row["Repository"] == name]
        for field, filename, title, kind in DEVELOPER_CHARTS:
            chart_rows = sorted(
                (
                    (f"{row['Developer']} <{row['Email']}>", Decimal(row[field]))
                    for row in repository_developers
                ),
                key=lambda item: (-item[1], item[0]),
            )
            write_bar_chart(
                charts / f"{slug(name)}-{filename}.svg", f"{title} - {name}", chart_rows, kind
            )


def _bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _repository_report(
    summary: dict[str, str],
    files: Sequence[dict[str, str]],
    languages: Sequence[dict[str, str]],
    developers: Sequence[dict[str, str]],
) -> str:
    name = summary["Repository"]
    repo_files = [row for row in files if row["Repository"] == name]
    repo_languages = [row for row in languages if row["Repository"] == name]
    repo_developers = [row for row in developers if row["Repository"] == name]
    sections = [
        f"# Repository: {markdown_text(name)}",
        _bullets(
            (
                f"Requested Ref: {code_span(summary['Requested Ref'])}",
                f"Resolved Ref: {code_span(summary['Resolved Ref'])}",
                f"Commit SHA: {code_span(summary['Commit SHA'])}",
                f"Total Files: {display_integer(summary['Total Files'])}",
                f"Source Code Files: {display_integer(summary['Source Files'])}",
                f"Number of Languages: {display_integer(summary['Languages'])}",
                f"Total Lines of Code: {display_integer(summary['Lines of Code'])}",
                f"Total Unique Commits: {display_integer(summary['Unique Commits'])}",
            )
        ),
        "## Files by Language\n\n"
        + markdown_table(
            ("Language", "Files", "% Files"),
            [
                (
                    row["Language"],
                    display_integer(row["Files"]),
                    display_decimal(row["Percentage Files"], "%"),
                )
                for row in repo_languages
            ],
        ),
        "## LOC by Language\n\n"
        + markdown_table(
            ("Language", "Lines of Code", "% Code"),
            [
                (
                    row["Language"],
                    display_integer(row["Lines of Code"]),
                    display_decimal(row["Percentage LOC"], "%"),
                )
                for row in repo_languages
            ],
        ),
        "## File-Level LOC\n\n"
        + markdown_table(
            ("File", "Language", "Lines of Code"),
            [
                (row["File"], row["Language"], display_integer(row["Lines of Code"]))
                for row in repo_files
            ],
        ),
        "## Developer Summary\n\n"
        + markdown_table(
            (
                "Developer",
                "Email",
                "First Commit",
                "Last Commit",
                "Commits",
                "Lines Added",
                "Lines Deleted",
                "Net Lines",
                "Active Days",
                "Avg LOC / Day",
                "Active Weeks",
                "Avg LOC / Week",
                "Active Months",
                "Avg LOC / Month",
            ),
            [
                (
                    row["Developer"],
                    row["Email"],
                    row["First Commit"],
                    row["Last Commit"],
                    display_integer(row["Commits"]),
                    display_integer(row["Lines Added"]),
                    display_integer(row["Lines Deleted"]),
                    display_integer(row["Net Lines"]),
                    display_integer(row["Active Days"]),
                    display_decimal(row["Average LOC per Active Day"]),
                    display_integer(row["Active Weeks"]),
                    display_decimal(row["Average LOC per Active Week"]),
                    display_integer(row["Active Months"]),
                    display_decimal(row["Average LOC per Active Month"]),
                )
                for row in repo_developers
            ],
        ),
        "## Developer Charts\n\n"
        + "\n\n".join(
            f"![{label}](../charts/{slug(name)}-{filename}.svg)"
            for label, filename, _, _ in DEVELOPER_CHARTS
        ),
    ]
    return "\n\n".join(sections) + "\n"


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def generate_reports(output: Path, title: str) -> None:
    reports = output / "reports"
    reports.mkdir(exist_ok=True)
    repositories = read_csv(output / "repository_summary.csv")
    files = read_csv(output / "files.csv")
    languages = read_csv(output / "languages.csv")
    developers = read_csv(output / "developer_summary.csv")
    global_developers = read_csv(output / "developer_global_summary.csv")
    global_languages = read_csv(output / "global_languages.csv")
    percentages = read_csv(output / "repository_percentages.csv")
    top_files = read_csv(output / "top_20_files.csv")
    validations = read_csv(output / "validation.csv")
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))

    for repository in repositories:
        _write_text(
            reports / f"{repository['Repository']}.md",
            _repository_report(repository, files, languages, developers),
        )

    total_files = sum(int(row["Total Files"]) for row in repositories)
    total_sources = sum(int(row["Source Files"]) for row in repositories)
    total_loc = sum(int(row["Lines of Code"]) for row in repositories)
    total_commits = sum(int(row["Unique Commits"]) for row in repositories)
    repository_table = markdown_table(
        (
            "Repository",
            "Total Files",
            "Source Files",
            "Languages",
            "Lines of Code",
            "Unique Commits",
        ),
        [
            (
                row["Repository"],
                display_integer(row["Total Files"]),
                display_integer(row["Source Files"]),
                display_integer(row["Languages"]),
                display_integer(row["Lines of Code"]),
                display_integer(row["Unique Commits"]),
            )
            for row in repositories
        ],
    )
    global_report = "\n\n".join(
        (
            "# GLOBAL SUMMARY",
            repository_table,
            "## Combined Totals\n\n"
            + _bullets(
                (
                    f"Total files: {display_integer(total_files)}",
                    f"Total source files: {display_integer(total_sources)}",
                    f"Total LOC: {display_integer(total_loc)}",
                    f"Total distinct languages: {display_integer(len(global_languages))}",
                    f"Sum of repository commit counts: {display_integer(total_commits)}",
                )
            ),
            "## Repository Percentages\n\n"
            + markdown_table(
                ("Repository", "% Total LOC", "% Total Files", "% Commit Count Sum"),
                [
                    (
                        row["Repository"],
                        display_decimal(row["Percentage Total LOC"], "%"),
                        display_decimal(row["Percentage Total Files"], "%"),
                        display_decimal(row["Percentage Sum Repository Commits"], "%"),
                    )
                    for row in percentages
                ],
            ),
            "## Top 20 Files\n\n"
            + markdown_table(
                ("Rank", "Repository", "File", "Language", "Lines of Code"),
                [
                    (
                        row["Rank"],
                        row["Repository"],
                        row["File"],
                        row["Language"],
                        display_integer(row["Lines of Code"]),
                    )
                    for row in top_files
                ],
            ),
            "## Global Language Distribution\n\n"
            + markdown_table(
                ("Language", "Files", "Lines of Code", "% Global LOC"),
                [
                    (
                        row["Language"],
                        display_integer(row["Files"]),
                        display_integer(row["Lines of Code"]),
                        display_decimal(row["Percentage Global LOC"], "%"),
                    )
                    for row in global_languages
                ],
            ),
            "## Consolidated Developers by Exact Identity\n\n"
            + markdown_table(
                (
                    "Developer",
                    "Email",
                    "Repositories",
                    "Commits",
                    "Lines Added",
                    "Active Days",
                    "Avg LOC / Day",
                    "Active Weeks",
                    "Avg LOC / Week",
                    "Active Months",
                    "Avg LOC / Month",
                ),
                [
                    (
                        row["Developer"],
                        row["Email"],
                        row["Repositories"],
                        display_integer(row["Commits"]),
                        display_integer(row["Lines Added"]),
                        display_integer(row["Active Days"]),
                        display_decimal(row["Average LOC per Active Day"]),
                        display_integer(row["Active Weeks"]),
                        display_decimal(row["Average LOC per Active Week"]),
                        display_integer(row["Active Months"]),
                        display_decimal(row["Average LOC per Active Month"]),
                    )
                    for row in global_developers
                ],
            ),
            "## Global Charts\n\n"
            + "\n\n".join(f"![{label}](../charts/{filename})" for label, filename in GLOBAL_CHARTS),
        )
    )
    _write_text(reports / "global-summary.md", global_report + "\n")

    loc_tool = metadata["loc_tool"]
    methodology = "\n\n".join(
        (
            "# METHODOLOGY AND REPRODUCIBILITY",
            "## Toolchain\n\n"
            + _bullets(
                (
                    f"Toolkit version: {code_span(metadata['toolkit_version'])}",
                    f"Git version: {code_span(metadata['git_version'])}",
                    f"LOC command: {code_span(loc_tool['command'])}",
                    f"LOC options: {code_span(' '.join(loc_tool['options']))}",
                    f"LOC version: {code_span(loc_tool['version'])}",
                    f"LOC executable SHA-256: {code_span(loc_tool['sha256'])}",
                    f"Python version: {code_span(metadata['python_version'])}",
                    f"Configuration SHA-256: {code_span(metadata['config_sha256'])}",
                )
            ),
            "## Snapshot References\n\n"
            + markdown_table(
                ("Repository", "Requested Ref", "Resolved Ref", "Commit SHA"),
                [
                    (
                        row["Repository"],
                        row["Requested Ref"],
                        row["Resolved Ref"],
                        row["Commit SHA"],
                    )
                    for row in repositories
                ],
            ),
            "## Deterministic Rules\n\n"
            + _bullets(
                (
                    "Remote repositories are mirrored into the external workspace; local "
                    "repositories are read in place and never checked out.",
                    "Tracked files come from NUL-delimited `git ls-tree -r -z` output for the "
                    "recorded commit SHA.",
                    "Regular files are materialized byte-for-byte with `git cat-file --batch`; "
                    "no checkout, filter, text conversion, or archive attribute is applied.",
                    "Source files, languages, and LOC come from the verified LOC tool, invoked "
                    "once per repository with the options listed above.",
                    "History covers "
                    + HISTORY_SCOPE_DESCRIPTIONS.get(
                        str(metadata["history_scope"]), str(metadata["history_scope"])
                    )
                    + ".",
                    "Unique commits use `git rev-list --count` over the history scope.",
                    "Developer contribution uses `git log --no-merges --root --numstat` with "
                    "rename detection, external diff drivers, and text conversion disabled and "
                    "the Myers diff algorithm pinned.",
                    "Binary numstat entries (`-`) are excluded from line counts. Merge commits "
                    "are excluded from contribution metrics.",
                    "Developer identity is exact `Author Name + Author Email`, unless an "
                    "explicit TOML alias maps it.",
                    "Active days use the local date of the author timestamp; active weeks use "
                    "ISO year-week; active months use `YYYY-MM`.",
                    "CSV ratios are rounded half-up to 12 decimals; Markdown and chart labels "
                    "are rounded to 2 decimals.",
                    "Reports and SVG charts are generated by re-reading canonical CSV files.",
                )
            ),
            "## Reproduction\n\n"
            + "```console\nrepo-audit audit --config audit.toml\n"
            + "repo-audit verify --output <output-dir>\n```",
        )
    )
    _write_text(output / "METHODOLOGY.md", methodology + "\n")

    def largest(field: str) -> dict[str, str]:
        return sorted(repositories, key=lambda row: (-int(row[field]), row["Repository"]))[0]

    largest_loc = largest("Lines of Code")
    largest_files = largest("Total Files")
    most_commits = largest("Unique Commits")
    most_used = (
        global_languages[0] if global_languages else {"Language": "N/A", "Lines of Code": "0"}
    )
    passed = sum(row["Status"] == "PASS" for row in validations)
    failed = len(validations) - passed
    source_checks = [row for row in validations if row["Check"] == "Source repository unchanged"]
    unchanged = bool(source_checks) and all(row["Status"] == "PASS" for row in source_checks)
    report = "\n\n".join(
        (
            f"# {markdown_text(title)}",
            "## EXECUTIVE SUMMARY\n\n"
            + "\n\n".join(
                (
                    f"**Repositories analyzed:** {display_integer(len(repositories))}",
                    f"**Total files:** {display_integer(total_files)}",
                    f"**Total source files:** {display_integer(total_sources)}",
                    f"**Total lines of code:** {display_integer(total_loc)}",
                    f"**Sum of repository commit counts:** {display_integer(total_commits)}",
                    f"**Distinct languages detected:** {display_integer(len(global_languages))}",
                    f"**Developers detected:** {display_integer(len(global_developers))}",
                    "**Largest repository by LOC:** "
                    f"{markdown_text(largest_loc['Repository'])} "
                    f"({display_integer(largest_loc['Lines of Code'])})",
                    "**Largest repository by files:** "
                    f"{markdown_text(largest_files['Repository'])} "
                    f"({display_integer(largest_files['Total Files'])})",
                    "**Repository with most commits:** "
                    f"{markdown_text(most_commits['Repository'])} "
                    f"({display_integer(most_commits['Unique Commits'])})",
                    "**Most used language by LOC:** "
                    f"{markdown_text(most_used['Language'])} "
                    f"({display_integer(most_used['Lines of Code'])})",
                )
            ),
            "## Reports\n\n"
            + _bullets(
                [
                    f"[{markdown_text(row['Repository'])}](reports/{row['Repository']}.md)"
                    for row in repositories
                ]
                + ["[Global summary](reports/global-summary.md)", "[Methodology](METHODOLOGY.md)"]
            ),
            "## VALIDATION SUMMARY\n\n"
            f"**Checks passed:** {display_integer(passed)}\n\n"
            f"**Checks failed:** {display_integer(failed)}",
            "## READ-ONLY VALIDATION\n\n"
            + _bullets(
                (
                    "Source worktree status and Git references unchanged (fingerprinted before "
                    f"and after the run): {'YES' if unchanged else 'NO'}",
                    "Commits, pushes, branches, merges, rebases, or pull requests issued by the "
                    "toolkit: NONE",
                )
            ),
        )
    )
    _write_text(output / "REPORT.md", report + "\n")
