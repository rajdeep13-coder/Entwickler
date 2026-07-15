from logging_config import configure_logging  # Centralized logging setup
def main() -> None:
    """Main entry point for the application."""
    configure_logging()
    # Your existing main code follows...
    setup_logging()
    logging.info("Test logging message")
    # Ensure logging is working as expected

    # Your existing main code follows...
