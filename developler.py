from logging_config import setup_logging  # Centralized logging setup

def main() -> None:
    """Main entry point for the application.""" 
    setup_logging()  # Set up logging once for the application
    # Your existing main code follows...
