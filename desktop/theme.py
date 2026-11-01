"""Shared day and night styles for the desktop widgets."""

STYLE = """
QWidget { color: #2e3935; font-family: 'Avenir Next', Arial; font-size: 13px; }
QMainWindow, QDialog { background: #f4f1e9; }
QLabel { background: transparent; }
QLabel#muted { color: #73796f; }
QLabel#eyebrow { color: #7c8575; font-size: 10px; font-weight: 600; letter-spacing: 1.6px; }
QLabel#title { font-family: Georgia, serif; font-size: 27px; color: #303c36; }
QLabel#dialogTitle { font-family: Georgia, serif; font-size: 24px; color: #303c36; }
QLabel#section { font-size: 14px; font-weight: 600; color: #39473e; }
QLabel#error { color: #a25543; }
QFrame#panel { background: #f8f6ef; border: 1px solid #deded2; border-radius: 8px; }
QFrame#card { background: #f4f1e9; border: 1px solid #deded2; border-radius: 6px; }
QFrame#subcard { background: #eeeee4; border: 1px solid #e0e1d5; border-radius: 6px; }
QFrame#nav { background: transparent; border: none; border-radius: 0; }
QPushButton { background: #efefe5; border: 1px solid #d5d9cd; border-radius: 5px; padding: 8px 12px; color: #3e4b42; }
QPushButton:hover { background: #e4e8dc; border-color: #a4b09c; }
QPushButton:pressed { background: #d7dfcf; border-color: #82927b; }
QPushButton:focus { border-color: #81927a; }
QPushButton:disabled { color: #a8ada1; background: #eeeee7; border-color: #e1e3d8; }
QPushButton#primary { color: #faf9f3; background: #718479; border-color: #718479; font-weight: 600; }
QPushButton#primary:hover { background: #62786a; border-color: #62786a; }
QPushButton#primary:pressed { background: #526d5b; border-color: #526d5b; }
QPushButton#primary:disabled { background: #b8c2b4; color: #f3f4ec; border-color: #b8c2b4; }
QPushButton#ghost { background: transparent; border-color: transparent; color: #64725f; }
QPushButton#ghost:hover { background: #e9eddf; color: #344b3c; }
QPushButton#danger { color: #9c5e4c; background: #f3eae2; border-color: #dfc7ba; }
QPushButton#navButton { background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 12px 20px 10px; color: #7a8275; }
QPushButton#navButton:hover { color: #3f5746; background: #eeefe5; }
QPushButton#navButton:checked { background: transparent; color: #385441; border-bottom: 2px solid #718479; font-weight: 600; }
QPushButton#recordMode { background: transparent; border: none; border-radius: 5px; padding: 5px 12px; color: #7a8275; }
QPushButton#recordMode:checked { color: #385441; background: #e9eddf; font-weight: 600; }
QWidget#statsMusic { border-top: 1px solid #dfe3d7; }
QPushButton::menu-indicator { image: none; width: 0; }
QMenu { background: #f8f6ef; color: #3e4b42; border: 1px solid #d7ddcd; padding: 6px; }
QMenu::item { background: transparent; padding: 9px 24px 9px 12px; border-radius: 3px; }
QMenu::item:selected { background: #e5eadc; color: #324b39; }
QMenu::item:disabled { color: #a0a899; }
QMenu::separator { height: 1px; background: #dfe3d5; margin: 5px 8px; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDateEdit, QTimeEdit, QComboBox {
 background: #faf9f4; color: #344136; border: 1px solid #d7dbcd; border-radius: 5px; padding: 8px;
 selection-background-color: #ccd8c7; selection-color: #293c2e; min-height: 19px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus { border-color: #8b9c81; background: #fffef9; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
 color: #263b2e; border: 2px solid #71866b; padding: 7px;
}
QComboBox QAbstractItemView { background: #faf9f3; color: #344136; border: 1px solid #d7dbcd; selection-background-color: #dce5d5; selection-color: #2d4434; }
QComboBox::drop-down { border: 0; width: 24px; }
QSpinBox::up-button, QDateEdit::up-button { width: 18px; }
QTreeWidget, QListWidget { background: #f7f7ef; border: 1px solid #dfe2d6; border-radius: 5px; outline: 0; alternate-background-color: #efefe6; }
QTreeWidget::item, QListWidget::item { padding: 8px 4px; border-bottom: 1px solid #e7e9df; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #dfe7d7; color: #2f4836; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #e9eedf; }
QHeaderView::section { background: #eef0e5; color: #75816d; border: 0; padding: 7px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }
QScrollBar::handle:vertical { background: #bcc6b4; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #aebaa4; border-radius: 3px; background: #faf9f3; }
QCheckBox::indicator:checked { background: #718479; border-color: #718479; }
QCheckBox::indicator:hover { border-color: #718479; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: transparent; color: #7b8672; padding: 10px 12px; border-bottom: 2px solid #e2e5d8; }
QTabBar::tab:selected { color: #3f5746; border-bottom: 2px solid #718479; }
QProgressBar { border: none; background: #e2e6d8; border-radius: 3px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #899b7b; border-radius: 3px; }
QSlider::groove:horizontal { height: 3px; background: #dce1d2; border-radius: 1px; }
QSlider::sub-page:horizontal { background: #718479; border-radius: 1px; }
QSlider::handle:horizontal { background: #f8f7ef; border: 1px solid #899b7b; width: 12px; height: 12px; margin: -5px 0; border-radius: 6px; }
QSlider::handle:horizontal:hover { background: #e1e8d8; border-color: #5d775e; }
QSlider::handle:horizontal:disabled { background: #efefe6; border-color: #c0c7b9; }
QSlider::sub-page:horizontal:disabled { background: #c0c7b9; }
QToolTip { background: #f8f7ef; color: #455440; border: 1px solid #c8d1be; padding: 7px; }
"""

