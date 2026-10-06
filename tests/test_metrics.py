from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_audit.gitops import prepare_repository
from repo_audit.metrics import (
    MetricError,
    decimal_ratio,
    developer_outputs,
    extract_commits,
    global_developer_summary,
    language_summary,
    percentage,
    validate_developer_series,
)
from repo_audit.models import DeveloperConfig, RepositorySpec

from helpers import command, commit_files, create_repository


def commit(
    sha: str, date: str, added: int, deleted: int, repository: str = "sample"
) -> dict[str, object]:
    return {
        "Repository": repository,
        "Commit SHA": sha * 40,
        "Author Name": "Developer",
        "Author Email": "developer@example.com",
        "Author Date": date,
        "Lines Added": added,
        "Lines Deleted": deleted,
    }


class PureMetricTests(unittest.TestCase):
    def test_decimal_formatting_is_canonical(self) -> None:
        self.assertEqual("33.333333333333", percentage(1, 3))
        self.assertEqual("0.666666666667", decimal_ratio(2, 3))
        self.assertEqual("0.000000000000", decimal_ratio(5, 0))
        self.assertEqual("0.000000000001", decimal_ratio(5, 10**13))

    def test_language_percentages_reconcile(self) -> None:
        rows = language_summary(
            "sample",
            [
                {"Language": "Python", "Lines of Code": 75},
                {"Language": "Python", "Lines of Code": 15},
                {"Language": "JSON", "Lines of Code": 10},
            ],
        )
        self.assertEqual(["Python", "JSON"], [row["Language"] for row in rows])
        self.assertEqual("90.000000000000", rows[0]["Percentage LOC"])
        self.assertEqual("66.666666666667", rows[0]["Percentage Files"])

    def test_developer_periods_use_author_local_dates(self) -> None:
        commits = [
            commit("a", "2025-12-31T23:00:00-06:00", 30, 4),
            commit("b", "2026-01-01T09:00:00-06:00", 10, 2),
        ]
        summaries, daily, weekly, monthly = developer_outputs("sample", commits)
        summary = summaries[0]
        self.assertEqual(
            (2, 1, 2), (summary["Active Days"], summary["Active Weeks"], summary["Active Months"])
        )
        self.assertEqual(decimal_ratio(40, 2), summary["Average LOC per Active Day"])
        self.assertEqual("2025-12-31T23:00:00-06:00", summary["First Commit"])
        validations = validate_developer_series(summaries, daily, weekly, monthly)
        self.assertEqual({"PASS"}, {row["Status"] for row in validations})

    def test_global_summary_counts_shared_commits_once(self) -> None:
        shared = commit("c", "2026-02-01T10:00:00+00:00", 7, 0, "fork-a")
        rows = global_developer_summary([shared, {**shared, "Repository": "fork-b"}])
        self.assertEqual(1, rows[0]["Commits"])
        self.assertEqual(7, rows[0]["Lines Added"])
        self.assertEqual("fork-a; fork-b", rows[0]["Repositories"])
        with self.assertRaisesRegex(MetricError, "inconsistent metadata"):
            global_developer_summary([shared, {**shared, "Repository": "fork-b", "Lines Added": 8}])


class CommitExtractionTests(unittest.TestCase):
    def test_extracts_numstat_aliases_exclusions_and_merges(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _ = create_repository(root, {"app.py": "a\nb\nc\n", "logo.png": b"\x89PNG\x00"})
            commit_files(
                source,
                {"app.py": "a\nb\n"},
                "alias commit",
                author="Dev Alias <alias@example.com>",
                date="2026-01-16T10:00:00+00:00",
            )
            command("git", "checkout", "--quiet", "-b", "topic", cwd=source)
            commit_files(
                source,
                {"bot.txt": "generated\n"},
                "bot commit",
                author="build-bot <bot@example.com>",
                date="2026-01-17T10:00:00+00:00",
            )
            command("git", "checkout", "--quiet", "main", cwd=source)
            commit_files(source, {"other.py": "x\n"}, "main work", date="2026-01-18T10:00:00+00:00")
            command("git", "merge", "--quiet", "--no-ff", "-m", "merge topic", "topic", cwd=source)
            prepared = prepare_repository(
                RepositorySpec(name="sample", path=source, fetch=False), root / "workspace", True
            )
            extraction = extract_commits(
                prepared,
                DeveloperConfig(
                    exclude_patterns=(r"bot@example\.com",),
                    aliases={
                        "Dev Alias <alias@example.com>": "Example Developer <developer@example.com>"
                    },
                ),
            )
            self.assertEqual(4, extraction.expected_commits)
            self.assertEqual(4, extraction.parsed_commits)
            self.assertEqual(1, extraction.excluded_commits)
            self.assertEqual(3, len(extraction.commits))
            self.assertEqual(
                [{"Repository": "sample", "Developer": "build-bot", "Email": "bot@example.com",
                  "Rule": r"bot@example\.com", "Commits": 1}],
                extraction.excluded_authors,
            )  # fmt: skip
            initial = extraction.commits[0]
            self.assertEqual(
                (3, 0, 1),
                (
                    initial["Lines Added"],
                    initial["Lines Deleted"],
                    initial["Binary Files Excluded"],
                ),
            )
            aliased = extraction.commits[1]
            self.assertEqual("Example Developer", aliased["Author Name"])
            self.assertEqual("Dev Alias", aliased["Original Author Name"])
            self.assertEqual((0, 1), (aliased["Lines Added"], aliased["Lines Deleted"]))
            self.assertEqual(
                {"Example Developer"}, {row["Author Name"] for row in extraction.commits}
            )


if __name__ == "__main__":
    unittest.main()
