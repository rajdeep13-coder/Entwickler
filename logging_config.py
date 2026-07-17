import logging
from rich.logging import RichHandler
from rich.console import Console


def log_test_message() -> None:
    logging.info("Logging configuration is set up.")
    """Log a test message to confirm logging is configured."""
    """Log a test message to confirm logging is configured."""
    """Log a test message to confirm logging is configured."""  
    if not logging.root.handlers:
        logging.info("Logging configuration is set up.")
    """Configure logging with RichHandler."""
