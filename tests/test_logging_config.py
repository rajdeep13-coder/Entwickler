import logging
import pytest
from logging_config import setup_logging

def test_logging_setup() -> None:
    """Test that logging is set up correctly."""
    setup_logging()
    logger = logging.getLogger("test_logger")
    logger.info("This is a test log message.")
    assert logger.level == logging.INFO
