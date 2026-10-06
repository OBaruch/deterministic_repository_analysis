from __future__ import annotations

import tempfile
import tomllib
import unittest
from pathlib import Path

from repo_audit.cli import CONFIG_TEMPLATE
from repo_audit.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def load(self, content: str):
        path = self.root / "audit.toml"
        path.write_text(content, encoding="utf-8")
        return load_config(path)

    def assert_rejected(self, content: str, message: str) -> None:
        with self.assertRaisesRegex(ConfigError, message):
            self.load(content)

    def test_loads_local_and_remote_repositories(self) -> None:
        config = self.load(
            """
schema_version = 1
output_dir = "../out"
workspace_dir = "../work"

[[repositories]]
name = "remote-service"
url = "https://example.com/org/remote-service.git"
ref = "main"

[[repositories]]
name = "local-service"
path = "../local-service"
"""
        )
        remote, local = config.repositories
        self.assertTrue(remote.is_remote)
        self.assertTrue(remote.fetch)
        self.assertFalse(local.fetch)
        self.assertEqual("HEAD", local.ref)
        self.assertEqual((self.root / "../local-service").resolve(), local.path)
        self.assertEqual(("cloc",), config.loc.command)
        self.assertEqual("branches-and-tags", config.history_scope)
        self.assertEqual("Deterministic Repository Audit", config.title)

    def test_rejects_unknown_keys(self) -> None:
        self.assert_rejected(
            'schema_version = 1\ntypo = true\n[[repositories]]\nname = "s"\npath = "../s"\n',
            "Unknown top-level key",
        )
        self.assert_rejected(
            'schema_version = 1\n[[repositories]]\nname = "s"\npath = "../s"\nbranch = "x"\n',
            r"Unknown repositories\[1\] key",
        )

    def test_requires_supported_schema_version(self) -> None:
        self.assert_rejected('[[repositories]]\nname = "s"\npath = "../s"\n', "schema_version")

    def test_requires_exactly_one_source(self) -> None:
        self.assert_rejected(
            'schema_version = 1\n[[repositories]]\nname = "s"\npath = "../s"\n'
            'url = "https://example.com/s.git"\n',
            "exactly one of path or url",
        )

    def test_rejects_duplicate_names_case_insensitively(self) -> None:
        self.assert_rejected(
            'schema_version = 1\n[[repositories]]\nname = "Svc"\npath = "../a"\n'
            '[[repositories]]\nname = "svc"\npath = "../b"\n',
            "Duplicate repository name",
        )

    def test_rejects_credentials_in_urls(self) -> None:
        self.assert_rejected(
            'schema_version = 1\n[[repositories]]\nname = "s"\n'
            'url = "https://user:token@example.com/s.git"\n',
            "must not embed credentials",
        )

    def test_rejects_partial_commit_sha(self) -> None:
        self.assert_rejected(
            'schema_version = 1\n[[repositories]]\nname = "s"\npath = "../s"\n'
            f'expected_sha = "{"a" * 41}"\n',
            "full 40- or 64-character",
        )

    def test_rejects_nested_output_and_workspace(self) -> None:
        self.assert_rejected(
            'schema_version = 1\noutput_dir = "../out"\nworkspace_dir = "../out/work"\n'
            '[[repositories]]\nname = "s"\npath = "../s"\n',
            "non-nested",
        )

    def test_rejects_unknown_history_scope(self) -> None:
        self.assert_rejected(
            'schema_version = 1\nhistory_scope = "everything"\n'
            '[[repositories]]\nname = "s"\npath = "../s"\n',
            "history_scope",
        )

    def test_validates_alias_format_and_rejects_chains(self) -> None:
        base = 'schema_version = 1\n[[repositories]]\nname = "s"\npath = "../s"\n'
        self.assert_rejected(
            base + '[developer.aliases]\n"bob" = "Bob <bob@example.com>"\n', "Name <email>"
        )
        self.assert_rejected(
            base + "[developer.aliases]\n"
            '"A <a@example.com>" = "B <b@example.com>"\n'
            '"B <b@example.com>" = "C <c@example.com>"\n',
            "chained aliases",
        )

    def test_rejects_invalid_exclusion_regex(self) -> None:
        self.assert_rejected(
            'schema_version = 1\n[developer]\nexclude_patterns = ["("]\n'
            '[[repositories]]\nname = "s"\npath = "../s"\n',
            "Invalid developer exclusion regex",
        )

    def test_cli_template_matches_example_and_is_valid(self) -> None:
        example = (ROOT / "examples" / "audit.example.toml").read_text(encoding="utf-8")
        self.assertEqual(CONFIG_TEMPLATE, example)
        tomllib.loads(example)
        config = self.load(example)
        self.assertEqual(2, len(config.repositories))


if __name__ == "__main__":
    unittest.main()
