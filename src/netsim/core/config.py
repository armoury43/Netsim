"""Application-level settings and configuration-file handling.

Application settings include the configuration directory, log level, saved
lab location, command history path, and terminal/GUI appearance. They are
separate from the running/startup configuration stored by simulated devices.
Settings are human-editable YAML stored in a per-user configuration directory.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from netsim.core.exceptions import ConfigDirectoryError, ConfigurationError

CONFIG_FILE_NAME = "config.yaml"
_MAX_CONFIG_FILE_BYTES = 1 * 1024 * 1024

VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


@dataclass
class ThemeSettings:
    """Terminal appearance settings (CLI/GUI share this).

    All colors are stored as names/hex strings rather than being tied to
    a specific rendering library, so both the CLI (e.g. ANSI mapping)
    and the graphical front-end can interpret them.
    """

    name: str = "default"
    background_color: str = "black"
    text_color: str = "white"
    prompt_color: str = "green"
    error_color: str = "red"


@dataclass
class Settings:
    """Top-level application settings.

    Attributes:
        log_level: One of :data:`VALID_LOG_LEVELS`.
        labs_dir: Directory where saved lab topologies live.
        history_file: Path to the persisted CLI command history.
        theme: Terminal appearance settings.
    """

    log_level: str = "INFO"
    labs_dir: Path = field(default_factory=lambda: Path("labs"))
    history_file: Path = field(default_factory=lambda: Path("history.txt"))
    theme: ThemeSettings = field(default_factory=ThemeSettings)

    def validate(self) -> None:
        """Validate settings, raising :class:`ConfigurationError` if invalid."""
        if not isinstance(self.log_level, str) or self.log_level not in VALID_LOG_LEVELS:
            raise ConfigurationError(
                f"Invalid log_level {self.log_level!r}; "
                f"must be one of {VALID_LOG_LEVELS}"
            )
        for field_name in ("labs_dir", "history_file"):
            value = getattr(self, field_name)
            if not isinstance(value, (str, Path)):
                raise ConfigurationError(f"Invalid {field_name}: expected a path string")
        if not isinstance(self.theme, ThemeSettings):
            raise ConfigurationError("Invalid theme: expected a mapping of theme settings")
        for field_name in ("name", "background_color", "text_color", "prompt_color", "error_color"):
            value = getattr(self.theme, field_name)
            if not isinstance(value, str):
                raise ConfigurationError(f"Invalid theme.{field_name}: expected a string")
            if len(value) > 128:
                raise ConfigurationError(f"Invalid theme.{field_name}: value exceeds 128 characters")


def get_config_dir() -> Path:
    """Resolve the netsim configuration directory for the current user.

    Does not create the directory; see :func:`ensure_config_dir`.

    Returns:
        The resolved configuration directory path.
    """
    env_override = os.environ.get("NETSIM_CONFIG_DIR")
    if env_override:
        return Path(env_override).expanduser()

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home).expanduser() / "netsim"

    return Path.home() / ".netsim"


def ensure_config_dir(config_dir: Path | None = None) -> Path:
    """Resolve and create the netsim configuration directory.

    Args:
        config_dir: Override the resolved directory (mainly for tests).

    Returns:
        The (now-existing) configuration directory path.

    Raises:
        ConfigDirectoryError: If the directory cannot be created, e.g.
            due to a permissions error.
    """
    target = config_dir if config_dir is not None else get_config_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigDirectoryError(
            f"Could not create config directory {target}: {exc}"
        ) from exc
    return target


def _settings_to_yaml_dict(settings: Settings) -> dict[str, Any]:
    """Convert a Settings dataclass into a YAML-friendly plain dict."""
    raw = asdict(settings)
    raw["labs_dir"] = str(settings.labs_dir)
    raw["history_file"] = str(settings.history_file)
    return raw


def _yaml_dict_to_settings(data: dict[str, Any]) -> Settings:
    """Convert a plain dict (as loaded from YAML) into a Settings dataclass.

    Unknown keys are ignored (forward-compatible with older config files);
    missing keys fall back to dataclass defaults.
    """
    known_fields = {f.name for f in fields(Settings)}
    filtered = {k: v for k, v in data.items() if k in known_fields}

    theme_data = filtered.pop("theme", None)
    if theme_data is None:
        theme = ThemeSettings()
    elif isinstance(theme_data, dict):
        known_theme_fields = {f.name for f in fields(ThemeSettings)}

        theme_values = {k: v for k, v in theme_data.items() if k in known_theme_fields}
        for key, value in theme_values.items():
            if not isinstance(value, str):
                raise ConfigurationError(f"Invalid theme.{key}: expected a string")
        theme = ThemeSettings(**theme_values)
    else:
        raise ConfigurationError("Config field 'theme' must be a YAML mapping")

    for field_name in ("labs_dir", "history_file"):
        if field_name in filtered:
            value = filtered[field_name]
            if not isinstance(value, str):
                raise ConfigurationError(f"Config field {field_name!r} must be a path string")
            try:
                filtered[field_name] = Path(value)
            except (TypeError, ValueError, OSError) as exc:
                raise ConfigurationError(f"Invalid path in config field {field_name!r}") from exc

    try:
        return Settings(theme=theme, **filtered)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid application configuration: {exc}") from exc


def load_settings(config_dir: Path | None = None) -> Settings:
    """Load settings from disk, or return defaults if no config file exists.

    Args:
        config_dir: Override the resolved config directory (mainly for tests).

    Returns:
        A validated :class:`Settings` instance.

    Raises:
        ConfigurationError: If the config file exists but is malformed,
            or contains invalid values.
    """
    target_dir = config_dir if config_dir is not None else get_config_dir()
    config_path = target_dir / CONFIG_FILE_NAME

    if not config_path.exists():
        return Settings()

    try:
        with config_path.open("rb") as stream:
            raw_bytes = stream.read(_MAX_CONFIG_FILE_BYTES + 1)
        if len(raw_bytes) > _MAX_CONFIG_FILE_BYTES:
            raise ConfigurationError(
                f"Config file {config_path} exceeds the {_MAX_CONFIG_FILE_BYTES}-byte size limit"
            )
        raw_text = raw_bytes.decode("utf-8")
        data = yaml.safe_load(raw_text) or {}
    except ConfigurationError:
        raise
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Could not read config file {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError(
            f"Config file {config_path} must contain a YAML mapping at the top level"
        )

    settings = _yaml_dict_to_settings(data)
    settings.validate()
    return settings


def save_settings(settings: Settings, config_dir: Path | None = None) -> Path:
    """Persist settings to disk as YAML.

    Args:
        settings: The settings to save. Validated before writing.
        config_dir: Override the resolved config directory (mainly for tests).

    Returns:
        The path the settings were written to.

    Raises:
        ConfigurationError: If ``settings`` fails validation.
        ConfigDirectoryError: If the config directory cannot be created.
    """
    settings.validate()
    target_dir = ensure_config_dir(config_dir)
    config_path = target_dir / CONFIG_FILE_NAME

    yaml_dict = _settings_to_yaml_dict(settings)
    config_path.write_text(
        yaml.safe_dump(yaml_dict, sort_keys=False),
        encoding="utf-8",
    )
    return config_path
