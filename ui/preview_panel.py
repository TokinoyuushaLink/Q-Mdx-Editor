from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from PySide6.QtCore import Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from preview_css import get_css


class PreviewPanel(QWidget):
    entry_link_clicked = Signal(str)

    def __init__(self, theme: str = "light",
                 font_family: str = "", font_size: float = 14.0,
                 parent=None):
        super().__init__(parent)
        self._theme = theme
        self._font_family = font_family
        self._font_size = font_size
        self._dict_css: str | None = None
        self._last_word: str = ""
        self._last_html: str = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._browser = QTextBrowser()
        self._browser.setOpenLinks(False)
        self._browser.setOpenExternalLinks(False)
        self._browser.anchorClicked.connect(self._on_anchor)
        self._apply_css()
        layout.addWidget(self._browser)

    # ── Public ─────────────────────────────────────────────────────────────────

    def set_theme(self, theme: str):
        self._theme = theme
        self._apply_css()
        if self._last_word or self._last_html:
            self.show_entry(self._last_word, self._last_html)

    def set_preview_font(self, family: str, size: float):
        self._font_family = family
        self._font_size = size
        self._apply_css()
        if self._last_word or self._last_html:
            self.show_entry(self._last_word, self._last_html)

    def set_dict_css(self, css: str | None):
        self._dict_css = css
        self._apply_css()
        if self._last_word or self._last_html:
            self.show_entry(self._last_word, self._last_html)

    def show_entry(self, word: str, html: str):
        self._last_word = word
        self._last_html = html
        if not html:
            if word:
                self._browser.setHtml(
                    f'<p style="color:#999;margin:16px">「{word}」暂无内容</p>'
                )
            else:
                self._browser.setHtml(
                    '<p style="color:#999;margin:16px">在编辑器中输入内容后在此预览</p>'
                )
            return
        if html.strip().startswith("@@@LINK="):
            target = html.strip().removeprefix("@@@LINK=").strip()
            self._browser.setHtml(
                f'<p style="font-style:italic">'
                f'跳转至: <a href="entry://{target}">{target}</a></p>'
            )
        else:
            self._browser.setHtml(html)
        self._browser.verticalScrollBar().setValue(0)

    def clear(self):
        self._last_word = ""
        self._last_html = ""
        self._browser.setHtml(
            '<p style="color:#999;margin:16px">打开或新建一个词典来开始编辑</p>'
        )

    # ── Private ────────────────────────────────────────────────────────────────

    def _apply_css(self):
        css = get_css(self._theme, self._font_family, self._font_size)
        if self._dict_css:
            css += "\n" + self._dict_css
        self._browser.document().setDefaultStyleSheet(css)

    def _on_anchor(self, url: QUrl):
        s = url.toString()
        if s.startswith("entry://"):
            word = s.removeprefix("entry://").strip("/")
            word = QUrl.fromPercentEncoding(word.encode())
            self.entry_link_clicked.emit(word)
        elif s.startswith(("http://", "https://")):
            QDesktopServices.openUrl(url)
