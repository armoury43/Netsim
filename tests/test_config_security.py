"""Security and robustness regression tests for application configuration."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from netsim.core.config import CONFIG_FILE_NAME, load_settings
from netsim.core.exceptions import ConfigurationError


class TestConfigurationSecurity(unittest.TestCase):
    def _load_text(self, text: str):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        config_path = Path(temporary.name) / CONFIG_FILE_NAME
        config_path.write_text(text, encoding="utf-8")
        return load_settings(Path(temporary.name))

    def test_wrong_path_types_are_reported_as_configuration_errors(self) -> None:
        for field_name, value in (("labs_dir", "[]"), ("history_file", "{}")):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ConfigurationError):
                    self._load_text(f"{field_name}: {value}\n")

    def test_unknown_theme_keys_are_ignored_but_wrong_types_are_rejected(self) -> None:
        settings = self._load_text("theme:\n  name: custom\n  future_option: ignored\n")
        self.assertEqual(settings.theme.name, "custom")

        with self.assertRaises(ConfigurationError):
            self._load_text("theme:\n  background_color: []\n")

    def test_non_mapping_theme_is_rejected_cleanly(self) -> None:
        with self.assertRaises(ConfigurationError):
            self._load_text("theme: [not, a, mapping]\n")

    def test_python_object_yaml_tags_cannot_execute_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "must-not-exist"

            text = f'!!python/object/apply:os.system ["touch {marker}"]\n'
            with self.assertRaises(ConfigurationError):
                self._load_text(text)
            self.assertFalse(marker.exists())

    def test_oversized_config_is_rejected_before_yaml_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / CONFIG_FILE_NAME
            config_path.write_bytes(b"#" + b"a" * (1024 * 1024))
            with self.assertRaisesRegex(ConfigurationError, "size limit"):
                load_settings(Path(temporary))

    def test_malformed_values_never_leak_type_error(self) -> None:
        malformed_documents = [
            "labs_dir: []\n",
            "history_file: {}\n",
            "theme:\n  unexpected: true\n  background_color: {}\n",
            "log_level: [DEBUG]\n",
        ]
        for document in malformed_documents:
            with self.subTest(document=document):
                with self.assertRaises(ConfigurationError):
                    self._load_text(document)

if __name__ == "__main__":
    unittest.main()
