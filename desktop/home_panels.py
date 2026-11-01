"""Legacy room and reward panels, retained for old room tests."""

from collections import Counter
from datetime import date

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QProgressBar, QSpinBox, QVBoxLayout,
)

from planner.rooms import Lamp


def _room_label(home, item):
    if not item.room_ids:
        return "Every room"
    return "Only: " + ", ".join(home.rooms[room_id].name for room_id in item.room_ids)


def _sprite(window, furniture_id):
    sprites = getattr(window.scene, "sprites", None)
    return sprites.get(furniture_id) if sprites is not None else None


def build_customize(window):
    """Arrange owned items in the selected room."""
    from .window import button, label, row

    home = window.home
    room = home.current_room
    content = window.make_panel("Make it your room", "Choose a room and arrange the furniture.")
    content.addWidget(label("YOUR ROOM", "eyebrow"))
    window.room_combo = QComboBox()
    for choice in home.rooms.values():
        window.room_combo.addItem(choice.name, choice.id)
    window.room_combo.setCurrentIndex(window.room_combo.findData(room.id))

    def select_room(index):
        room_id = window.room_combo.itemData(index)

        def change():
            home.select_room(room_id)
            window.selected_slot_id = None

        window.operate(change, "Room changed. Its arrangement has been restored.")

    window.room_combo.currentIndexChanged.connect(select_room)
    content.addWidget(window.room_combo)
    content.addWidget(label(room.description, "muted", True))
    content.addWidget(label("Each room remembers its own arrangement. Your furniture collection travels with you.", "muted", True))
    content.addWidget(button("Design and arrange books", window.edit_books, "primary"))

    content.addWidget(label("CHOOSE A SPOT", "eyebrow"))
    window.slot_combo = QComboBox()
    placements = home.placements
    valid_slots = {slot.id for slot in room.slots}
    if window.selected_slot_id not in valid_slots:
        window.selected_slot_id = room.slots[0].id
    for slot in room.slots:
        occupied = placements.get(slot.id)
        suffix = home.catalog[occupied["furniture_id"]].name if occupied else "Empty"
        window.slot_combo.addItem(f"{slot.name}  —  {suffix}", slot.id)
    window.slot_combo.setCurrentIndex(window.slot_combo.findData(window.selected_slot_id))

    def select_slot(index):
        window.selected_slot_id = window.slot_combo.itemData(index)
        window.show_page("customize")

    window.slot_combo.currentIndexChanged.connect(select_slot)
    content.addWidget(window.slot_combo)
    slot = room.slot(window.selected_slot_id)
    placed = placements.get(slot.id)
    if placed:
        current_item = home.catalog[placed["furniture_id"]]
        content.addWidget(label(f"In this spot: {current_item.name}", "section", True))
        remove_button = button("Return to inventory", lambda: window.operate(
            lambda: home.remove(slot.id), "Furniture returned to your inventory."))
        if isinstance(current_item, Lamp):
            lamp_button = button("Turn light off" if placed["light_on"] else "Turn light on",
                                 lambda: window.operate(lambda: home.toggle_lamp(slot.id)))
            content.addLayout(row(remove_button, lamp_button))
        else:
            content.addWidget(remove_button)
        content.addWidget(label("Remove the current item before putting another one in this spot.", "muted", True))
    else:
        content.addWidget(label("This spot is ready for something of yours.", "muted", True))

    content.addWidget(label("YOUR FURNITURE", "eyebrow"))
    used = Counter(instance["furniture_id"] for instance in placements.values())
    window.furniture_list = QListWidget()
    window.furniture_list.setIconSize(QSize(46, 46))
    window.furniture_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    window.furniture_list.setWordWrap(True)
    window.furniture_list.setMinimumHeight(180)
    window.furniture_list.setMaximumHeight(260)
    first_available = None
    for furniture_id, count in home.inventory.items():
        item = home.catalog[furniture_id]
        available = count - used[furniture_id]
        compatible = item.fits(room.id, slot)
        room_compatible = not item.room_ids or room.id in item.room_ids
        if not room_compatible:
            detail = "Belongs to another room"
        elif not compatible:
            detail = "Choose a different spot"
        elif not available:
            detail = "All copies are already placed in this room"
        else:
            detail = f"{available} available here"
        entry = QListWidgetItem(f"{item.name}  ×{count}\n{_room_label(home, item)}\n{detail}")
        entry.setSizeHint(QSize(280, 88))
        entry.setData(Qt.ItemDataRole.UserRole, furniture_id)
        entry.setToolTip(item.description + "\n" + _room_label(home, item))
        pixmap = _sprite(window, furniture_id)
        if pixmap is not None and not pixmap.isNull():
            entry.setIcon(QIcon(pixmap))
        if not compatible or not available or placed:
            entry.setFlags(entry.flags() & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsSelectable)
        elif first_available is None:
            first_available = entry
        window.furniture_list.addItem(entry)
    content.addWidget(window.furniture_list)

    def place_selected():
        selected = window.furniture_list.currentItem()
        if selected is None:
            window.notify("Choose an available item and an empty compatible spot.")
            return
        furniture_id = selected.data(Qt.ItemDataRole.UserRole)
        window.operate(lambda: home.place(furniture_id, slot.id), "Furniture placed.")

    window.place_furniture_button = button("Place in this spot", place_selected, "primary")
    window.place_furniture_button.setEnabled(False)
    window.furniture_list.currentItemChanged.connect(
        lambda current, previous: window.place_furniture_button.setEnabled(
            current is not None and bool(current.flags() & Qt.ItemFlag.ItemIsEnabled)))
    if first_available is not None:
        window.furniture_list.setCurrentItem(first_available)
    content.addWidget(window.place_furniture_button)
    content.addWidget(label("The same owned piece can be used in each room. Two placements inside one room need two copies.", "muted", True))
    content.addWidget(button("Discover more furniture  →", lambda: window.show_page("rewards"), "ghost"))
    content.addStretch()


