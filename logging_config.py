import logging
from rich.logging import RichHandler
from rich.console import Console

def configure_logging() -> None:
    """Configure logging for the application."""
    console = Console()
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console)],
    )


def log_test_message() -> None:
    """Log a test message to confirm logging is configured."""  
    if not logging.root.handlers:
        logging.info("Logging configuration is set up.")
        return  # Early return if logging is not configured
