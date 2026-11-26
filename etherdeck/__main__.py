import argparse
import signal
import sys

from . import VERSION
from . import bridge


def main():
    parser = argparse.ArgumentParser(prog="etherdeck")
    parser.add_argument("--version", action="version", version="Pocket RF OS " + VERSION)
    parser.add_argument("--port", help="explicit USB serial device (default: one ESP32-S3)")
    parser.add_argument("--check", action="store_true", help="check bridge identity and bundled firmware")
    args = parser.parse_args()
    try:
        if args.check:
            print(f"Bundled {bridge.PROFILE} firmware {bridge.pack()[0]}")
            with bridge.Bridge(args.port) as usb:
                print(f"{usb.port}: EtherDeck bridge {usb.version}")
            return 0
        from .app import App

        app = App(args.port)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: setattr(app, "running", False))
        app.run()
    except (OSError, bridge.BridgeError) as exc:
        print(f"Pocket RF OS: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
