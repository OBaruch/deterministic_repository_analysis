# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Requirement IDs refer to [specs.md](specs.md).

## [Unreleased]

## [0.2.0] - 2026-10-06

First public release under the Apache License 2.0. This release hardens determinism and correctness and introduces the AI-native development documents.

### Added

- `repo-audit verify` independently recomputes every derived table from canonical data, checks artifacts and headers, and supports `--json` output for agents (FR-VAL-04).
- `history_scope` configuration (`branches-and-tags` by default, or `all-refs`) (FR-HIS-01, FR-CFG-07).
- Before/after fingerprints of every source repository's status and refs, recorded as validation evidence (FR-VAL-03).
- Independent validation checks against the LOC tool's own totals and `git rev-list` counts (FR-VAL-01).
- `excluded_authors.csv` now includes the number of excluded commits per identity.
- `snapshots/<name>/manifest.json` in the workspace, mapping every materialized file to its tracked path and blob ID.
- `intent.md`, `specs.md`, and `plan.md` as the project's source of truth; issue and pull request templates, code owners, Dependabot, code of conduct, and NOTICE.
- CI quality gates: Ruff lint and format, strict mypy, tests on Linux, macOS, and Windows with Python 3.11 to 3.14, and an integration job with the official cloc release.

### Changed

- Snapshots are materialized from raw blobs with `git cat-file --batch` instead of `git archive`, so Git attributes, end-of-line conversion, and smudge filters can no longer change measured content (FR-LOC-02).
- Each materialized file is stored in its own numbered directory with a safe name, preventing parse errors and case-insensitive collisions (FR-LOC-03).
- cloc runs with JSON output, `--skip-uniqueness`, `--timeout=0`, `--hide-rate`, and an empty options file. Identical files are now each counted, and results no longer depend on machine speed or user configuration (FR-LOC-05).
- `git log` pins rename detection, diff algorithm, text conversion, external diff, mailmap, color, signatures, and encoding (FR-HIS-03).
- Unique commits and contribution metrics exclude hosting-internal refs such as `refs/pull/*`, notes, and stashes by default (FR-HIS-01).
- The resolved ref is recorded by its full name, for example `refs/heads/main` (FR-SRC-04).
- Exit codes distinguish failures (`1`) from usage and configuration errors (`2`) (FR-CLI-02).
- Markdown reports escape data, so file names such as `__init__.py` render literally (FR-RPT-02).
- `REPORT.md` states measured check results instead of fixed text (FR-RPT-05).
- Subprocess output is decoded as UTF-8 on every platform (NFR-05).
- `bootstrap-cloc` reuses a verified download without network access (FR-LOC-08).
- The read-only guard parses commands into tokens and Git subcommands, protects the workspace and output directories, supports Copilot CLI payloads, and denies with exit code 2 on every host (SEC-03 to SEC-05).
- Agent adapters use only documented host fields: strict mode is passed as a guard argument, Claude subagents no longer run in plan mode (which prevented them from running commands), and Copilot hooks use the version 1 hook file format (AGT-05, AGT-06).

### Fixed

- Files whose names contain commas or quotes were mis-parsed from cloc's CSV output.
- cloc's default duplicate detection silently excluded tracked files with identical content.
- Several validation checks compared a value with itself and could never fail.
- A local repository inside the output or workspace directory was not rejected.
- Data that looked like Markdown links could abort PDF generation.

### Security

- Repository URLs that embed credentials are rejected (FR-CFG-05).
- Mirrors whose remote URL no longer matches the configuration are rejected (FR-SRC-03).
- Chained developer aliases are rejected (FR-CFG-08).

## [0.1.0] - 2026-10-05

### Added

- Initial provider-agnostic, deterministic Git audit CLI.
- Local repository and remote bare-mirror sources.
- cloc bootstrap, version and hash verification, canonical data, validation, charts, and PDF.
- GitHub Copilot, Claude Code, and Codex skills, subagents, and hooks.

[Unreleased]: https://github.com/OBaruch/deterministic_repository_analysis/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/OBaruch/deterministic_repository_analysis/releases/tag/v0.2.0
[0.1.0]: https://github.com/OBaruch/deterministic_repository_analysis/blob/main/CHANGELOG.md#010---2026-10-05
