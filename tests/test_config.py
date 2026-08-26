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


def test_codex_notification_and_proactive_settings_are_loaded(tmp_path: Path) -> None:
    config = tmp_path / "settings.yaml"
    config.write_text(
        """
codex:
  enabled: false
  investigation:
    enabled: false
    mode: read_only
    timeout_seconds: 45
    max_invocations: 2
    window_seconds: 120
    auto_investigate: false
notifications:
  enabled: false
  minimum_priority: CRITICAL
  cooldown_seconds: 12
  dedup_window_seconds: 34
proactive_agent:
  enabled: false
  notify_on: [SYSTEM_DISK_LOW]
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.codex.enabled is False
    assert settings.codex.investigation.enabled is False
    assert settings.codex.investigation.timeout_seconds == 45
    assert settings.codex.investigation.max_invocations == 2
    assert settings.notifications.enabled is False
    assert settings.notifications.minimum_priority == 40
    assert settings.proactive_agent.enabled is False
    assert settings.proactive_agent.notify_on == ("SYSTEM_DISK_LOW",)


def test_investigation_mode_must_remain_read_only(tmp_path: Path) -> None:
    config = tmp_path / "unsafe.yaml"
    config.write_text("codex:\n  investigation:\n    mode: write\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="mode must be read_only"):
        load_settings(config)
