"""Minimal stand-in for cloc used by the test suite.

It mimics `cloc --by-file --json --list-file=... --out=...`: one entry per
recognized file keyed by the path from the list file, a header, and a SUM
entry, or `{}` when nothing is recognized. Set FAKE_CLOC_SUM_OFFSET to make
the SUM entry disagree with the per-file rows.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

LANGUAGES = {".py": "Python", ".md": "Markdown", ".json": "JSON", ".toml": "TOML"}

if "--version" in sys.argv:
    print("test-cloc-1")
    raise SystemExit(0)

options = dict(argument.split("=", 1) for argument in sys.argv[1:] if "=" in argument)
for required in ("--config", "--list-file", "--out"):
    if required not in options:
        raise SystemExit(f"fake_cloc: missing {required}")
for flag in ("--by-file", "--json", "--skip-uniqueness", "--timeout=0", "--hide-rate"):
    if flag not in sys.argv:
        raise SystemExit(f"fake_cloc: missing {flag}")

results: dict[str, dict[str, object]] = {}
for line in Path(options["--list-file"]).read_text(encoding="utf-8").splitlines():
    path = Path(line)
    language = LANGUAGES.get(path.suffix.lower())
    if not language or path.stat().st_size == 0:
        continue
    code = sum(1 for text in path.read_text(encoding="utf-8").splitlines() if text.strip())
    results[line] = {"blank": 0, "comment": 0, "code": code, "language": language}

output = Path(options["--out"])
if not results:
    output.write_text("{}\n", encoding="utf-8")
    raise SystemExit(0)
total = sum(int(str(entry["code"])) for entry in results.values())
payload = {
    "header": {"cloc_version": "test-cloc-1", "n_files": len(results)},
    **results,
    "SUM": {
        "blank": 0,
        "comment": 0,
        "code": total + int(os.environ.get("FAKE_CLOC_SUM_OFFSET", "0")),
        "nFiles": len(results),
    },
}
output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
