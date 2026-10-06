from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from repo_audit import bootstrap

PAYLOAD = b"#!/usr/bin/env perl\nprint '2.10';\n"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


class BootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self._temporary.name) / "tools"
        assets = {
            "Windows": ("cloc.exe", "https://example.invalid/cloc.exe", DIGEST),
            "default": ("cloc.pl", "https://example.invalid/cloc.pl", DIGEST),
        }
        patches = (
            mock.patch.object(bootstrap, "CLOC_ASSETS", assets),
            mock.patch.object(bootstrap.shutil, "which", return_value="/usr/bin/perl"),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_installs_verified_download_and_reuses_it_offline(self) -> None:
        with mock.patch.object(
            bootstrap.urllib.request, "urlopen", return_value=io.BytesIO(PAYLOAD)
        ) as urlopen:
            target, command, digest = bootstrap.bootstrap_cloc(self.directory)
        self.assertEqual(1, urlopen.call_count)
        self.assertEqual(PAYLOAD, target.read_bytes())
        self.assertEqual(DIGEST, digest)
        self.assertEqual(str(target), command[-1])
        with mock.patch.object(bootstrap.urllib.request, "urlopen") as urlopen:
            bootstrap.bootstrap_cloc(self.directory)
        urlopen.assert_not_called()

    def test_rejects_hash_mismatch_without_leaving_files(self) -> None:
        with (
            mock.patch.object(
                bootstrap.urllib.request, "urlopen", return_value=io.BytesIO(b"tampered")
            ),
            self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"),
        ):
            bootstrap.bootstrap_cloc(self.directory)
        self.assertEqual([], list(self.directory.iterdir()))


if __name__ == "__main__":
    unittest.main()
