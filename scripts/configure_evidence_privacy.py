"""Compatibility entry point; implementation lives in the standalone subproject."""

from tallyv_image_preprocessing.cli import build_profile, main

__all__ = ["build_profile", "main"]

if __name__ == "__main__":
    main()
