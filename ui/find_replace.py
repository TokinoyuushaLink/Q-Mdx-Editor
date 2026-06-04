from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QTextEdit,
)
from PySide6.QtGui import QTextDocument, QTextCursor
from PySide6.QtCore import Qt


class FindReplaceDialog(QDialog):
    def __init__(self, editor: QTextEdit, parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setWindowTitle("查找 / 替换")
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.resize(400, 160)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Find row
        find_row = QHBoxLayout()
        find_row.addWidget(QLabel("查找:"))
        self._find_edit = QLineEdit()
        self._find_edit.returnPressed.connect(self._find_next)
        find_row.addWidget(self._find_edit)
        layout.addLayout(find_row)

        # Replace row
        repl_row = QHBoxLayout()
        repl_row.addWidget(QLabel("替换:"))
        self._repl_edit = QLineEdit()
        repl_row.addWidget(self._repl_edit)
        layout.addLayout(repl_row)

        # Options
        opt_row = QHBoxLayout()
        self._case_cb = QCheckBox("区分大小写")
        self._whole_cb = QCheckBox("全字匹配")
        opt_row.addWidget(self._case_cb)
        opt_row.addWidget(self._whole_cb)
        opt_row.addStretch()
        layout.addLayout(opt_row)

        # Buttons
        btn_row = QHBoxLayout()
        self._status = QLabel("")
        self._status.setStyleSheet("color: #888; font-size: 11px;")
        btn_find     = QPushButton("查找下一个")
        btn_repl     = QPushButton("替换")
        btn_repl_all = QPushButton("全部替换")
        btn_find.clicked.connect(self._find_next)
        btn_repl.clicked.connect(self._replace_one)
        btn_repl_all.clicked.connect(self._replace_all)
        btn_row.addWidget(self._status)
        btn_row.addStretch()
        btn_row.addWidget(btn_find)
        btn_row.addWidget(btn_repl)
        btn_row.addWidget(btn_repl_all)
        layout.addLayout(btn_row)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _flags(self) -> QTextDocument.FindFlag:
        f = QTextDocument.FindFlag(0)
        if self._case_cb.isChecked():
            f |= QTextDocument.FindFlag.FindCaseSensitively
        if self._whole_cb.isChecked():
            f |= QTextDocument.FindFlag.FindWholeWords
        return f

    def _find_next(self) -> bool:
        term = self._find_edit.text()
        if not term:
            return False
        found = self._editor.find(term, self._flags())
        if not found:
            # wrap around
            self._editor.moveCursor(QTextCursor.MoveOperation.Start)
            found = self._editor.find(term, self._flags())
        self._status.setText("" if found else "未找到")
        return found

    def _replace_one(self):
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self._repl_edit.text())
        self._find_next()

    def _replace_all(self):
        term = self._find_edit.text()
        if not term:
            return
        repl = self._repl_edit.text()
        flags = self._flags()
        self._editor.moveCursor(QTextCursor.MoveOperation.Start)
        count = 0
        while self._editor.find(term, flags):
            self._editor.textCursor().insertText(repl)
            count += 1
        self._status.setText(f"已替换 {count} 处" if count else "未找到")

    def show_and_focus(self):
        self.show()
        self.raise_()
        self._find_edit.setFocus()
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            self._find_edit.setText(cursor.selectedText())
            self._find_edit.selectAll()
