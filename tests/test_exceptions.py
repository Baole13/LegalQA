"""
Unit tests for custom exception types.
"""

import pytest

from src.utils.exceptions import (
    ConfigurationError,
    DataLoadError,
    GenerationError,
    LegalQAException,
    ModelLoadError,
    RankingError,
    RetrievalError,
    ValidationError,
)


class TestLegalQAException:
    """Tests for base LegalQAException."""

    def test_base_exception_creation(self):
        """Test creating base exception."""
        exc = LegalQAException("Test message", "TEST_ERROR")
        assert exc.message == "Test message"
        assert exc.error_code == "TEST_ERROR"
        assert str(exc) == "Test message"

    def test_base_exception_default_code(self):
        """Test base exception has default error code."""
        exc = LegalQAException("Test message")
        assert exc.error_code == "UNKNOWN_ERROR"


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_configuration_error_creation(self):
        """Test creating configuration error."""
        exc = ConfigurationError("Config file missing")
        assert exc.message == "Config file missing"
        assert exc.error_code == "CONFIG_ERROR"


class TestDataLoadError:
    """Tests for DataLoadError."""

    def test_data_load_error_creation(self):
        """Test creating data load error."""
        exc = DataLoadError("Data file corrupted")
        assert exc.message == "Data file corrupted"
        assert exc.error_code == "DATA_LOAD_ERROR"


class TestModelLoadError:
    """Tests for ModelLoadError."""

    def test_model_load_error_creation(self):
        """Test creating model load error."""
        exc = ModelLoadError("Model weights missing")
        assert exc.message == "Model weights missing"
        assert exc.error_code == "MODEL_LOAD_ERROR"


class TestValidationError:
    """Tests for ValidationError."""

    def test_validation_error_creation(self):
        """Test creating validation error."""
        exc = ValidationError("Question too short")
        assert exc.message == "Question too short"
        assert exc.error_code == "VALIDATION_ERROR"


class TestRetrievalError:
    """Tests for RetrievalError."""

    def test_retrieval_error_creation(self):
        """Test creating retrieval error."""
        exc = RetrievalError("Search failed")
        assert exc.message == "Search failed"
        assert exc.error_code == "RETRIEVAL_ERROR"


class TestRankingError:
    """Tests for RankingError."""

    def test_ranking_error_creation(self):
        """Test creating ranking error."""
        exc = RankingError("Reranking failed")
        assert exc.message == "Reranking failed"
        assert exc.error_code == "RANKING_ERROR"


class TestGenerationError:
    """Tests for GenerationError."""

    def test_generation_error_creation(self):
        """Test creating generation error."""
        exc = GenerationError("Answer generation failed")
        assert exc.message == "Answer generation failed"
        assert exc.error_code == "GENERATION_ERROR"


class TestExceptionHierarchy:
    """Tests for exception hierarchy."""

    def test_all_exceptions_inherit_from_base(self):
        """Test all custom exceptions inherit from LegalQAException."""
        exceptions = [
            ConfigurationError("test"),
            DataLoadError("test"),
            ModelLoadError("test"),
            ValidationError("test"),
            RetrievalError("test"),
            RankingError("test"),
            GenerationError("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, LegalQAException)
            assert isinstance(exc, Exception)
