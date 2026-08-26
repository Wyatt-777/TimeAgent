"""Typed configuration loading and validation for Local PC Agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


class ConfigError(ValueError):
    """Raised when the application configuration is invalid."""


@dataclass(frozen=True)
class AgentSettings:
    name: str = "LocalPCAgent"
    log_level: str = "INFO"


@dataclass(frozen=True)
class ProcessMonitorSettings:
    enabled: bool = True
    interval_seconds: float = 2.0
    important_processes: tuple[str, ...] = (
        "Code.exe",
        "python.exe",
        "codex.exe",
        "claude.exe",
    )


@dataclass(frozen=True)
class CodingAgentMonitorSettings:
    enabled: bool = True
    interval_seconds: float = 2.0
    process_names: tuple[str, ...] = ("codex.exe", "claude.exe")


@dataclass(frozen=True)
class FileMonitorSettings:
    enabled: bool = True
    recursive: bool = True
    paths: tuple[str, ...] = ("D:/trackTime/local-pc-agent",)
    ignore: tuple[str, ...] = (
        ".git",
        "node_modules",
        ".venv",
        "__pycache__",
        "target",
        "build",
        "data",
    )


@dataclass(frozen=True)
class WindowMonitorSettings:
    enabled: bool = True
    interval_seconds: float = 1.0


@dataclass(frozen=True)
class SystemMonitorSettings:
    enabled: bool = True
    interval_seconds: float = 10.0


@dataclass(frozen=True)
class StorageSettings:
    sqlite_path: str = "data/agent.db"
    log_path: str = "data/logs"


@dataclass(frozen=True)
class PrivacySettings:
    screen_capture_enabled: bool = False
    retain_screenshots_days: int = 1


@dataclass(frozen=True)
class AgentBrainSettings:
    enabled: bool = False


@dataclass(frozen=True)
class Settings:
    agent: AgentSettings = field(default_factory=AgentSettings)
    process_monitor: ProcessMonitorSettings = field(default_factory=ProcessMonitorSettings)
    coding_agent_monitor: CodingAgentMonitorSettings = field(default_factory=CodingAgentMonitorSettings)
    file_monitor: FileMonitorSettings = field(default_factory=FileMonitorSettings)
    window_monitor: WindowMonitorSettings = field(default_factory=WindowMonitorSettings)
    system_monitor: SystemMonitorSettings = field(default_factory=SystemMonitorSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    privacy: PrivacySettings = field(default_factory=PrivacySettings)
    agent_brain: AgentBrainSettings = field(default_factory=AgentBrainSettings)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "Settings":
        """Build and validate settings from a YAML-compatible mapping."""
        agent = _section(raw, "agent")
        process = _section(raw, "process_monitor")
        coding_agents = _section(raw, "coding_agent_monitor")
        files = _section(raw, "file_monitor")
        window = _section(raw, "window_monitor")
        system = _section(raw, "system_monitor")
        storage = _section(raw, "storage")
        privacy = _section(raw, "privacy")
        brain = _section(raw, "agent_brain")

        settings = cls(
            agent=AgentSettings(
                name=_string(agent, "name", AgentSettings.name),
                log_level=_string(agent, "log_level", AgentSettings.log_level).upper(),
            ),
            process_monitor=ProcessMonitorSettings(
                enabled=_bool(process, "enabled", True),
                interval_seconds=_number(process, "interval_seconds", 2.0),
                important_processes=_strings(process, "important_processes", ProcessMonitorSettings.important_processes),
            ),
            coding_agent_monitor=CodingAgentMonitorSettings(
                enabled=_bool(coding_agents, "enabled", True),
                interval_seconds=_number(coding_agents, "interval_seconds", 2.0),
                process_names=_strings(coding_agents, "process_names", CodingAgentMonitorSettings.process_names),
            ),
            file_monitor=FileMonitorSettings(
                enabled=_bool(files, "enabled", True),
                recursive=_bool(files, "recursive", True),
                paths=_strings(files, "paths", FileMonitorSettings.paths),
                ignore=_strings(files, "ignore", FileMonitorSettings.ignore),
            ),
            window_monitor=WindowMonitorSettings(
                enabled=_bool(window, "enabled", True),
                interval_seconds=_number(window, "interval_seconds", 1.0),
            ),
            system_monitor=SystemMonitorSettings(
                enabled=_bool(system, "enabled", True),
                interval_seconds=_number(system, "interval_seconds", 10.0),
            ),
            storage=StorageSettings(
                sqlite_path=_string(storage, "sqlite_path", StorageSettings.sqlite_path),
                log_path=_string(storage, "log_path", StorageSettings.log_path),
            ),
            privacy=PrivacySettings(
                screen_capture_enabled=_bool(privacy, "screen_capture_enabled", False),
                retain_screenshots_days=_integer(privacy, "retain_screenshots_days", 1),
            ),
            agent_brain=AgentBrainSettings(enabled=_bool(brain, "enabled", False)),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        """Validate cross-field constraints used by v0.1."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.agent.log_level not in valid_levels:
            raise ConfigError(f"Unsupported log level: {self.agent.log_level}")
        intervals = {
            "process_monitor.interval_seconds": self.process_monitor.interval_seconds,
            "coding_agent_monitor.interval_seconds": self.coding_agent_monitor.interval_seconds,
            "window_monitor.interval_seconds": self.window_monitor.interval_seconds,
            "system_monitor.interval_seconds": self.system_monitor.interval_seconds,
        }
        for name, value in intervals.items():
            if value <= 0:
                raise ConfigError(f"{name} must be greater than zero")
        if self.file_monitor.enabled and not self.file_monitor.paths:
            raise ConfigError("file_monitor.paths must not be empty when monitoring is enabled")
        if self.privacy.retain_screenshots_days < 0:
            raise ConfigError("privacy.retain_screenshots_days cannot be negative")


def load_settings(
    config_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Load YAML settings, applying supported environment overrides."""
    env = os.environ if environ is None else environ
    selected_path = config_path or env.get("LOCAL_PC_AGENT_CONFIG")
    path = Path(selected_path) if selected_path else Path(__file__).with_name("default.yaml")
    if not path.exists():
        raise ConfigError(f"Configuration file does not exist: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Unable to read configuration: {path}") from exc
    if not isinstance(raw, Mapping):
        raise ConfigError("Configuration root must be a mapping")

    values = dict(raw)
    if "LOCAL_PC_AGENT_LOG_LEVEL" in env:
        values.setdefault("agent", {})
        if not isinstance(values["agent"], Mapping):
            raise ConfigError("agent must be a mapping")
        values["agent"] = dict(values["agent"])
        values["agent"]["log_level"] = env["LOCAL_PC_AGENT_LOG_LEVEL"]
    return Settings.from_mapping(values)


def _section(raw: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, Mapping):
        raise ConfigError(f"{name} must be a mapping")
    return value


def _string(section: Mapping[str, Any], name: str, default: str) -> str:
    value = section.get(name, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string")
    return value


def _bool(section: Mapping[str, Any], name: str, default: bool) -> bool:
    value = section.get(name, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{name} must be a boolean")
    return value


def _number(section: Mapping[str, Any], name: str, default: float) -> float:
    value = section.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number")
    return float(value)


def _integer(section: Mapping[str, Any], name: str, default: int) -> int:
    value = section.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} must be an integer")
    return value


def _strings(section: Mapping[str, Any], name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = section.get(name, default)
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ConfigError(f"{name} must be a list of non-empty strings")
    return tuple(value)
