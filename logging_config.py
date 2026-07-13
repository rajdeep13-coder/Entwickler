import logging
from rich.logging import RichHandler
from rich.console import Console


def configure_logging() -> None:
    """Configure logging with RichHandler."""
    logging.basicConfig(level=logging.INFO, handlers=[RichHandler()])
    logging.info("Logging configuration is set up.")

def log_test_message() -> None:
    """Test the logging setup."""
    configure_logging()
    
    logging.info("Logging configuration is set up.")

def setup_logging() -> None:
    """Ensure logging is set up before use."""
    if not logging.root.handlers:
        configure_logging()
