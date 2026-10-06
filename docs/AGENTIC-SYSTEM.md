# Agentic System

The toolkit is designed to be operated by AI coding agents without ever letting them become the source of a number. The workflow is defined once as an open [Agent Skill](https://agentskills.io) and exposed through thin, host-specific adapters. The deterministic CLI owns every calculation.

## Roles

| Role | Responsibility | Writes |
| --- | --- | --- |
| Repository Auditor (orchestrator) | Runs preflight, the CLI, and verification; reports facts verbatim | Only through the CLI, into the external workspace and output |
| Audit Preflight | Validates configuration, refs, SHA pins, Git, the LOC tool, and path isolation | None |
| Audit Validator | Runs `repo-audit verify`, checks `validation.csv`, metadata, and source status | None |

## Shared skill

`.agents/skills/repository-audit/` is the canonical skill, discovered by GitHub Copilot and Codex. `.claude/skills/repository-audit/` is a verbatim mirror for Claude Code; a test fails if the two directories diverge.

## Host adapters

### GitHub Copilot

| Asset | Purpose |
| --- | --- |
| `.github/agents/repository-auditor.agent.md` | Orchestrator, with `audit-preflight` and `audit-validator` as subagents |
| `.github/agents/audit-preflight.agent.md`, `audit-validator.agent.md` | Read-only subagents (`user-invocable: false`) |
| `.github/prompts/audit-repositories.prompt.md` | `/Audit Repositories` entry point |
| `.github/hooks/read-only-audit.json` | Repository hook in the Copilot hook format (version 1), read by VS Code, Copilot CLI, and Copilot cloud agent |

Each custom agent also attaches an agent-scoped `PreToolUse` hook that runs the guard in strict mode (VS Code local agents).

### Claude Code

| Asset | Purpose |
| --- | --- |
| `CLAUDE.md` | Imports [AGENTS.md](../AGENTS.md) |
| `.claude/agents/` | The same three roles; the orchestrator preloads the skill |
| `.claude/settings.json` | Project hook that runs the guard in path-protection mode |
| Agent frontmatter hooks | Strict-mode guard while each audit agent runs |

Hooks use the documented exec form (`command` plus `args`) with `${CLAUDE_PROJECT_DIR}`, so paths with spaces work on every platform. Project subagent hooks run after you accept the workspace trust dialog.

### Codex

| Asset | Purpose |
| --- | --- |
| [AGENTS.md](../AGENTS.md) | Project guidance |
| `.agents/skills/` | Standard skill (`$repository-audit`) |
| `.codex/agents/*.toml` | `repository_auditor`, plus `audit_preflight` and `audit_validator` with `sandbox_mode = "read-only"` |
| `.codex/hooks.json` | Project hook that runs the guard in path-protection mode |
| `.codex/config.toml` | Enables agents with up to four concurrent threads |

Codex asks you to review and trust non-managed hooks; use `/hooks` to do so. With the default `workspace-write` sandbox, Codex can only write inside the project directory and temporary locations. Either add your `output_dir` and `workspace_dir` to `sandbox_workspace_write.writable_roots` in your Codex configuration, or approve the escalation when the audit runs. Read-only subagents also need network access approved if preflight checks remote refs.

## Read-only guard

Every adapter runs `scripts/read_only_guard.py`, a standalone script that uses only the Python standard library.

| Mode | Used by | Behavior |
| --- | --- | --- |
| Path protection (default) | Project hooks on every host | Denies edits and mutating shell commands (including redirections, `rm`, `mv`, `cp`, `sed -i`, PowerShell `*-Item` and `*-Content` cmdlets, and mutating Git subcommands) that target a configured source repository, the workspace, or the output directory |
| Strict (`--strict`) | Audit agents | Additionally denies every mutating or unrecognized Git subcommand anywhere, including `push`, `pull`, `fetch`, `commit`, `reset`, `update-ref`, and branch, tag, or config writes |

Read-only inspection stays available in strict mode: `log`, `show`, `diff`, `status`, `rev-parse`, `ls-tree`, `ls-remote`, `branch --list`, `tag -l`, `stash list`, `config <key>`, `remote -v`, and similar.

The guard reads protected paths from `audit.toml` (or `--config`, or `REPO_AUDIT_CONFIG`) and applies the same defaults as the CLI when `output_dir` or `workspace_dir` is omitted. It tokenizes shell commands, follows `cd` within a command, and resolves relative paths against the hook's working directory.

**Protocol.** Allowed calls exit `0` silently. Denied calls print the reason on standard error and exit `2`, the blocking convention shared by Claude Code, Codex, GitHub Copilot CLI, and the VS Code agent harness. Malformed hook input is denied. In strict mode, an unreadable configuration is denied too; in path-protection mode it produces a warning so that you can still fix the file.

**Prerequisites.** Hooks invoke `python` (Claude Code), `python3` (Copilot on Linux and macOS, Codex), or `py -3` (Windows). The interpreter must be Python 3.11 or newer. Launch your agent host from the toolkit's activated virtual environment so these commands resolve to the right interpreter.

**Limits.** The guard is a guardrail for cooperative agents, not a sandbox. It cannot see through interpreter one-liners or arbitrary scripts. Combine it with operating-system controls for high-assurance use (see [SECURITY.md](../SECURITY.md)).
