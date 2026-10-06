from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from repo_audit import pdf
from repo_audit.reporting import markdown_table


class PdfTests(unittest.TestCase):
    def build(self, report_body: str) -> str:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "reports").mkdir()
            with (output / "repository_summary.csv").open(
                "w", encoding="utf-8", newline=""
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "Repository",
                        "Total Files",
                        "Source Files",
                        "Lines of Code",
                        "Unique Commits",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Repository": "sample",
                        "Total Files": 2,
                        "Source Files": 1,
                        "Lines of Code": 10,
                        "Unique Commits": 3,
                    }
                )
            (output / "REPORT.md").write_text(report_body, encoding="utf-8")
            (output / "METHODOLOGY.md").write_text("# Methodology\n", encoding="utf-8")
            (output / "reports" / "global-summary.md").write_text(
                "# Global\n\n[Methodology](../METHODOLOGY.md)\n", encoding="utf-8"
            )
            (output / "reports" / "sample.md").write_text("# Sample\n", encoding="utf-8")
            return pdf.build_html(output, "Generic <Audit>").read_text(encoding="utf-8")

    def test_builds_html_with_cover_contents_and_sections(self) -> None:
        content = self.build("# Report\n\n**Checks passed:** 4\n")
        self.assertIn("Generic &lt;Audit&gt;", content)
        self.assertIn("<strong>Checks passed:</strong> 4", content)
        self.assertIn("Methodology and reproducibility", content)
        self.assertIn('<a href="file://', content)

    def test_data_that_looks_like_markdown_is_rendered_literally(self) -> None:
        table = markdown_table(
            ("File", "Owner"),
            (("[evil](javascript:alert(1)).py", "a|b"), ("__init__.py", "`tick`")),
        )
        content = self.build(f"# Report\n\n{table}\n\nRef `refs/heads/main` and `` a`b ``\n")
        self.assertIn("<td>[evil](javascript:alert(1)).py</td>", content)
        self.assertIn("<td>a|b</td>", content)
        self.assertIn("<td>__init__.py</td>", content)
        self.assertIn("<td>`tick`</td>", content)
        self.assertIn("<code>refs/heads/main</code>", content)
        self.assertIn("<code>a`b</code>", content)
        self.assertNotIn('javascript:alert(1)"', content)

    def test_rejects_links_that_escape_the_output_directory(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "escapes output directory"):
            self.build("# Report\n\n[secret](../../etc/passwd)\n")

    def test_browser_arguments_include_configured_extra_flags(self) -> None:
        html_path = Path(tempfile.gettempdir()) / "report.html"
        with mock.patch.dict(pdf.os.environ, {"REPO_AUDIT_BROWSER_ARGS": "--no-sandbox --lang=en"}):
            arguments = pdf._browser_arguments(Path("chrome"), "p", Path("o.pdf"), html_path)
        self.assertIn("--lang=en", arguments)
        self.assertTrue(arguments[-1].startswith("file:"))

    def test_browser_discovery_prefers_explicit_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            browser = Path(temporary) / "custom-browser"
            browser.write_text("", encoding="utf-8")
            with mock.patch.dict(pdf.os.environ, {"REPO_AUDIT_BROWSER": str(browser)}):
                self.assertEqual(browser.resolve(), pdf._browser())

    def test_browser_arguments_disable_sandbox_only_for_root(self) -> None:
        html_path = Path(tempfile.gettempdir()) / "report.html"
        with mock.patch.object(pdf.os, "geteuid", create=True, return_value=0):
            self.assertIn(
                "--no-sandbox",
                pdf._browser_arguments(Path("chrome"), "p", Path("o.pdf"), html_path),
            )
        with mock.patch.object(pdf.os, "geteuid", create=True, return_value=1000):
            self.assertNotIn(
                "--no-sandbox",
                pdf._browser_arguments(Path("chrome"), "p", Path("o.pdf"), html_path),
            )


if __name__ == "__main__":
    unittest.main()
