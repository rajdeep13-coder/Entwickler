import logging
from rich.console import Console
from rich.logging import RichHandler

def configure_logging(console: Console) -> None:
    """Configure the logging settings for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
