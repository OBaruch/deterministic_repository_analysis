@AGENTS.md

For audit requests, use the `repository-audit` skill and prefer the `repository-auditor` agent, which delegates preflight and verification to the read-only `audit-preflight` and `audit-validator` subagents.

For changes to the toolkit, follow the workflow in AGENTS.md: specification first ([specs.md](specs.md)), decisions in [plan.md](plan.md), then code, tests, and documentation together.
