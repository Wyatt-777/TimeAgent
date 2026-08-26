import json
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parents[1] / "integrations" / "codex" / "personal-observer"


def test_personal_observer_manifest_registers_read_only_components() -> None:
    manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))

    assert manifest["name"] == "personal-observer"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["interface"]["capabilities"] == ["Read"]
    assert len(manifest["interface"]["defaultPrompt"]) == 3


def test_personal_observer_mcp_registration_points_to_observer_server() -> None:
    registration = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    server = registration["mcpServers"]["local_pc_agent_observer"]

    assert server["command"].endswith(".venv/Scripts/python.exe")
    assert server["args"][:3] == ["-m", "integrations.mcp.observer_mcp", "--database"]
    assert server["args"][-2:] == ["--workspace", "D:/trackTime/local-pc-agent"]
    assert server["cwd"] == "D:/trackTime/local-pc-agent"


def test_observer_status_skill_has_required_frontmatter_and_read_only_boundary() -> None:
    skill = (PLUGIN_ROOT / "skills" / "observer-status" / "SKILL.md").read_text(encoding="utf-8")

    assert skill.startswith("---\nname: observer-status\n")
    assert "observer_get_status" in skill
    assert "strictly read-only" in skill
    assert "Never modify files" in skill


def test_personal_observer_includes_c3_workflows_and_commands() -> None:
    investigate = (PLUGIN_ROOT / "skills" / "investigate-event" / "SKILL.md").read_text(encoding="utf-8")
    session_review = (PLUGIN_ROOT / "skills" / "coding-session-review" / "SKILL.md").read_text(encoding="utf-8")

    assert "name: investigate-event" in investigate
    assert "observer_get_pending_alerts" in investigate
    assert "name: coding-session-review" in session_review
    assert "observer_get_active_session" in session_review
    assert "Never modify files" in investigate
    assert "Never modify files" in session_review

    command_names = {
        path.name
        for path in (PLUGIN_ROOT / "commands").glob("*.md")
    }
    assert command_names == {"observer-status.md", "recent-events.md", "investigate-latest.md"}

    readme = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
    assert "clean-machine packaging" in readme
    assert "read-only" in readme


def test_personal_observer_hook_registration_is_optional_and_session_only() -> None:
    hooks = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))

    assert set(hooks["hooks"]) == {"SessionStart", "SessionEnd"}
    assert hooks["hooks"]["SessionStart"][0]["matcher"] == "startup|resume|clear|compact"
    assert hooks["hooks"]["SessionEnd"][0]["matcher"] == "other"
    for event_groups in hooks["hooks"].values():
        handler = event_groups[0]["hooks"][0]
        assert handler["type"] == "command"
        assert handler["timeout"] == 3
        assert "hook_entry.py" in handler["commandWindows"]
    assert (PLUGIN_ROOT / "hooks" / "hook_entry.py").is_file()
