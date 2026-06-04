import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit,
    QListView, QPushButton, QMessageBox,
    QAbstractItemView,
)
from PySide6.QtCore import (
    Signal, Qt, QEvent, QTimer, QThread,
    QAbstractListModel, QModelIndex,
)
from PySide6.QtGui import QFont

from bg import bg_spawn as _spawn


# ── Virtual word model ─────────────────────────────────────────────────────────

class _WordModel(QAbstractListModel):
    """Holds all words in a plain Python list; view is virtual (no item objects)."""
    renamed = Signal(str, str)   # (old, new) — emitted from inline edit

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all: list[str] = []
        self._display: list[str] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._display)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._display):
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._display[index.row()]
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        old = self._display[index.row()]
        new = str(value).strip()
        if not new:
            return False
        if old != new:
            self._display[index.row()] = new
            self.dataChanged.emit(index, index,
                                  [Qt.ItemDataRole.EditRole, Qt.ItemDataRole.DisplayRole])
            self.renamed.emit(old, new)
        return True

    def flags(self, index) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (Qt.ItemFlag.ItemIsEnabled |
                Qt.ItemFlag.ItemIsSelectable |
                Qt.ItemFlag.ItemIsEditable)

    def set_words(self, words: list[str], filter_q: str = ""):
        import time
        t = time.perf_counter()
        self.beginResetModel()
        print(f"[model] beginResetModel: {(time.perf_counter()-t)*1000:.1f}ms", file=sys.stderr, flush=True)
        t = time.perf_counter()
        self._all = words
        self._display = (
            [w for w in words if w.lower().startswith(filter_q)]
            if filter_q else words
        )
        print(f"[model] data assign: {(time.perf_counter()-t)*1000:.1f}ms", file=sys.stderr, flush=True)
        t = time.perf_counter()
        self.endResetModel()
        print(f"[model] endResetModel: {(time.perf_counter()-t)*1000:.1f}ms", file=sys.stderr, flush=True)

    def apply_filter(self, filtered: list[str]):
        """Apply a pre-computed filtered list (called from async filter callback)."""
        self.beginResetModel()
        self._display = filtered
        self.endResetModel()

    def row_of(self, word: str) -> int:
        try:
            return self._display.index(word)
        except ValueError:
            return -1


# ── Entry list panel ───────────────────────────────────────────────────────────

