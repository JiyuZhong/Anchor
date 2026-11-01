#!/bin/bash
# Double-click on macOS. First launch installs the isolated GUI dependency.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'from PySide6.QtWidgets import QApplication' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
# Some macOS folders propagate Finder's hidden flag to Qt plugin binaries.
# Qt ignores hidden plugins, so clear that flag only inside this app's venv.
plugin_dir="$(.venv/bin/python -c 'import PySide6, pathlib; print(pathlib.Path(PySide6.__file__).parent / "Qt" / "plugins")')"
if [ -d "$plugin_dir" ]; then
  chflags -R nohidden "$plugin_dir"
fi
exec .venv/bin/python app.py "$@"
