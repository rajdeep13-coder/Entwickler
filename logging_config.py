import logging
from rich.logging import RichHandler
from rich.console import Console


def configure_logging() -> None:
    """Configure logging with RichHandler."""
    logging.basicConfig(level=logging.INFO, handlers=[RichHandler()])
    logging.info("Logging configuration is set up.")

from logging_setup import setup_logging
def log_test_message() -> None:
    """Test the logging setup."""
    
