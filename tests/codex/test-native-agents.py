#!/usr/bin/env python3
"""Check that Codex's declared roles retain their source contracts."""

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "agents"
CODEX = SOURCE / "codex"

MODELS = {
    "reviewer-low": ("gpt-5.6-sol", "high"),
    "reviewer-medium": ("gpt-5.6-sol", "xhigh"),
    "reviewer-high": ("gpt-6-astra", "high"),
    "adversarial-reviewer": ("gpt-6-astra", "high"),
    "task-reviewer": ("gpt-5.6-sol", "high"),
    "critique": ("gpt-6-astra", "high"),
    "plan-executor": ("gpt-5.6-sol", "xhigh"),
    "task-executor": ("gpt-5.6-sol", "high"),
    "qa-loop": ("gpt-5.6-sol", "high"),
}

READ_ONLY = {
    "reviewer-low", "reviewer-medium", "reviewer-high",
    "adversarial-reviewer", "task-reviewer",
}

NO_DELEGATION = (
    "\nDo not delegate this review to another agent. Return your own findings "
    "to the dispatching session.\n"
)


def source_contract(name):
    source = (SOURCE / f"{name}.md").read_text()
    _, frontmatter, body = source.split("---", 2)
    fields = {}
    for line in frontmatter.strip().splitlines():
        key, value = line.split(": ", 1)
        fields[key] = value
    return fields, body.lstrip("\n")


class NativeAgentContracts(unittest.TestCase):
    def test_complete_role_set_and_source_contracts(self):
        self.assertEqual(
            {path.stem for path in CODEX.glob("*.toml")}, set(MODELS)
        )
        for name, model_and_effort in MODELS.items():
            with self.subTest(name=name):
                data = tomllib.loads((CODEX / f"{name}.toml").read_text())
                fields, body = source_contract(name)
                self.assertEqual(
                    set(data),
                    {"name", "description", "model", "model_reasoning_effort", "developer_instructions"},
                )
                self.assertEqual(data["name"], f"doperpowers:{name}")
                self.assertEqual(data["description"], fields["description"])
                self.assertEqual(
                    (data["model"], data["model_reasoning_effort"]),
                    model_and_effort,
                )
                if name.startswith("reviewer-"):
                    body = body.replace("`CLAUDE.md`", "`AGENTS.md`")
                if name == "task-reviewer":
                    body = body.replace("do not Read a\nchanged file", "do not read a\nchanged file")
                if name in READ_ONLY:
                    body += NO_DELEGATION
                self.assertEqual(data["developer_instructions"], body)


if __name__ == "__main__":
    unittest.main()
