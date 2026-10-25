from __future__ import annotations

from pathlib import Path

from braingraph.config import BrainGraphConfig

INTEGRATIONS: dict[str, dict[str, str | tuple[str, ...]]] = {
    "codex": {
        "label": "Codex",
        "commands": ("codex",),
        "path": ".codex/braingraph.md",
        "body": """# BrainGraph for Codex

Always use BrainGraph context before reading broad sections of the repository.

Workflow:
1. Run `braingraph query "<task>"` first.
2. Read only the returned files unless more detail is required.
3. Prefer `braingraph path "<file A>" "<file B>"` for cross-module reasoning.
4. Avoid scanning the full repo unless BrainGraph reports low confidence.

Slash shortcut:
- `/brainGraph .` refreshes the local graph
- `/brainGraph query "<task>"` retrieves compact context
""",
    },
    "claude": {
        "label": "Claude Code",
        "commands": ("claude", "claude-code"),
        "path": ".claude/commands/brainGraph.md",
        "body": """# BrainGraph for Claude Code

Use BrainGraph first.

Before opening many files:
- run `braingraph query "$ARGUMENTS"`
- inspect the returned files
- only then read individual files

For repository refresh:
- run `braingraph .`
""",
    },
    "cursor": {
        "label": "Cursor",
        "commands": ("cursor",),
        "path": ".cursor/rules/braingraph.mdc",
        "body": """---
description: BrainGraph-first repository navigation
alwaysApply: true
---

Use BrainGraph before broad file reads.

- `braingraph query "<task>"`
- `braingraph path "<from>" "<to>"`
- `braingraph explain "<system>"`

Open only the files BrainGraph marks relevant unless the task proves otherwise.
""",
    },
    "gemini": {
        "label": "Gemini CLI",
        "commands": ("gemini", "gemini-cli"),
        "path": ".gemini/commands/brainGraph.md",
        "body": """# BrainGraph for Gemini CLI

BrainGraph command policy:

1. `braingraph query "<task>"`
2. `braingraph explain "<system>"`
3. Read only the listed files

Do not scan the full repository first when BrainGraph data exists.
""",
    },
    "copilot": {
        "label": "Copilot Chat",
        "commands": ("copilot", "copilot-chat"),
        "path": ".github/instructions/braingraph.instructions.md",
        "body": """# BrainGraph for Copilot Chat

Use BrainGraph context before broad repository reads.

- Query: `braingraph query "<task>"`
- Explain: `braingraph explain "<system>"`
- Path search: `braingraph path "<from>" "<to>"`

Favor targeted file opens over full-repo traversal.
""",
    },
}


def install_integration(project_path: Path, tool: str) -> Path:
    config = BrainGraphConfig.load(project_path)
    config.ensure_dirs()
    spec = INTEGRATIONS[tool]
    body = str(spec["body"])
    repo_file = project_path / str(spec["path"])
    repo_file.parent.mkdir(parents=True, exist_ok=True)
    if not (repo_file.exists() and repo_file.read_text(encoding="utf-8") == body):
        repo_file.write_text(body, encoding="utf-8")
    mirror = config.integrations_dir / f"{tool}.md"
    mirror.write_text(body, encoding="utf-8")
    return repo_file
