import logging
from rich.logging import RichHandler
from rich.console import Console


def log_test_message() -> None:
    """Log a test message to confirm logging is configured."""  
    if not logging.root.handlers:
        logging.info("Logging configuration is set up.")
        return  # Early return if logging is not configured
