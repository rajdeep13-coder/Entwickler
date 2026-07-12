from logging_config import configure_logging  # Centralized logging setup
def main() -> None:
    """Main entry point for the application."""
    # Your existing main code follows...
def test_logging_config() -> None:
    setup_logging()
    configure_logging()
    logging.info("Test logging message")
    # Ensure logging is working as expected

    # Your existing main code follows...
