# Configuration Reference

The CLI reads TOML schema version 1. Unknown keys are rejected.

## Top Level

| Key | Default | Meaning |
| --- | --- | --- |
| `schema_version` | required | Must be `1`. |
| `title` | `Deterministic Repository Audit` | Report title. |
| `output_dir` | `../repo-audit-output` | Canonical outputs. Must be outside every local source repository. |
| `workspace_dir` | `../repo-audit-workspace` | Remote mirrors and snapshots. Must be outside every local source repository and not nested with `output_dir`. |
| `generate_pdf` | `false` | Render HTML and PDF reports with a Chromium-based browser. |
| `require_clean` | `true` | Require local worktrees to be clean before analysis. |
| `history_scope` | `branches-and-tags` | `branches-and-tags` counts history reachable from branches, tags, remote-tracking branches, and the snapshot commit. `all-refs` uses every ref, including pull-request refs, notes, and stashes. |

## LOC Tool

`[loc]` accepts `command` as a string or argument array, plus optional `expected_version` and `expected_sha256`. The same command is applied to every repository in a run.

Run `repo-audit bootstrap-cloc` to download and verify the pinned official cloc release. Copy the printed command and SHA-256 into the config when strict tool pinning is required.

## Repositories

Each `[[repositories]]` table requires a unique `name` (letters, digits, `.`, `_`, `-`) and exactly one of:

- `url`: cloned as a bare mirror under the workspace. Never embed credentials in the URL.
- `path`: local Git repository read in place.

Optional fields are `ref` (default `HEAD`), `expected_sha` (full 40- or 64-character SHA), and `fetch` (default `true` for `url`, `false` for `path`). Record the resolved SHA from the first run and set `expected_sha` for repeatable runs.

## Developers

`developer.exclude_patterns` is an explicit list of regular expressions matched against `Name <email>`. The default is empty.

`developer.aliases` maps an exact `Name <email>` identity to a canonical `Name <email>` identity. Aliases cannot be chained. Never add aliases based on model reasoning; they must come from the user or an approved identity source.
