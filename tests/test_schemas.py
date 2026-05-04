"""
Unit tests for API validation schemas.
"""

import pytest
from pydantic import ValidationError

from src.api.schemas import AskRequest, RetrievalDebugRequest


class TestAskRequest:
    """Tests for AskRequest schema validation."""

    def test_valid_ask_request(self):
        """Test valid ask request is accepted."""
        req = AskRequest(question="Luật hôn nhân là gì?", top_k=5)
        assert req.question == "Luật hôn nhân là gì?"
        assert req.top_k == 5

    def test_ask_request_default_top_k(self):
        """Test top_k defaults to 5."""
        req = AskRequest(question="Luật hôn nhân là gì?")
        assert req.top_k == 5

    def test_ask_request_question_too_short(self):
        """Test question must be at least 3 characters."""
        with pytest.raises(ValidationError):
            AskRequest(question="Hi")

    def test_ask_request_question_empty(self):
        """Test empty question is rejected."""
        with pytest.raises(ValidationError):
            AskRequest(question="")

    def test_ask_request_top_k_too_low(self):
        """Test top_k must be at least 1."""
        with pytest.raises(ValidationError):
            AskRequest(question="Valid question", top_k=0)

    def test_ask_request_top_k_too_high(self):
        """Test top_k must not exceed 10."""
        with pytest.raises(ValidationError):
            AskRequest(question="Valid question", top_k=11)

    def test_ask_request_top_k_boundary_values(self):
        """Test top_k boundary values."""
        # Minimum valid value
        req = AskRequest(question="Valid", top_k=1)
        assert req.top_k == 1

        # Maximum valid value
        req = AskRequest(question="Valid", top_k=10)
        assert req.top_k == 10


class TestRetrievalDebugRequest:
    """Tests for RetrievalDebugRequest schema validation."""

    def test_valid_retrieval_debug_request(self):
        """Test valid retrieval debug request is accepted."""
        req = RetrievalDebugRequest(question="Luật hôn nhân là gì?", top_k=10)
        assert req.question == "Luật hôn nhân là gì?"
        assert req.top_k == 10

    def test_retrieval_debug_request_default_top_k(self):
        """Test top_k defaults to 10."""
        req = RetrievalDebugRequest(question="Valid question")
        assert req.top_k == 10

    def test_retrieval_debug_request_question_too_short(self):
        """Test question must be at least 3 characters."""
        with pytest.raises(ValidationError):
            RetrievalDebugRequest(question="Hi")

    def test_retrieval_debug_request_top_k_too_low(self):
        """Test top_k must be at least 1."""
        with pytest.raises(ValidationError):
            RetrievalDebugRequest(question="Valid question", top_k=0)

    def test_retrieval_debug_request_top_k_too_high(self):
        """Test top_k must not exceed 20."""
        with pytest.raises(ValidationError):
            RetrievalDebugRequest(question="Valid question", top_k=21)

    def test_retrieval_debug_request_top_k_boundary_values(self):
        """Test top_k boundary values."""
        # Minimum valid value
        req = RetrievalDebugRequest(question="Valid", top_k=1)
        assert req.top_k == 1

        # Maximum valid value
        req = RetrievalDebugRequest(question="Valid", top_k=20)
        assert req.top_k == 20
