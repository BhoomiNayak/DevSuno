"""Entry point for both ``python -m voicepair`` and ``python -m devsuno``."""

from .cli import main

__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())
