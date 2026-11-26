import argparse
import os
import signal
import sys

from . import VERSION
from . import bridge, hat


def main():
    parser = argparse.ArgumentParser(prog="etherdeck")
    parser.add_argument("--version", action="version", version="Pocket RF OS " + VERSION)
    parser.add_argument("--transport", choices=("hat", "usb"), default="hat",
                        help="top CAP (default) or optional ADV USB bridge")
    parser.add_argument("--port", help="select an explicit USB serial device and use USB mode")
    parser.add_argument("--check", action="store_true", help="check bridge identity and bundled firmware")
    args = parser.parse_args()
    usb = args.transport == "usb" or bool(args.port)
    try:
        if args.check and not usb:
            snapshot = hat.status()
            print(f"Pocket RF OS {VERSION} — CardputerZero EXT 2.54-14P")
            print(*hat.summary(snapshot), sep="\n")
            for label, _, actions in hat.CAPS:
                for action, command in actions:
                    print(f"{label} / {action}: {'installed' if hat.available(command) else 'missing'}")
            print("JosephCGS ADV board: wiring diagnosis only")
            return 0
        if args.check:
            print(f"Bundled {bridge.PROFILE} firmware {bridge.pack()[0]}")
            with bridge.Bridge(args.port) as usb:
                print(f"{usb.port}: EtherDeck bridge {usb.version}")
            return 0
        from .app import App

        app = App(args.port, usb=usb)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: setattr(app, "running", False))
        app.run()
        if app.launch_target:
            os.execv(app.launch_target[0], app.launch_target)
    except (OSError, bridge.BridgeError) as exc:
        print(f"Pocket RF OS: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
