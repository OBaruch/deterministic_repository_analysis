from __future__ import annotations

import csv
import filecmp
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from repo_audit.config import load_config
from repo_audit.pipeline import OUTPUT_MARKER, ValidationError, run_audit
from repo_audit.reporting import CSV_SCHEMAS
from repo_audit.verify import verify_output

from helpers import command, commit_files, create_repository, local_repository_entry, write_config


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.source, self.sha = create_repository(
            self.root,
            {
                "module.py": "value = 1\n",
                "pkg/__init__.py": "VERSION = 1\n",
                "pkg/empty.py": "",
                "docs/README.md": "# Docs\n\nText\n",
                "assets/logo.png": b"\x89PNG\x00",
            },
        )
        commit_files(
            self.source,
            {"module.py": "value = 1\nother = 2\n"},
            "second",
            author="Second Developer <second@example.com>",
            date="2026-02-03T08:30:00-05:00",
        )
        self.sha = command("git", "rev-parse", "HEAD", cwd=self.source)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def config(self, extra: str = ""):
        return load_config(
            write_config(
                self.root, local_repository_entry("sample", self.source, self.sha), extra=extra
            )
        )

    def test_end_to_end_local_audit_passes_every_check(self) -> None:
        output = run_audit(self.config())
        for name in (
            *CSV_SCHEMAS,
            "REPORT.md",
            "METHODOLOGY.md",
            "metadata.json",
            "audit-data.json",
        ):
            self.assertTrue((output / name).is_file(), name)
        validations = read_rows(output / "validation.csv")
        self.assertGreater(len(validations), 10)
        self.assertEqual({"PASS"}, {row["Status"] for row in validations})
        summary = read_rows(output / "repository_summary.csv")[0]
        self.assertEqual(
            ("5", "3", "2", "5", "2"),
            (
                summary["Total Files"],
                summary["Source Files"],
                summary["Languages"],
                summary["Lines of Code"],
                summary["Unique Commits"],
            ),
        )
        report = (output / "REPORT.md").read_text(encoding="utf-8")
        self.assertIn("**Checks failed:** 0", report)
        self.assertIn("unchanged (fingerprinted before and after the run): YES", report)
        self.assertIn(
            "\\_\\_init\\_\\_.py", (output / "reports" / "sample.md").read_text(encoding="utf-8")
        )
        metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(self.sha, metadata["repositories"][0]["commit_sha"])
        self.assertEqual("branches-and-tags", metadata["history_scope"])
        self.assertEqual("", command("git", "status", "--porcelain", cwd=self.source))
        rows = verify_output(output)
        self.assertEqual([], [row for row in rows if row["Status"] != "PASS"])

    def test_repeated_runs_produce_identical_outputs(self) -> None:
        config = self.config()
        first = self.root / "first-run"
        run_audit(config).rename(first)
        second = run_audit(config)
        comparison = filecmp.dircmp(first, second)
        self.assertEqual([], comparison.left_only + comparison.right_only + comparison.diff_files)
        for name, subdirectory in comparison.subdirs.items():
            self.assertEqual([], subdirectory.diff_files, name)

    def test_refuses_to_replace_unmarked_or_unforced_output(self) -> None:
        config = self.config()
        config.output_dir.mkdir(parents=True)
        (config.output_dir / "keep.txt").write_text("user data", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "not empty"):
            run_audit(config)
        with self.assertRaisesRegex(RuntimeError, "unmarked directory"):
            run_audit(config, force=True)
        (config.output_dir / "keep.txt").unlink()
        run_audit(config)
        self.assertTrue((config.output_dir / OUTPUT_MARKER).is_file())
        run_audit(config, force=True)

    def test_inconsistent_loc_report_fails_validation_with_evidence(self) -> None:
        with (
            mock.patch.dict(os.environ, {"FAKE_CLOC_SUM_OFFSET": "1"}),
            self.assertRaisesRegex(ValidationError, "1 validation check"),
        ):
            run_audit(self.config())
        output = self.root / "output"
        failures = [row for row in read_rows(output / "validation.csv") if row["Status"] == "FAIL"]
        self.assertEqual(
            ["LOC tool SUM(code) = Sum(LOC by file)"], [row["Check"] for row in failures]
        )
        self.assertFalse((output / "REPORT.md").exists())

    def test_verify_detects_tampered_outputs(self) -> None:
        output = run_audit(self.config())
        files = output / "files.csv"
        files.write_text(
            files.read_text(encoding="utf-8-sig").replace(",2\n", ",3\n", 1), encoding="utf-8-sig"
        )
        failures = [row["Check"] for row in verify_output(output) if row["Status"] != "PASS"]
        self.assertIn("Repository LOC = Sum(LOC by file)", failures)
        self.assertIn("audit-data.json files.csv = CSV", failures)

    def test_remote_mirror_audit(self) -> None:
        config_path = write_config(
            self.root,
            f"""
[[repositories]]
name = "remote-sample"
url = "{self.source.as_uri()}"
ref = "main"
expected_sha = "{self.sha}"
""",
        )
        output = run_audit(load_config(config_path))
        summary = read_rows(output / "repository_summary.csv")[0]
        self.assertEqual("refs/heads/main", summary["Resolved Ref"])
        self.assertTrue(
            (self.root / "workspace" / "mirrors" / "remote-sample.git" / "HEAD").is_file()
        )


if __name__ == "__main__":
    unittest.main()
