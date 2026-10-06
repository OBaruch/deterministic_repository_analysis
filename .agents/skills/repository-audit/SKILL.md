---
name: repository-audit
description: "Run deterministic, read-only quantitative audits of one or more Git repositories. Use for repository metrics, LOC and language reports, unique commit counts, developer contribution by active period, charts, reproducibility evidence, or PDF audit reports. Do not use for effort, cost, productivity, staffing, or delivery estimates."
license: Apache-2.0
compatibility: "Requires Python 3.11+, Git, and cloc (installable with `repo-audit bootstrap-cloc`). A Chromium-based browser is optional for PDF output. Works with GitHub Copilot, Claude Code, and Codex."
metadata:
  version: "0.2.0"
  safety: "read-only-source-repositories"
---

# Deterministic Repository Audit

The `repo-audit` CLI is the only quantitative calculation engine. Agents orchestrate, verify, and report; they never invent, estimate, or repair a number.

## Workflow

1. Read `audit.toml` and [configuration.md](./references/configuration.md). If it does not exist, create it with `repo-audit init audit.toml` and ask the user for repositories and refs.
2. Delegate preflight to `audit-preflight` when that subagent is available; otherwise run `repo-audit validate-config --config audit.toml` and the read-only checks it describes.
3. Confirm that `output_dir` and `workspace_dir` are outside every local source repository.
4. Run `repo-audit audit --config audit.toml`. Add `--pdf` only when a PDF is requested and a Chromium-based browser is available. Use `--force` only to replace a previous audit output.
5. Delegate verification to `audit-validator` when available; otherwise run `repo-audit verify --config audit.toml`.
6. Require every row in `validation.csv` and every `repo-audit verify` check to be `PASS`.
7. Return links to `REPORT.md`, the canonical CSV files, and the PDF when generated. Quote figures exactly as written in those files.

## Hard Constraints

- Never run mutating Git operations against source repositories.
- Never create, edit, or delete files inside source repositories, the audit workspace, or the audit output.
- Never estimate, interpolate, round differently, or manually repair a number.
- Never combine developer identities without an explicit `developer.aliases` mapping in `audit.toml`.
- When a fact is not deterministically available, say so and preserve the failure evidence.

For calculation definitions and traceability rules, read [methodology.md](./references/methodology.md).
