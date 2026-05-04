"""
Unit tests for logging infrastructure.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from src.utils.logger import configure_root_logger, get_logger


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_creates_logger(self):
        """Test get_logger creates a logger."""
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_get_logger_returns_same_instance(self):
        """Test get_logger returns same instance for same name."""
        logger1 = get_logger("test.module1")
        logger2 = get_logger("test.module1")
        assert logger1 is logger2

    def test_get_logger_has_handlers(self):
        """Test get_logger configures handlers."""
        logger = get_logger("test.module2")
        # Should have at least console handler (file handler may fail in test env)
        assert len(logger.handlers) >= 1

    def test_get_logger_accepts_custom_level(self):
        """Test get_logger accepts custom logging level."""
        logger = get_logger("test.module3", level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_get_logger_default_level(self):
        """Test get_logger defaults to INFO level."""
        logger = get_logger("test.module4")
        assert logger.level == logging.INFO

    def test_logger_can_log_messages(self):
        """Test logger can actually log messages."""
        logger = get_logger("test.module5")
        try:
            logger.info("Test info message")
            logger.debug("Test debug message")
            logger.warning("Test warning message")
            logger.error("Test error message")
        except Exception as e:
            pytest.fail(f"Logger failed to log message: {e}")


class TestConfigureRootLogger:
    """Tests for configure_root_logger function."""

    def test_configure_root_logger_returns_logger(self):
        """Test configure_root_logger returns root logger."""
        logger = configure_root_logger()
        assert isinstance(logger, logging.Logger)
        assert logger.name == "root"

    def test_configure_root_logger_accepts_custom_level(self):
        """Test configure_root_logger accepts custom level."""
        logger = configure_root_logger(level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_configure_root_logger_has_handlers(self):
        """Test configure_root_logger configures handlers."""
        logger = configure_root_logger()
        assert len(logger.handlers) >= 1

    def test_configure_root_logger_default_level(self):
        """Test configure_root_logger defaults to INFO level."""
        logger = configure_root_logger()
        assert logger.level == logging.INFO


class TestLoggerNameFormatting:
    """Tests for logger name formatting and hierarchy."""

    def test_logger_hierarchy(self):
        """Test logger hierarchy is maintained."""
        parent_logger = get_logger("app")
        child_logger = get_logger("app.module")

        # They should be different loggers
        assert parent_logger.name == "app"
        assert child_logger.name == "app.module"

    def test_module_logger_names(self):
        """Test typical module logger names."""
        loggers = [
            get_logger("src.api.app"),
            get_logger("src.qa.pipeline"),
            get_logger("src.retrieval.hybrid_retriever"),
        ]

        for logger in loggers:
            assert isinstance(logger, logging.Logger)
            assert logger.name.startswith("src.")
