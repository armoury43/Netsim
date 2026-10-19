"""Tests for netsim.core.logging_config."""

from __future__ import annotations

import io
import logging
import tempfile
import unittest
from pathlib import Path

from netsim.core.logging_config import (
    LOGGER_NAME,
    configure_logging,
    get_logger,
    reset_logging_state_for_tests,
)


class TestConfigureLogging(unittest.TestCase):
    def setUp(self) -> None:
        reset_logging_state_for_tests()

        self._close_all_handlers()

    def tearDown(self) -> None:
        reset_logging_state_for_tests()
        self._close_all_handlers()

    @staticmethod
    def _close_all_handlers() -> None:
        logger = logging.getLogger(LOGGER_NAME)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def test_returns_logger_named_netsim(self) -> None:
        logger = configure_logging(force=True)
        self.assertEqual(logger.name, LOGGER_NAME)

    def test_sets_requested_level(self) -> None:
        logger = configure_logging(level=logging.DEBUG, force=True)
        self.assertEqual(logger.level, logging.DEBUG)

    def test_does_not_propagate_to_root(self) -> None:

        logger = configure_logging(force=True)
        self.assertFalse(logger.propagate)

    def test_second_call_is_a_no_op_without_force(self) -> None:
        stream_a = io.StringIO()
        stream_b = io.StringIO()

        logger_a = configure_logging(stream=stream_a, force=True)
        handlers_after_first = list(logger_a.handlers)

        logger_b = configure_logging(stream=stream_b)
        handlers_after_second = list(logger_b.handlers)

        self.assertEqual(handlers_after_first, handlers_after_second)

    def test_force_reconfigures_handlers(self) -> None:
        configure_logging(force=True)
        first_handler_count = len(logging.getLogger(LOGGER_NAME).handlers)

        configure_logging(force=True)
        second_handler_count = len(logging.getLogger(LOGGER_NAME).handlers)

        self.assertEqual(first_handler_count, second_handler_count)

    def test_writes_to_provided_stream(self) -> None:
        stream = io.StringIO()
        configure_logging(level=logging.INFO, stream=stream, force=True)

        logger = get_logger("netsim.test_writes_to_provided_stream")
        logger.info("hello from test")

        self.assertIn("hello from test", stream.getvalue())

    def test_optionally_writes_to_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "nested" / "netsim.log"
            configure_logging(
                level=logging.INFO,
                stream=io.StringIO(),
                log_file=log_file,
                force=True,
            )
            logger = get_logger("netsim.test_optionally_writes_to_log_file")
            logger.info("file line")

            self.assertTrue(log_file.exists())
            self.assertIn("file line", log_file.read_text(encoding="utf-8"))


class TestGetLogger(unittest.TestCase):
    def test_returns_logger_nested_under_netsim(self) -> None:
        logger = get_logger("netsim.core.something")
        self.assertEqual(logger.name, "netsim.core.something")

if __name__ == "__main__":
    unittest.main()
