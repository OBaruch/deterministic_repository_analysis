# Intent

| | |
| --- | --- |
| **Document role** | Why this project exists and what it must never become |
| **Status** | Active |
| **Applies to** | Version 0.2.x and later |
| **Owner** | Maintainers (see [CODEOWNERS](.github/CODEOWNERS)) |
| **Change policy** | Maintainer approval required. Agents may propose changes but must not apply them unprompted. |

This repository follows an AI-native software development lifecycle. Three documents form its source of truth, read in order:

1. **[intent.md](intent.md)** (this file): the problem, the users, the principles, and the boundaries. It changes rarely.
2. **[specs.md](specs.md)**: the observable behavior the toolkit must have, as numbered, testable requirements.
3. **[plan.md](plan.md)**: how the requirements are implemented, the decisions taken, and what comes next.

Code, tests, and agent instructions must trace back to these documents. When they disagree, the documents win and the discrepancy is a defect.

## Problem

Organizations regularly need hard numbers about their code: how large a set of repositories is, which languages it uses, how much history it has, and who contributed to it and when. These numbers feed technical due diligence, portfolio reviews, migration planning, licensing and compliance work, and engineering reporting.

In practice such figures are produced with ad hoc scripts, spreadsheets, or, increasingly, by asking an AI assistant. The results are hard to reproduce, silently depend on local tool configuration, mix facts with estimates, and can modify the very repositories being measured. Language models in particular can produce numbers that look precise but were never computed.

## Mission

Provide a **deterministic, read-only, evidence-producing** toolkit that turns any set of Git repositories into reproducible quantitative facts, and that AI agents can operate safely without ever becoming the source of a number.

## Users

| User | Need |
| --- | --- |
| Engineering leaders and auditors | Trustworthy size, language, and history figures for reviews and due diligence |
| Platform and developer-experience teams | A repeatable, scriptable audit that runs in CI or on a workstation |
| Compliance and governance functions | Traceable evidence: pinned inputs, recorded tool versions, and validation results |
| AI coding agents (GitHub Copilot, Claude Code, Codex) | A safe workflow to orchestrate audits and report results without computing them |

## Principles

Ranked: when two principles conflict, the higher one wins.

1. **Deterministic over plausible.** The same inputs (repositories at pinned commits, configuration, tool versions) produce byte-identical canonical outputs. If a value cannot be determined exactly, the run fails rather than estimates.
2. **Read-only by construction.** Analyzed repositories are never modified. The toolkit writes only to an external workspace and an output directory, and proves that sources are unchanged.
3. **Evidence over assertion.** Every reported figure is traceable to canonical data, every aggregate is reconciled programmatically, and the outputs can be re-verified independently.
4. **Explicit over inferred.** Identities, aliases, exclusions, and history scope are configuration, never heuristics. Nothing is merged, excluded, or guessed silently.
5. **Agents orchestrate, the engine computes.** AI agents run the CLI, interpret failures, and relay facts verbatim. They never calculate, interpolate, or repair data.
6. **Portable and dependency-light.** Any Git host, any of the supported agent hosts, Linux, macOS, and Windows. The runtime uses only the Python standard library, Git, and a pinned LOC tool.
7. **Privacy-aware.** Outputs can contain names, emails, and private paths. The toolkit never publishes them and keeps them out of version control by default.

## Non-goals

The toolkit deliberately does **not**:

- estimate effort, cost, duration, staffing, productivity, or delivery dates;
- judge code quality, security posture, or architecture;
- rank, score, or evaluate individual people;
- infer that two identities are the same person;
- act as a security sandbox (its guardrails complement, not replace, operating-system controls);
- operate as a hosted service or send repository data anywhere.

## Responsible use

Lines of code and commit counts describe artifacts, not people. They vary with language, generated code, refactoring style, squash policies, and pairing practices. Developer-level tables exist to support factual questions (for example, who touched a codebase during a period), **not** to measure individual performance or productivity. Organizations deploying this toolkit should define who may access developer-level outputs and for what purpose, in line with applicable privacy and labor regulations.

## Success criteria

| Criterion | Target |
| --- | --- |
| Reproducibility | Two runs with identical inputs produce identical canonical CSV, JSON, Markdown, and SVG files |
| Integrity | 100% of validation checks and independent verification checks pass before a run is reported as successful |
| Safety | Zero modifications to analyzed repositories, demonstrated by before/after fingerprints in every run |
| Traceability | Every requirement in [specs.md](specs.md) maps to code and to at least one automated test |
| Portability | CI passes on Linux, macOS, and Windows for every supported Python version |
| Agent safety | Audit agents on every supported host run with the read-only guard in strict mode |

## Human decisions

Some choices are reserved for people and must never be made by an agent on its own initiative:

- which repositories, refs, and commit SHAs are in scope;
- identity aliases and author exclusion rules;
- the history scope (`branches-and-tags` or `all-refs`);
- who may access, retain, or publish audit outputs;
- changes to this document.
