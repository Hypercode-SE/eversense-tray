import argparse
import logging

import notify2

from app import GlucoseApp

notify2.init("Eversense CGM")


def setup_logging(verbose=False):
    """Setup logging configuration based on verbosity level."""
    log_level = logging.DEBUG if verbose else logging.INFO

    # Get the root logger and update its level
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Update all existing handlers
    for handler in root_logger.handlers:
        handler.setLevel(log_level)


def main():
    parser = argparse.ArgumentParser(
        description="Eversense CGM Tray Application - A system tray application for monitoring glucose levels "
        "from Eversense CGM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s              Run the application with normal logging
  %(prog)s -v           Run the application with debug logging enabled
  %(prog)s --verbose    Run the application with debug logging enabled
  %(prog)s --help       Show this help message
        """,
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging output")

    args = parser.parse_args()

    # Setup logging based on command line arguments
    setup_logging(verbose=args.verbose)

    if args.verbose:
        print("Debug logging enabled")

    app = GlucoseApp()
    app.run()


if __name__ == "__main__":
    main()
