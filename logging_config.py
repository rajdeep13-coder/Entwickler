import logging
from rich.logging import RichHandler
from rich.console import Console

def setup_logging() -> None:
    """Configure logging for the application."""
    console = Console()
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler(console=console, rich_tracebacks=True)])

def log_test_message() -> None:
    """Test the logging setup."""
    
