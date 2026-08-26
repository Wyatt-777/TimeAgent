from pathlib import Path

import pytest

from config.settings import ConfigError, load_settings


def test_load_default_settings() -> None:
    settings = load_settings()

    assert settings.agent.name == "LocalPCAgent"
    assert settings.process_monitor.interval_seconds == 2.0
    assert settings.file_monitor.paths == ("D:/trackTime/local-pc-agent",)
    assert settings.agent_brain.enabled is False
    assert settings.coding_agent_monitor.process_names == ("codex.exe", "claude.exe")


def test_environment_can_override_log_level() -> None:
    settings = load_settings(environ={"LOCAL_PC_AGENT_LOG_LEVEL": "debug"})

    assert settings.agent.log_level == "DEBUG"


def test_invalid_interval_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "invalid.yaml"
    config.write_text("window_monitor:\n  interval_seconds: 0\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="window_monitor.interval_seconds"):
        load_settings(config)
