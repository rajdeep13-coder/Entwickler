from logging_config import configure_logging  # Centralized logging setup
import logging
def main() -> None:
    
    """Main entry point for the application."""
    configure_logging()
    logging.getLogger().info("Logging configuration is set up.")
    logging.info("Test logging message")
    

    # Your existing main code follows...
