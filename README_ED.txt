ANCHOR - A Quiet Study for Your Goals
COMP9001 Final Project | Submission prepared 1 November 2026 (Sydney)

WHAT THIS PROGRAM DOES
Anchor is a Python desktop companion for students and people managing personal
projects. An illustrated study contains goals, nested tasks, focus timing,
optional bounded catch-up, daily statistics and archived project books. Book
covers/spines, personal notes, day/night mode and UI-free immersion are supported.
Spotify/Apple Music control is optional on macOS; normal planning works without
either player. Project data is stored locally.

EXTERNAL FILES
Project repository: https://github.com/JiyuZhong/Anchor
Download URL: https://github.com/JiyuZhong/Anchor/releases/tag/v1.1.3
Mac app: https://github.com/JiyuZhong/Anchor/releases/download/v1.1.3/Anchor-macOS-AppleSilicon.zip
Offline source kit: https://github.com/JiyuZhong/Anchor/releases/download/v1.1.3/Anchor-Offline-Source.zip
Portable source: https://github.com/JiyuZhong/Anchor/releases/download/v1.1.3/Anchor-Source.zip

The repository's Release assets should contain these two final archives:
  Anchor-macOS-AppleSilicon.zip   Offline app, includes Python and Qt.
  Anchor-Offline-Source.zip       Source plus local GUI dependency wheels.

The course permits external files exceeding Ed's 2 MB limit. The Python files
and this README must still be uploaded to Ed as instructed. Check the tutor's
download permissions. Keep hosted files unchanged after the course deadline.
The repository is public. The two runtime archives are supplied as assets of
release v1.1.3. Their uploaded sizes and SHA256 values match the locally tested
files. The submission verification record documents the final access check.
Keep these hosted files unchanged after the course deadline.

OPTION 1 - OFFLINE APP ON AN APPLE SILICON MAC
1. Download and extract Anchor-macOS-AppleSilicon.zip completely.
2. Open Anchor.app. Python, PySide6, Shiboken and Qt are included.
3. Open Preview.command starts disposable sample projects for evaluation.
The app is arm64, not a Windows/Linux/Intel-only executable. It was tested on
the author's Apple Silicon Mac. This student build is ad-hoc signed and is not
Apple-notarised; macOS may ask for its standard Open Anyway approval.

OPTION 2 - SOURCE WITH BUNDLED OFFLINE GUI DEPENDENCIES
1. Download and extract Anchor-Offline-Source.zip completely.
2. Use CPython 3.10, 3.11, 3.12 or 3.13. Python 3.14 is not supported by the
   pinned PySide6 release. Follow that archive's offline setup instructions.
3. Its wheelhouse includes macOS universal2, Windows x86_64 and Linux x86_64
   GUI packages. Installation uses local files, not the package index.
4. Open the app with the provided launcher or the archive's stated command.
Only macOS was tested locally; other platforms have dependency-tag checks.
Linux still requires a working graphical desktop and the Qt system libraries
listed in the offline archive. The offline source kit includes GUI libraries,
but does not include a Python interpreter for every operating system.

OPTION 3 - THESE ED SOURCES WITH AN EXISTING PYTHON ENVIRONMENT
Keep the package directories intact; do not flatten their __init__.py files.
From the folder containing app.py:
  python3 -m pip install -r requirements.txt
  python3 app.py
On Windows the interpreter command may be python rather than python3.
This option needs internet if the GUI dependencies are not installed already.
The macOS Launch Anchor.command creates an isolated environment automatically.

DISPOSABLE PREVIEW AND CORE DEMO
  python3 app.py --preview
Preview starts with explicit sample projects and fictional focus/music data.
Changes are discarded on exit and do not replace personal profiles.

  python3 app.py --demo
The deterministic command-line example uses only Python's standard library.
It demonstrates the planning/persistence core; it is not the full GUI.

MAIN USER FLOW
1. Notebook -> New project: choose a deadline or an ongoing daily goal. New
   dated goals link daily/total effort using the inclusive number of dates.
2. Tasks: outline tasks/subtasks during creation or add them later. Select a
   task or subtask to focus. Parent totals include both; records count once.
3. Focus: start, pause/resume, finish, then adjust actual start/end periods.
   The combined periods determine the recorded minutes and hourly chart.
4. Daily plan: see the usual pace and optional extra. Extra is bounded by 25%
   of the usual pace, at most 15 minutes and the project's daily maximum.
5. Records: inspect a saved day's hourly bars and observed music, or add/edit/
   backfill/delete a time record. The latest record change can be undone.
6. Archive with a reflection and revisit Collection. Reopening retains history.
7. Project options -> Book cover and position edits templates, colours, pictures
   and shelf cells. Hide interface or Look outside gives an immersive view.

ADVANCED PYTHON TOPICS
File I/O: planner/storage.py reads/writes JSON. A complete temporary file is
flushed and replaces the destination before the new in-memory state is used.
This stores projects, tasks, work records and appearance/preferences.

Recursion: planner/models.py TaskNode.find() searches nested task children;
TaskNode.is_complete() rolls up completion. planner/planning.py task_minutes()
recursively totals a task and its descendants without counting entries twice.

Error handling: invalid input, damaged saves and failed writes are handled
without silently replacing existing data with an empty project collection.

SAVES AND LIMITATIONS
Source mode uses data/ beside app.py. The packaged Mac app uses
~/Library/Application Support/Anchor/. Back up the entire profile directory,
including images. An explicit --data /path/planner.json selects another folder.
No personal saves or credentials are included in this submission.

Confirmed work periods determine record minutes and the chart. Original timer
observations remain separate, and music is clipped to the confirmed periods
without being extended or moved. Older records keep their original values
until periods are explicitly set, and receive no guessed chart hours. Music is
observed only while connected and focusing; its two-second polling boundaries
are approximate. Real player Automation permission remains an interactive check.
Active unsaved sessions cannot be recovered after a crash. Furniture placement,
room switching and daily draws are not part of the current interface.

SOURCE LAYOUT
app.py       Entry point, preview mode and local profile selection.
planner/     Models, calculations, timer, observations and persistence.
desktop/     Native controls, chart, shared room geometry and book rendering.
tools/       Reproducible source, offline-dependency and Mac-app packaging.
docs/        Architecture explanation.

CORE WALKTHROUGH AND PREVIEW
Use --demo for the standard-library planning walkthrough. Use --preview to
open the interface with disposable sample data; no personal profile is changed.
