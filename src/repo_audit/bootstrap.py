"""Download and verify the pinned official cloc release."""

from __future__ import annotations

import hashlib
import platform
import shutil
import urllib.request
from pathlib import Path

CLOC_VERSION = "2.10"
CLOC_ASSETS = {
    "Windows": (
        "cloc-2.10.exe",
        "https://github.com/AlDanial/cloc/releases/download/v2.10/cloc-2.10.exe",
        "97786c4b5bb71d2be67e42061a2f5d03db73bbf88228f8710001d770e867bbef",
    ),
    "default": (
        "cloc-2.10.pl",
        "https://github.com/AlDanial/cloc/releases/download/v2.10/cloc-2.10.pl",
        "bf59272455172108072a0a106379f7509fd4349bdcfd85203bac038ccd286d83",
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bootstrap_cloc(directory: Path) -> tuple[Path, tuple[str, ...], str]:
    """Install the pinned cloc release into ``directory`` and return its TOML command.

    An existing file with the expected SHA-256 is reused without network access.
    """
    system = platform.system()
    filename, url, expected_hash = CLOC_ASSETS.get(system, CLOC_ASSETS["default"])
    if system != "Windows" and not shutil.which("perl"):
        raise RuntimeError("Perl is required to run the official cloc script on this platform")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    if not target.is_file() or _sha256(target) != expected_hash:
        temporary = directory / f".{filename}.download"
        try:
            with (
                urllib.request.urlopen(url, timeout=60) as response,
                temporary.open("wb") as output,
            ):
                shutil.copyfileobj(response, output)
            digest = _sha256(temporary)
            if digest != expected_hash:
                raise RuntimeError(
                    f"Downloaded cloc SHA-256 mismatch: expected {expected_hash}, got {digest}"
                )
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    if system != "Windows":
        target.chmod(target.stat().st_mode | 0o111)
        command: tuple[str, ...] = ("perl", str(target.resolve()))
    else:
        command = (str(target.resolve()),)
    return target.resolve(), command, expected_hash
