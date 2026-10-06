# Contributing

Thank you for helping improve Deterministic Repository Audit. This project values correctness, reproducibility, and safety above feature count, so every change follows the same disciplined loop.

## Development setup

```console
git clone https://github.com/OBaruch/deterministic_repository_analysis.git
cd deterministic_repository_analysis
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Quality gates

Run these before opening a pull request; CI runs the same checks on Linux, macOS, and Windows:

```console
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
mypy
```

The test suite uses a stand-in LOC tool (`tests/fixtures/fake_cloc.py`) and temporary Git repositories, so it needs no network access. CI additionally runs an end-to-end audit with the official cloc release.

## How changes are made

This project uses an AI-native development lifecycle, described in [plan.md](plan.md#1-ai-native-delivery-workflow):

1. **Intent.** Confirm the change fits [intent.md](intent.md). Changes to principles or non-goals need maintainer agreement first; open an issue.
2. **Specification.** For any change in observable behavior, update [specs.md](specs.md) first. Add or amend requirements with stable IDs (never renumber) and, where useful, an acceptance scenario.
3. **Plan.** Record new architectural decisions in the decision log of [plan.md](plan.md).
4. **Implementation.** Keep changes small. Add tests for metric formulas, Git parsing, paths, hooks, and report schemas. Update the traceability table if new modules or test files appear.
5. **Documentation.** Update the docs, the shared skill (`.agents/skills/repository-audit/`, mirrored verbatim to `.claude/skills/repository-audit/`), and every affected agent adapter in the same change.
6. **Changelog.** Add an entry under *Unreleased* in [CHANGELOG.md](CHANGELOG.md).

AI-assisted contributions are welcome and held to the same standard. The author of a pull request is responsible for every line in it, regardless of how it was produced.

## Requirements for changes

- Keep the runtime dependency-free unless a dependency removes substantial complexity and the decision is approved and recorded.
- Preserve read-only source behavior and external artifact isolation.
- Reject unknown configuration keys rather than silently ignoring typos.
- Pin any Git or LOC tool option whose default could vary between machines.
- Do not add real repository identifiers, URLs, SHAs, names, emails, credentials, or generated audit results.

## Pull requests

Use the pull request template. Explain the behavioral change, cite requirement IDs, show the evidence (tests and checks you ran), and describe any compatibility effect on GitHub Copilot, Claude Code, or Codex. Changes to hooks, Git commands, identity handling, configuration parsing, or formulas require review by a code owner.

## Reporting issues

Use the issue templates. Never include private repository data, real audit outputs, or credentials in a public issue; report security problems as described in [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the [Apache License, Version 2.0](LICENSE).
