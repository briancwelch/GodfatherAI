"""Compatibility entry point for existing Mac launchers; uses the shared tray app."""

from godfather_worker.desktop_app import Application, main

__all__ = ["Application", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
