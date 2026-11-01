"""Prepare the Ed source hand-in without personal data or a machine runtime.

Run from the project folder:
    python3 tools/prepare_submission.py --require-readme

The root project's source files remain authoritative. This script rebuilds only
submission/01_Ed_Code and submission/Anchor-Ed-Code.zip. Padlet, presentation and
external-runtime materials are maintained separately and are never cleared.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile


PYTHON_FOLDERS = ("planner", "desktop", "tools")
SUPPORT_FILES = (
    "requirements.txt",
    "INSTALL.txt",
    "Launch Anchor.command",
    "docs/ARCHITECTURE.md",
)
OPTIONAL_SUPPORT_FILES = (
    "AI_DECLARATION.txt",
    "AI_ACKNOWLEDGEMENT.txt",
    "ACKNOWLEDGEMENTS.txt",
    "assets/IMAGE_SOURCE.txt",
    "assets/ROOMS_IMAGE_SOURCE.txt",
    "assets/FURNITURE_IMAGE_SOURCE.txt",
    "assets/WINDOWS_IMAGE_SOURCE.txt",
)
FORBIDDEN_PARTS = {"data", ".venv", "output", "__pycache__", ".git", "separate_materials", "tests"}

ED_UPLOAD_INSTRUCTIONS = """ED CODE SUBMISSION - WHAT TO UPLOAD

Upload README.txt and all Python source files to the course's Code Submission
slide. Do not replace those required uploads with only a ZIP or external link.

This folder preserves the application layout:
  app.py                 Application entry point
  planner/               Models, calculations and local storage
  desktop/               Native interface and scene
  tools/                 Source-packaging utilities

Keep these package directories when uploading. Files such as __init__.py must
stay inside their respective package; do not flatten all folders into one list.
If Ed's interface cannot preserve directories, confirm its accepted method with
the teaching team before uploading. The Ed upload interface has not been tested
by this preparation script.

Anchor-Ed-Code.zip is a convenient copy of this folder and is below 2 MB. It is
not a substitute for any direct README/Python-file uploads required by Ed.

The full offline runtime, if supplied, is in ../04_External_Files/. It is too
large for Ed and must be hosted separately using the course's permitted method.
README.txt must contain its real final download URL. A local path or placeholder
is not an external download link. Verify tutor access before the deadline.

No personal saves, virtual environment, generated screenshots, assignment
documents or historical raster artwork are included in this source folder.
"""

EXTERNAL_UPLOAD_INSTRUCTIONS = """EXTERNAL FILES - UPLOAD BEFORE THE DEADLINE

The course permits files exceeding Ed's 2 MB limit to be hosted on GitHub or
OneDrive, with a link in README.txt. README.txt and the Python source files must
still be uploaded directly to Ed as instructed by the teaching team.

The offline application archive is:
  Anchor-macOS-AppleSilicon.zip

The source-and-dependency kit is:
  Anchor-Offline-Source.zip
It contains local macOS universal2, Windows x86_64 and Linux x86_64 wheels.
It requires an existing supported CPython interpreter and suitable OS desktop
libraries. Only macOS execution was tested locally; see each archive's README.

Only describe that archive as ready after it actually exists and has been
checked. It targets Apple Silicon Macs; it is not a Windows or Linux runtime.
Keep the source hand-in available even when distributing the offline app.

1. Upload both final runtime archives to GitHub or OneDrive.
2. Obtain a genuine download link and verify the tutor has access.
3. Put that exact URL, the platform requirements and launch instructions in
   submission/README_FOR_ED.txt, then run:
     python3 tools/prepare_submission.py --require-readme
   The tool copies that master README to 01_Ed_Code/README.txt.
4. Upload that final README.txt together with all required Python files to Ed.
5. Keep the externally hosted files unchanged after the course deadline. The
   tutors may check their last-modified timestamps. Do not overwrite the linked
   files with a later build after the deadline.

The announcement says Sunday at 11:59 pm. For the week containing 1 November
2026, Sunday is 1 November; confirm the course's stated timezone. This note does
not extend or reinterpret the deadline.

