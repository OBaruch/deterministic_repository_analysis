# Plan

| | |
| --- | --- |
| **Document role** | How the specifications are implemented, the decisions behind them, and what comes next |
| **Status** | Living document, current release 0.2.0 |
| **Derives from** | [intent.md](intent.md), [specs.md](specs.md) |
| **Change policy** | Update with every change that adds a decision, completes a milestone, or alters the roadmap |

## 1. AI-native delivery workflow

Every change, whether written by a person or an agent, follows the same loop:

```text
Intent ──► Spec ──► Plan ──► Implement ──► Verify ──► Release
  ▲                                           │
  └───────────── learnings and defects ◄──────┘
```

| Stage | Artifact | Who decides | Agent role |
| --- | --- | --- | --- |
| Intent | [intent.md](intent.md) | Maintainers | Propose wording; never change scope unprompted |
| Spec | [specs.md](specs.md) | Maintainers review | Draft requirement changes with IDs and acceptance scenarios *before* code |
| Plan | This document | Maintainers review | Record decisions, milestones, and risks |
| Implement | `src/`, `scripts/`, agent adapters | Author | Small, test-first changes that cite requirement IDs |
| Verify | Tests, `ruff`, `mypy`, CI, `repo-audit verify` | CI and reviewers | Run every quality gate locally before proposing a change |
| Release | [CHANGELOG.md](CHANGELOG.md), tag | Maintainers | Prepare notes; never tag or publish |

Rules that keep the loop honest:

- A pull request that changes observable behavior updates `specs.md` in the same pull request and cites the affected requirement IDs.
- A new architectural choice gets an entry in the decision log below.
- Tests are named after behavior and map to requirements through the traceability table in [specs.md](specs.md#10-traceability).
- Agents treat these documents as instructions of higher priority than their own assumptions (see [AGENTS.md](AGENTS.md)).

## 2. Architecture summary

The full architecture, module map, and trust boundaries are described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). In short:

| Layer | Modules | Responsibility |
| --- | --- | --- |
| Interface | `cli.py` | Commands, exit codes, error reporting |
| Configuration | `config.py`, `models.py` | Strict TOML parsing into immutable models |
| Acquisition | `gitops.py` | Mirrors, ref resolution, blob materialization, source fingerprints |
| Measurement | `loc.py`, `metrics.py` | LOC tool invocation and parsing, history extraction, pure aggregations |
| Orchestration | `pipeline.py` | Run order, derived tables, validation, metadata |
| Evidence | `reporting.py`, `pdf.py`, `verify.py` | Canonical CSV/JSON, reports, charts, independent verification |
| Agent safety | `scripts/read_only_guard.py`, agent adapters | Host-agnostic read-only enforcement and workflows |

## 3. Decision log

| ID | Decision | Rationale | Alternatives considered |
| --- | --- | --- | --- |
| D-001 | The CLI is the only calculation engine; agents orchestrate. | Language models can produce plausible but uncomputed numbers. Determinism and auditability require a single engine. | Agent-computed metrics (rejected). |
| D-002 | Python standard library only at runtime. | Minimal supply-chain surface and simple installation in restricted environments. | pandas, GitPython, Jinja2 (rejected for footprint). |
| D-003 | Remote sources are bare mirrors in an external workspace. | Complete ref data without a worktree; never touches user clones. | Shallow or single-branch clones (incomplete history). |
| D-004 | Snapshots are materialized from raw blobs with `git cat-file --batch` instead of `git archive`. | `git archive` applies `export-ignore`, `export-subst`, end-of-line conversion, and smudge filters such as Git LFS, which makes content depend on attributes and machine configuration. | `git archive` (used in 0.1.0), worktree checkout. |
| D-005 | Each materialized file lives in its own numbered directory with a sanitized name. | cloc echoes file names unescaped in CSV and JSON, so names with commas, quotes, or backslashes corrupt parsing. Numbered directories also avoid case-insensitive collisions, long Windows paths, and cloc's always-excluded directory names. | Mirror the repository tree (used in 0.1.0). |
| D-006 | cloc runs with `--json --skip-uniqueness --timeout=0 --hide-rate` and an empty `--config`. | Removes four sources of non-determinism: user options files, duplicate-content suppression, machine-speed timeouts, and timing data in raw evidence. JSON also exposes `SUM.nFiles` for an independent check. | CSV output with default options (used in 0.1.0). |
| D-007 | Default history scope is branches, tags, remote-tracking branches, and the snapshot commit. | Hosting mirrors expose `refs/pull/*`, notes, and stashes, which inflate counts with unmerged or private work. `all-refs` remains available explicitly. | `--all` only (used in 0.1.0). |
| D-008 | `git log` flags pin renames, diff algorithm, text conversion, external diff, mailmap, color, signatures, and encoding. | User or system Git configuration must not change line counts or identities. | Rely on defaults. |
| D-009 | Exact identities with explicit, non-chained aliases. | Identity merging is a human decision; chains hide intent. | Heuristic merging, `.mailmap` (may be offered later as opt-in). |
| D-010 | Canonical ratios use `Decimal`, rounded half-up to 12 places. | Platform-independent, stable string representation for byte-identical outputs. | Floating point. |
| D-011 | Validation checks compare independent sources (LOC tool totals, `git rev-list` counts, source fingerprints). | Checks that compare a value with itself prove nothing. | Self-referential sums (partly used in 0.1.0). |
| D-012 | `repo-audit verify` recomputes every derived table from canonical data. | Gives validator agents a deterministic tool, so verification never depends on model arithmetic. | Agent-side spot checks. |
| D-013 | The guard denies with exit code 2 and a reason on standard error. | The only blocking convention shared by Claude Code, Codex, GitHub Copilot CLI, and the VS Code agent harness; host-specific JSON shapes differ and Codex rejects unknown fields. | Host-specific JSON decisions. |
| D-014 | The guard parses shell commands into tokens and Git subcommands. | A single regular expression produced false positives (`git log -- add.py`) and missed verbs (`pull`, `fetch`, `update-ref`). | Regex matching (used in 0.1.0). |
| D-015 | Apache License 2.0. | Permissive, explicit patent grant, common for enterprise tooling. | MIT. |

