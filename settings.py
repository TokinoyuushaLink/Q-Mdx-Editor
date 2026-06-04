from PySide6.QtCore import QSettings


class AppSettings:
    _ORG = "DictEditor"
    _APP = "DictEditor"

    def __init__(self):
        self._s = QSettings(self._ORG, self._APP)

    # ── General ───────────────────────────────────────────────────────────────

    @property
    def default_db(self) -> str:
        return self._s.value("general/default_db", "")

    @default_db.setter
    def default_db(self, v: str):
        self._s.setValue("general/default_db", v)

    @property
    def auto_open_default(self) -> bool:
        return bool(self._s.value("general/auto_open_default", True))

    @auto_open_default.setter
    def auto_open_default(self, v: bool):
        self._s.setValue("general/auto_open_default", bool(v))

    @property
    def autosave_enabled(self) -> bool:
        v = self._s.value("general/autosave_enabled", False)
        if isinstance(v, bool):
            return v
        return str(v).lower() not in ('0', 'false', 'no')

    @autosave_enabled.setter
    def autosave_enabled(self, v: bool):
        self._s.setValue("general/autosave_enabled", bool(v))

    @property
    def autosave_ms(self) -> int:
        return int(self._s.value("general/autosave_ms", 800))

    @autosave_ms.setter
    def autosave_ms(self, v: int):
        self._s.setValue("general/autosave_ms", int(v))

    @property
    def tab_width(self) -> int:
        return int(self._s.value("general/tab_width", 4))

    @tab_width.setter
    def tab_width(self, v: int):
        self._s.setValue("general/tab_width", int(v))

    @property
    def html_trigger_enabled(self) -> bool:
        v = self._s.value("editor/html_trigger", True)
        if isinstance(v, bool):
            return v
        return str(v).lower() not in ('0', 'false', 'no')

    @html_trigger_enabled.setter
    def html_trigger_enabled(self, v: bool):
        self._s.setValue("editor/html_trigger", bool(v))

    @property
    def editor_font_family(self) -> str:
        return str(self._s.value("editor/font_family", "Consolas"))

    @editor_font_family.setter
    def editor_font_family(self, v: str):
        self._s.setValue("editor/font_family", v)

    @property
    def editor_font_size(self) -> float:
        return float(self._s.value("editor/font_size", 10.0))

    @editor_font_size.setter
    def editor_font_size(self, v: float):
        self._s.setValue("editor/font_size", float(v))

    @property
    def preview_font_family(self) -> str:
        return str(self._s.value("preview/font_family", ""))

    @preview_font_family.setter
    def preview_font_family(self, v: str):
        self._s.setValue("preview/font_family", v)

    @property
    def preview_font_size(self) -> float:
        return float(self._s.value("preview/font_size", 14.0))

    @preview_font_size.setter
    def preview_font_size(self, v: float):
        self._s.setValue("preview/font_size", float(v))

    @property
    def splitter_mode(self) -> str:
        return str(self._s.value("appearance/splitter_mode", "auto"))

    @splitter_mode.setter
    def splitter_mode(self, v: str):
        self._s.setValue("appearance/splitter_mode", v)

    # ── Appearance ────────────────────────────────────────────────────────────

    @property
    def theme(self) -> str:
        return self._s.value("appearance/theme", "light")

    @theme.setter
    def theme(self, v: str):
        self._s.setValue("appearance/theme", v)

    # ── Recent files ──────────────────────────────────────────────────────────

    def recent_files(self) -> list[str]:
        v = self._s.value("general/recent", [])
        if not v:
            return []
        return v if isinstance(v, list) else [v]

    def add_recent(self, path: str):
        files = self.recent_files()
        if path in files:
            files.remove(path)
        files.insert(0, path)
        self._s.setValue("general/recent", files[:10])

    def remove_recent(self, path: str):
        files = self.recent_files()
        if path in files:
            files.remove(path)
            self._s.setValue("general/recent", files)
