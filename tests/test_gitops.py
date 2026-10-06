from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from repo_audit.config import load_config
from repo_audit.gitops import (
    GitError,
    history_revisions,
    materialized_name,
    prepare_repository,
    validate_output_isolation,
    verify_unchanged,
)
from repo_audit.models import RepositorySpec

from helpers import command, commit_files, create_repository


class GitOperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_materializes_exact_blob_bytes_ignoring_attributes(self) -> None:
        source, sha = create_repository(
            self.root,
            {
                ".gitattributes": (
                    "*.txt text eol=crlf\nignored.py export-ignore\nsubst.py export-subst\n"
                ),
                "notes.txt": "line one\nline two\n",
                "ignored.py": "print('kept')\n",
                "subst.py": "VERSION = '$Format:%H$'\n",
                "bin/data.bin": b"\x00\x01\r\n\x02",
            },
        )
        prepared = prepare_repository(
            RepositorySpec(name="sample", path=source, ref="main", expected_sha=sha, fetch=False),
            self.root / "workspace",
            require_clean=True,
        )
        self.assertEqual(sha, prepared.commit_sha)
        for path in prepared.tracked_files:
            self.assertEqual(
                (source / path).read_bytes(), prepared.snapshot_files[path].read_bytes(), path
            )
        self.assertEqual(
            "VERSION = '$Format:%H$'\n", prepared.snapshot_files["subst.py"].read_text()
        )
        self.assertTrue((prepared.snapshot_path / "manifest.json").is_file())
        verify_unchanged(prepared)

    @unittest.skipIf(os.name == "nt", "creating symbolic links requires privileges on Windows")
    def test_symlinks_are_tracked_but_not_materialized(self) -> None:
        source, sha = create_repository(self.root, {"app.py": "x = 1\n"})
        (source / "link.py").symlink_to("app.py")
        sha = commit_files(source, {}, "add link")
        prepared = prepare_repository(
            RepositorySpec(name="sample", path=source, expected_sha=sha, fetch=False),
            self.root / "workspace",
            require_clean=True,
        )
        self.assertEqual(("app.py", "link.py"), prepared.tracked_files)
        self.assertEqual("120000", prepared.file_modes["link.py"])
        self.assertNotIn("link.py", prepared.snapshot_files)

    def test_safe_materialized_names(self) -> None:
        self.assertEqual("module.py", materialized_name("src/module.py"))
        self.assertEqual("Makefile", materialized_name("Makefile"))
        self.assertEqual(".eslintrc.js", materialized_name(".eslintrc.js"))
        self.assertEqual("file.py", materialized_name('src/we,ird "name".py'))
        self.assertEqual("file.py", materialized_name("src/über.py"))
        self.assertEqual("file.c", materialized_name("aux.c"))
        self.assertEqual("file", materialized_name("trailing."))
        self.assertEqual("file.d.ts", materialized_name("types copy.d.ts"))

    def test_rejects_expected_sha_mismatch(self) -> None:
        source, _ = create_repository(self.root, {"app.py": "x = 1\n"})
        with self.assertRaisesRegex(GitError, "expected"):
            prepare_repository(
                RepositorySpec(name="sample", path=source, expected_sha="0" * 40, fetch=False),
                self.root / "workspace",
                require_clean=True,
            )

    def test_rejects_dirty_repository_when_clean_is_required(self) -> None:
        source, _ = create_repository(self.root, {"app.py": "x = 1\n"})
        (source / "untracked.py").write_text("y = 2\n", encoding="utf-8")
        with self.assertRaisesRegex(GitError, "not clean"):
            prepare_repository(
                RepositorySpec(name="sample", path=source, fetch=False),
                self.root / "workspace",
                require_clean=True,
            )

    def test_detects_reference_changes_during_audit(self) -> None:
        source, _ = create_repository(self.root, {"app.py": "x = 1\n"})
        prepared = prepare_repository(
            RepositorySpec(name="sample", path=source, fetch=False),
            self.root / "workspace",
            require_clean=True,
        )
        command("git", "branch", "feature", cwd=source)
        with self.assertRaisesRegex(GitError, "changed during the audit"):
            verify_unchanged(prepared)

    def test_mirror_history_excludes_hosting_refs_by_default(self) -> None:
        upstream, _ = create_repository(self.root, {"app.py": "x = 1\n"}, name="upstream")
        main_sha = command("git", "rev-parse", "HEAD", cwd=upstream)
        command("git", "checkout", "--quiet", "-b", "unmerged", cwd=upstream)
        pull_sha = commit_files(upstream, {"pr.py": "y = 2\n"}, "unmerged pull request")
        command("git", "update-ref", "refs/pull/1/head", pull_sha, cwd=upstream)
        command("git", "checkout", "--quiet", "main", cwd=upstream)
        command("git", "branch", "--quiet", "-D", "unmerged", cwd=upstream)
        spec = RepositorySpec(name="remote", url=upstream.as_uri(), ref="main")

        default = prepare_repository(spec, self.root / "workspace", require_clean=True)
        self.assertEqual(main_sha, default.commit_sha)
        self.assertEqual(("--branches", "--tags", "--remotes", main_sha), default.history_revisions)
        count = command(
            "git", "rev-list", "--count", *default.history_revisions, cwd=default.git_path
        )
        self.assertEqual("1", count)

        everything = prepare_repository(
            spec, self.root / "workspace", require_clean=True, history_scope="all-refs"
        )
        count = command(
            "git", "rev-list", "--count", *everything.history_revisions, cwd=everything.git_path
        )
        self.assertEqual("2", count)
        self.assertEqual(("--all",), history_revisions("all-refs", main_sha))

    def test_rejects_mirror_that_tracks_another_url(self) -> None:
        first, _ = create_repository(self.root, {"a.py": "a = 1\n"}, name="first")
        second, _ = create_repository(self.root, {"b.py": "b = 1\n"}, name="second")
        workspace = self.root / "workspace"
        prepare_repository(RepositorySpec(name="svc", url=first.as_uri()), workspace, True)
        with self.assertRaisesRegex(GitError, "tracks"):
            prepare_repository(RepositorySpec(name="svc", url=second.as_uri()), workspace, True)

    def test_output_isolation_in_both_directions(self) -> None:
        source, _ = create_repository(self.root, {"app.py": "x = 1\n"})
        inside = self.root / "audit-inside.toml"
        inside.write_text(
            f'schema_version = 1\noutput_dir = "{(source / "out").as_posix()}"\n'
            f'workspace_dir = "{(self.root / "work").as_posix()}"\n'
            f'[[repositories]]\nname = "s"\npath = "{source.as_posix()}"\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(GitError, "must be outside"):
            validate_output_isolation(load_config(inside))
        around = self.root / "audit-around.toml"
        around.write_text(
            f'schema_version = 1\noutput_dir = "{self.root.as_posix()}"\n'
            f'workspace_dir = "{(self.root.parent / "elsewhere-work").as_posix()}"\n'
            f'[[repositories]]\nname = "s"\npath = "{source.as_posix()}"\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(GitError, "must not be inside"):
            validate_output_isolation(load_config(around))


if __name__ == "__main__":
    unittest.main()
