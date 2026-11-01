"""Create a portable source archive without personal saves or the local runtime.

Run: python tools/package_source.py
The recipient still needs Python and the dependency in requirements.txt.
"""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


OPTIONAL_FILES = (
    "AI_DECLARATION.txt", "AI_ACKNOWLEDGEMENT.txt", "ACKNOWLEDGEMENTS.txt",
)
EXCLUDED_PARTS = {"__pycache__", "separate_materials", "tests"}


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / "dist" / "Anchor-source.zip"
    destination.parent.mkdir(exist_ok=True)
    files = [root / name for name in (
        "app.py", "requirements.txt", "README.txt", "INSTALL.txt", "Launch Anchor.command",
        "docs/ARCHITECTURE.md",
    )]
    files.extend(root / name for name in OPTIONAL_FILES if (root / name).is_file())
    for folder in ("planner", "desktop", "docs", "assets", "tools"):
        files.extend(path for path in (root / folder).rglob("*")
                     if path.is_file() and not EXCLUDED_PARTS.intersection(path.relative_to(root).parts)
                     and path.name != ".DS_Store"
                     and (folder != "assets" or path.suffix == ".txt"))
    missing = [str(path.relative_to(root)) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing release files: " + ", ".join(missing))
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            archive.write(path, Path("Anchor") / path.relative_to(root))
    print(f"Source archive: {destination}")
    print("Personal data, .venv, screenshots, retired raster artwork and assignment documents are excluded.")


if __name__ == "__main__":
    main()
