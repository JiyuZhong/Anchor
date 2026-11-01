ANCHOR
COMP9001 Final Project

Anchor is a desktop planner for students and personal projects. You can break a
goal into tasks, record the time you spend on it, and keep the project as a book
when you finish or decide to stop. The room is drawn with Python and Qt.

RUN FROM SOURCE
Use CPython 3.10-3.13. The pinned PySide6 version does not support Python 3.14.

On macOS, double-click Launch Anchor.command. It creates a local .venv and
installs the GUI dependency on first use. This first installation needs internet.

Or run these commands from the folder containing app.py:
  python3 -m pip install -r requirements.txt
  python3 app.py

On Windows, the command may be python rather than python3. GUI use requires a
graphical desktop. Only the macOS version has been run on a physical machine.

To try the program without changing a personal profile:
  python3 app.py --preview
The preview uses fictional projects and focus/music records. Its changes are
removed when you close it.

A command-line example of the core logic needs no GUI library:
  python3 app.py --demo

USING ANCHOR
Room shows the study and today's recorded time. Click a project book, or open
Notebook to choose a project. The five bottom buttons show different views of
the same room: Room, Notebook, Focus, Collection and Music.

Notebook has three fixed section tabs:
- Tasks: add tasks and subtasks, rename or delete them, and mark leaf tasks done.
  Select a task to start a focus session for it.
- Daily plan: see today's suggested time and what still fits before the deadline.
- Records: view hourly focus bars or open Entries to add, edit, backfill or delete
  a work record. You can undo the latest record change, including after a restart.

A goal may have a deadline or continue without one. Set a daily target and daily
maximum. The original total estimate of a dated project stays fixed. An ongoing
goal tracks each day's target and keeps a separate lifetime total. Completing a
task or outcome is separate from recording time.

Focus is a count-up timer. Start, pause, resume, then finish and confirm the
actual minutes, work date and task before saving. Cancelling that form leaves
the session paused. Page changes and hiding the interface do not stop the timer.

CATCH-UP
Catch-up is optional and is off for new goals. Its daily extra is limited to the
smallest of 15 minutes, one quarter of the daily target rounded down, and the
space left under the daily maximum.

Dated projects spread the remaining estimate across the dates left. A 300-minute
plan over five days at 60 minutes/day can suggest 75 minutes on day two if day
one has no record and the daily cap allows it. Recording 20 minutes today leaves
55 more; it does not raise the 75-minute total. Any time that cannot fit is shown.

Ongoing goals consider only yesterday's gap. About one third of that gap can be
added today, within the same limits. Earlier gaps do not accumulate. Backfilling
a record recalculates the suggestion. These are time suggestions; they do not
create extra tasks or change a deadline.

DAILY STATISTICS
Records -> Overview shows a selected day for one goal or all goals. Move across
the chart to inspect each hour. The readout stays above the plot. Left/right
keys also inspect hours; Esc clears the inspection.

Bars use saved timer observations and exclude pauses. Confirmed record minutes
and dates can be corrected separately. A correction does not move the observed
timeline. Older/manual entries without timing keep their totals but have no
guessed hourly bars. The chart updates after a focus session is saved.

Music entries show tracks observed while focusing and connected to a player.
Track boundaries are approximate because player status is read every two seconds.

BOOKS AND COLLECTION
Each project has a book. Open project options -> Book cover and position, or
use Design and arrange your books in Collection. There are four templates,
separate cover/spine colours and images, and 30 fixed shelf cells. A spine uses
one cell; a front-facing cover uses three adjacent cells. Books can be placed
automatically, assigned a cell or taken off the shelf. Projects remain available
in the interface if the shelf is full.

Images are copied into the profile folder, so moving the original file does not
break a saved cover. Collection also has an upload/change-cover button.

Archive a project with a reflection, whether it is complete or unfinished. Its
tasks and records stay available. Reopen it to continue editing. Changing an
archived book's appearance does not reopen the project.

ROOM OPTIONS
Use the day/night button to change the lighting and interface colours. Your
notes supports several entries; one appears on Room when you return, or when
you choose another note. It stays in place while you read.

Hide interface removes the controls. Esc or a double-click brings them back.
Look outside opens a closer view of the same landscape. Animation and full
screen are in the options menu.

Ctrl+1-5: change view. Ctrl+N: new project. Ctrl+B: book editor.
Ctrl+I: hide/show interface. F11: full screen.

MUSIC ON macOS
Choose music in Spotify or Apple Music, select that player in Anchor and press
Connect. Anchor shows the track and controls play/pause, previous/next and player
volume. It does not provide streaming, playlists or a music account.

macOS may ask for Automation permission. Connecting is explicit; opening the
Music page alone does not contact a player. The connection continues across
pages. The record turns while the player reports playback and animation is on.
Closing Anchor leaves the external player playing. Real player permission and
playback still need an interactive check; automated tests simulate responses.

SAVED FILES
Source mode uses data/ beside app.py:
  planner.json        Projects, tasks, work records and the latest undo.
  books.json          Book appearance and positions.
  room-settings.json  Notes, animation and day/night preference.
  images/             Project pictures.
  book-images/        Cover and spine pictures.

The packaged Mac app uses ~/Library/Application Support/Anchor/ instead.
--data /path/planner.json selects a different profile directory. Back up the
whole directory, including images. Personal profiles are not included in releases.

An unsaved timer cannot be recovered after a crash. Pause when away and check
time after system sleep. Suggestions use a cap per project, not a shared daily
cap across every project. The current interface has one fixed room and no
furniture draw, room switching, cloud sync or closed-app reminders.

CODE
planner/ contains the models, calculations, timer and JSON storage.
desktop/ contains the native interface and scene drawing.
tools/ contains the source and runtime packaging scripts.

File I/O is used to save and restore records; recursion is used to search and
total nested tasks. See docs/ARCHITECTURE.md for the main data flow.

DOWNLOAD AND INSTALLATION
https://github.com/JiyuZhong/Anchor/releases/tag/v1.1.0
INSTALL.txt explains the Mac app, portable source and offline dependency kit.
