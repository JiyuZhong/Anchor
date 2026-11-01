"""Build an offline source distribution with platform-specific Qt wheels.

Run with the project's Python interpreter. Existing wheel downloads are reused:
    .venv/bin/python tools/build_offline_kit.py
Use --no-download for the final source freeze after the wheels are available.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


TARGETS = {
    "macos": "macosx_12_0_universal2",
    "windows": "win_amd64",
    "linux": "manylinux_2_28_x86_64",
}
SUPPORT = (
    "requirements.txt", "INSTALL.txt", "docs/ARCHITECTURE.md",
)
OPTIONAL_SUPPORT = (
    "AI_DECLARATION.txt", "AI_ACKNOWLEDGEMENT.txt", "ACKNOWLEDGEMENTS.txt",
    "assets/IMAGE_SOURCE.txt", "assets/ROOMS_IMAGE_SOURCE.txt",
    "assets/FURNITURE_IMAGE_SOURCE.txt", "assets/WINDOWS_IMAGE_SOURCE.txt",
)
EXCLUDED_PARTS = {"__pycache__", "separate_materials", "tests"}


KIT_README = """ANCHOR - OFFLINE SOURCE KIT

This archive contains the Python source and the original PySide6 Essentials /
shiboken6 6.8.3 dependency wheels. Installing these local wheels does not need
an internet connection. This is separate from the Apple Silicon .app package.

REQUIREMENTS
- An existing 64-bit CPython 3.10, 3.11, 3.12 or 3.13 installation, with venv/pip.
  Python 3.14 is excluded by the dependencies' Requires-Python metadata.
- macOS 12+ on Apple Silicon or Intel; or Windows x86_64; or Linux x86_64 with
  glibc 2.28+ and a desktop display. Windows ARM64 and Linux ARM64/musl are not
  supplied. The operating system must also satisfy Qt 6.8 platform requirements.
- Linux still needs its normal desktop libraries/plugins. Bundled Python wheels
  do not provide a complete Linux OS or install missing system packages.

SETUP
1. Extract the whole archive into a writable folder. Keep wheelhouse/ together
   with OFFLINE_SETUP.py, requirements.txt and the source package directories.
2. In that folder, use a supported interpreter:
     macOS/Linux: python3 OFFLINE_SETUP.py
     Windows:     py -3.12 OFFLINE_SETUP.py
   On Linux distributions where venv/ensurepip is absent, install that component
   through your Python provider before using this kit.
3. To install and immediately open disposable sample projects:
     python3 OFFLINE_SETUP.py --launch --preview
   On Windows use py -3.12 instead of python3. The supplied platform launchers
   perform the same local setup and forward --preview when requested.

AFTER SETUP
  macOS/Linux: .venv/bin/python app.py
  Windows:     .venv\\Scripts\\python.exe app.py
  Add --preview for temporary demonstration projects; changes are discarded
  when that preview closes. Normal source-mode saves live in this folder/data.
  Back up the entire data directory, including copied book/project images.

The music remote is optional and macOS only. Connect is explicit and may request
macOS Automation permission. Core planning/focus/records work without a music
application. No credentials or personal project saves are in this archive.

CONTENTS AND VERIFICATION
  wheelhouse/macos/     Universal2 macOS dependency wheels
  wheelhouse/windows/   Windows x86_64 dependency wheels
  wheelhouse/linux/     Linux manylinux_2_28_x86_64 dependency wheels
  WHEELS_SHA256.txt     SHA256 hashes checked by OFFLINE_SETUP.py
  BUILD_MANIFEST.json   Source/dependency hashes and exact compatibility tags
  THIRD_PARTY_NOTICES/  Available upstream license texts and source information
  README_SOURCE.txt    Full application usage guide

The preparation check installs the macOS wheels from this kit with --no-index
into a fresh temporary environment and checks GUI startup on the build Mac.
Windows and Linux wheel tags are checked, but those OS versions are not claimed
to have been independently executed. See VALIDATION.txt when supplied.

