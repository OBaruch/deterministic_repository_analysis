# Specifications

| | |
| --- | --- |
| **Document role** | What the toolkit must do, as numbered and testable requirements |
| **Status** | Active, describes version 0.2.0 |
| **Derives from** | [intent.md](intent.md) |
| **Implemented by** | [plan.md](plan.md), `src/repo_audit/`, `scripts/read_only_guard.py`, agent adapters |
| **Change policy** | Update this document *before* changing observable behavior. Every requirement must stay covered by at least one automated test. |

The key words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are used as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119). Requirement identifiers are stable: never renumber or reuse them; mark retired requirements as *Withdrawn* instead.

## 1. Glossary

| Term | Definition |
| --- | --- |
| Source repository | A Git repository being audited, configured by local `path` or remote `url`. |
| Snapshot | The tree of one resolved commit SHA, materialized byte-for-byte in the workspace. |
| Tracked file | Any entry returned by `git ls-tree -r` for the snapshot commit, including symbolic links and submodule references. |
| Source file | A tracked file for which the LOC tool reports a language. |
| LOC | The LOC tool's `code` count for a file (blank and comment lines excluded). |
| History scope | The set of refs whose reachable commits are counted (`branches-and-tags` or `all-refs`). |
| Exact identity | The pair `Author Name` + `Author Email` as recorded in a commit, after explicit alias mapping. |
| Active period | A calendar day, ISO week, or month (from the author timestamp's local date) with at least one attributed commit. |
| Canonical data | The CSV and JSON files from which every report, chart, and verification is derived. |
| Workspace | External directory holding remote mirrors and snapshots. |
| Output | External directory holding canonical data, reports, charts, and raw LOC evidence. |

## 2. System context

```text
audit.toml ──► repo-audit CLI ──► Git (read-only) ──► source repositories / remote mirrors
                    │
                    ├──► LOC tool (cloc, pinned) on the workspace snapshot
                    │
                    └──► output: canonical CSV/JSON ─► Markdown, SVG, HTML, PDF
                                    ▲
AI agents ── orchestrate ───────────┘   (guarded by scripts/read_only_guard.py)
```

## 3. Functional requirements

### 3.1 Configuration

| ID | Requirement |
| --- | --- |
| FR-CFG-01 | The CLI MUST read a TOML file with `schema_version = 1` and MUST reject any other schema version. |
| FR-CFG-02 | Unknown keys at any level MUST be rejected with an error that names them. |
| FR-CFG-03 | Each repository MUST define exactly one of `path` or `url`, and a name matching `^[A-Za-z0-9][A-Za-z0-9._-]*$`, unique case-insensitively. |
| FR-CFG-04 | `expected_sha`, when set, MUST be a full 40- or 64-character hexadecimal SHA. |
| FR-CFG-05 | Repository URLs MUST NOT embed a password or token. |
| FR-CFG-06 | `output_dir` and `workspace_dir` MUST be distinct and not nested within each other. Relative paths resolve against the configuration file's directory. |
| FR-CFG-07 | `history_scope` MUST be `branches-and-tags` (default) or `all-refs`. |
| FR-CFG-08 | Developer aliases MUST use the exact `Name <email>` format on both sides and MUST NOT be chained. Exclusion patterns MUST be valid regular expressions. |
| FR-CFG-09 | `repo-audit init` MUST write a template identical to `examples/audit.example.toml` and MUST NOT overwrite an existing file. |

### 3.2 Source acquisition

| ID | Requirement |
| --- | --- |
| FR-SRC-01 | Remote repositories MUST be cloned as bare mirrors under `<workspace>/mirrors/<name>.git`; local repositories MUST be read in place and never checked out. |
| FR-SRC-02 | Git commands MUST run non-interactively (no credential prompts) and without optional locks. |
| FR-SRC-03 | A reused mirror whose `remote.origin.url` differs from the configured URL MUST be rejected. |
| FR-SRC-04 | Refs MUST resolve to exactly one commit SHA, trying the literal ref, `refs/heads/`, `refs/tags/`, and `refs/remotes/origin/` in that order. The resolved ref MUST be recorded by its full name. |
| FR-SRC-05 | A resolved SHA that differs from `expected_sha` MUST stop the run. |
| FR-SRC-06 | When `require_clean = true`, a local repository with any status entry (including untracked files) MUST stop the run. |
| FR-SRC-07 | `output_dir` and `workspace_dir` MUST be outside every local repository, and no local repository may be inside either of them. |

### 3.3 Snapshot and LOC

| ID | Requirement |
| --- | --- |
| FR-LOC-01 | The tracked file inventory MUST come from NUL-delimited `git ls-tree -r -z --full-tree` for the resolved SHA. |
| FR-LOC-02 | Regular files (modes `100644`, `100755`) MUST be materialized with their exact blob bytes via `git cat-file --batch`; no checkout, filter, text conversion, or archive attribute may alter content. |
| FR-LOC-03 | Each materialized file MUST live in its own numbered directory with a CSV-, JSON-, and filesystem-safe name that preserves LOC detection (safe names verbatim, otherwise safe suffixes only). |
| FR-LOC-04 | The LOC tool MUST be resolved once per run, and its version and SHA-256 MUST match `expected_version` and `expected_sha256` when configured. |
| FR-LOC-05 | The LOC tool MUST run with `--by-file --json --skip-uniqueness --timeout=0 --hide-rate` and an empty `--config` file so that user configuration, duplicate detection, and machine speed cannot change results. |
| FR-LOC-06 | Every reported file MUST map back to exactly one tracked path; any unknown path MUST stop the run. |
| FR-LOC-07 | Every tracked file not counted MUST appear in `excluded_files.csv` with one deterministic reason. |
| FR-LOC-08 | `repo-audit bootstrap-cloc` MUST download the pinned cloc 2.10 release, verify its published SHA-256 before installing, and reuse a verified copy without network access. |

### 3.4 History and developer metrics

| ID | Requirement |
| --- | --- |
| FR-HIS-01 | With `branches-and-tags`, history MUST be `--branches --tags --remotes <snapshot SHA>`; with `all-refs`, it MUST be `--all`. |
| FR-HIS-02 | Unique commits MUST equal `git rev-list --count` over the history scope. |
| FR-HIS-03 | Contribution MUST come from `git log --no-merges --root --numstat` with `--no-renames --diff-algorithm=myers --no-ext-diff --no-textconv --no-color --no-mailmap --no-show-signature --encoding=UTF-8`. |
| FR-HIS-04 | Binary numstat entries (`-`) MUST be counted per commit and excluded from line totals. Unexpected numstat lines MUST stop the run. |
| FR-HIS-05 | Identity MUST be the exact author name and email, replaced only by an explicit alias. Authors matching an exclusion pattern MUST be listed in `excluded_authors.csv` with the matching rule and commit count. |
| FR-HIS-06 | Active days, ISO weeks, and months MUST be derived from the author timestamp's local date. Averages MUST equal lines added divided by active periods. |
| FR-HIS-07 | Global developer figures MUST count a commit SHA shared by several repositories once, and MUST stop the run if its metadata differs between repositories. |

### 3.5 Aggregation and derived tables

| ID | Requirement |
| --- | --- |
| FR-AGG-01 | Ratios MUST use decimal arithmetic rounded half-up to 12 places in canonical data; presentation MAY round to 2 places. |
| FR-AGG-02 | Global languages, repository percentages, the top 20 files, and the global developer summary MUST be derived from canonical per-file, per-language, and per-commit rows. |
| FR-AGG-03 | All tables MUST be sorted deterministically (by value, then by name or path). |

### 3.6 Validation and verification

| ID | Requirement |
| --- | --- |
| FR-VAL-01 | Each run MUST record reconciliation checks in `validation.csv` (catalog in section 6). |
| FR-VAL-02 | Any failed check MUST fail the run after writing the canonical CSV files as evidence, and MUST NOT produce `REPORT.md`. |
| FR-VAL-03 | Each run MUST fingerprint every source repository's status and refs before and after analysis and record the comparison. |
| FR-VAL-04 | `repo-audit verify` MUST recompute every derived table from canonical data, compare it with the written outputs, check artifact presence and CSV headers, and MUST NOT modify any file. |
| FR-VAL-05 | When a run fails with an exception, source fingerprints MUST still be re-checked and any change reported alongside the original error. |

### 3.7 Reporting

| ID | Requirement |
| --- | --- |
| FR-RPT-01 | Reports and charts MUST be generated by re-reading canonical CSV files. |
| FR-RPT-02 | Data rendered in Markdown MUST be escaped so that paths, names, and refs are displayed literally. |
| FR-RPT-03 | SVG charts MUST be valid XML with escaped labels and deterministic geometry. |
| FR-RPT-04 | PDF generation MUST be optional, use a Chromium-based browser, refuse links that leave the output directory, and validate the produced file. |
| FR-RPT-05 | `REPORT.md` MUST state passed and failed check counts and the before/after source fingerprint result. |

### 3.8 Command-line interface

| ID | Requirement |
| --- | --- |
| FR-CLI-01 | Commands: `init`, `validate-config`, `audit`, `verify`, `bootstrap-cloc`, and `--version`. |
| FR-CLI-02 | Exit codes: `0` success, `1` audit or verification failure, `2` usage or configuration error. |
| FR-CLI-03 | `audit` MUST refuse a non-empty output directory unless `--force` is given **and** the directory carries the toolkit marker. |
| FR-CLI-04 | `verify --json` MUST print every check as machine-readable JSON for agents. |

## 4. Non-functional requirements

| ID | Requirement |
| --- | --- |
| NFR-01 | **Determinism.** Re-running an audit with identical inputs on the same machine MUST produce byte-identical outputs. Outputs MUST NOT contain timestamps of the run. |
| NFR-02 | **Portability.** The toolkit MUST support Python 3.11 to 3.14 on Linux, macOS, and Windows. |
| NFR-03 | **Dependencies.** The runtime MUST use only the Python standard library, Git, and the configured LOC tool. Development tools MAY be optional extras. |
| NFR-04 | **Scalability.** Blob content MUST be streamed in bounded chunks rather than loaded into memory as a whole archive. |
| NFR-05 | **Locale independence.** Subprocess text MUST be decoded as UTF-8 regardless of the platform locale. |
| NFR-06 | **Quality gates.** Code MUST pass `ruff check`, `ruff format --check`, strict `mypy`, and the full test suite in CI. |

## 5. Safety and security requirements

| ID | Requirement |
| --- | --- |
| SEC-01 | The toolkit MUST NOT run commit, push, merge, rebase, checkout, reset, branch, tag, or any other mutating Git command against a source repository. Local `fetch` occurs only when explicitly enabled. |
| SEC-02 | Generated outputs and the local `audit.toml` MUST be ignored by version control by default. |
| SEC-03 | The read-only guard MUST deny, for every supported agent host, edits and mutating shell commands that target a source repository, the workspace, or the output directory. |
| SEC-04 | In strict mode the guard MUST deny every mutating or unrecognized Git subcommand and MUST allow read-only inspection (for example `log`, `show`, `status`, `branch --list`, `config <key>`). |
| SEC-05 | The guard MUST deny by writing the reason to standard error and exiting with code `2`. It MUST fail closed on malformed hook input and, in strict mode, when an existing configuration cannot be read. Default `output_dir` and `workspace_dir` locations MUST be protected when not configured explicitly. |
| SEC-06 | `--force` MUST only delete directories that carry the toolkit's output marker. |

## 6. Validation catalog

Recorded in `validation.csv` by every run:

| Scope | Check |
| --- | --- |
| Repository | LOC tool SUM(code) = Sum(LOC by file) |
| Repository | LOC tool SUM(nFiles) = Source files |
| Repository | Sum(LOC by language) = Repository LOC |
| Repository | Sum(files by language) = Source files |
| Repository | Source files + excluded files = Tracked files |
| Repository | Parsed non-merge commits = git rev-list --no-merges --count |
| Repository | Attributed + excluded-author commits = Parsed non-merge commits |
| Repository | Sum(developer commits) = Attributed commits |
| Repository / developer | Sum(Daily, Weekly, Monthly Lines Added) = Developer Total Lines Added |
| Repository / developer | Distinct Daily, Weekly, Monthly periods = Active Days, Weeks, Months |
| Repository / developer | Daily, Weekly, Monthly average = Lines Added / active periods |
| Global | Sum(LOC by repository) = Sum(LOC by file) |
| Global | Sum(LOC by global language) = Sum(LOC by file) |
| Global | Sum(tracked files by repository) = Source files + excluded files |
| Repository | Source repository unchanged (before/after fingerprint digests) |

Additionally checked by `repo-audit verify`: output marker, presence and headers of every canonical file, recomputation of `languages.csv`, every developer table, `global_languages.csv`, `repository_percentages.csv`, `top_20_files.csv`, and `developer_global_summary.csv`, consistency of `metadata.json` and `audit-data.json` with the CSV files, chart presence, and the recorded `validation.csv` result.

## 7. Data contracts

### 7.1 Canonical files

| File | Columns |
| --- | --- |
| `repository_summary.csv` | Repository, Requested Ref, Resolved Ref, Commit SHA, Total Files, Source Files, Languages, Lines of Code, Unique Commits |
| `files.csv` | Repository, File, Language, Lines of Code |
| `languages.csv` | Repository, Language, Files, Lines of Code, Percentage Files, Percentage LOC |
| `commits.csv` | Repository, Commit SHA, Author Name, Author Email, Original Author Name, Original Author Email, Author Date, Lines Added, Lines Deleted, Net Lines, Binary Files Excluded |
| `developer_summary.csv` | Repository, Developer, Email, First Commit, Last Commit, Commits, Lines Added, Lines Deleted, Net Lines, Active Days, Average LOC per Active Day, Active Weeks, Average LOC per Active Week, Active Months, Average LOC per Active Month |
| `developer_daily.csv` / `_weekly` / `_monthly` | Repository, Developer, Email, Date / ISO Week / Month, Commits, Lines Added, Lines Deleted |
| `developer_global_summary.csv` | Developer, Email, Repositories, Commits, Lines Added, Active Days, Average LOC per Active Day, Active Weeks, Average LOC per Active Week, Active Months, Average LOC per Active Month |
| `excluded_files.csv` | Repository, File, Reason |
| `excluded_authors.csv` | Repository, Developer, Email, Rule, Commits |
| `global_languages.csv` | Language, Files, Lines of Code, Percentage Global LOC |
| `repository_percentages.csv` | Repository, Lines of Code, Percentage Total LOC, Files, Percentage Total Files, Unique Commits, Percentage Sum Repository Commits |
| `top_20_files.csv` | Rank, Repository, File, Language, Lines of Code |
| `validation.csv` | Scope, Check, Expected, Actual, Status |

CSV files are UTF-8 with a byte-order mark (for spreadsheet compatibility) and RFC 4180 line endings. `metadata.json` records the toolkit, Git, Python, and LOC tool versions, the LOC tool hash and options, the configuration hash, the history scope, and every resolved snapshot. `audit-data.json` embeds the metadata and every canonical table.

### 7.2 Excluded file reasons

`Git symbolic link`, `Git submodule reference`, `Tracked object is not a regular file`, `Empty tracked file`, `Binary, compiled, archive, font, or media extension`, `Data file extension not recognized as source`, `Not recognized as source by LOC tool`.

## 8. Agent integration requirements

| ID | Requirement |
| --- | --- |
| AGT-01 | The workflow MUST be defined once as an Agent Skill (`.agents/skills/repository-audit/`) and mirrored verbatim for Claude Code (`.claude/skills/`). |
| AGT-02 | Each host (GitHub Copilot, Claude Code, Codex) MUST provide the same three roles: an orchestrator, a read-only preflight agent, and a read-only validator agent. |
| AGT-03 | Agents MUST obtain every number from CLI-generated files and MUST NOT compute, estimate, or repair values. |
| AGT-04 | The validator role MUST use `repo-audit verify` for independent verification. |
| AGT-05 | Every agent definition that can run commands MUST attach the read-only guard in strict mode where the host supports agent-scoped hooks; project-level hooks MUST attach it in path-protection mode. |
| AGT-06 | Host configuration MUST use only fields documented by each host. |

## 9. Acceptance scenarios

1. **Reproducible audit.** *Given* a clean local repository pinned by `expected_sha`, *when* the audit runs twice with `--force`, *then* every output file is byte-identical and every validation and verification check passes.
2. **Hosting refs excluded.** *Given* a remote whose mirror contains `refs/pull/*` commits that are not on any branch, *when* the audit uses the default history scope, *then* those commits are not counted; with `all-refs` they are.
3. **Unsafe file names.** *Given* tracked files whose names contain commas, quotes, or non-ASCII characters, *when* LOC is measured, *then* each file is counted under its original path.
4. **Inconsistent LOC report.** *Given* a LOC report whose SUM disagrees with its per-file rows, *when* the audit runs, *then* it exits with code 1, writes `validation.csv` with the failing check, and does not write `REPORT.md`.
5. **Tampered output.** *Given* a completed output in which a canonical value was edited, *when* `repo-audit verify` runs, *then* it exits with code 1 and names the failing reconciliations.
6. **Agent attempts a mutation.** *Given* a strict audit session, *when* an agent tries `git push`, `git commit`, or an edit inside a source repository or the output directory, *then* the guard blocks the call with an explanatory reason.

## 10. Traceability

| Requirement group | Implementation | Tests |
| --- | --- | --- |
| FR-CFG | `src/repo_audit/config.py`, `src/repo_audit/cli.py` | `tests/test_config.py`, `tests/test_cli.py` |
| FR-SRC | `src/repo_audit/gitops.py` | `tests/test_gitops.py`, `tests/test_pipeline.py` |
| FR-LOC | `src/repo_audit/gitops.py`, `src/repo_audit/loc.py`, `src/repo_audit/bootstrap.py` | `tests/test_gitops.py`, `tests/test_loc.py`, `tests/test_bootstrap.py` |
| FR-HIS | `src/repo_audit/metrics.py`, `src/repo_audit/gitops.py` | `tests/test_metrics.py`, `tests/test_gitops.py` |
| FR-AGG | `src/repo_audit/metrics.py`, `src/repo_audit/pipeline.py` | `tests/test_metrics.py`, `tests/test_pipeline.py` |
| FR-VAL | `src/repo_audit/pipeline.py`, `src/repo_audit/verify.py` | `tests/test_pipeline.py`, `tests/test_cli.py` |
| FR-RPT | `src/repo_audit/reporting.py`, `src/repo_audit/pdf.py` | `tests/test_reporting.py`, `tests/test_pdf.py`, `tests/test_pipeline.py` |
| FR-CLI | `src/repo_audit/cli.py` | `tests/test_cli.py`, `tests/test_pipeline.py` |
| NFR | Whole package, `pyproject.toml`, `.github/workflows/ci.yml` | `tests/test_pipeline.py` (determinism), CI matrix |
| SEC | `src/repo_audit/gitops.py`, `src/repo_audit/pipeline.py`, `scripts/read_only_guard.py` | `tests/test_read_only_guard.py`, `tests/test_gitops.py`, `tests/test_pipeline.py` |
| AGT | `.agents/`, `.claude/`, `.codex/`, `.github/agents/`, `.github/hooks/` | `tests/test_agent_assets.py` |
