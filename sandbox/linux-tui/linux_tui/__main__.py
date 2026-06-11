"""Entry point: `python -m linux_tui`."""
from linux_tui.app import LinuxTUIApp


def main() -> None:
    app = LinuxTUIApp()
    app.run()


if __name__ == "__main__":
    main()
