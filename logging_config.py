"""
logging_config — Module to configure logging for the application.

This module extracts the logging configuration.
"""

import logging
from rich.logging import RichHandler
from rich.console import Console

def setup_logging() -> None:
    """Setup the logging configuration for the application."""
    console = Console()
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
