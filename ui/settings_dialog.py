from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTabWidget, QWidget, QLabel, QLineEdit, QPushButton,
    QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QDialogButtonBox, QFileDialog,
    QFontComboBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from settings import AppSettings
from themes import THEMES


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._s = settings
        self.setWindowTitle("设置")
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setMinimumWidth(460)
        self._setup_ui()
        self._load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._make_general_tab(), "通用")
        tabs.addTab(self._make_appearance_tab(), "外观")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── General tab ───────────────────────────────────────────────────────────

    def _make_general_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setVerticalSpacing(10)

        # Default DB
        db_row = QHBoxLayout()
        self._default_db = QLineEdit()
        self._default_db.setPlaceholderText("未设置")
        self._default_db.setReadOnly(True)
        browse_btn = QPushButton("浏览…")
        browse_btn.setFixedWidth(60)
        browse_btn.clicked.connect(self._browse_db)
        clear_btn = QPushButton("清除")
        clear_btn.setFixedWidth(48)
        clear_btn.clicked.connect(lambda: self._default_db.clear())
        db_row.addWidget(self._default_db)
        db_row.addWidget(browse_btn)
        db_row.addWidget(clear_btn)
        form.addRow("默认词典:", db_row)

        # Auto-open
        self._auto_open = QCheckBox("启动时自动打开默认词典")
        form.addRow("", self._auto_open)

        # Autosave toggle + delay
        self._autosave_enabled = QCheckBox("启用自动保存")
        form.addRow("自动保存:", self._autosave_enabled)

        autosave_row = QHBoxLayout()
        self._autosave = QSpinBox()
        self._autosave.setRange(200, 5000)
        self._autosave.setSingleStep(100)
        self._autosave.setSuffix(" ms")
        self._autosave.setFixedWidth(100)
        autosave_row.addWidget(self._autosave)
        autosave_row.addStretch()
        form.addRow("自动保存延迟:", autosave_row)
        self._autosave_enabled.toggled.connect(self._autosave.setEnabled)

        # Tab width
        self._tab_width = QSpinBox()
        self._tab_width.setRange(1, 8)
        self._tab_width.setSuffix(" 格")
        self._tab_width.setFixedWidth(80)
        form.addRow("缩进宽度:", self._tab_width)

        # HTML trigger
        self._html_trigger = QCheckBox("输入 < 时触发 HTML 标签自动补全")
        form.addRow("自动补全:", self._html_trigger)

        return w

    # ── Appearance tab ────────────────────────────────────────────────────────

    def _make_appearance_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setVerticalSpacing(10)

        self._theme_combo = QComboBox()
        for key, t in THEMES.items():
            self._theme_combo.addItem(t.name, key)
        self._theme_combo.setFixedWidth(120)
        form.addRow("主题:", self._theme_combo)

        hint = QLabel("主题更改即时生效，关闭此对话框后完全应用。")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        form.addRow("", hint)

        # Editor font
        font_row = QHBoxLayout()
        self._font_combo = QFontComboBox()
        self._font_combo.setFixedWidth(200)
        self._font_size_spin = QDoubleSpinBox()
        self._font_size_spin.setRange(6.0, 32.0)
        self._font_size_spin.setSingleStep(0.5)
        self._font_size_spin.setDecimals(1)
        self._font_size_spin.setSuffix(" pt")
        self._font_size_spin.setFixedWidth(80)
        font_row.addWidget(self._font_combo)
        font_row.addWidget(self._font_size_spin)
        font_row.addStretch()
        form.addRow("编辑器字体:", font_row)

        self._font_preview = QLabel("AaBbCc  <div>示例文字</div>")
        self._font_preview.setStyleSheet("color: #888;")
        form.addRow("", self._font_preview)

        self._font_combo.currentFontChanged.connect(self._update_font_preview)
        self._font_size_spin.valueChanged.connect(self._update_font_preview)

        # Preview font
        preview_font_row = QHBoxLayout()
        self._preview_font_combo = QFontComboBox()
        self._preview_font_combo.setFixedWidth(200)
        self._preview_font_size_spin = QDoubleSpinBox()
        self._preview_font_size_spin.setRange(8.0, 40.0)
        self._preview_font_size_spin.setSingleStep(1.0)
        self._preview_font_size_spin.setDecimals(0)
        self._preview_font_size_spin.setSuffix(" px")
        self._preview_font_size_spin.setFixedWidth(80)
        preview_font_row.addWidget(self._preview_font_combo)
        preview_font_row.addWidget(self._preview_font_size_spin)
        preview_font_row.addStretch()
        form.addRow("预览字体:", preview_font_row)

        self._preview_font_hint = QLabel("留空使用系统默认字体（Segoe UI）")
        self._preview_font_hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", self._preview_font_hint)

        return w

    def _update_font_preview(self):
        family = self._font_combo.currentFont().family()
        size   = self._font_size_spin.value()
        self._font_preview.setFont(QFont(family, size))

    # ── Load / Save ───────────────────────────────────────────────────────────

    def _load(self):
        self._default_db.setText(self._s.default_db)
        self._auto_open.setChecked(self._s.auto_open_default)
        self._autosave_enabled.setChecked(self._s.autosave_enabled)
        self._autosave.setEnabled(self._s.autosave_enabled)
        self._autosave.setValue(self._s.autosave_ms)
        self._tab_width.setValue(self._s.tab_width)
        self._html_trigger.setChecked(self._s.html_trigger_enabled)
        idx = self._theme_combo.findData(self._s.theme)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        self._font_combo.setCurrentFont(QFont(self._s.editor_font_family))
        self._font_size_spin.setValue(self._s.editor_font_size)
        self._update_font_preview()
        family = self._s.preview_font_family
        self._preview_font_combo.setCurrentFont(QFont(family) if family else QFont())
        self._preview_font_size_spin.setValue(self._s.preview_font_size)

    def _save_and_accept(self):
        self._s.default_db          = self._default_db.text().strip()
        self._s.auto_open_default   = self._auto_open.isChecked()
        self._s.autosave_enabled    = self._autosave_enabled.isChecked()
        self._s.autosave_ms         = self._autosave.value()
        self._s.tab_width           = self._tab_width.value()
        self._s.html_trigger_enabled = self._html_trigger.isChecked()
        self._s.theme               = self._theme_combo.currentData()
        self._s.editor_font_family  = self._font_combo.currentFont().family()
        self._s.editor_font_size    = float(self._font_size_spin.value())
        self._s.preview_font_family = self._preview_font_combo.currentFont().family()
        self._s.preview_font_size   = float(self._preview_font_size_spin.value())
        self.accept()

    def _browse_db(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择默认词典", "", "SQLite 词典 (*.sqlite)"
        )
        if path:
            self._default_db.setText(path)

    # ── Public helper ─────────────────────────────────────────────────────────

    @property
    def selected_theme(self) -> str:
        return self._theme_combo.currentData()
