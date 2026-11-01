# Anchor: code guide

The application has two parts: `planner/` handles saved data and calculations;
`desktop/` presents them with PySide6. The core does not depend on Qt.

## Where to start

| File | Purpose |
| --- | --- |
| `app.py` | Starts the app, selects a profile and provides preview/core-demo modes. |
| `planner/models.py` | Project, task and work-record fields and validation. |
| `planner/service.py` | Operations that validate and save changes. |
| `planner/storage.py` | JSON loading and complete-file replacement. |
| `planner/planning.py` | Progress, task totals and daily suggestions. |
| `planner/timer.py` | Idle/running/paused timer using a monotonic clock. |
| `planner/activity.py` | Active intervals and observed music within a session. |
| `planner/statistics.py` | Local-day totals and 24 hourly buckets. |
| `planner/books.py` | Book appearance and shelf-cell allocation. |
| `desktop/window.py` | Page changes and the main user actions. |
| `desktop/notebook.py` | Fixed navigation, task/record pages and statistics workspace. |
| `desktop/study_geometry.py`, `scene.py` | Shared room coordinates, cameras and painting. |
| `desktop/music.py` | Asynchronous player commands and status polling. |

## Saving a change

For a manual time entry, the window opens `WorkLogDialog`. Its payload goes to
`PlannerService.add_work()`, which checks the values and prepares a changed
project. `_commit()` saves that state through `JsonRepository` before replacing
the current in-memory project.

`JsonRepository.save()` writes a temporary file next to the target, flushes it,
and uses `os.replace()`. A failed write leaves the previous file and service
state in place. Loading damaged JSON raises an error instead of creating an
empty replacement. This is the project's main use of **File I/O**.

The service returns copies of projects so the interface cannot change a saved
object without going through validation. The latest record edit stores before
and after snapshots. Undo changes that record only, preserving later unrelated
project edits. It is one-step record undo, not a general edit history.

## Tasks and recursion

A project contains tasks. Each `TaskNode` may contain child tasks. A task belongs
to a project; it is not a subclass of Project. The depth is limited to project,
task/stage and child task.

`TaskNode.find()` checks itself, then searches its children. It stops when it
finds the requested ID or has checked every branch. `is_complete()` collects
leaf completion states. `task_minutes()` adds a node's own records and calls
itself for each child. Each record belongs to one node and is counted once in a
subtree total. These are the project's uses of **Recursion**.

Recorded minutes, task completion and project outcome are separate values.
Reaching the original time estimate does not mark an outcome complete.
The project form accepts an optional initial task tree; the service validates
and saves it with the project in one write. Adding a child clears the parent's
old leaf-completion flag, while preserving all records. Both parent and child
IDs are valid focus targets. The task list shows inclusive totals and separates
row selection from completion checkboxes.

## Daily suggestions

Let B be the usual daily target, M the daily maximum, and C the extra-time cap:

    C = min(15, B // 4, M - B)

Validation requires M >= B. With catch-up off, the schedule uses the usual pace.
With catch-up on, a dated project calculates its required daily total from the
remaining estimate R, today's recorded minutes T and remaining dates N:

    required = ceil((R + T) / N)
    target = min(B + C, max(B, required))
    still_needed = min(R, max(target - T, 0))

Adding today's recorded amount before dividing keeps the daily total stable as
work is logged. The schedule repeats this allocation for the dates left and
reports any remaining amount as `unscheduled_minutes`.

For a goal without a deadline, only yesterday's gap G is considered:

    extra = min(ceil(G / 3), C)
    still_needed = max(B + extra - T, 0)

Older gaps and yesterday's suggested extra are not carried forward. The preview
shows seven dates; future dates use the usual pace until they become today.
Suggestions are calculated from records rather than stored as debt.

## Timer observations and statistics

`FocusTimer` measures elapsed time. `ActivityCapture` keeps the corresponding
active intervals and track changes. Pausing closes the active interval; resuming
starts another. Cancelling confirmation or failing a save retains the paused
session. Successful saving or explicit discard clears it.

A focus WorkLog may have `focus_details`, containing intervals, music and measured
seconds. The user-confirmed date/minutes remain separate. Editing those values
does not rewrite the original observations. Old records without details keep
that field empty.

Statistics clip saved intervals to the selected local date and bucket them by
hour. UTC arithmetic handles midnight and daylight-saving changes. Repeated
local hours share a column. No timestamp is inferred from when an old entry was
created. The chart has a fixed readout and only repaints its hover state when
the inspected hour changes or its brief highlight transition advances.

## Room and book drawing

All five views project the same world coordinates through different fixed
cameras. Books rest on the shelf-board tops. Cover, spine and page faces are
mapped to their own projected planes, with depth ordering for overlapping parts.
The same projection is used for painting and hit regions.

Static depth layers are cached; only leaves and the playing record change during
ordinary animation frames. The cache is bounded to six variants and is cleared
when relevant scene settings or book appearance change. Measured draw time is
not a measurement of physical display frame rate.

Book appearance is saved separately from project records. Explicit shelf cells
are reserved before automatic placement. Front-facing books require three
adjacent cells on one shelf. Image copies are made on Save; a failed save removes
copies made by that attempt. An abrupt process exit can still leave an unused
image copy because image copying and JSON replacement are separate operations.

## Player connection

The Mac controller runs fixed AppleScript commands through QProcess. `Connect`
starts the shared MusicSession; opening a panel alone does not connect. It polls
every two seconds and continues across pages. Identical replies do not rewrite
controls. Commands arriving during a read are queued.

Music observations cover only connected, active focus intervals. They are
approximate polling observations, not a complete listening history. Earlier
development checks used simulated replies; live Automation permission is a
separate interactive check.

## Profiles and distribution

Source mode saves beside app.py in `data/`. A frozen Mac app uses the user's
`Library/Application Support/Anchor/`, outside the app resources. Preview uses a
temporary directory and cannot overwrite a personal profile. Unsaved running
sessions are not recovered after a crash.

The v1.1.1 release provides the consolidated source and installation packages.
The runtime app targets Apple Silicon; the offline source kit supplies Qt
wheels for the documented platforms and needs Python 3.10-3.13.
