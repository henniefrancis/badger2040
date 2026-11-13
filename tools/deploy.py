"""Deploy the section badge to a Badger 2040 over USB with mpremote.

  python tools/deploy.py --config <folder with badge.json> --port COM3
  python tools/deploy.py --config config --allow-placeholders --dry-run

--config   folder holding badge.json and optionally images/ and icons/ (keep it
           in a PRIVATE place; the real files are never committed to this repo)
--port     serial port of the badge (COM3, /dev/ttyACM0, ...)

The config is validated first. Files copied (nothing else is touched):
  device/launcher.py               -> /launcher.py
  device/lib/badgekit.py           -> /lib/badgekit.py
  device/henniefrancis/{personal,aws,microsoft,project,awscommza,dotcore,devconf}.py -> /henniefrancis/
                                   (awscommza.py, dotcore.py and devconf.py replace the older apps of the same name)
  icons   (config icons/ override the repo defaults)       -> /henniefrancis/
          (icon-awscommza.png, icon-dotcore.png and icon-devconf.png come only from your config icons/; skipped if absent)
  images  (config images/ override the repo defaults)      -> /images/
  <config>/badge.json              -> /henniefrancis/config/badge.json
  (generated) launcher state       -> /state/launcher.json  (boot to launcher page 1; --keep-state skips)
The older apps (hennie.py, summit.py, ...) already on the badge are left alone.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import validate_config  # noqa: E402

DEVICE = os.path.join(ROOT, "device")
APPS = ("personal", "aws", "microsoft", "project", "awscommza", "dotcore", "devconf")
PORT_RE = re.compile(r"^(COM\d{1,3}|/dev/tty[A-Za-z0-9._-]{1,30}|/dev/cu\.[A-Za-z0-9._-]{1,30})\Z")
PNG_NAME_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,60}\.png\Z")
REMOTE_DIRS = ("/lib", "/images", "/state", "/henniefrancis", "/henniefrancis/config")
# Boot to launcher page 1 instead of re-opening the last app (which hid the new launcher on first deploy).
LAUNCHER_STATE_REMOTE = "/state/launcher.json"
LAUNCHER_STATE = '{"page": 0, "running": "launcher"}\n'


def _pngs(folder):
    """Valid .png file names in folder (empty if the folder does not exist)."""
    if not os.path.isdir(folder):
        return {}
    return {n: os.path.join(folder, n) for n in sorted(os.listdir(folder))
            if PNG_NAME_RE.match(n) and os.path.isfile(os.path.join(folder, n))}


def build_plan(config_dir):
    """Return a list of (local_path, remote_path)."""
    plan = [
        (os.path.join(DEVICE, "launcher.py"), "/launcher.py"),
        (os.path.join(DEVICE, "lib", "badgekit.py"), "/lib/badgekit.py"),
    ]
    for app in APPS:
        plan.append((os.path.join(DEVICE, "henniefrancis", app + ".py"), "/henniefrancis/%s.py" % app))
    icons = {n: p for n, p in _pngs(os.path.join(DEVICE, "henniefrancis")).items() if n.startswith("icon-")}
    icons.update({n: p for n, p in _pngs(os.path.join(config_dir, "icons")).items() if n.startswith("icon-")})
    images = _pngs(os.path.join(DEVICE, "images"))
    images.update(_pngs(os.path.join(config_dir, "images")))
    plan += [(p, "/henniefrancis/" + n) for n, p in sorted(icons.items())]
    plan += [(p, "/images/" + n) for n, p in sorted(images.items())]
    plan.append((os.path.join(config_dir, "badge.json"), "/henniefrancis/config/badge.json"))
    return plan


def mpremote(port, *args):
    return [sys.executable, "-m", "mpremote", "connect", port] + list(args)


def run_plan(port, plan, reset_state=True):
    for d in REMOTE_DIRS:  # mkdir fails if the folder exists; that is fine
        subprocess.run(mpremote(port, "fs", "mkdir", ":" + d), capture_output=True, text=True, check=False)
    with tempfile.TemporaryDirectory() as tmp:
        items = list(plan)
        if reset_state:
            state_file = os.path.join(tmp, "launcher.json")
            with open(state_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(LAUNCHER_STATE)
            items.append((state_file, LAUNCHER_STATE_REMOTE))
        args = []
        for i, (local, remote) in enumerate(items):
            if i:
                args.append("+")
            args += ["fs", "cp", local, ":" + remote]
        subprocess.run(mpremote(port, *args), check=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, help="folder containing badge.json (private)")
    ap.add_argument("--port", help="serial port, e.g. COM3 (required unless --dry-run)")
    ap.add_argument("--allow-placeholders", action="store_true", help="deploy even if the config is the example")
    ap.add_argument("--allow-placeholder-images", action="store_true",
                    help="deploy repo placeholder logos/icons where you supplied none (prints a warning)")
    ap.add_argument("--keep-state", action="store_true",
                    help="do not reset /state/launcher.json (default: boot to launcher page 1)")
    ap.add_argument("--dry-run", action="store_true", help="validate and print the file list, copy nothing")
    ap.add_argument("--reset", action="store_true", help="reset the badge when finished")
    args = ap.parse_args(argv)

    config_dir = os.path.abspath(args.config)
    if not os.path.isdir(config_dir):
        print("error: --config must be a folder containing badge.json", file=sys.stderr)
        return 2
    if not args.dry_run:
        if not args.port or not PORT_RE.match(args.port):
            print("error: --port must look like COM3 or /dev/ttyACM0", file=sys.stderr)
            return 2

    errors, report = validate_config.validate(config_dir, args.allow_placeholders, args.allow_placeholder_images)
    for line in report:
        print(line)
    if errors:
        for e in errors:
            print("ERROR: " + e, file=sys.stderr)
        print("not deploying: fix the config first", file=sys.stderr)
        return 1

    plan = build_plan(config_dir)
    for local, remote in plan:
        print("%s -> %s" % (os.path.relpath(local, ROOT) if local.startswith(ROOT) else local, remote))
    if args.keep_state:
        print("launcher state kept (--keep-state)")
    else:
        print("(generated) %s -> %s" % (LAUNCHER_STATE, LAUNCHER_STATE_REMOTE))
    if args.dry_run:
        print("dry run: nothing copied")
        return 0
    try:
        run_plan(args.port, plan, reset_state=not args.keep_state)
        if args.reset:
            subprocess.run(mpremote(args.port, "reset"), check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        print("error: deploy failed: %s" % e, file=sys.stderr)
        return 1
    print("deployed %d files" % len(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
