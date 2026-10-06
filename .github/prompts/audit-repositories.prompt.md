---
name: "Audit Repositories"
description: "Run a deterministic, read-only quantitative audit using audit.toml and independently verify every generated artifact."
agent: "Repository Auditor"
---

Run the `repository-audit` workflow for the repositories in `audit.toml`.

- Perform preflight before analysis and stop on any failure.
- Keep source repositories, the audit workspace, and the audit output free of manual edits.
- Use only CLI-generated quantitative values.
- Generate the configured CSV, JSON, Markdown, SVG, and optional PDF artifacts.
- Run `repo-audit verify` and require every check to pass before reporting completion.
