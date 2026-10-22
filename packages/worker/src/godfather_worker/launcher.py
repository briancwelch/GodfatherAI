"""Opening the normal worker starts the desktop; explicit arguments retain the CLI."""

import sys


def main() -> int:
    arguments = sys.argv[1:]
    if "--install-update" in arguments:
        from godfather_worker.linux_setup import main as install_update
        from godfather_worker.updates import update_failure

        try:
            return install_update()
        except Exception:
            return update_failure()
    if not arguments or all(arg in ("--login", "--self-test") for arg in arguments):
        from godfather_worker.desktop_app import main as desktop

        return desktop()
    from godfather_worker.cli import main as command_line

    return command_line()


if __name__ == "__main__":
    raise SystemExit(main())