def _show_reward(window, item):
    """Show the reward after its inventory change has been saved."""
    from .window import button, label, row

    dialog = QDialog(window)
    dialog.setWindowTitle("Something new for your room")
    dialog.setMinimumWidth(390)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(28, 26, 28, 24)
    layout.setSpacing(16)
    layout.addWidget(label("A LITTLE REWARD FOR SHOWING UP", "eyebrow"))
    pixmap = _sprite(window, item.id)
    if pixmap is not None and not pixmap.isNull():
        picture = QLabel()
        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        picture.setPixmap(pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(picture)
    layout.addWidget(label(item.name, "dialogTitle", True))
    layout.addWidget(label(item.description, "muted", True))
    layout.addWidget(label(_room_label(window.home, item), "muted", True))
    layout.addWidget(label("Saved to your furniture collection.", "muted"))
    layout.addLayout(row(button("Keep for later", dialog.reject, "ghost"),
                         button("Arrange your room", dialog.accept, "primary")))
    if dialog.exec() == QDialog.DialogCode.Accepted:
        window.show_page("customize")


def build_rewards(window):
    """Show the daily check-in and reward controls."""
    from .window import button, duration, label, row

    home = window.home
    focus_minutes = window.service.focus_minutes_on(date.today())
    status = home.reward_status(focus_minutes)
    content = window.make_panel("Little things, earned", "Show up for your plans. Make this space your own.")
    content.addWidget(label(date.today().strftime("%A, %d %B").upper(), "eyebrow"))
    content.addWidget(label(f"{duration(focus_minutes)} / {duration(status['goal'])}", "title"))
    content.addWidget(label("Confirmed focus time today", "muted"))
    progress = QProgressBar()
    progress.setRange(0, status["goal"])
    progress.setValue(min(focus_minutes, status["goal"]))
    progress.setTextVisible(False)
    content.addWidget(progress)
    if status["remaining_minutes"]:
        content.addWidget(label(f"{duration(status['remaining_minutes'])} to today's goal. Finish a focus session and confirm its time to count it.", "muted", True))
    else:
        content.addWidget(label("Today's focus goal is reached.", "section"))

    window.check_in_button = button("Checked in today ✓" if status["checked_in"] else "Check in today",
                                    lambda: window.operate(home.check_in, "Checked in. Today's goal is saved."))
    window.check_in_button.setEnabled(not status["checked_in"])

    def claim_reward():
        result = []

        def draw():
            actual = window.service.focus_minutes_on(date.today())
            result.append(home.draw(actual))

        if window.operate(draw, "Your new furniture is saved."):
            _show_reward(window, result[0])

    window.draw_button = button("Today's draw claimed" if status["claimed"] else "Draw one piece of furniture",
                                claim_reward, "primary")
    window.draw_button.setEnabled(status["eligible"])
    content.addWidget(window.check_in_button)
    content.addWidget(window.draw_button)
    if status["claimed"]:
        claimed = home.catalog[status["reward_id"]]
        content.addWidget(label(f"Today's find: {claimed.name}", "section", True))
        content.addWidget(button("Arrange your room  →", lambda: window.show_page("customize"), "ghost"))
    elif not status["checked_in"]:
        content.addWidget(label("Check in and reach the focus goal to unlock today's draw. You can check in before or after focusing.", "muted", True))
    content.addWidget(label("One free draw per local calendar day. Only saved Focus sessions count; manually entered time does not unlock a reward.", "muted", True))

    content.addWidget(label("YOUR DAILY RHYTHM", "eyebrow"))
    goal = QSpinBox()
    goal.setRange(1, 1440)
    goal.setSuffix(" min")
    goal.setValue(status["next_goal"])
    window.daily_goal_spin = goal

    def save_goal():
        goal.interpretText()
        minutes = goal.value()
        message = "Goal saved for your next check-in." if status["checked_in"] else "Daily focus goal saved."
        window.operate(lambda: home.set_daily_goal(minutes), message)

    content.addLayout(row(goal, button("Save goal", save_goal)))
    if status["checked_in"]:
        content.addWidget(label(f"Today's goal is locked at {duration(status['goal'])}. Changes apply to your next day's check-in.", "muted", True))
    else:
        content.addWidget(label("Your goal is fixed when you check in. Later changes do not lower or raise that day's requirement.", "muted", True))

    remaining = [item for item in home.catalog.values() if item.id not in home.inventory]
    content.addWidget(label(f"STILL TO DISCOVER  ·  {len(remaining)}" if remaining else "YOUR COLLECTION IS COMPLETE", "eyebrow"))
    content.addWidget(label("Every room's special pieces are in the draw. Unowned items have equal chances; after collecting them all, draws give extra copies.", "muted", True))
    catalogue = QListWidget()
    catalogue.setIconSize(QSize(36, 36))
    catalogue.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    catalogue.setWordWrap(True)
    catalogue.setMinimumHeight(160)
    catalogue.setMaximumHeight(240)
    catalogue.setSelectionMode(QListWidget.SelectionMode.NoSelection)
    for item in remaining or home.catalog.values():
        entry = QListWidgetItem(f"{item.name}\n{_room_label(home, item)}")
        entry.setToolTip(item.description)
        pixmap = _sprite(window, item.id)
        if pixmap is not None and not pixmap.isNull():
            entry.setIcon(QIcon(pixmap))
        catalogue.addItem(entry)
    content.addWidget(catalogue)
    content.addStretch()
