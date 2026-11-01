"""Launch Anchor, temporary previews or the command-line core demo."""

import argparse
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import os
import stat

from planner import JsonRepository, PlannerService


def default_data_path() -> Path:
    """Return the default profile path for source or bundled runs."""
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent / "data" / "planner.json"
    if sys.platform == "darwin":
        folder = Path.home() / "Library" / "Application Support" / "Anchor"
    elif sys.platform == "win32":
        folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Anchor"
    else:
        folder = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "Anchor"
    return folder / "planner.json"


def demonstrate() -> None:
    with TemporaryDirectory(prefix="comp9001-core-demo-") as folder:
        repository = JsonRepository(Path(folder) / "demo.json")
        service = PlannerService(repository, today=lambda: date(2026, 10, 28))
        project = service.create_project(
            "Prepare a presentation", start_date=date(2026, 10, 27),
            deadline=date(2026, 10, 31), planned_minutes=300,
            daily_minutes=60, daily_limit_minutes=80,
            motivation="I want to explain my own work with confidence.",
        )
        stage = service.add_task(project.id, "Build the explanation")
        task = service.add_task(project.id, "Write the outline", parent_id=stage.id)
        print("1. Yesterday has no entry; suggested extra effort:")
        print(service.schedule(project.id))
        service.add_work(project.id, date(2026, 10, 27), 60, task.id, "Forgot to log this yesterday.")
        print("\n2. Backfill yesterday; the bar and suggestion update from the records:")
        print(service.progress(project.id))
        print(service.schedule(project.id))
        service.update_project(project.id, title="My COMP9001 presentation")
        service.undo_last_work_change()
        print("\n3. Undo the entry; keep the later project rename:")
        print(service.get_project(project.id).title)
        print(service.progress(project.id))
        service.add_work(project.id, date(2026, 10, 27), 60, task.id)
        service.archive_project(project.id)
        reopened = PlannerService(repository)
        print("\n4. Reload an archived, partially filled project:")
        print(reopened.progress(project.id))
        print("Archive preserved:", reopened.get_project(project.id).archived_at is not None)


def launch_desktop(data_path, preview=False, screenshot=None, page="room"):
    try:
        import PySide6
        # Qt skips plugins marked hidden by Finder. Repair only the local venv.
        if sys.platform == "darwin":
            local_venv = Path(__file__).resolve().parent / ".venv"
            plugins = Path(PySide6.__file__).parent / "Qt" / "plugins"
            if plugins.is_relative_to(local_venv):
                for path in plugins.rglob("*"):
                    flags = path.stat().st_flags
                    if flags & stat.UF_HIDDEN:
                        os.chflags(path, flags & ~stat.UF_HIDDEN)
        from PySide6.QtCore import QLockFile, QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        print("Anchor needs its desktop dependency. Run:\n  python -m pip install -r requirements.txt\nThen run: python app.py", file=sys.stderr)
        return 1
    from desktop.window import AnchorWindow
    from desktop.sample import seed_sample
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName("Anchor")
    data_path = Path(data_path).resolve()
    data_path.parent.mkdir(parents=True, exist_ok=True)
    # One lock per profile prevents two windows from overwriting each other.
    lock = QLockFile(str(data_path) + ".lock")
    if not lock.tryLock(100):
        QMessageBox.warning(None, "Anchor is already open", "This data file is being used by another Anchor window. Close it before reopening.")
        return 1
    try:
        service = PlannerService(JsonRepository(data_path))
        if preview:
            seed_sample(service)
        root = Path(__file__).resolve().parent
        window = AnchorWindow(service, data_path, root / "assets", preview)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        QMessageBox.critical(None, "Could not open your room", f"Your saved data has not been reset.\n\n{exc}\n\nData file: {data_path}")
        lock.unlock()
        return 1
    window.show()
    window.show_page(page)
    if screenshot:
        def capture():
            path = Path(screenshot).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            saved = window.grab().save(str(path))
            print(f"Screenshot {'saved' if saved else 'FAILED'}: {path}")
            application.exit(0 if saved else 1)
        QTimer.singleShot(450, capture)
    result = application.exec()
    lock.unlock()
    return result


def main():
    parser = argparse.ArgumentParser(description="Anchor — an illustrated study for your plans and progress")
    parser.add_argument("--demo", action="store_true", help="Run the deterministic core workflow")
    parser.add_argument("--preview", action="store_true", help="Open a disposable room with sample projects; personal data is untouched")
    parser.add_argument("--data", type=Path, help="Use an explicit JSON save location")
    parser.add_argument("--screenshot", type=Path, help="Save a preview screenshot and exit (implies --preview)")
    parser.add_argument("--page", choices=["room", "plan", "focus", "collection", "music", "immersive", "outside"], default="room")
    args = parser.parse_args()
    if args.demo:
        demonstrate()
        return 0
    if args.preview or args.screenshot:
        with TemporaryDirectory(prefix="anchor-preview-") as folder:
            return launch_desktop(Path(folder) / "planner.json", True, args.screenshot, args.page)
    else:
        return launch_desktop(args.data or default_data_path(), page=args.page)


if __name__ == "__main__":
    raise SystemExit(main())
