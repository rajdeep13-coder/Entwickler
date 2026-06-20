import logging
from logging_config import setup_logging
import pytest

def test_setup_logging() -> None:
    """Test the setup_logging function."""
    setup_logging()
    logging.info("Test logging message")
    assert logging.getLogger().level == logging.INFO
