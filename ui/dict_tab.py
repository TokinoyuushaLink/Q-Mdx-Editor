import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter, QMessageBox, QInputDialog,
)
from PySide6.QtCore import Signal, Qt, QTimer, QThread

from bg import bg_spawn as _spawn
from db import DictDB
from ui.entry_list import EntryListPanel
from ui.editor_panel import EditorPanel
from ui.preview_panel import PreviewPanel


def _init_db(path: str):
    """Runs in background: open DB + WAL setup + fetch word list + CSS."""
    db = DictDB(path)
    words = db.all_words()
    css = db.get_meta("css")
    return db, words, css


class DictTab(QWidget):
    count_changed = Signal(int)

    def __init__(self, db_path: str, theme: str = "light",
                 autosave_ms: int = 800, autosave_enabled: bool = False,
                 tab_width: int = 4,
                 splitter_mode: str = "auto",
                 editor_font_family: str = "Consolas",
                 editor_font_size: float = 10.0,
                 html_trigger: bool = True,
                 preview_font_family: str = "",
                 preview_font_size: float = 14.0,
                 parent=None):
        super().__init__(parent)
        self._db_path       = db_path
        self._db: DictDB | None = None
        self._init_thread: QThread | None = None
        self._splitter_mode = splitter_mode
        self._setup_ui(theme, autosave_ms, autosave_enabled, tab_width,
                       preview_font_family, preview_font_size)
        self._editor.set_editor_font(editor_font_family, editor_font_size)
        self._editor.set_html_trigger(html_trigger)
        self._list_panel.set_loading(True)
        # Defer so the tab widget paints before we start the DB thread
        QTimer.singleShot(0, self._start_async_init)

    def _start_async_init(self):
        print(f"[tab] async init start: {Path(self._db_path).name}", file=sys.stderr, flush=True)
        self._init_thread = _spawn(
            lambda: _init_db(self._db_path),
            self._on_init_done,
        )

    def _on_init_done(self, result):
        import time
        self._init_thread = None
        db, words, css = result
        self._db = db

        t = time.perf_counter()
        self._preview.set_dict_css(css)
        print(f"[tab] set_dict_css: {(time.perf_counter()-t)*1000:.1f}ms", file=sys.stderr, flush=True)

        t = time.perf_counter()
        self._list_panel.set_loading(False)
        print(f"[tab] set_loading: {(time.perf_counter()-t)*1000:.1f}ms", file=sys.stderr, flush=True)

        t = time.perf_counter()
        self._list_panel.load_words(words)
        print(f"[tab] load_words returned: {(time.perf_counter()-t)*1000:.1f}ms", file=sys.stderr, flush=True)

        t0_after = time.perf_counter()
        def _tick0():
            print(f"[tab] event-loop tick0 (after load_words): {(time.perf_counter()-t0_after)*1000:.1f}ms", file=sys.stderr, flush=True)
        def _tick1():
            print(f"[tab] event-loop tick1 (after load_words): {(time.perf_counter()-t0_after)*1000:.1f}ms", file=sys.stderr, flush=True)
        QTimer.singleShot(0,   _tick0)
        QTimer.singleShot(200, _tick1)

        t = time.perf_counter()
        self.count_changed.emit(len(words))
        print(f"[tab] count_changed: {(time.perf_counter()-t)*1000:.1f}ms", file=sys.stderr, flush=True)

        print(f"[tab] init done: {len(words)} words", file=sys.stderr, flush=True)

    # ── UI ─────────────────────────────────────────────────────────────────────

    # Width threshold (px) below which editor+preview stack vertically.
    _BREAKPOINT = 900

    def _setup_ui(self, theme: str, autosave_ms: int, autosave_enabled: bool, tab_width: int,
                  preview_font_family: str = "", preview_font_size: float = 14.0):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Outer splitter: word list | [editor + preview]
        self._outer_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._outer_splitter.setChildrenCollapsible(False)

        # Inner splitter: editor | preview  (orientation adapts to window width)
        self._inner_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._inner_splitter.setChildrenCollapsible(False)

        self._list_panel = EntryListPanel()
        self._editor     = EditorPanel(autosave_ms=autosave_ms,
                                       autosave_enabled=autosave_enabled,
                                       tab_width=tab_width)
        self._preview    = PreviewPanel(theme=theme,
                                        font_family=preview_font_family,
                                        font_size=preview_font_size)

        self._inner_splitter.addWidget(self._editor)
        self._inner_splitter.addWidget(self._preview)
        self._inner_splitter.setSizes([450, 450])
        self._inner_splitter.setStretchFactor(0, 1)
        self._inner_splitter.setStretchFactor(1, 1)

        self._outer_splitter.addWidget(self._list_panel)
        self._outer_splitter.addWidget(self._inner_splitter)
        self._outer_splitter.setSizes([200, 900])
        self._outer_splitter.setStretchFactor(0, 0)
        self._outer_splitter.setStretchFactor(1, 1)

        layout.addWidget(self._outer_splitter)

        self._list_panel.word_selected.connect(self._on_word_selected)
        self._list_panel.word_added.connect(self._on_word_added)
        self._list_panel.word_added_inline.connect(self._on_word_added_inline)
        self._list_panel.words_deleted.connect(self._on_words_deleted)
        self._list_panel.word_renamed.connect(self._on_list_word_renamed)
        self._list_panel.selection_changed.connect(self._on_list_selection_changed)

        self._editor.content_changed.connect(self._preview.show_entry)
        self._editor.save_requested.connect(self._on_save_entry)
        self._editor.orphan_save_requested.connect(self._on_orphan_save_requested)

        self._preview.entry_link_clicked.connect(self._list_panel.select_word)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._splitter_mode == "auto":
            want_v = event.size().width() < self._BREAKPOINT
            self._set_inner_orient(
                Qt.Orientation.Vertical if want_v else Qt.Orientation.Horizontal
            )

    def set_splitter_mode(self, mode: str):
        """mode: 'auto' | 'horizontal' | 'vertical'"""
        self._splitter_mode = mode
        if mode == "horizontal":
            self._set_inner_orient(Qt.Orientation.Horizontal)
        elif mode == "vertical":
            self._set_inner_orient(Qt.Orientation.Vertical)
        else:  # auto: apply based on current width immediately
            want_v = self.width() < self._BREAKPOINT
            self._set_inner_orient(
                Qt.Orientation.Vertical if want_v else Qt.Orientation.Horizontal
            )

    def _set_inner_orient(self, orient: Qt.Orientation):
        if self._inner_splitter.orientation() == orient:
            return
        self._inner_splitter.setOrientation(orient)
        total = (self._inner_splitter.height() if orient == Qt.Orientation.Vertical
                 else self._inner_splitter.width())
        half  = max(1, total // 2)
        self._inner_splitter.setSizes([half, half])

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def db_path(self) -> str:
        return self._db_path

    @property
    def dict_name(self) -> str:
        return Path(self._db_path).stem

    @property
    def db(self) -> DictDB | None:
        return self._db

    def entry_count(self) -> int:
        return self._db.word_count() if self._db else 0

    def set_theme(self, theme: str):
        self._preview.set_theme(theme)

    def set_autosave_ms(self, ms: int):
        self._editor.set_autosave_ms(ms)

    def set_autosave_enabled(self, enabled: bool):
        self._editor.set_autosave_enabled(enabled)

    def set_tab_width(self, width: int):
        self._editor.set_tab_width(width)

    def set_editor_font(self, family: str, size: float):
        self._editor.set_editor_font(family, size)

    def set_html_trigger(self, enabled: bool):
        self._editor.set_html_trigger(enabled)

    def set_preview_font(self, family: str, size: float):
        self._preview.set_preview_font(family, size)

    def set_editor_mode(self, mode: str):
        self._editor.set_mode(mode)

    def close_db(self):
        self._editor.save_now()
        if self._db:
            self._db.close()
            self._db = None

    def refresh(self):
        """Reload entry list; clear editor/preview if current entry was removed."""
        if not self._db:
            return
        current = self._list_panel.current_word()
        self._refresh_list()
        if current is None or self._db.get_entry(current) is None:
            self._editor.clear()
            self._preview.clear()

    # ── Dict / CSS helpers ─────────────────────────────────────────────────────

    def edit_css(self):
        if not self._db:
            return
        from PySide6.QtWidgets import QInputDialog
        current = self._db.get_meta("css") or ""
        text, ok = QInputDialog.getMultiLineText(
            self, "编辑词典 CSS", "CSS:", current
        )
        if ok:
            if text.strip():
                self._db.set_meta("css", text.strip())
            else:
                self._db.delete_meta("css")
            self._preview.set_dict_css(text.strip() or None)

    def show_stats(self):
        if not self._db:
            return
        count = self._db.word_count()
        QMessageBox.information(
            self, "词典统计",
            f"词典: {self.dict_name}\n"
            f"词条数: {count}\n"
            f"文件: {self._db_path}"
        )

    # ── Entry CRUD ─────────────────────────────────────────────────────────────

    def _refresh_list(self):
        if not self._db:
            return
        words = self._db.all_words()
        self._list_panel.load_words(words)
        self.count_changed.emit(len(words))

    def _on_word_selected(self, word: str):
        if not self._db:
            return
        # Orphan dirty: ask before switching away
        if self._editor.current_word() == "" and self._editor.is_dirty():
            orphan_html = self._editor.current_html()
            if orphan_html.strip():
                reply = QMessageBox.question(
                    self, "保存草稿",
                    "当前草稿未关联任何词条，是否保存到当前词典？",
                    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard,
                )
                if reply == QMessageBox.StandardButton.Save:
                    self._on_orphan_save_requested(orphan_html)
        elif self._editor.is_dirty() and self._editor.current_word():
            self._editor.save_now()
        html = self._db.get_entry(word) or ""
        self._editor.load_entry(word, html)
        self._preview.show_entry(word, html)

    def _on_word_added(self, word: str):
        if not self._db:
            return
        if self._db.get_entry(word) is not None:
            QMessageBox.information(
                self, "提示", f"「{word}」已存在，将跳转到该词条。"
            )
        else:
            self._db.set_entry(word, "")
        self._refresh_list()
        self._list_panel.select_word(word)

    def _on_word_added_inline(self, word: str):
        if not self._db:
            return
        self._db.set_entry(word, "")
        self._refresh_list()
        self._list_panel.select_word(word)
        # Start inline rename so user can change the placeholder name
        QTimer.singleShot(50, lambda: self._list_panel.start_editing_word(word))

    def _on_words_deleted(self, words: list):
        if not self._db:
            return
        for word in words:
            self._db.delete_entry(word)
        self._editor.clear()
        self._preview.clear()
        self._refresh_list()

    def _on_list_selection_changed(self, count: int):
        multi = count > 1
        if multi and self._editor.is_dirty() and self._editor.current_word():
            self._editor.save_now()
        self._editor.setEnabled(not multi)
        self._preview.setEnabled(not multi)

    def _on_save_entry(self, word: str, html: str):
        if not self._db:
            return
        self._db.set_entry(word, html)

    def _on_orphan_save_requested(self, html: str):
        if not self._db:
            return
        name, ok = QInputDialog.getText(self, "保存草稿", "词条名称:")
        if ok and name.strip():
            word = name.strip()
            if self._db.get_entry(word) is not None:
                QMessageBox.information(self, "提示", f"「{word}」已存在，内容已合并保存。")
            self._db.set_entry(word, html)
            self._refresh_list()
            self._editor.load_entry(word, html)
            self._list_panel.select_word(word)

    def _on_list_word_renamed(self, old: str, new: str):
        if not self._db:
            return
        if self._db.get_entry(new) is not None:
            QMessageBox.warning(self, "重命名失败", f"词条「{new}」已存在。")
            self._refresh_list()
            self._list_panel.select_word(old)
            return
        html = self._editor.current_html()
        self._db.rename_entry(old, new, html)
        self._editor.load_entry(new, html)
        self._refresh_list()
        self._list_panel.select_word(new)