class EntryListPanel(QWidget):
    word_selected      = Signal(str)
    word_added         = Signal(str)
    word_added_inline  = Signal(str)        # new entry created inline (no dialog)
    words_deleted      = Signal(list)       # list[str] — one or many
    word_renamed       = Signal(str, str)   # (old, new)
    selection_changed  = Signal(int)        # count of selected items

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending_q: str = ""
        self._running_q: str | None = None
        self._filter_thread: QThread | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._add_btn = QPushButton("＋ 新建词条")
        self._add_btn.setToolTip("新建词条（Ctrl+Shift+N）")
        self._add_btn.clicked.connect(self._on_add)
        layout.addWidget(self._add_btn)

        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索词条…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        self._model = _WordModel()
        self._model.renamed.connect(self.word_renamed)

        self._list = QListView()
        self._list.setFont(QFont("Segoe UI", 10))
        self._list.setUniformItemSizes(True)
        self._list.setLayoutMode(QListView.LayoutMode.Batched)
        self._list.setBatchSize(300)
        self._list.setModel(self._model)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._list.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._list.installEventFilter(self)
        layout.addWidget(self._list)

        self._filter_debounce = QTimer(self)
        self._filter_debounce.setSingleShot(True)
        self._filter_debounce.setInterval(150)
        self._filter_debounce.timeout.connect(self._run_filter)

    # ── Public ─────────────────────────────────────────────────────────────────

    def load_words(self, words: list[str]):
        """Replace displayed word list; re-applies any active search filter."""
        q = self._search.text().strip().lower()
        self._model.set_words(words, q)
        print(f"[list] load_words: {len(words)} total, q={repr(q)}, display={self._model.rowCount()}", file=sys.stderr, flush=True)

    def set_loading(self, loading: bool):
        """Show/hide loading state — disables interaction while DB is initialising."""
        self._add_btn.setEnabled(not loading)
        if loading:
            self._search.setEnabled(False)
            self._search.setPlaceholderText("加载中…")
        else:
            self._search.setEnabled(True)
            self._search.setPlaceholderText("搜索词条…")

    def select_word(self, word: str):
        row = self._model.row_of(word)
        if row >= 0:
            idx = self._model.index(row)
            self._list.setCurrentIndex(idx)
            self._list.scrollTo(idx)

    def current_word(self) -> str | None:
        idx = self._list.currentIndex()
        return self._model.data(idx) if idx.isValid() else None

    def selected_words(self) -> list[str]:
        idxs = self._list.selectionModel().selectedIndexes()
        return [w for idx in idxs if (w := self._model.data(idx))]

    def delete_selected(self):
        """Public entry point for menu/shortcut-triggered deletion."""
        self._on_delete_selected()

    # ── Search (debounced, async) ───────────────────────────────────────────────

    def _on_search(self, text: str):
        self._pending_q = text.strip().lower()
        print(f"[search] input → pending_q={repr(self._pending_q)}", file=sys.stderr, flush=True)
        self._filter_debounce.start()

    def _run_filter(self):
        running = self._filter_thread is not None and self._filter_thread.isRunning()
        print(f"[search] debounce fired: pending={repr(self._pending_q)}, thread_running={running}", file=sys.stderr, flush=True)
        if running:
            return
        self._start_filter(self._pending_q)

    def _start_filter(self, q: str):
        self._running_q = q
        words = self._model._all
        print(f"[search] _start_filter: q={repr(q)}, word_count={len(words)}", file=sys.stderr, flush=True)

        def do_filter():
            result = [w for w in words if w.lower().startswith(q)] if q else words
            print(f"[search] bg done: q={repr(q)}, results={len(result)}", file=sys.stderr, flush=True)
            return result

        self._filter_thread = _spawn(do_filter, self._on_filter_done)
        self._filter_thread.finished.connect(self._check_filter_pending)

    def _on_filter_done(self, filtered: list[str]):
        import time
        print(f"[search] apply_filter: {len(filtered)} items → model", file=sys.stderr, flush=True)
        t = time.perf_counter()
        self._model.apply_filter(filtered)
        print(f"[search] apply_filter done: {(time.perf_counter()-t)*1000:.1f}ms", file=sys.stderr, flush=True)
        t0 = time.perf_counter()
        QTimer.singleShot(0, lambda: print(f"[search] tick0 after filter: {(time.perf_counter()-t0)*1000:.1f}ms", file=sys.stderr, flush=True))

    def _check_filter_pending(self):
        print(f"[search] thread finished: pending={repr(self._pending_q)}, ran={repr(self._running_q)}", file=sys.stderr, flush=True)
        self._filter_thread = None
        if self._pending_q != self._running_q:
            self._start_filter(self._pending_q)

    # ── Private ────────────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self._list and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Delete:
                self._on_delete_selected()
                return True
        return super().eventFilter(obj, event)

    def _on_selection_changed(self, selected, deselected):
        words = self.selected_words()
        count = len(words)
        self.selection_changed.emit(count)
        if count == 1:
            self.word_selected.emit(words[0])

    def _on_delete_selected(self):
        words = self.selected_words()
        if not words:
            return
        if len(words) == 1:
            msg = f'确定删除「{words[0]}」？'
        else:
            msg = f'确定删除选中的 {len(words)} 个词条？'
        reply = QMessageBox.question(
            self, "删除词条", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.words_deleted.emit(words)

    def _on_add(self):
        placeholder = self._unique_placeholder()
        self.word_added_inline.emit(placeholder)

    def _unique_placeholder(self) -> str:
        base = "新词条"
        existing = set(self._model._all)
        if base not in existing:
            return base
        i = 1
        while f"{base}_{i}" in existing:
            i += 1
        return f"{base}_{i}"

    def start_editing_word(self, word: str):
        row = self._model.row_of(word)
        if row >= 0:
            idx = self._model.index(row)
            self._list.setCurrentIndex(idx)
            self._list.scrollTo(idx)
            self._list.edit(idx)
