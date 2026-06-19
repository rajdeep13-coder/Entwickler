import logging
import pytest
from setup_logging import setup_logging

def test_setup_logging(caplog):
    """Test if logging is set up correctly."""
    setup_logging()
    with caplog.at_level(logging.INFO):
        logging.info("This is a test log message.")
    assert "This is a test log message." in caplog.text
import logging
import pytest
from logging_config import setup_logging

def test_logging_setup() -> None:
    """Test that logging is set up correctly."""
    setup_logging()
    logger = logging.getLogger("test_logger")
    logger.info("This is a test log message.")
    assert logger.level == logging.INFO
