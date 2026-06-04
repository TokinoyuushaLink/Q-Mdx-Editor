from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListView, QPushButton, QLabel, QMessageBox,
    QAbstractItemView,
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QThread,
    QAbstractListModel, QModelIndex,
)
from PySide6.QtGui import QFont

from bg import bg_spawn as _spawn
from db import DictDB


# ── Virtual list model ─────────────────────────────────────────────────────────

class _ManagerModel(QAbstractListModel):
    """Stores words in a plain Python list; QListView renders only visible rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all: list[str] = []
        self._display: list[str] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._display)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._display):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display[index.row()]
        return None

    def set_all(self, words: list[str]):
        self.beginResetModel()
        self._all = words
        self._display = words
        self.endResetModel()

    def apply_filter(self, filtered: list[str]):
        self.beginResetModel()
        self._display = filtered
        self.endResetModel()

    def total_count(self) -> int:
        return len(self._all)

    def display_count(self) -> int:
        return len(self._display)

    def word_at(self, row: int) -> str:
        return self._display[row]


# ── Dialog ─────────────────────────────────────────────────────────────────────

class EntryManagerDialog(QDialog):
    def __init__(self, db: DictDB, parent=None):
        super().__init__(parent)
        self._db = db
        self._all_words: list[str] = []
        self._load_thread: QThread | None = None
        self._active_thread: QThread | None = None
        self._pending_q: str = ""
        self._running_q: str | None = None
        self.setWindowTitle("词条管理")
        self.resize(420, 580)
        self._setup_ui()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(280)
        self._debounce.timeout.connect(self._run_filter)
        self._load_all()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("过滤:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("输入关键词过滤词条…")
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._filter_edit)
        layout.addLayout(filter_row)

        self._status = QLabel("加载中…")
        self._status.setStyleSheet("color:#888;font-size:11px;")
        layout.addWidget(self._status)

        self._model = _ManagerModel()

        self._list = QListView()
        self._list.setFont(QFont("Segoe UI", 10))
        self._list.setUniformItemSizes(True)
        self._list.setLayoutMode(QListView.LayoutMode.Batched)
        self._list.setBatchSize(300)
        self._list.setModel(self._model)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.selectionModel().selectionChanged.connect(self._on_sel_changed)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._del_btn = QPushButton("删除选中词条")
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self._del_btn)
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # ── Load (async) ───────────────────────────────────────────────────────────

    def _load_all(self):
        self._status.setText("加载中…")
        self._filter_edit.setEnabled(False)
        self._del_btn.setEnabled(False)
        self._load_thread = _spawn(self._db.all_words, self._on_loaded)

    def _on_loaded(self, words: list[str]):
        self._load_thread = None
        self._all_words = words
        self._model.set_all(words)
        self._filter_edit.setEnabled(True)
        self._update_status()

    # ── Filter (async, debounced) ──────────────────────────────────────────────

    def _on_filter_changed(self, text: str):
        self._pending_q = text.strip().lower()
        self._debounce.start()

    def _run_filter(self):
        if self._active_thread and self._active_thread.isRunning():
            return
        self._start_filter(self._pending_q)

    def _start_filter(self, q: str):
        self._running_q = q
        self._status.setText("过滤中…")
        words = self._all_words

        def do_filter():
            return [w for w in words if q in w.lower()] if q else words

        self._active_thread = _spawn(do_filter, self._on_filtered)
        self._active_thread.finished.connect(self._check_pending)

    def _on_filtered(self, filtered: list[str]):
        self._model.apply_filter(filtered)
        self._update_status()

    def _check_pending(self):
        self._active_thread = None
        if self._pending_q != self._running_q:
            self._start_filter(self._pending_q)

    def _update_status(self):
        shown = self._model.display_count()
        total = self._model.total_count()
        if shown == total:
            self._status.setText(f"共 {total} 条")
        else:
            self._status.setText(f"显示 {shown} 条（共 {total} 条）")

    # ── Selection / Delete ─────────────────────────────────────────────────────

    def _on_sel_changed(self):
        count = len(self._list.selectionModel().selectedIndexes())
        self._del_btn.setEnabled(count > 0)

    def _delete_selected(self):
        indexes = self._list.selectionModel().selectedIndexes()
        words = [self._model.word_at(idx.row()) for idx in indexes]
        if not words:
            return
        reply = QMessageBox.question(
            self, "批量删除",
            f"确定删除选中的 {len(words)} 个词条？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for w in words:
            self._db.delete_entry(w)
        self._filter_edit.clear()
        self._load_all()
