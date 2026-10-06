from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from repo_audit.gitops import prepare_repository
from repo_audit.loc import LocError, analyze_snapshot, resolve_loc_tool
from repo_audit.models import LocToolConfig, RepositorySpec

from helpers import FAKE_CLOC, create_repository, fake_loc_config


class LocTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def prepare(self, files: dict[str, str | bytes]):
        source, sha = create_repository(self.root, files)
        return prepare_repository(
            RepositorySpec(name="sample", path=source, expected_sha=sha, fetch=False),
            self.root / "workspace",
            require_clean=True,
        )

    def test_counts_every_file_and_maps_unsafe_names_back(self) -> None:
        prepared = self.prepare(
            {
                "app.py": "print('one')\n\nprint('two')\n",
                "copy/app.py": "print('one')\n\nprint('two')\n",
                "odd, name's [1].py": "value = 1\n",
                "empty.py": "",
                "README.md": "# Example\n",
                "logo.png": b"\x89PNG\r\n",
            }
        )
        result = analyze_snapshot(resolve_loc_tool(fake_loc_config()), prepared, self.root / "raw")
        by_file = {str(row["File"]): row for row in result.files}
        self.assertEqual({"app.py", "copy/app.py", "odd, name's [1].py", "README.md"}, set(by_file))
        self.assertEqual(2, by_file["copy/app.py"]["Lines of Code"])
        self.assertEqual(1, by_file["odd, name's [1].py"]["Lines of Code"])
        self.assertEqual(6, result.reported_code)
        self.assertEqual(4, result.reported_files)
        reasons = {str(row["File"]): row["Reason"] for row in result.exclusions}
        self.assertEqual("Empty tracked file", reasons["empty.py"])
        self.assertEqual("Binary, compiled, archive, font, or media extension", reasons["logo.png"])
        self.assertEqual(len(prepared.tracked_files), len(result.files) + len(result.exclusions))

    def test_handles_snapshot_without_recognized_sources(self) -> None:
        prepared = self.prepare({"logo.png": b"\x89PNG\r\n", "data.bin": b"\x00"})
        result = analyze_snapshot(resolve_loc_tool(fake_loc_config()), prepared, self.root / "raw")
        self.assertEqual([], result.files)
        self.assertEqual((0, 0), (result.reported_code, result.reported_files))
        self.assertEqual(2, len(result.exclusions))

    def test_verifies_tool_version_and_hash(self) -> None:
        with self.assertRaisesRegex(LocError, "version mismatch"):
            resolve_loc_tool(
                LocToolConfig(command=(sys.executable, str(FAKE_CLOC)), expected_version="9.99")
            )
        with self.assertRaisesRegex(LocError, "SHA-256 mismatch"):
            resolve_loc_tool(
                LocToolConfig(command=(sys.executable, str(FAKE_CLOC)), expected_sha256="0" * 64)
            )
        tool = resolve_loc_tool(LocToolConfig(command=(sys.executable, str(FAKE_CLOC))))
        self.assertEqual("test-cloc-1", tool.version)
        self.assertEqual(64, len(tool.sha256))

    def test_reports_missing_tool(self) -> None:
        with self.assertRaisesRegex(LocError, "LOC tool not found"):
            resolve_loc_tool(LocToolConfig(command=("definitely-not-an-installed-cloc",)))


if __name__ == "__main__":
    unittest.main()
