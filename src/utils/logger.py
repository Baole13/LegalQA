"""
Structured logging utility for LegalQA project.

Provides centralized logging configuration with support for console and file output.
All modules should use get_logger() to create module-specific loggers.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


# Ensure logs directory exists
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# Standard format for all loggers
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Get or create a logger for the given module name.
    
    Args:
        name: Module name (typically __name__)
        level: Logging level (default: INFO)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (for persistent logging)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            LOGS_DIR / f"{name.replace('.', '_')}.log",
            maxBytes=10_000_000,  # 10MB
            backupCount=5,
        )
        file_handler.setLevel(logging.DEBUG)  # File gets all messages
        file_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Failed to setup file logging: {e}")
    
    return logger


def configure_root_logger(level: int = logging.INFO) -> logging.Logger:
    """
    Configure the root logger for the entire application.
    
    Args:
        level: Logging level
    
    Returns:
        Root logger instance
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    return root_logger


# Initialize root logger
configure_root_logger()