## 4. Milestones

### M0, version 0.1.0: baseline (delivered)

Initial provider-agnostic CLI, canonical CSV/JSON, Markdown/SVG/PDF reports, and adapters for GitHub Copilot, Claude Code, and Codex.

### M1, version 0.2.0: correctness and AI-native hardening (delivered)

| Work item | Requirements |
| --- | --- |
| Byte-exact blob snapshots with safe, collision-free names | FR-LOC-01 to FR-LOC-03 |
| Deterministic cloc invocation, JSON parsing, and SUM reconciliation | FR-LOC-04 to FR-LOC-07, FR-VAL-01 |
| History scope that excludes hosting-internal refs by default | FR-HIS-01, FR-HIS-02, FR-CFG-07 |
| Pinned `git log` options and strict numstat parsing | FR-HIS-03, FR-HIS-04 |
| Non-tautological validation, source fingerprints, failure evidence | FR-VAL-01 to FR-VAL-05 |
| `repo-audit verify` independent recomputation | FR-VAL-04, AGT-04 |
| Markdown escaping and safe PDF rendering | FR-RPT-02, FR-RPT-04 |
| Exit codes, idempotent cloc bootstrap, stricter configuration | FR-CLI-02, FR-LOC-08, FR-CFG-04 to FR-CFG-08 |
| Token-based read-only guard with portable deny protocol | SEC-03 to SEC-05 |
| Agent adapters aligned with documented host formats | AGT-01 to AGT-06 |
| Intent, specs, and plan; lint, strict typing, CI matrix, integration job | NFR-02, NFR-06 |

### M2, version 0.3.0: proposed

Candidates, to be specified in `specs.md` before implementation:

| Candidate | Motivation |
| --- | --- |
| JSON Schemas for `audit.toml` and canonical outputs | Editor validation and contract tests for downstream consumers |
| Optional `.mailmap` support (off by default) | Use identity data already curated in repositories, explicitly opted in |
| Time-window filters (`since` / `until`) for history metrics | Period-bounded reporting without rewriting refs |
| Per-directory LOC breakdown | Component-level sizing for monorepos |
| Release provenance (signed tags, build attestations) and PyPI publishing | Supply-chain transparency for organizational adoption |
| Windows integration job with the official `cloc.exe` | End-to-end coverage of the Windows bootstrap path |

## 5. Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| cloc language definitions change between versions | Different LOC for identical code | Version and SHA-256 pinning; versions recorded in metadata |
| Git behavior differs across versions | Different counts or parsing failures | Explicit flags, strict parsing, recorded Git version, CI on three operating systems |
| Agent host hook formats evolve | Guard silently not running | Asset tests pin documented fields; guard fails closed on bad input; documentation lists host prerequisites |
| `python` resolves to an interpreter older than 3.11 | Guard cannot read the configuration | Strict mode denies with an actionable message; launch agents from the toolkit virtual environment |
| Developer-level data misused for performance evaluation | Harm to individuals, regulatory exposure | Responsible-use statement in [intent.md](intent.md), access-control guidance in [SECURITY.md](SECURITY.md) |
| Very large repositories | Long runs, disk usage in the workspace | Streaming blob materialization; workspace outside sources; documented sizing |

## 6. Definition of done

A change is done when:

1. `specs.md` describes the new behavior and the traceability table is current.
2. `python -m unittest discover -s tests -v` passes.
3. `ruff check .`, `ruff format --check .`, and `mypy` pass.
4. Documentation, the skill, and every affected agent adapter are updated together.
5. [CHANGELOG.md](CHANGELOG.md) has an entry under *Unreleased*.
6. CI is green on Linux, macOS, and Windows.

## 7. Release process

1. Move *Unreleased* entries in [CHANGELOG.md](CHANGELOG.md) under the new version and date.
2. Update `version` in `pyproject.toml`, `__version__` in `src/repo_audit/__init__.py`, and `metadata.version` in both skill files.
3. Confirm CI is green on the release commit.
4. Create an annotated tag `vX.Y.Z` and a GitHub release whose notes are the changelog section.
