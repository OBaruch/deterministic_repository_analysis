from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "read_only_guard.py"
SPEC = importlib.util.spec_from_file_location("read_only_guard", SCRIPT)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GUARD
SPEC.loader.exec_module(GUARD)


class ReadOnlyGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name).resolve()
        self.toolkit = self.root / "toolkit"
        self.source = self.root / "source"
        self.output = self.root / "output"
        for directory in (self.toolkit, self.source):
            directory.mkdir()
        self.config = self.toolkit / "audit.toml"
        self.config.write_text(
            f'output_dir = "{self.output.as_posix()}"\n'
            f'workspace_dir = "{(self.root / "work").as_posix()}"\n'
            f'[[repositories]]\nname = "sample"\npath = "../source"\n',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def shell(
        self, command: str, *, strict: bool = False, cwd: Path | None = None, tool: str = "Bash"
    ):
        return GUARD.evaluate(
            {
                "tool_name": tool,
                "tool_input": {"command": command},
                "cwd": str(cwd or self.toolkit),
            },
            config_path=self.config,
            strict=strict,
        )

    def edit(self, tool: str, tool_input: dict[str, object]):
        return GUARD.evaluate(
            {"tool_name": tool, "tool_input": tool_input, "cwd": str(self.toolkit)},
            config_path=self.config,
            strict=False,
        )

    def test_strict_mode_blocks_mutating_git_anywhere(self) -> None:
        for command in (
            "git push origin main",
            "git -C /elsewhere commit -m x",
            "git pull",
            "git fetch --all",
            "git branch feature",
            "git tag v1",
            "git stash",
            "git config user.name Someone",
            "git update-ref refs/heads/x HEAD",
            "git gc",
            "git some-alias",
            "cd /tmp && git checkout -b x",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(self.shell(command, strict=True))

    def test_strict_mode_allows_read_only_git(self) -> None:
        for command in (
            "git log --all --oneline -- add.py src/reset.py",
            "git show HEAD:merge.py",
            "git -C ../source status --porcelain",
            "git rev-parse --verify main^{commit}",
            "git branch --show-current",
            "git branch -a",
            "git branch --list 'release/*'",
            "git tag -l",
            "git tag --contains HEAD",
            "git stash list",
            "git config user.name",
            "git config --get remote.origin.url",
            "git remote -v",
            "git log --format='%H %an' | head -5",
            "git status 2>&1",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self.shell(command, strict=True, tool="PowerShell"))

    def test_non_strict_blocks_git_mutations_in_protected_repositories(self) -> None:
        self.assertIn("source repository", self.shell(f"git -C {self.source} commit -m x"))
        self.assertIn("source repository", self.shell("git commit -am x", cwd=self.source))
        self.assertIn("source repository", self.shell("cd ../source && git reset --hard"))
        self.assertIsNone(self.shell("git commit -m 'toolkit change'"))

    def test_blocks_mutating_shell_commands_targeting_protected_locations(self) -> None:
        for command in (
            "rm -rf ../source/build",
            f"Remove-Item -Recurse {self.source}\\build",
            "cd ../source; touch new.txt",
            "echo data > ../source/file.txt",
            f"sed -i 's/a/b/' {self.source}/app.py",
            f"cp report.md {self.output}/REPORT.md",
            f"echo tampered >> {self.output}/files.csv",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(self.shell(command))

    def test_allows_harmless_shell_commands(self) -> None:
        for command in (
            "rm -rf build",
            "echo data > notes.txt",
            "cat ../source/app.py > /dev/null",
            f"ls {self.source}",
            f"repo-audit audit --config {self.config} --force",
            "python -m unittest discover -s tests 2>&1 | tail -5",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self.shell(command))

    def test_blocks_file_edits_in_protected_locations_across_hosts(self) -> None:
        self.assertIn(
            "blocks edits", self.edit("Write", {"file_path": str(self.source / "app.py")})
        )
        self.assertIn(
            "audit output", self.edit("Edit", {"file_path": str(self.output / "files.csv")})
        )
        self.assertIsNotNone(
            self.edit("replace_string_in_file", {"filePath": str(self.source / "a.py")})
        )
        self.assertIsNotNone(self.edit("create_file", {"filePath": "../source/new.py"}))
        patch = "*** Begin Patch\n*** Update File: ../source/app.py\n@@\n-a\n+b\n*** End Patch\n"
        self.assertIsNotNone(self.edit("apply_patch", {"command": patch}))
        self.assertIsNone(self.edit("Write", {"file_path": str(self.toolkit / "notes.md")}))
        self.assertIsNone(self.edit("Read", {"file_path": str(self.source / "app.py")}))

    def test_default_output_and_workspace_are_protected(self) -> None:
        self.config.write_text(
            '[[repositories]]\nname = "s"\npath = "../source"\n', encoding="utf-8"
        )
        self.assertIn("audit output", self.shell("rm -rf ../repo-audit-output/files.csv"))
        self.assertIn("audit workspace", self.shell("touch ../repo-audit-workspace/x"))

    def test_unreadable_config_fails_closed_only_in_strict_mode(self) -> None:
        self.config.write_text("not = [valid", encoding="utf-8")
        self.assertIn("cannot identify protected paths", self.shell("ls", strict=True))
        with contextlib.redirect_stderr(io.StringIO()) as warning:
            self.assertIsNone(self.shell("ls"))
        self.assertIn("path protection is inactive", warning.getvalue())

    def test_uninspectable_shell_input_is_denied(self) -> None:
        reason = GUARD.evaluate(
            {"tool_name": "Bash", "tool_input": {}}, config_path=self.config, strict=False
        )
        self.assertIn("could not inspect", reason)

    def run_main(self, payload: object, *arguments: str) -> tuple[int, str, str]:
        stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch("sys.stdin", stdin),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = GUARD.main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_main_denies_with_exit_code_two_and_reason_on_stderr(self) -> None:
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "git push"},
            "cwd": str(self.toolkit),
        }
        code, stdout, stderr = self.run_main(payload, "--strict", "--config", str(self.config))
        self.assertEqual((2, ""), (code, stdout))
        self.assertIn("git push", stderr)

    def test_main_accepts_copilot_cli_payloads(self) -> None:
        payload = {
            "toolName": "bash",
            "toolArgs": json.dumps({"command": f"rm -rf {self.source}"}),
            "cwd": str(self.toolkit),
        }
        code, _, stderr = self.run_main(payload, "--config", str(self.config))
        self.assertEqual(2, code)
        self.assertIn("source repository", stderr)

    def test_main_allows_silently_and_fails_closed_on_bad_input(self) -> None:
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "cwd": str(self.toolkit),
        }
        self.assertEqual(
            (0, "", ""), self.run_main(payload, "--strict", "--config", str(self.config))
        )
        code, _, stderr = self.run_main("not json")
        self.assertEqual(2, code)
        self.assertIn("invalid hook JSON", stderr)


if __name__ == "__main__":
    unittest.main()
