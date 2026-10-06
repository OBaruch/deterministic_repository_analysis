# Organization Rollout

This guide helps platform, engineering-enablement, and governance teams adopt the toolkit at scale.

## Recommended distribution

1. Fork or mirror this repository into your organization's namespace, or consume a pinned release tag.
2. Protect the default branch, require CI, and require code-owner review for hooks, configuration parsing, Git commands, and metric formulas (see [CODEOWNERS](../.github/CODEOWNERS)).
3. Pin a reviewed release for teams and record it alongside every audit output.
4. Distribute the standard skill through your supported skill or plugin mechanism when repository-local installation is not desired.

## Installation models

### Clone per audit

Users clone the toolkit, create a local, git-ignored `audit.toml`, and write output to an approved location. This is the simplest and most isolated model.

### Internal Python package

Build the package (`python -m pip wheel .` or `python -m build`) and publish it to an internal index. Teams install `deterministic-repository-audit==<approved-version>` and copy only the agent assets they need into their workspace or user profile.

### Managed agent assets

- **GitHub Copilot:** distribute the skill and custom agents through repository templates or organization-level configuration; deploy the guard as a policy hook where required.
- **Claude Code:** deploy skills, subagents, and hooks through managed settings or a reviewed plugin.
- **Codex:** distribute `.agents/skills`, managed hooks, and agent definitions through managed configuration or a reviewed plugin.

## Governance checklist

- Approve Git, cloc, Python, and browser versions; pin cloc with `expected_version` and `expected_sha256`.
- Decide whether remote fetches may use interactive credentials (the toolkit never prompts).
- Choose the history scope deliberately; keep the default `branches-and-tags` unless unmerged or hosting-internal refs are in scope.
- Define approved bot exclusion patterns and identity aliases outside of any model, and keep them under review.
- Store outputs in access-controlled locations: developer names, emails, and private paths may be present.
- Define who may access developer-level tables and for which purposes, consistent with privacy and labor regulations (see [intent.md](../intent.md#responsible-use)).
- Retain the configuration, `metadata.json`, canonical CSV files, `validation.csv`, and the toolkit version together, and re-verify them with `repo-audit verify`.
- Run secret scanning before publishing toolkit changes.

## Team quick instructions

1. Install Python 3.11+, Git, and the toolkit in a virtual environment.
2. Run `repo-audit bootstrap-cloc` once and paste the printed command and hash into `[loc]`.
3. Run `repo-audit init audit.toml` and add repository URLs or paths and refs.
4. Keep `output_dir` and `workspace_dir` outside every source repository.
5. Run `repo-audit validate-config`, then `repo-audit audit`, then `repo-audit verify`.
6. Pin the resolved SHAs in `expected_sha` for repeat runs.
