# Usage

## Installation

From a clone, install in editable mode for development or as a regular package:

```console
python -m pip install -e ".[dev]"   # development, with Ruff and mypy
python -m pip install .             # regular local install
```

Run `repo-audit --help` to list commands, or `repo-audit <command> --help` for details.

## Commands

### `repo-audit init [path]`

Creates a schema-version-1 TOML template (default `audit.toml`). It never overwrites an existing file. The template is identical to [examples/audit.example.toml](../examples/audit.example.toml).

### `repo-audit bootstrap-cloc [--directory path]`

Downloads cloc 2.10 from its official GitHub release, verifies the published SHA-256 before installing, and prints the exact TOML command and hash. Windows receives the official executable; other systems receive the official Perl script and require Perl. A previously verified copy is reused without network access. The default directory, `.repo-audit-tools/`, is ignored by Git.

### `repo-audit validate-config [--config path]`

Strictly parses the configuration, rejects unknown keys, validates names, SHAs, URLs, regular expressions, aliases, paths, and the history scope, then prints the normalized result as JSON.

### `repo-audit audit [--config path] [--force] [--pdf | --no-pdf]`

Runs the audit. A non-empty output directory requires `--force`, and `--force` only replaces a directory that carries the toolkit's `.repo-audit-output.json` marker. The PDF flags override `generate_pdf` for one run.

### `repo-audit verify [--output path | --config path] [--json]`

Independently verifies a completed output: required files and CSV headers, the recorded validation result, metadata consistency, and a full recomputation of every derived table from canonical per-file and per-commit data. It never modifies files. `--json` prints every check for automated consumers and agents.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Audit or verification failure (Git, LOC tool, validation, or I/O error) |
| `2` | Usage or configuration error |

## Configuration reference

| Key | Default | Description |
| --- | --- | --- |
| `schema_version` | required | Must be `1`. |
| `title` | `Deterministic Repository Audit` | Report title. |
| `output_dir` | `../repo-audit-output` | Canonical outputs. Relative paths resolve against the configuration file. |
| `workspace_dir` | `../repo-audit-workspace` | Mirrors and snapshots. Must not be nested with `output_dir`. |
| `generate_pdf` | `false` | Also render HTML and PDF. |
| `require_clean` | `true` | Fail when a local repository has uncommitted or untracked files. |
| `history_scope` | `branches-and-tags` | History counted for commits and contribution: see [Methodology](METHODOLOGY.md#history-metrics). |
| `loc.command` | `["cloc"]` | LOC tool command as a string or argument array. |
| `loc.expected_version` | empty | Required `--version` output when set. |
| `loc.expected_sha256` | empty | Required SHA-256 of the LOC tool file when set. |
| `developer.exclude_patterns` | `[]` | Regular expressions matched against `Name <email>`. |
| `developer.aliases` | `{}` | Exact `Name <email>` to canonical `Name <email>`. Chains are rejected. |

Each `[[repositories]]` table accepts:

| Key | Default | Description |
| --- | --- | --- |
| `name` | required | Unique name: letters, digits, `.`, `_`, `-`. |
| `url` | | Remote URL, mirrored into the workspace. Credentials in the URL are rejected. |
| `path` | | Local repository, read in place. Exactly one of `url` or `path` is required. |
| `ref` | `HEAD` | Branch, tag, full ref, or commit SHA. |
| `expected_sha` | empty | Full 40- or 64-character SHA that the ref must resolve to. |
| `fetch` | `true` for `url`, `false` for `path` | Update refs before analysis. |

## Sources

Remote `url` entries use a bare mirror under `workspace_dir/mirrors/<name>.git`; a mirror that tracks a different URL is rejected. Local `path` entries are read in place and never checked out. `fetch = true` on a local repository runs `git fetch --all --tags --prune`, which updates refs but never tracked files; leave it `false` when local refs are already complete.

## Reproducible runs

1. Pin the LOC tool with `expected_version` and `expected_sha256`.
2. Fetch the desired refs.
3. Run once and review the resolved refs and SHAs in `repository_summary.csv`.
4. Copy each SHA into `expected_sha`.
5. Keep the configuration, `metadata.json`, the canonical CSV files, and the toolkit version together.

Repeated runs with the same inputs produce byte-identical outputs.

## Developer identities

Aliases use exact strings and map directly to a canonical identity:

```toml
[developer.aliases]
"Alternate Name <alternate@example.com>" = "Canonical Name <canonical@example.com>"
```

Exclusions are regular expressions matched against `Name <email>`. Keep the list empty unless your organization has an approved, deterministic rule (for example, for build bots). Excluded identities and their commit counts appear in `excluded_authors.csv`.

## PDF output

PDF rendering uses a Chromium-based browser in headless mode. The toolkit searches for `msedge`, `microsoft-edge`, `google-chrome`, `chrome`, `chromium`, and `chromium-browser` on the `PATH` (and the default Edge and Chrome locations on Windows). Set `REPO_AUDIT_BROWSER` to an executable path to choose one explicitly. When running as root, for example in a container, the browser sandbox is disabled automatically because Chromium refuses to start otherwise.

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| `LOC tool not found` | Run `repo-audit bootstrap-cloc` and copy the printed command into `[loc]`. |
| `Could not resolve Git ref` | Fetch the ref, or use a full ref name or commit SHA. |
| SHA mismatch | Do not bypass it: confirm whether the intended snapshot changed, then update `expected_sha` deliberately. |
| `is not clean` | Commit, stash, or remove local changes yourself, or set `require_clean = false`. Status must still remain unchanged during the run. |
| `Output directory is not empty` | Choose a new `output_dir`, or use `--force` to replace a previous audit output. |
| `Mirror ... tracks ...` | The workspace contains a mirror for another URL under the same name. Remove it or rename the repository entry. |
| Validation failures | Inspect `validation.csv`; the canonical CSV files are kept as evidence. Report the issue if the inputs are consistent. |
| No browser for PDF | Set `REPO_AUDIT_BROWSER` or run with `--no-pdf`. |
| Agent hook not running | Check workspace trust and hook settings in your agent host, and launch it from the activated virtual environment. See [AGENTIC-SYSTEM.md](AGENTIC-SYSTEM.md). |
