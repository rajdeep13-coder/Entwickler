import logging
from rich.logging import RichHandler
from rich.console import Console


def log_test_message() -> None:
    configure_logging()
    
    logging.info("Logging configuration is set up.")
def configure_logging() -> None:
    """Configure logging with RichHandler."""
    if not logging.root.handlers:
        logging.basicConfig(level=logging.INFO, handlers=[RichHandler()])
        logging.info("Logging configuration is set up.")
        configure_logging()
