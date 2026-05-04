"""
Custom exception types for LegalQA project.

Enables proper error handling, logging, and HTTP error mapping.
"""


class LegalQAException(Exception):
    """Base exception for all LegalQA errors."""

    def __init__(self, message: str, error_code: str = "UNKNOWN_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ConfigurationError(LegalQAException):
    """Raised when configuration loading or validation fails."""

    def __init__(self, message: str):
        super().__init__(message, "CONFIG_ERROR")


class DataLoadError(LegalQAException):
    """Raised when data/artifacts cannot be loaded."""

    def __init__(self, message: str):
        super().__init__(message, "DATA_LOAD_ERROR")


class ModelLoadError(LegalQAException):
    """Raised when model loading fails."""

    def __init__(self, message: str):
        super().__init__(message, "MODEL_LOAD_ERROR")


class ValidationError(LegalQAException):
    """Raised when input validation fails."""

    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR")


class RetrievalError(LegalQAException):
    """Raised when retrieval pipeline fails."""

    def __init__(self, message: str):
        super().__init__(message, "RETRIEVAL_ERROR")


class RankingError(LegalQAException):
    """Raised when reranking fails."""

    def __init__(self, message: str):
        super().__init__(message, "RANKING_ERROR")


class GenerationError(LegalQAException):
    """Raised when answer generation fails."""

    def __init__(self, message: str):
        super().__init__(message, "GENERATION_ERROR")
