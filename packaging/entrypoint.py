"""PyInstaller entry point for the installed ``peaks.app`` console script."""

from peaks.app import main

if __name__ == "__main__":
    result = main()
    raise SystemExit(0 if result is None else result)