This archive is larger than Ed's 2 MB limit. Upload the final ZIP to the course-
approved GitHub/OneDrive location, put a genuine accessible link in the README
uploaded to Ed, and keep the hosted file unchanged after the course deadline.
The Python files and README still need their required direct Ed submission.
"""


def project_sources(root):
    paths = [root / "app.py"]
    for folder in ("planner", "desktop", "tools"):
        paths.extend(path for path in (root / folder).rglob("*.py")
                     if path.is_file() and not EXCLUDED_PARTS.intersection(
                         path.relative_to(root).parts))
    return sorted(set(paths))


def wheel_files(root, download=True):
    result = {}
    for target, tag in TARGETS.items():
        destination = root / ".submission-build" / "wheels" / target
        destination.mkdir(parents=True, exist_ok=True)
        wheels = sorted(destination.glob("*.whl"))
        if len(wheels) != 2:
            if not download:
                raise FileNotFoundError("Missing dependency wheels for " + target)
            subprocess.run([sys.executable, "-m", "pip", "download", "--only-binary=:all:",
                            "--platform", tag, "--python-version", "3.12", "--implementation", "cp",
                            "--abi", "abi3", "--dest", str(destination), "-r", str(root / "requirements.txt"),
                            "--disable-pip-version-check", "--cache-dir", str(root / ".submission-build" / "pip-cache")], check=True)
            wheels = sorted(destination.glob("*.whl"))
        if len(wheels) != 2 or not all("-6.8.3-cp39-abi3-" + tag in wheel.name for wheel in wheels):
            raise ValueError("Unexpected Qt dependency set for " + target)
        for wheel in wheels:
            with ZipFile(wheel) as archive:
                metadata = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
                text = archive.read(metadata).decode("utf-8")
                if "Requires-Python: <3.14,>=3.9" not in text:
                    raise ValueError("Unexpected dependency Python compatibility: " + wheel.name)
        result[target] = wheels
    return result


def build_kit(root, download=True):
    root = Path(root).resolve()
    external = root / "submission" / "04_External_Files"
    external.mkdir(parents=True, exist_ok=True)
    destination = external / "Anchor-Offline-Source"
    output = external / "Anchor-Offline-Source.zip"
    wheels = wheel_files(root, download)
    notices = root / ".submission-build" / "third-party-notices"
    validation = root / ".submission-build" / "offline-validation.txt"
    with TemporaryDirectory(prefix="anchor-offline-kit-") as folder:
        kit = Path(folder) / "Anchor-Offline-Source"
        kit.mkdir()
        support = [root / name for name in SUPPORT]
        support.extend(root / name for name in OPTIONAL_SUPPORT if (root / name).is_file())
        for source in project_sources(root) + support:
            relative = source.relative_to(root)
            target = kit / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        shutil.copy2(root / "README.txt", kit / "README_SOURCE.txt")
        (kit / "README.txt").write_text(KIT_README, encoding="utf-8")
        shutil.copy2(root / "tools" / "offline_setup.py", kit / "OFFLINE_SETUP.py")
        launchers = {
            "Launch Offline.command": '#!/bin/bash\nset -e\ncd "$(dirname "$0")"\nexec python3 OFFLINE_SETUP.py --launch "$@"\n',
            "Launch Offline.sh": '#!/bin/sh\nset -e\ncd "$(dirname "$0")"\nexec python3 OFFLINE_SETUP.py --launch "$@"\n',
            "Launch Offline.bat": '@echo off\r\ncd /d "%~dp0"\r\nwhere py >nul 2>nul\r\nif errorlevel 1 (\r\n  python OFFLINE_SETUP.py --launch %*\r\n) else (\r\n  py -3 OFFLINE_SETUP.py --launch %*\r\n)\r\nif errorlevel 1 pause\r\n',
        }
        for name, text in launchers.items():
            path = kit / name
            path.write_bytes(text.encode("utf-8"))
            if not name.endswith(".bat"):
                path.chmod(0o755)
        hashes = []
        for target, files in wheels.items():
            for wheel in files:
                relative = Path("wheelhouse") / target / wheel.name
                path = kit / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(wheel, path)
                hashes.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + relative.as_posix())
        (kit / "WHEELS_SHA256.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
        if notices.is_dir():
            shutil.copytree(notices, kit / "THIRD_PARTY_NOTICES")
        else:
            (kit / "THIRD_PARTY_NOTICES").mkdir()
        # Preserve any license files supplied inside the unmodified upstream wheels.
        for files in wheels.values():
            for wheel in files:
                with ZipFile(wheel) as archive:
                    for name in archive.namelist():
                        if ".dist-info/licenses/" in name and not name.endswith("/"):
                            target = kit / "THIRD_PARTY_NOTICES" / name
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(archive.read(name))
        if validation.is_file():
            shutil.copy2(validation, kit / "VALIDATION.txt")
        manifest = {
            "dependency_versions": {"PySide6-Essentials": "6.8.3", "shiboken6": "6.8.3"},
            "source_python_versions": "CPython 3.10 through 3.13",
            "wheel_tags": TARGETS,
            "files": {path.relative_to(kit).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in sorted(kit.rglob("*")) if path.is_file()},
        }
        (kit / "BUILD_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        temporary_zip = Path(folder) / "Anchor-Offline-Source.zip"
        with ZipFile(temporary_zip, "w", ZIP_DEFLATED) as archive:
            for path in sorted(kit.rglob("*")):
                if path.is_file():
                    archive.write(path, Path("Anchor-Offline-Source") / path.relative_to(kit),
                                  compress_type=ZIP_STORED if path.suffix == ".whl" else ZIP_DEFLATED)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(kit, destination)
        shutil.copyfile(temporary_zip, output)
    return output


def main():
    parser = argparse.ArgumentParser(description="Build Anchor's offline source-and-wheel kit.")
    parser.add_argument("--no-download", action="store_true", help="Require cached wheels without internet access.")
    args = parser.parse_args()
    path = build_kit(Path(__file__).resolve().parents[1], download=not args.no_download)
    print(f"Offline source archive: {path}")
    print(f"Size: {path.stat().st_size / 1024**2:.1f} MiB. No personal saves or virtual environments included.")


if __name__ == "__main__":
    main()
