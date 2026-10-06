# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.2.x | Yes |
| < 0.2 | No |

## Reporting a vulnerability

Please report vulnerabilities privately through [GitHub private vulnerability reporting](https://github.com/OBaruch/deterministic_repository_analysis/security/advisories/new). Do not open a public issue, and do not include credentials, private repository data, or real audit outputs in any report.

Include the affected version, the operating system and agent host if relevant, and the minimal steps to reproduce. Maintainers will acknowledge the report, keep you informed of progress, and coordinate disclosure once a fix is available.

## Sensitive data

Audit outputs can contain private repository names, URLs, local paths, commit metadata, developer names, and email addresses. The local `audit.toml`, generated outputs, mirrors, snapshots, and downloaded tools are ignored by Git by default. Store and share outputs according to the access policy of the source repositories, and restrict developer-level tables to people with a legitimate need (see [intent.md](intent.md#responsible-use)).

Never place credentials in repository URLs; the configuration loader rejects URLs with embedded passwords or tokens. Use the platform's Git credential manager or another approved non-interactive credential mechanism.

## Read-only guarantees and their limits

The toolkit:

- uses bare mirrors for remote sources and never checks out local sources;
- reads file content from Git objects into an external workspace;
- fingerprints each source's status and refs before and after every run;
- refuses to delete any output directory that lacks its marker file.

Agent hooks (`scripts/read_only_guard.py`) block mutating Git commands and edits to protected paths for cooperative agents. They are application-level guardrails, **not a security sandbox**: a determined process can bypass them, for example through an interpreter one-liner.

For high-assurance use:

- run audits under an account with read-only permissions on remotes;
- mount local source repositories read-only;
- isolate the workspace and output directories;
- review hook definitions before trusting them in your agent host;
- disable network access after remote mirrors are fetched;
- scan generated outputs before wider distribution.

## Supply chain

The runtime has no Python dependencies. `repo-audit bootstrap-cloc` downloads a pinned cloc release and verifies its SHA-256 before installing it. Pin `expected_version` and `expected_sha256` in `audit.toml` to detect any change to the LOC tool between runs.
