"""`python -m taskproof` — same entry point as the `taskproof` script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
