## Summary

<!-- What changes and why. Link the issue if there is one. -->

## Requirements

<!-- Requirement IDs from specs.md that this change adds, modifies, or implements (for example FR-LOC-05, SEC-03). Write "none" for documentation-only or internal changes. -->

## Evidence

- [ ] `python -m unittest discover -s tests -v`
- [ ] `ruff check .` and `ruff format --check .`
- [ ] `mypy`
- [ ] New or changed behavior is covered by tests

## AI-native lifecycle

- [ ] `specs.md` updated before or with any change in observable behavior
- [ ] New architectural decisions recorded in `plan.md`
- [ ] `intent.md` unchanged, or the change was agreed with maintainers
- [ ] Documentation, the shared skill, and affected agent adapters (Copilot, Claude Code, Codex) updated together
- [ ] `CHANGELOG.md` entry under *Unreleased*

## Safety

- [ ] No real repository URLs, identities, credentials, or audit outputs are included
- [ ] Read-only guarantees are preserved (no new mutating Git commands, no writes outside workspace and output)
