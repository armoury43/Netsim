"""Tests for netsim.core.config."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from netsim.core.config import (
    CONFIG_FILE_NAME,
    Settings,
    ThemeSettings,
    ensure_config_dir,
    get_config_dir,
    load_settings,
    save_settings,
)
from netsim.core.exceptions import ConfigDirectoryError, ConfigurationError


class TestGetConfigDir(unittest.TestCase):
    def test_env_override_takes_priority(self) -> None:
        with mock.patch.dict(
            os.environ, {"NETSIM_CONFIG_DIR": "/tmp/custom-netsim"}, clear=False
        ):
            self.assertEqual(get_config_dir(), Path("/tmp/custom-netsim"))

    def test_falls_back_to_xdg_config_home(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NETSIM_CONFIG_DIR", None)
            with mock.patch.dict(
                os.environ, {"XDG_CONFIG_HOME": "/tmp/xdg"}, clear=False
            ):
                self.assertEqual(get_config_dir(), Path("/tmp/xdg/netsim"))

    def test_falls_back_to_home_dot_netsim(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NETSIM_CONFIG_DIR", None)
            os.environ.pop("XDG_CONFIG_HOME", None)
            self.assertEqual(get_config_dir(), Path.home() / ".netsim")


class TestEnsureConfigDir(unittest.TestCase):
    def test_creates_directory_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "netsim"
            self.assertFalse(target.exists())

            result = ensure_config_dir(target)

            self.assertTrue(target.exists())
            self.assertEqual(result, target)

    def test_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "netsim"
            ensure_config_dir(target)

            ensure_config_dir(target)
            self.assertTrue(target.exists())

    def test_raises_config_directory_error_on_failure(self) -> None:

        with tempfile.TemporaryDirectory() as tmp:
            blocking_file = Path(tmp) / "not_a_dir"
            blocking_file.write_text("i am a file")
            target = blocking_file / "netsim"

            with self.assertRaises(ConfigDirectoryError):
                ensure_config_dir(target)


class TestSettingsValidation(unittest.TestCase):
    def test_default_settings_are_valid(self) -> None:
        Settings().validate()

    def test_invalid_log_level_rejected(self) -> None:
        settings = Settings(log_level="NOT_A_LEVEL")
        with self.assertRaises(ConfigurationError):
            settings.validate()


class TestLoadSettings(unittest.TestCase):
    def test_returns_defaults_when_no_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings(config_dir=Path(tmp))
            self.assertEqual(settings, Settings())

    def test_raises_on_malformed_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / CONFIG_FILE_NAME
            config_path.write_text("not: valid: yaml: [", encoding="utf-8")

            with self.assertRaises(ConfigurationError):
                load_settings(config_dir=Path(tmp))

    def test_raises_when_top_level_is_not_a_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / CONFIG_FILE_NAME
            config_path.write_text("- just\n- a\n- list\n", encoding="utf-8")

            with self.assertRaises(ConfigurationError):
                load_settings(config_dir=Path(tmp))

    def test_unknown_keys_are_ignored_for_forward_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / CONFIG_FILE_NAME
            config_path.write_text(
                "log_level: DEBUG\nsome_future_field: 123\n", encoding="utf-8"
            )

            settings = load_settings(config_dir=Path(tmp))
            self.assertEqual(settings.log_level, "DEBUG")


class TestSaveAndLoadRoundTrip(unittest.TestCase):
    def test_round_trip_preserves_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            original = Settings(
                log_level="WARNING",
                labs_dir=Path("my-labs"),
                history_file=Path("my-history.txt"),
                theme=ThemeSettings(
                    name="solarized",
                    background_color="#002b36",
                    text_color="#839496",
                    prompt_color="#268bd2",
                    error_color="#dc322f",
                ),
            )

            save_settings(original, config_dir=config_dir)
            loaded = load_settings(config_dir=config_dir)

            self.assertEqual(loaded, original)

    def test_save_creates_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "does" / "not" / "exist" / "yet"
            self.assertFalse(config_dir.exists())

            save_settings(Settings(), config_dir=config_dir)

            self.assertTrue((config_dir / CONFIG_FILE_NAME).exists())

    def test_save_rejects_invalid_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Settings(log_level="BOGUS")
            with self.assertRaises(ConfigurationError):
                save_settings(invalid, config_dir=Path(tmp))

if __name__ == "__main__":
    unittest.main()