No files are uploaded automatically by these preparation tools. A real external
URL has to be supplied after upload; no invented URL is a valid submission.
"""


def source_files(root):
    """Return all project Python files, including this packaging utility."""
    paths = [root / "app.py"]
    for folder in PYTHON_FOLDERS:
        paths.extend(path for path in (root / folder).rglob("*.py")
                     if path.is_file() and not FORBIDDEN_PARTS.intersection(path.relative_to(root).parts))
    return sorted(set(paths))


def prepare_submission(root, require_readme=False):
    root = Path(root).resolve()
    destination = root / "submission"
    ed_folder = destination / "01_Ed_Code"
    ed_archive = destination / "Anchor-Ed-Code.zip"
    external_readme = destination / "04_External_Files" / "README_EXTERNAL_UPLOAD.txt"
    supplied_readme = destination / "README_FOR_ED.txt"
    if require_readme and not supplied_readme.is_file():
        raise FileNotFoundError("Create submission/README_FOR_ED.txt before the final Ed build.")

    python_files = source_files(root)
    files = python_files + [root / name for name in SUPPORT_FILES]
    missing = [str(path.relative_to(root)) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing submission sources: " + ", ".join(missing))
    files.extend(root / name for name in OPTIONAL_SUPPORT_FILES if (root / name).is_file())
    destination.mkdir(exist_ok=True)

    with TemporaryDirectory(prefix="anchor-ed-prepare-") as folder:
        staging = Path(folder)
        prepared = staging / "01_Ed_Code"
        prepared.mkdir()
        for path in files:
            relative = path.relative_to(root)
            if FORBIDDEN_PARTS.intersection(relative.parts):
                raise ValueError("Private/runtime path in source selection: " + str(relative))
            target = prepared / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        if supplied_readme.is_file():
            shutil.copy2(supplied_readme, prepared / "README.txt")
        (prepared / "README_ED_UPLOAD.txt").write_text(ED_UPLOAD_INSTRUCTIONS, encoding="utf-8")

        selected = sorted(path for path in prepared.rglob("*") if path.is_file())
        manifest = {
            "python_files": len(python_files),
            "readme_supplied": supplied_readme.is_file(),
            "files": {
                path.relative_to(prepared).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in selected
            },
        }
        (prepared / "SOURCE_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        selected.append(prepared / "SOURCE_MANIFEST.json")
        archive_path = staging / "Anchor-Ed-Code.zip"
        with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
            for path in sorted(selected):
                archive.write(path, path.relative_to(prepared))
        with ZipFile(archive_path) as archive:
            if archive.testzip() is not None:
                raise ValueError("The prepared source archive did not pass its CRC check.")
            for path in selected:
                name = path.relative_to(prepared).as_posix()
                if archive.read(name) != path.read_bytes():
                    raise ValueError("The prepared archive has a stale file: " + name)
        if archive_path.stat().st_size >= 2_000_000:
            raise ValueError("The Ed source archive exceeds the conservative 2 MB limit.")

        # Commit only our generated outputs. Sibling submission materials are
        # left untouched, including a runtime archive that may still be building.
        if ed_folder.exists():
            shutil.rmtree(ed_folder)
        shutil.copytree(prepared, ed_folder)
        shutil.copyfile(archive_path, ed_archive)

    external_readme.parent.mkdir(parents=True, exist_ok=True)
    external_readme.write_text(EXTERNAL_UPLOAD_INSTRUCTIONS, encoding="utf-8")
    result = {
        "python_files": len(python_files),
        "readme_supplied": supplied_readme.is_file(),
        "ed_folder": str(ed_folder),
        "ed_archive": str(ed_archive),
        "archive_bytes": ed_archive.stat().st_size,
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="Prepare Anchor's Ed source hand-in.")
    parser.add_argument("--require-readme", action="store_true",
                        help="Fail instead of producing a draft without README.txt.")
    args = parser.parse_args()
    result = prepare_submission(Path(__file__).resolve().parents[1], args.require_readme)
    print(json.dumps(result, indent=2))
    if not result["readme_supplied"]:
        print("DRAFT: README.txt is missing. Supply submission/README_FOR_ED.txt and rebuild before uploading.")
    print("Other submission categories and personal data were not copied or cleared.")


if __name__ == "__main__":
    main()
