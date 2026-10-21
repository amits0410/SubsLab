"""The shared studio palette; keep contrast and widget states in one place."""
from PySide6.QtGui import QColor, QFontDatabase, QPalette

BACKGROUND = "#11171e"
SURFACE = "#19222c"
ELEVATED = "#222e3a"
TEXT = "#e8eef4"
MUTED = "#9aabbc"
ACCENT = "#41c9b7"
SELECTED = "#e7bc54"
ERROR = "#ff7b84"

STYLE = """
QWidget { color: #e8eef4; font-size: 13px; }
QMainWindow, QDialog { background: #11171e; }
QToolBar { background: #19222c; border: 0; border-bottom: 1px solid #2b3948; spacing: 6px; padding: 8px; }
QToolBar QLabel#brand { font-size: 20px; font-weight: 700; color: #41c9b7; padding: 0 18px 0 6px; }
QMenuBar, QMenu { background: #19222c; }
QMenuBar::item, QMenu::item { padding: 7px 14px; }
QMenuBar::item:selected, QMenu::item:selected { background: #2b3f4c; }
QLabel#sectionTitle { font-size: 16px; font-weight: 600; }
QLabel#muted, QLabel#jobDetails { color: #9aabbc; }
QLabel#emptyTitle { font-size: 23px; font-weight: 600; }
QLabel#badge { background: #253643; color: #9edbd2; border-radius: 5px; padding: 3px 7px; }
QFrame#panel { background: #19222c; border: 1px solid #2b3948; border-radius: 10px; }
QPushButton, QToolButton { background: #24313e; border: 1px solid #354555; border-radius: 6px; padding: 6px 10px; min-height: 18px; }
QPushButton:hover, QToolButton:hover { background: #2e4250; border-color: #608092; }
QPushButton:pressed, QToolButton:pressed { background: #152c34; }
QPushButton:checked, QToolButton:checked { color: #a1f4e7; background: #17413f; border-color: #41c9b7; }
QPushButton:disabled, QToolButton:disabled { color: #66798b; background: #1a242e; border-color: #2b3948; }
QPushButton#primary { color: #0c2525; background: #41c9b7; font-weight: 600; border-color: #41c9b7; }
QPushButton#primary:hover { background: #68dfce; }
QPushButton#primary:disabled { color: #627e7b; background: #25403f; border-color: #25403f; }
QPushButton#danger { color: #ffadb3; }
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #101a24; border: 1px solid #344555; border-radius: 5px; padding: 5px 7px; selection-background-color: #28675f; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #41c9b7; }
QPlainTextEdit { font-size: 15px; padding: 8px; }
QComboBox QAbstractItemView, QListWidget { background: #19222c; selection-background-color: #244944; }
QListWidget { border: 1px solid #344555; border-radius: 7px; padding: 5px; }
QListWidget::item { padding: 10px; }
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: #11171e; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3b5060; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { border: 1px solid #344555; border-radius: 5px; background: #101a24; text-align: center; min-height: 20px; }
QProgressBar::chunk { background: #237c73; border-radius: 4px; }
QSlider::groove:horizontal { height: 5px; background: #344555; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #41c9b7; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; background: #e8eef4; margin: -4px 0; border-radius: 6px; }
QSplitter::handle { background: #263541; width: 5px; }
QStatusBar { background: #19222c; color: #9aabbc; }
QToolTip { background: #24313e; color: #e8eef4; border: 1px solid #4c6578; padding: 5px; }
"""


def apply_theme(application):
    application.setStyle("Fusion")
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSize(10)
    application.setFont(font)
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, BACKGROUND), (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Base, "#101a24"), (QPalette.ColorRole.AlternateBase, SURFACE),
        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, ELEVATED),
        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, "#28675f"),
        (QPalette.ColorRole.HighlightedText, TEXT), (QPalette.ColorRole.ToolTipBase, ELEVATED),
        (QPalette.ColorRole.ToolTipText, TEXT),
    ):
        palette.setColor(role, QColor(color))
    application.setPalette(palette)
    application.setStyleSheet(STYLE)
