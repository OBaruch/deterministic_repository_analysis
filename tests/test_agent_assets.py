"""Consistency checks for the agent adapters, hook wiring, and documentation links."""

from __future__ import annotations

import filecmp
import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIRECTORIES = (".agents", ".claude", ".codex", ".github", "examples")
GUARD = "scripts/read_only_guard.py"
CLAUDE_HOOK_KEYS = {"type", "command", "args", "timeout", "async", "asyncRewake", "shell"}


def frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"{path} has no YAML frontmatter")
    return text.split("---", 2)[1]


def markdown_files() -> list[Path]:
    ignored = {".git", ".venv", "venv", "build", "dist", "node_modules"}
    return [
        path
        for path in ROOT.rglob("*.md")
        if not ignored.intersection(path.relative_to(ROOT).parts)
        and not any(part.endswith(".egg-info") for part in path.parts)
    ]


class AgentAssetTests(unittest.TestCase):
    def test_json_and_toml_assets_parse(self) -> None:
        for directory in ASSET_DIRECTORIES:
            for path in (ROOT / directory).rglob("*.json"):
                json.loads(path.read_text(encoding="utf-8"))
            for path in (ROOT / directory).rglob("*.toml"):
                tomllib.loads(path.read_text(encoding="utf-8"))
        tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_agent_and_skill_frontmatter(self) -> None:
        paths = [
            *ROOT.glob(".agents/skills/*/SKILL.md"),
            *ROOT.glob(".claude/skills/*/SKILL.md"),
            *ROOT.glob(".github/agents/*.agent.md"),
            *ROOT.glob(".claude/agents/*.md"),
            *ROOT.glob(".github/prompts/*.prompt.md"),
        ]
        self.assertGreaterEqual(len(paths), 9)
        for path in paths:
            header = frontmatter(path)
            self.assertIn("description:", header, path)
            if path.name == "SKILL.md":
                self.assertIn(f"name: {path.parent.name}", header, path)

    def test_claude_skill_mirrors_the_standard_skill(self) -> None:
        standard = ROOT / ".agents/skills/repository-audit"
        claude = ROOT / ".claude/skills/repository-audit"
        comparison = filecmp.dircmp(standard, claude)
        self.assertEqual([], comparison.left_only + comparison.right_only)
        for relative in ("SKILL.md", "references/configuration.md", "references/methodology.md"):
            self.assertEqual(
                (standard / relative).read_text(encoding="utf-8"),
                (claude / relative).read_text(encoding="utf-8"),
                relative,
            )

    def test_claude_hooks_use_documented_fields_and_reach_the_guard(self) -> None:
        settings = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
        handlers = [
            handler for group in settings["hooks"]["PreToolUse"] for handler in group["hooks"]
        ]
        for handler in handlers:
            self.assertLessEqual(set(handler), CLAUDE_HOOK_KEYS)
            self.assertTrue(any(GUARD in argument for argument in handler["args"]))
        for path in ROOT.glob(".claude/agents/*.md"):
            header = frontmatter(path)
            self.assertNotIn("env:", header, path)
            self.assertNotIn("permissionMode: plan", header, path)
            self.assertIn(GUARD, header, path)
            self.assertIn("--strict", header, path)

    def test_every_agent_adapter_runs_the_guard_in_strict_mode(self) -> None:
        for path in ROOT.glob(".github/agents/*.agent.md"):
            header = frontmatter(path)
            self.assertIn(f"{GUARD} --strict", header, path)
            self.assertNotIn("reasoning-effort", header, path)
        copilot = json.loads(
            (ROOT / ".github/hooks/read-only-audit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(1, copilot["version"])
        self.assertIn(GUARD, copilot["hooks"]["preToolUse"][0]["bash"])
        codex = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
        self.assertIn(GUARD, codex["hooks"]["PreToolUse"][0]["hooks"][0]["command"])

    def test_agent_rosters_are_consistent(self) -> None:
        names = {"repository_auditor", "audit_preflight", "audit_validator"}
        codex = {
            tomllib.loads(path.read_text(encoding="utf-8"))["name"]
            for path in ROOT.glob(".codex/agents/*.toml")
        }
        self.assertEqual(names, codex)
        claude = {path.stem.replace("-", "_") for path in ROOT.glob(".claude/agents/*.md")}
        self.assertEqual(names, claude)
        copilot = {
            path.name.removesuffix(".agent.md").replace("-", "_")
            for path in ROOT.glob(".github/agents/*.agent.md")
        }
        self.assertEqual(names, copilot)

    def test_relative_markdown_links_resolve(self) -> None:
        link = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
        broken = []
        for path in markdown_files():
            text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
            for target in link.findall(text):
                if "://" in target or target.startswith("mailto:"):
                    continue
                if not (path.parent / target).exists():
                    broken.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual([], broken)


if __name__ == "__main__":
    unittest.main()
