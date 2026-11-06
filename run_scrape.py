"""Convenience runner for Windows users who do not install the CLI command."""
from scraper.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
