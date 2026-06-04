from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QMenuBar, QWidget,
    QLabel, QFileDialog, QProgressDialog, QMessageBox, QVBoxLayout,
    QHBoxLayout, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QApplication

from db import DictDB
from mdx_io import import_mdx, export_mdx
from settings import AppSettings
from themes import THEMES
from ui.dict_tab import DictTab
from ui.settings_dialog import SettingsDialog


class _Worker(QObject):
    progress = Signal(int)
    finished = Signal(int)
    error    = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            count = self._fn(*self._args, progress=self.progress.emit, **self._kwargs)
            self.finished.emit(count)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings):
        super().__init__()
        self._settings = settings
        self._recent_actions: list[QAction] = []
        self.setWindowTitle("词典编辑器")
        self.resize(1200, 720)
        self._setup_ui()
        self._setup_menu()
        self._apply_theme(settings.theme, save=False)

        if settings.auto_open_default and settings.default_db:
            p = settings.default_db
            if Path(p).exists():
                self._open_dict(p)

    # ── UI setup ───────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.tabBar().setExpanding(True)
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border: none; margin: 0; }"
            "QTabBar { border: none; }"
            "QTabBar::tab { padding: 2px 14px; min-width: 60px; }"
            "QTabBar::tab:!selected { background: palette(window); }"
            "QTabBar::tab:selected { background: palette(base); }"
        )
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.setVisible(False)

        self._welcome = self._build_welcome()

        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._welcome, 1)
        v.addWidget(self._tabs, 1)
        self.setCentralWidget(container)

        self._count_label = QLabel("未打开词典")
        self._save_status_label = QLabel("")
        self._save_status_label.setStyleSheet("color:#888;padding:0 6px;")
        self.statusBar().addWidget(self._count_label)
        self.statusBar().addPermanentWidget(self._save_status_label)

    # ── Menu setup ─────────────────────────────────────────────────────────────

    def _setup_menu(self):
        mb = QMenuBar(self)
        self._menu_bar = mb

        # ── 文件 ──────────────────────────────────────────────────────────────
        file_m = mb.addMenu("文件(&F)")

        file_m.addAction(self._act("新建词典(&N)", self._action_new_dict))
        file_m.addAction(self._act("打开词典(&O)…", self._action_open_dict,
                                    QKeySequence.StandardKey.Open))

        self._recent_menu = file_m.addMenu("最近打开(&R)")
        self._rebuild_recent_menu()

        file_m.addSeparator()
        file_m.addAction(self._act("关闭当前词典(&W)", self._close_current_tab,
                                    QKeySequence("Ctrl+W")))
        file_m.addAction(self._act("关闭全部词典", self._close_all_tabs))
        file_m.addSeparator()
        file_m.addAction(self._act("导入 MDX…", self._action_import_mdx))
        self._export_act = self._act("导出 MDX…", self._action_export_mdx)
        self._export_act.setEnabled(False)
        file_m.addAction(self._export_act)
        file_m.addSeparator()
        file_m.addAction(self._act("设置(&,)", self._open_settings,
                                    QKeySequence("Ctrl+,")))
        file_m.addSeparator()
        file_m.addAction(self._act("退出(&Q)", self.close,
                                    QKeySequence.StandardKey.Quit))

        # ── 编辑 ──────────────────────────────────────────────────────────────
        edit_m = mb.addMenu("编辑(&E)")
        edit_m.addAction(self._act("撤销", self._editor_undo,
                                    QKeySequence.StandardKey.Undo))
        edit_m.addAction(self._act("重做", self._editor_redo,
                                    QKeySequence.StandardKey.Redo))
        edit_m.addSeparator()
        edit_m.addAction(self._act("剪切", self._editor_cut,
                                    QKeySequence.StandardKey.Cut))
        edit_m.addAction(self._act("复制", self._editor_copy,
                                    QKeySequence.StandardKey.Copy))
        edit_m.addAction(self._act("粘贴", self._editor_paste,
                                    QKeySequence.StandardKey.Paste))
        edit_m.addSeparator()
        edit_m.addAction(self._act("查找 / 替换…", self._open_find_replace,
                                    QKeySequence("Ctrl+H")))
        edit_m.addSeparator()
        edit_m.addAction(self._act("全选", self._editor_select_all,
                                    QKeySequence.StandardKey.SelectAll))

        # ── 词条 ──────────────────────────────────────────────────────────────
        entry_m = mb.addMenu("词条(&T)")
        entry_m.addAction(self._act("新建词条", self._new_entry,
                                     QKeySequence.StandardKey.New))
        entry_m.addAction(self._act("删除当前词条", self._delete_current_entry,
                                     QKeySequence("Ctrl+Delete")))
        entry_m.addSeparator()
        entry_m.addAction(self._act("词条管理…", self._open_entry_manager))
        entry_m.addSeparator()

        insert_m = entry_m.addMenu("插入格式")
        insert_m.addAction(self._act("粗体 <b>",    lambda: self._toolbar_action("bold")))
        insert_m.addAction(self._act("斜体 <i>",    lambda: self._toolbar_action("italic")))
        insert_m.addAction(self._act("词目 <hw>",   lambda: self._toolbar_action("hw")))
        insert_m.addAction(self._act("音标 <pr>",   lambda: self._toolbar_action("pr")))
        insert_m.addAction(self._act("词性 <pos>",  lambda: self._toolbar_action("pos")))
        insert_m.addAction(self._act("例句 <ex>",   lambda: self._toolbar_action("ex")))
        insert_m.addAction(self._act("跳转链接",     lambda: self._toolbar_action("link")))
        insert_m.addAction(self._act("设为重定向",   lambda: self._toolbar_action("redirect")))

        # ── 词典 ──────────────────────────────────────────────────────────────
        dict_m = mb.addMenu("词典(&D)")
        dict_m.addAction(self._act("编辑词典 CSS…", self._action_edit_css))
        dict_m.addAction(self._act("词典属性…",     self._action_dict_stats))

        # ── 视图 ──────────────────────────────────────────────────────────────
        view_m = mb.addMenu("视图(&V)")
        theme_m = view_m.addMenu("主题")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._theme_acts: dict[str, QAction] = {}
        for key, t in THEMES.items():
            a = self._act(t.name, lambda checked, k=key: self._apply_theme(k))
            a.setCheckable(True)
            a.setChecked(key == self._settings.theme)
            self._theme_group.addAction(a)
            theme_m.addAction(a)
            self._theme_acts[key] = a

        layout_m = view_m.addMenu("布局")
        self._layout_group = QActionGroup(self)
        self._layout_group.setExclusive(True)
        self._layout_acts: dict[str, QAction] = {}
        cur_mode = self._settings.splitter_mode
        for key, label in [("auto", "自动"), ("horizontal", "垂直分割"), ("vertical", "水平分割")]:
            a = self._act(label, lambda checked, k=key: self._apply_splitter_mode(k),
                          checkable=True, checked=(key == cur_mode))
            self._layout_group.addAction(a)
            layout_m.addAction(a)
            self._layout_acts[key] = a

        view_m.addSeparator()
        self._wrap_act = self._act("自动换行", self._toggle_word_wrap,
                                    checkable=True, checked=False)
        view_m.addAction(self._wrap_act)
        view_m.addSeparator()

        editor_mode_m = view_m.addMenu("编辑器模式(&M)")
        self._editor_mode_group = QActionGroup(self)
        self._editor_mode_group.setExclusive(True)
        self._editor_mode_acts: dict[str, QAction] = {}
        for key, label in [("md", "Markdown（默认）"), ("html", "HTML")]:
            a = self._act(label, lambda checked, k=key: self._set_editor_mode(k),
                          checkable=True, checked=(key == "md"))
            self._editor_mode_group.addAction(a)
            editor_mode_m.addAction(a)
            self._editor_mode_acts[key] = a

        view_m.addSeparator()

        # ── 编辑器字号 ────────────────────────────────────────────────────────
        editor_size_m = view_m.addMenu("编辑器字号")
        self._editor_size_group = QActionGroup(self)
        self._editor_size_group.setExclusive(True)
        self._editor_size_acts: dict[float, QAction] = {}
        cur_esize = self._settings.editor_font_size
        for pt in [8, 9, 10, 11, 12, 13, 14, 16]:
            a = self._act(f"{pt} pt",
                          lambda checked, s=float(pt): self._set_editor_font_size(s),
                          checkable=True, checked=(float(pt) == cur_esize))
            self._editor_size_group.addAction(a)
            editor_size_m.addAction(a)
            self._editor_size_acts[float(pt)] = a

        # ── 预览字号 ──────────────────────────────────────────────────────────
        preview_size_m = view_m.addMenu("预览字号")
        self._preview_size_group = QActionGroup(self)
        self._preview_size_group.setExclusive(True)
        self._preview_size_acts: dict[float, QAction] = {}
        cur_psize = self._settings.preview_font_size
        for px in [11, 12, 13, 14, 15, 16, 18, 20]:
            a = self._act(f"{px} px",
                          lambda checked, s=float(px): self._set_preview_font_size(s),
                          checkable=True, checked=(float(px) == cur_psize))
            self._preview_size_group.addAction(a)
            preview_size_m.addAction(a)
            self._preview_size_acts[float(px)] = a

        view_m.addSeparator()
        view_m.addAction(self._act("状态栏", self._toggle_statusbar,
                                    checkable=True, checked=True))

        # ── 帮助 ──────────────────────────────────────────────────────────────
        help_m = mb.addMenu("帮助(&H)")
        help_m.addAction(self._act("关于…", self._show_about))

        self.setMenuBar(mb)

    # ── Helper: create QAction ─────────────────────────────────────────────────

    def _act(self, text: str, slot=None, shortcut=None,
             checkable=False, checked=False) -> QAction:
        a = QAction(text, self)
        if slot:      a.triggered.connect(slot)
        if shortcut:  a.setShortcut(shortcut)
        if checkable: a.setCheckable(True)
        if checkable: a.setChecked(checked)
        return a

    # ── Tab helpers ────────────────────────────────────────────────────────────

    def _add_tab(self, widget: QWidget, title: str) -> int:
        return self._tabs.addTab(widget, title)

    def _remove_tab(self, index: int):
        widget = self._tabs.widget(index)
        self._tabs.removeTab(index)
        if widget:
            widget.deleteLater()

    def _update_info_bar(self):
        count = self._tabs.count()
        self._tabs.tabBar().setVisible(count >= 2)
        self._welcome.setVisible(count == 0)
        self._tabs.setVisible(count > 0)
        if count == 0:
            self._refresh_welcome_recent()

    def _build_welcome(self) -> QWidget:
        w = QWidget()
        outer = QHBoxLayout(w)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.setSpacing(40)

        # ── 左侧：主操作 ──────────────────────────────────────────────────────
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(10)

        msg = QLabel("尚未打开任何词典")
        msg.setStyleSheet("font-size: 15px; color: #888;")

        acts = QLabel('<a href="open">打开词典</a>　　<a href="new">新建词典</a>')
        acts.linkActivated.connect(self._on_welcome_link)

        lv.addWidget(msg)
        lv.addWidget(acts)
        outer.addWidget(left)

        # ── 分隔线 ────────────────────────────────────────────────────────────
        self._welcome_sep = QFrame()
        self._welcome_sep.setFrameShape(QFrame.Shape.VLine)
        self._welcome_sep.setFrameShadow(QFrame.Shadow.Sunken)
        outer.addWidget(self._welcome_sep)

        # ── 右侧：最近打开 ────────────────────────────────────────────────────
        self._welcome_right = QWidget()
        rv = QVBoxLayout(self._welcome_right)
        rv.setAlignment(Qt.AlignmentFlag.AlignTop)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(4)
        self._welcome_recent_box = rv
        outer.addWidget(self._welcome_right)

        self._refresh_welcome_recent()
        return w

    def _refresh_welcome_recent(self):
        box = self._welcome_recent_box
        while box.count():
            item = box.takeAt(0)
            if w := item.widget():
                w.deleteLater()

        recent = self._settings.recent_files()[:5]
        self._welcome_recent_paths = list(recent)
        has = bool(recent)
        self._welcome_sep.setVisible(has)
        self._welcome_right.setVisible(has)
        if not has:
            return

        hdr = QLabel("最近打开")
        hdr.setStyleSheet("color: #888; font-size: 11px;")
        box.addWidget(hdr)

        for i, path in enumerate(recent):
            lbl = QLabel(f'<a href="r{i}">{Path(path).stem}</a>')
            lbl.setToolTip(path)
            lbl.linkActivated.connect(self._on_welcome_link)
            box.addWidget(lbl)

    def _on_welcome_link(self, href: str):
        if href == "open":
            self._action_open_dict()
        elif href == "new":
            self._action_new_dict()
        elif href.startswith("r") and href[1:].isdigit():
            idx = int(href[1:])
            paths = getattr(self, "_welcome_recent_paths", [])
            if idx < len(paths):
                self._open_recent(paths[idx])

    # ── Theme ──────────────────────────────────────────────────────────────────

    def _apply_theme(self, key: str, save: bool = True):
        theme = THEMES.get(key, THEMES["light"])
        app = QApplication.instance()
        app.setStyle("Fusion")
        app.setPalette(theme.palette)
        # Force every widget to re-evaluate palette references and repaint.
        style = app.style()
        for w in app.allWidgets():
            style.unpolish(w)
            style.polish(w)
            w.update()
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, DictTab):
                tab.set_theme(key)
        if save:
            self._settings.theme = key
        if key in self._theme_acts:
            self._theme_acts[key].setChecked(True)

    # ── Dict open / close ──────────────────────────────────────────────────────

    def _open_dict(self, path: str):
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, DictTab) and tab.db_path == path:
                self._tabs.setCurrentIndex(i)
                return
        tab = DictTab(
            path,
            theme=self._settings.theme,
            autosave_ms=self._settings.autosave_ms,
            autosave_enabled=self._settings.autosave_enabled,
            tab_width=self._settings.tab_width,
            splitter_mode=self._settings.splitter_mode,
            editor_font_family=self._settings.editor_font_family,
            editor_font_size=self._settings.editor_font_size,
            html_trigger=self._settings.html_trigger_enabled,
            preview_font_family=self._settings.preview_font_family,
            preview_font_size=self._settings.preview_font_size,
        )
        tab.count_changed.connect(self._update_count)
        tab._editor.save_status_changed.connect(
            lambda text, warn, t=tab: self._on_editor_save_status(t, text, warn)
        )
        tab._editor.mode_changed.connect(
            lambda mode, t=tab: self._on_editor_mode_changed(t, mode)
        )
        name = Path(path).stem
        idx = self._add_tab(tab, name)
        self._tabs.setCurrentIndex(idx)
        self._settings.add_recent(path)
        self._rebuild_recent_menu()
        self._export_act.setEnabled(True)
        self._update_count(tab.entry_count())
        self._update_info_bar()

    def _close_tab(self, index: int):
        tab = self._tabs.widget(index)
        if isinstance(tab, DictTab):
            tab.close_db()
        self._remove_tab(index)
        if self._tabs.count() == 0:
            self._count_label.setText("未打开词典")
            self._export_act.setEnabled(False)
            self._update_save_status("", False)
        self._update_info_bar()

    def _close_current_tab(self):
        idx = self._tabs.currentIndex()
        if idx >= 0:
            self._close_tab(idx)

    def _close_all_tabs(self):
        while self._tabs.count():
            self._close_tab(0)

    def _current_tab(self) -> DictTab | None:
        idx = self._tabs.currentIndex()
        w = self._tabs.widget(idx) if idx >= 0 else None
        return w if isinstance(w, DictTab) else None

    # ── File actions ───────────────────────────────────────────────────────────

    def _action_new_dict(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "新建词典", "", "SQLite 词典 (*.sqlite)"
        )
        if path:
            if not path.endswith(".sqlite"):
                path += ".sqlite"
            self._open_dict(path)

    def _action_open_dict(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开词典", "", "SQLite 词典 (*.sqlite)"
        )
        if path:
            self._open_dict(path)

    def _action_import_mdx(self):
        mdx_path, _ = QFileDialog.getOpenFileName(
            self, "选择 MDX 文件", "", "MDict 词典 (*.mdx)"
        )
        if not mdx_path:
            return
        default = Path(mdx_path).stem + ".sqlite"
        db_path, _ = QFileDialog.getSaveFileName(
            self, "保存为 SQLite", default, "SQLite 词典 (*.sqlite)"
        )
        if not db_path:
            return
        if not db_path.endswith(".sqlite"):
            db_path += ".sqlite"
        self._run_bg(
            "正在导入…", import_mdx, mdx_path, db_path,
            on_done=lambda n: (
                self._open_dict(db_path),
                QMessageBox.information(self, "导入完成", f"成功导入 {n} 条词条"),
            )
        )

    def _action_export_mdx(self):
        tab = self._current_tab()
        if not tab:
            return
        tab._editor.save_now()
        from PySide6.QtWidgets import QInputDialog
        title, ok = QInputDialog.getText(
            self, "词典标题", "MDX 标题:", text=tab.dict_name
        )
        if not ok:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 MDX", title + ".mdx", "MDict 词典 (*.mdx)"
        )
        if not path:
            return
        self._run_bg(
            "正在导出…", export_mdx, tab.db_path, path,
            title=title,
            on_done=lambda n: QMessageBox.information(
                self, "导出完成", f"成功导出 {n} 条词条\n{path}"
            )
        )

    def _action_edit_css(self):
        tab = self._current_tab()
        if tab:
            tab.edit_css()
        else:
            QMessageBox.warning(self, "提示", "请先打开一个词典。")

    def _action_dict_stats(self):
        tab = self._current_tab()
        if tab:
            tab.show_stats()

    # ── Edit actions (delegate to focused editor) ──────────────────────────────

    def _editor_undo(self):
        tab = self._current_tab()
        if tab: tab._editor.raw_editor().undo()

    def _editor_redo(self):
        tab = self._current_tab()
        if tab: tab._editor.raw_editor().redo()

    def _editor_cut(self):
        tab = self._current_tab()
        if tab: tab._editor.raw_editor().cut()

    def _editor_copy(self):
        tab = self._current_tab()
        if tab: tab._editor.raw_editor().copy()

    def _editor_paste(self):
        tab = self._current_tab()
        if tab: tab._editor.raw_editor().paste()

    def _editor_select_all(self):
        tab = self._current_tab()
        if tab: tab._editor.raw_editor().selectAll()

    def _open_find_replace(self):
        tab = self._current_tab()
        if not tab:
            return
        if not hasattr(self, "_find_dlg") or self._find_dlg is None:
            from ui.find_replace import FindReplaceDialog
            self._find_dlg = FindReplaceDialog(tab._editor.raw_editor(), self)
        else:
            self._find_dlg._editor = tab._editor.raw_editor()
        self._find_dlg.show_and_focus()

    # ── Entry actions (delegate to current tab) ────────────────────────────────

    def _new_entry(self):
        tab = self._current_tab()
        if tab:
            tab._list_panel._on_add()

    def _delete_current_entry(self):
        tab = self._current_tab()
        if tab:
            tab._list_panel.delete_selected()

    def _open_entry_manager(self):
        tab = self._current_tab()
        if not tab or not tab.db:
            QMessageBox.warning(self, "提示", "请先打开一个词典（或等待加载完成）。")
            return
        from ui.entry_manager import EntryManagerDialog
        dlg = EntryManagerDialog(tab.db, self)
        dlg.exec()
        tab.refresh()

    def _toolbar_action(self, name: str):
        tab = self._current_tab()
        if not tab:
            return
        tb = tab._editor._toolbar
        actions = {
            "bold":     lambda: tb._wrap("<b>", "</b>"),
            "italic":   lambda: tb._wrap("<i>", "</i>"),
            "hw":       lambda: tb._wrap('<b class="hw">', "</b>"),
            "pr":       lambda: tb._wrap('<span class="pr">', "</span>"),
            "pos":      lambda: tb._wrap('<span class="pos">', "</span>"),
            "ex":       lambda: tb._wrap('<p class="ex">', "</p>"),
            "link":     tb._insert_entry_link,
            "redirect": tb._insert_redirect,
        }
        if name in actions:
            actions[name]()

    # ── View ───────────────────────────────────────────────────────────────────

    def _set_editor_mode(self, mode: str):
        tab = self._current_tab()
        if tab:
            tab.set_editor_mode(mode)
        if mode in self._editor_mode_acts:
            self._editor_mode_acts[mode].setChecked(True)

    def _on_editor_mode_changed(self, from_tab: DictTab, mode: str):
        if from_tab is self._current_tab():
            if mode in self._editor_mode_acts:
                self._editor_mode_acts[mode].setChecked(True)

    def _toggle_word_wrap(self, checked: bool):
        tab = self._current_tab()
        if tab:
            tab._editor.set_word_wrap(checked)

    def _set_editor_font_size(self, size: float):
        self._settings.editor_font_size = size
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, DictTab):
                tab.set_editor_font(self._settings.editor_font_family, size)
        if size in self._editor_size_acts:
            self._editor_size_acts[size].setChecked(True)

    def _set_preview_font_size(self, size: float):
        self._settings.preview_font_size = size
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, DictTab):
                tab.set_preview_font(self._settings.preview_font_family, size)
        if size in self._preview_size_acts:
            self._preview_size_acts[size].setChecked(True)

    def _toggle_statusbar(self, checked: bool):
        self.statusBar().setVisible(checked)

    def _apply_splitter_mode(self, mode: str):
        self._settings.splitter_mode = mode
        if mode in self._layout_acts:
            self._layout_acts[mode].setChecked(True)
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, DictTab):
                tab.set_splitter_mode(mode)

    # ── Settings ───────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec():
            self._apply_theme(self._settings.theme, save=False)
            for i in range(self._tabs.count()):
                tab = self._tabs.widget(i)
                if isinstance(tab, DictTab):
                    tab.set_autosave_ms(self._settings.autosave_ms)
                    tab.set_autosave_enabled(self._settings.autosave_enabled)
                    tab.set_tab_width(self._settings.tab_width)
                    tab.set_editor_font(self._settings.editor_font_family,
                                        self._settings.editor_font_size)
                    tab.set_html_trigger(self._settings.html_trigger_enabled)
                    tab.set_preview_font(self._settings.preview_font_family,
                                         self._settings.preview_font_size)

    # ── Help ───────────────────────────────────────────────────────────────────

    def _show_about(self):
        QMessageBox.about(
            self, "关于词典编辑器",
            "<b>词典编辑器</b><br>"
            "基于 PySide6 + SQLite 的 MDict 词典制作工具<br><br>"
            "支持格式: .sqlite (编辑) / .mdx (导入 / 导出)"
        )

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _update_count(self, count: int):
        tab = self._current_tab()
        if tab:
            self._count_label.setText(f"{count} 条词条 — {tab.dict_name}")

    def _update_save_status(self, text: str, warn: bool):
        color = "#e06c00" if warn else "#888"
        self._save_status_label.setStyleSheet(f"color:{color};padding:0 6px;")
        self._save_status_label.setText(text)

    def _on_editor_save_status(self, from_tab: DictTab, text: str, warn: bool):
        if from_tab is self._current_tab():
            self._update_save_status(text, warn)

    def _on_tab_changed(self, index: int):
        tab = self._tabs.widget(index) if index >= 0 else None
        if isinstance(tab, DictTab):
            self._update_count(tab.entry_count())
            self._wrap_act.setChecked(tab._editor.word_wrap_enabled())
            dirty = tab._editor.is_dirty()
            self._update_save_status("未保存 ●" if dirty else "已保存", warn=dirty)
            mode = tab._editor.editor_mode
            if mode in self._editor_mode_acts:
                self._editor_mode_acts[mode].setChecked(True)
        else:
            self._count_label.setText("未打开词典")
            self._wrap_act.setChecked(False)
            self._update_save_status("", False)
        self._export_act.setEnabled(isinstance(tab, DictTab))
        self._update_info_bar()

    # ── Recent files ───────────────────────────────────────────────────────────

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        files = self._settings.recent_files()
        if not files:
            self._recent_menu.addAction("（无）").setEnabled(False)
            return
        for path in files:
            a = self._recent_menu.addAction(Path(path).name)
            a.setToolTip(path)
            a.triggered.connect(lambda checked, p=path: self._open_recent(p))
        self._recent_menu.addSeparator()
        self._recent_menu.addAction("清除记录", self._clear_recent)

    def _open_recent(self, path: str):
        if Path(path).exists():
            self._open_dict(path)
        else:
            QMessageBox.warning(self, "文件不存在", f"找不到：\n{path}")
            self._settings.remove_recent(path)
            self._rebuild_recent_menu()

    def _clear_recent(self):
        from PySide6.QtCore import QSettings
        QSettings("DictEditor", "DictEditor").remove("general/recent")
        self._rebuild_recent_menu()

    # ── Background worker ──────────────────────────────────────────────────────

    def _run_bg(self, title: str, fn, *args, on_done=None, **kwargs):
        dlg = QProgressDialog(title, None, 0, 0, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setCancelButton(None)
        dlg.show()

        self._bg_thread = QThread()
        self._bg_worker = _Worker(fn, *args, **kwargs)
        self._bg_worker.moveToThread(self._bg_thread)
        self._bg_thread.started.connect(self._bg_worker.run)
        self._bg_worker.progress.connect(
            lambda n: dlg.setLabelText(f"{title} {n} 条…")
        )
        self._bg_worker.finished.connect(
            lambda n: (dlg.close(), self._bg_thread.quit(),
                       on_done(n) if on_done else None)
        )
        self._bg_worker.error.connect(
            lambda msg: (dlg.close(), self._bg_thread.quit(),
                         QMessageBox.critical(self, "错误", msg))
        )
        self._bg_thread.start()

    # ── Close event ────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, DictTab):
                tab.close_db()
        event.accept()
