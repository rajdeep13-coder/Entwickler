"""
logging_config.py

This module contains the logging configuration for the application.
"""

import logging
from rich.console import Console
from rich.logging import RichHandler

def setup_logging() -> None:
    """Set up logging configuration."""
    console = Console()
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )
