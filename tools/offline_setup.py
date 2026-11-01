"""Install bundled GUI wheels; copied to the offline kit root before use."""

import argparse
import hashlib
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import venv


def target_platform():
    machine = platform.machine().lower()
    if sys.platform == "darwin" and machine in ("arm64", "aarch64", "x86_64", "amd64"):
        version = tuple(int(value) for value in platform.mac_ver()[0].split(".")[:2])
        if version < (12, 0):
            raise RuntimeError("The bundled Qt wheels require macOS 12 or newer.")
        return "macos"
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "windows"
    if sys.platform.startswith("linux") and machine in ("amd64", "x86_64"):
        name, version = platform.libc_ver()
        parts = tuple(int(value) for value in version.split(".")[:2]) if version else ()
        if name != "glibc" or parts < (2, 28):
            raise RuntimeError("The Linux wheels require x86_64 with glibc 2.28 or newer; musl is not supported.")
        return "linux"
    raise RuntimeError("No wheel set is supplied for this operating system or CPU architecture.")


def verify_wheels(root, target):
    entries = (root / "WHEELS_SHA256.txt").read_text(encoding="utf-8").splitlines()
    checked = 0
    for line in entries:
        expected, relative = line.split("  ", 1)
        if not relative.startswith("wheelhouse/" + target + "/"):
            continue
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("A supplied dependency is missing or damaged: " + relative)
        checked += 1
    if checked != 2:
        raise RuntimeError("Expected PySide6 Essentials and shiboken6 for this platform.")


def repair_mac_plugin_flags(python, environment):
    if sys.platform != "darwin":
        return
    code = "from pathlib import Path; import PySide6; print(Path(PySide6.__file__).parent / 'Qt' / 'plugins')"
    folder = Path(subprocess.check_output([str(python), "-c", code], text=True).strip()).resolve()
    if not folder.is_relative_to(environment.resolve()):
        raise RuntimeError("The selected Qt plugins are outside this kit's environment.")
    for path in folder.rglob("*"):
        flags = path.stat().st_flags
        if flags & stat.UF_HIDDEN:
            os.chflags(path, flags & ~stat.UF_HIDDEN)


def main():
    parser = argparse.ArgumentParser(description="Set up Anchor from local wheels only.")
    parser.add_argument("--launch", action="store_true", help="Open Anchor after successful setup.")
    parser.add_argument("--preview", action="store_true", help="Use disposable sample projects when launching.")
    args = parser.parse_args()
    if sys.implementation.name != "cpython" or not (3, 10) <= sys.version_info[:2] < (3, 14):
        raise RuntimeError("Use 64-bit CPython 3.10, 3.11, 3.12 or 3.13. Python 3.14 is not supported by these Qt wheels.")
    root = Path(__file__).resolve().parent
    target = target_platform()
    verify_wheels(root, target)
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        print("Creating a local Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    version = subprocess.check_output([str(python), "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], text=True).strip()
    if tuple(int(part) for part in version.split(".")) != sys.version_info[:2]:
        raise RuntimeError("This folder already has an environment from a different Python version. Extract a fresh kit before setup.")
    command = [str(python), "-m", "pip", "install", "--no-index", "--no-cache-dir",
               "--disable-pip-version-check", "--find-links", str(root / "wheelhouse" / target),
               "-r", str(root / "requirements.txt")]
    subprocess.run(command, check=True)
    repair_mac_plugin_flags(python, environment)
    subprocess.run([str(python), "-c", "from PySide6.QtWidgets import QApplication; print('Anchor GUI dependency import passed.')"], check=True)
    print("Offline setup complete. No package index was contacted.", flush=True)
    if args.launch:
        command = [str(python), str(root / "app.py")]
        if args.preview:
            command.append("--preview")
        return subprocess.call(command, cwd=root)
    print("Launch with this folder's .venv Python and app.py, or rerun with --launch --preview.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("Offline setup could not finish: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
