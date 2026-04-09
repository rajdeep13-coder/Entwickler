import logging
import pytest
from rich.console import Console
from logging_config import configure_logging

def test_logging_config(caplog):
    """Test that the logging configuration is correctly applied."""
    console = Console()
    configure_logging(console)

    # Creating a logger and logging a message to test if it works correctly
    logger = logging.getLogger("test_logger")
    logger.info("Test Log Message")

    assert "Test Log Message" in caplog.text
