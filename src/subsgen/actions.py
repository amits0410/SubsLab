"""Shared key bindings used by both registration and the shortcut reference."""
from dataclasses import dataclass
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QLabel, QMenu, QSizePolicy, QToolButton, QWidget

from .branding import APP_NAME
from .ui_widgets import FixedToolBar


@dataclass(frozen=True)
class ShortcutSpec:
    keys: str
    label: str
    callback: str
    typing_sensitive: bool = True


def primary(keys: str) -> str:
    # Qt maps Ctrl to Command on macOS; Meta represents the physical Control key.
    return "Ctrl+" + keys


SHORTCUTS = (
    ShortcutSpec("Space", "Play or pause", "toggle_playback"),
    ShortcutSpec("K", "Play or pause", "toggle_playback"),
    ShortcutSpec("J", "Seek backward 5 seconds", "seek_back"),
    ShortcutSpec("L", "Seek forward 5 seconds", "seek_forward"),
    ShortcutSpec(primary("Left"), "Previous cue", "previous_cue"),
    ShortcutSpec(primary("Right"), "Next cue", "next_cue"),
    ShortcutSpec("Return", "Play active or selected cue", "_play_context_cue"),
    ShortcutSpec("Shift+Return", "Play cue with 0.5 seconds of context", "_play_context_with_handles"),
    ShortcutSpec("S", "Split at playhead", "_split_selected"),
    ShortcutSpec("Delete", "Delete selected cue", "_delete_selected_confirmed"),
    ShortcutSpec("I", "Set cue start to playhead", "set_start"),
    ShortcutSpec("O", "Set cue end to playhead", "set_end"),
    ShortcutSpec("Alt+Left", "Nudge start −100 ms", "start_back"),
    ShortcutSpec("Alt+Right", "Nudge start +100 ms", "start_forward"),
    ShortcutSpec("Alt+Shift+Left", "Nudge end −100 ms", "end_back"),
    ShortcutSpec("Alt+Shift+Right", "Nudge end +100 ms", "end_forward"),
    ShortcutSpec("F7", "Previous warning", "previous_warning", False),
    ShortcutSpec("F8", "Next warning", "next_warning", False),
)


def native_shortcut(keys: str) -> str:
    return QKeySequence(keys).toString(QKeySequence.SequenceFormat.NativeText)


def build_actions(window):
    """One QAction per command, shared across menus, toolbar, and reference."""
    self = window
    self.actions = {}

    def action(key, label, callback, shortcut=None):
        item = QAction(label, self)
        if isinstance(shortcut, QKeySequence.StandardKey):
            item.setShortcuts(shortcut)
        elif shortcut is not None:
            item.setShortcut(QKeySequence(shortcut))
        item.triggered.connect(lambda _checked=False: callback())
        self.actions[key] = item
        return item

    open_media = action("open", "Open media…", self.open_media, QKeySequence.StandardKey.Open)
    import_srt = action("import", "Import SRT…", self.open_srt, primary("Shift+O"))
    save = action("save", "Save SRT", self.save_document, QKeySequence.StandardKey.Save)
    save_copy = action("save_copy", "Save as copy…", lambda: self.save_document(force_copy=True), QKeySequence.StandardKey.SaveAs)
    export = action("export", "Export VTT / ASS…", self.export_additional_format)
    undo = action("undo", "Undo", self.undo_action, QKeySequence.StandardKey.Undo)
    redo = action("redo", "Redo", self.redo_action, QKeySequence.StandardKey.Redo)
    find = action("find", "Find / replace…", self.open_find_replace, QKeySequence.StandardKey.Find)
    reflow = action("reflow", "Reflow subtitles", self.reflow_current_subtitles)
    readability = action("readability", "Readability settings…", self.open_readability_settings, primary(","))
    models = action("models", "Local AI models…", self.open_models)
    report = action("quality", "Quality report…", self.open_quality_report)
    shortcuts = action("shortcuts", "Keyboard shortcuts…", self.show_shortcuts)
    quit_action = action("quit", "Quit " + APP_NAME, self.close, QKeySequence.StandardKey.Quit)
    quit_action.setMenuRole(QAction.MenuRole.QuitRole)
    menu_bar = self.menuBar()
    menu_bar.setNativeMenuBar(True)
    for title, items in (
        ("&File", [open_media, import_srt, None, save, save_copy, export, None, quit_action]),
        ("&Edit", [undo, redo, None, find]),
        ("&Subtitles", [reflow, readability, report]),
        ("&Playback", []), ("&Tools", [models]), ("&Help", [shortcuts]),
    ):
        menu = menu_bar.addMenu(title)
        if title == "&Playback":
            self.playback_menu = menu
        for item in items:
            menu.addSeparator() if item is None else menu.addAction(item)
    self.playback_menu.addAction(action("play", "Play / pause", self.toggle_playback))
    self.playback_menu.addAction(action("play_cue", "Play active or selected cue", self._play_context_cue))
    self.playback_menu.addAction(action("loop", "Toggle cue loop", lambda: self.loop_button.toggle()))

    toolbar = FixedToolBar(APP_NAME)
    toolbar.setObjectName("mainToolbar")
    toolbar.setMovable(False)
    toolbar.setFloatable(False)
    toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
    toolbar.toggleViewAction().setVisible(False)
    toolbar.toggleViewAction().setEnabled(False)
    self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
    self.addToolBar(toolbar)
    brand = QLabel(APP_NAME)
    brand.setObjectName("brand")
    toolbar.addWidget(brand)
    toolbar.addActions([open_media, import_srt])
    toolbar.addSeparator()
    toolbar.addActions([undo, redo])
    self.undo_button = toolbar.widgetForAction(undo)
    self.redo_button = toolbar.widgetForAction(redo)
    self.undo_fix_button = self.undo_button
    stretch = QWidget()
    stretch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    toolbar.addWidget(stretch)
    tools_button = QToolButton()
    tools_button.setText("Tools")
    tools_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    tools_menu = QMenu(tools_button)
    tools_menu.addActions([models, readability, reflow, find, report, shortcuts])
    tools_button.setMenu(tools_menu)
    toolbar.addWidget(tools_button)
    toolbar.addAction(save)
    export_button = QToolButton()
    export_button.setText("Export ▾")
    export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    export_menu = QMenu(export_button)
    export_menu.addActions([save_copy, export])
    export_button.setMenu(export_menu)
    toolbar.addWidget(export_button)
