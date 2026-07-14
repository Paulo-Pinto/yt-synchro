"""Logging configuration for yt-synchro."""

import logging
import logging.handlers
from pathlib import Path

from .config import LOG_FILE, CONFIG_DIR


def setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("yt_synchro")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
