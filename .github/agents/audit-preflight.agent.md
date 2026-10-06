---
name: "audit-preflight"
description: "Read-only preflight for repository audits: configuration, refs, SHA pins, source/output isolation, Git availability, and LOC tool verification."
tools: [read, search, execute]
user-invocable: false
hooks:
  PreToolUse:
    - type: command
      command: "python3 scripts/read_only_guard.py --strict"
      windows: "py -3 scripts/read_only_guard.py --strict"
      timeout: 10
---

Run only read-only checks and return a PASS/FAIL matrix per repository with the exact command output as evidence:

1. `repo-audit validate-config --config audit.toml`
2. `git --version` and the configured LOC command with `--version`.
3. For local repositories: `git -C <path> rev-parse --verify <ref>^{commit}` and `git -C <path> status --porcelain`.
4. For remote repositories: `git ls-remote <url> <ref>` when network access is available.
5. Confirm that `output_dir` and `workspace_dir` are outside every local repository.

Do not run the full audit, do not fetch, and do not modify files.
