import argparse
from pathlib import Path
import signal
import subprocess
import sys

from . import VERSION
from . import hat


def run_app(app):
    while app.running:
        app.run()
        if not app.launch_target:
            break
        command, app.launch_target = app.launch_target, None
        app.running = True
        try:
            name = Path(command[-1]).name
            print(f"Pocket RF OS: opened {name}", flush=True)
            result = subprocess.run(command, check=False)
            print(f"Pocket RF OS: returned from {name} ({result.returncode})", flush=True)
            app.notice = "原厂工具退出异常" if result.returncode else ""
        except OSError:
            app.notice = "无法打开原厂工具"
        app.dirty = True


def main():
    parser = argparse.ArgumentParser(prog="etherdeck")
    parser.add_argument("--version", action="version", version="Pocket RF OS " + VERSION)
    parser.add_argument("--check", action="store_true", help="check CAP interface and installed tools")
    args = parser.parse_args()
    try:
        if args.check:
            snapshot = hat.status()
            print(f"Pocket RF OS {VERSION} — CardputerZero EXT 2.54-14P")
            print(*hat.summary(snapshot), sep="\n")
            for label, _, actions in hat.CAPS:
                for action, command in actions:
                    print(f"{label} / {action}: {'installed' if hat.available(command) else 'missing'}")
            return 0
        from .app import App

        app = App()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: setattr(app, "running", False))
        run_app(app)
    except OSError as exc:
        print(f"Pocket RF OS: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