# Preserve the same layout and interaction states while adapting paper/ink
# contrast to the room's night palette.
NIGHT_STYLE = STYLE + """
QWidget { color: #dde2d7; }
QMainWindow, QDialog { background: #1f2831; }
QLabel#muted { color: #a2ad9e; }
QLabel#eyebrow { color: #a5b496; }
QLabel#title, QLabel#dialogTitle, QLabel#section { color: #e0e5d9; }
QLabel#error { color: #e4aa91; }
QFrame#panel { background: #29343d; border-color: #455247; }
QFrame#card, QFrame#subcard { background: #303c42; border-color: #455247; }
QPushButton { background: #34413f; border-color: #52604f; color: #dce3d4; }
QPushButton:hover { background: #405246; border-color: #899c7c; }
QPushButton:pressed { background: #4e6250; }
QPushButton:disabled { color: #728074; background: #2d383a; border-color: #3e4c40; }
QPushButton#primary { background: #9aaf8d; color: #1e2d27; border-color: #9aaf8d; }
QPushButton#primary:hover { background: #b2c2a0; border-color: #b2c2a0; }
QPushButton#primary:pressed { background: #859d79; }
QPushButton#primary:disabled { background: #52654e; color: #929e86; border-color: #52654e; }
QPushButton#ghost { background: transparent; border-color: transparent; color: #b3bfaa; }
QPushButton#ghost:hover { background: #34423c; color: #e2e9d9; }
QPushButton#danger { color: #e0ab97; background: #493b37; border-color: #766052; }
QPushButton#navButton { background: transparent; color: #a2ad9e; border: none; border-bottom: 2px solid transparent; }
QPushButton#navButton:hover { background: #2d3a34; color: #dae5cc; }
QPushButton#navButton:checked { color: #d5e3c3; background: transparent; border-bottom: 2px solid #a6b88e; }
QPushButton#recordMode { background: transparent; color: #a2ad9e; border: none; }
QPushButton#recordMode:checked { color: #d5e3c3; background: #35453f; }
QWidget#statsMusic { border-top-color: #465448; }
QMenu { background: #29343d; color: #dde2d7; border-color: #52604f; }
QMenu::item:selected { background: #42523f; color: #e5ecd9; }
QMenu::separator { background: #455247; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDateEdit, QTimeEdit, QComboBox {
 background: #202b31; color: #dce4d5; border-color: #4b5a4a;
 selection-background-color: #4e6448; selection-color: #ecf2e3;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus { background: #26332f; border-color: #9aaf84; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus { color: #f0f4e8; border-color: #b3c99d; }
QComboBox QAbstractItemView { background: #29343a; color: #dce4d5; border-color: #4b5a4a; selection-background-color: #4b6044; selection-color: #eff4e5; }
QTreeWidget, QListWidget { background: #263236; border-color: #455447; alternate-background-color: #2d3a39; }
QTreeWidget::item, QListWidget::item { border-bottom-color: #3c4b40; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #475d43; color: #e9f0de; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #374b3d; }
QHeaderView::section { background: #34413b; color: #b4c2a8; }
QScrollBar::handle:vertical { background: #596d53; }
QCheckBox::indicator { background: #23312e; border-color: #819576; }
QCheckBox::indicator:checked { background: #a8bc92; border-color: #a8bc92; }
QTabBar::tab { color: #aab79f; border-bottom-color: #465442; }
QTabBar::tab:selected { color: #d3e2be; border-bottom-color: #a2b887; }
QProgressBar { background: #41513f; }
QProgressBar::chunk { background: #a2b68c; }
QSlider::groove:horizontal { background: #465641; }
QSlider::sub-page:horizontal { background: #a8bd92; }
QSlider::handle:horizontal { background: #d3dfc4; border-color: #91a67c; }
QSlider::handle:horizontal:disabled { background: #3e4b3c; border-color: #65775c; }
QToolTip { background: #29383a; color: #e0e8d7; border-color: #778e66; }
"""
