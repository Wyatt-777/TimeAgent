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
