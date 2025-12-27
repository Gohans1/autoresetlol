import logging
import sys
from logging.handlers import RotatingFileHandler
from constants import AppConfig


def setup_logger(name: str = "AutoResetLoL") -> logging.Logger:
    """
    Sets up a logger with both console and rotating file handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers if function is called multiple times
    if logger.hasHandlers():
        return logger

    # Formatters
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")

    # File Handler (Rotating)
    # 1MB max size, keep 3 backup files
    file_handler = RotatingFileHandler(
        AppConfig.LOG_FILE, maxBytes=1_048_576, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # Add Handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# Global logger instance
logger = setup_logger()
