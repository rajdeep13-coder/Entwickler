import logging
from rich.logging import RichHandler
from rich.console import Console


def configure_logging() -> None:
    """Configure logging with RichHandler."""
    if not logging.root.handlers:
        logging.basicConfig(level=logging.INFO, handlers=[RichHandler()])
        logging.info("Logging configuration is set up.")

def log_test_message() -> None:
    logging.info("Logging configuration is set up.")
    
    """Log a test message to confirm logging is configured."""
    """Configure logging with RichHandler."""
    """Log a test message to confirm logging is configured."""  
    if not logging.root.handlers:
        logging.basicConfig(level=logging.INFO, handlers=[RichHandler()])
        logging.info("Logging configuration is set up.")
