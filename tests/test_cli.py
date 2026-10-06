from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from repo_audit import __version__
from repo_audit.cli import EXIT_FAILURE, EXIT_SUCCESS, EXIT_USAGE, main

from helpers import create_repository, local_repository_entry, write_config


def invoke(*arguments: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = main(list(arguments))
        except SystemExit as exit_request:
            code = int(exit_request.code or 0)
    return code, stdout.getvalue(), stderr.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_version(self) -> None:
        code, stdout, _ = invoke("--version")
        self.assertEqual(EXIT_SUCCESS, code)
        self.assertIn(__version__, stdout)

    def test_init_creates_template_and_refuses_overwrite(self) -> None:
        target = self.root / "audit.toml"
        self.assertEqual(EXIT_SUCCESS, invoke("init", str(target))[0])
        self.assertIn("schema_version = 1", target.read_text(encoding="utf-8"))
        code, _, stderr = invoke("init", str(target))
        self.assertEqual(EXIT_USAGE, code)
        self.assertIn("Refusing to overwrite", stderr)

    def test_validate_config_reports_normalized_paths(self) -> None:
        source, _ = create_repository(self.root, {"app.py": "x = 1\n"})
        config = write_config(self.root, local_repository_entry("sample", source))
        code, stdout, _ = invoke("validate-config", "--config", str(config))
        self.assertEqual(EXIT_SUCCESS, code)
        summary = json.loads(stdout)
        self.assertEqual(["sample"], summary["repositories"])
        self.assertEqual("branches-and-tags", summary["history_scope"])

    def test_invalid_config_is_a_usage_error(self) -> None:
        config = self.root / "audit.toml"
        config.write_text("schema_version = 2\n", encoding="utf-8")
        code, _, stderr = invoke("validate-config", "--config", str(config))
        self.assertEqual(EXIT_USAGE, code)
        self.assertIn("configuration error", stderr)

    def test_audit_and_verify_round_trip(self) -> None:
        source, sha = create_repository(self.root, {"app.py": "x = 1\n"})
        config = write_config(self.root, local_repository_entry("sample", source, sha))
        code, stdout, stderr = invoke("audit", "--config", str(config))
        self.assertEqual(EXIT_SUCCESS, code, stderr)
        self.assertIn("Audit completed", stdout)
        code, stdout, _ = invoke("verify", "--config", str(config))
        self.assertEqual(EXIT_SUCCESS, code)
        self.assertIn("Verification passed", stdout)
        code, stdout, _ = invoke("verify", "--output", str(self.root / "output"), "--json")
        self.assertEqual(EXIT_SUCCESS, code)
        self.assertTrue(json.loads(stdout)["checks"])

    def test_runtime_failures_use_exit_code_one(self) -> None:
        source, _ = create_repository(self.root, {"app.py": "x = 1\n"})
        config = write_config(self.root, local_repository_entry("sample", source, "0" * 40))
        code, _, stderr = invoke("audit", "--config", str(config))
        self.assertEqual(EXIT_FAILURE, code)
        self.assertIn("expected", stderr)
        code, stdout, _ = invoke("verify", "--output", str(self.root / "missing"))
        self.assertEqual(EXIT_FAILURE, code)
        self.assertIn("Verification failed", stdout)


if __name__ == "__main__":
    unittest.main()
