import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPlainTextEdit,
    QPushButton, QFrame, QHBoxLayout, QInputDialog, QColorDialog,
    QCompleter,
)
from PySide6.QtCore import Signal, QTimer, Qt, QRect, QSize
from PySide6.QtGui import (
    QFont, QSyntaxHighlighter, QTextCharFormat, QColor,
    QKeySequence, QPainter, QTextCursor, QTextBlockFormat,
)

from md_convert import is_markdown, strip_marker, add_marker, md_to_html


# ── Font helper ───────────────────────────────────────────────────────────────

def _make_editor_font(family: str, size: float) -> QFont:
    """Return a QFont with DirectWrite antialiasing (avoids GDI jagged edges)."""
    f = QFont(family)
    f.setPointSizeF(size)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


# ── HTML formatting helpers ────────────────────────────────────────────────────

_VOID_ELEMENTS = frozenset([
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
    'link', 'meta', 'param', 'source', 'track', 'wbr',
])

_BLOCK_ELEMENTS = frozenset([
    'address', 'article', 'aside', 'blockquote', 'dd', 'details',
    'dialog', 'div', 'dl', 'dt', 'fieldset', 'figcaption', 'figure',
    'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header',
    'hgroup', 'li', 'main', 'nav', 'ol', 'p', 'pre', 'section',
    'summary', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'ul',
])


def _format_html(html: str, tab: str = '\t') -> str:
    """Pretty-print an HTML fragment.

    Block-level elements are placed on their own lines with indentation.
    Inline elements stay on the same line as surrounding content, so
    mixed-content lines (e.g. "text <b>bold</b> more") are preserved intact
    and round-trip cleanly through _minify_html.
    """
    html = html.strip()
    if not html or html.startswith('@@@LINK='):
        return html

    bp = '|'.join(_BLOCK_ELEMENTS)

    # Insert newlines around block-level tags (avoid doubling via lookbehind).
    html = re.sub(rf'(?<=[^\n])(<(?:{bp})(?:\s[^>]*)?>)',  r'\n\1', html, flags=re.IGNORECASE)
    html = re.sub(rf'(<(?:{bp})(?:\s[^>]*)?>)(?=[^\n])',   r'\1\n', html, flags=re.IGNORECASE)
    html = re.sub(rf'(?<=[^\n])(<\/(?:{bp})>)',             r'\n\1', html, flags=re.IGNORECASE)
    html = re.sub(rf'(<\/(?:{bp})>)(?=[^\n])',              r'\1\n', html, flags=re.IGNORECASE)

    lines  = [ln.strip() for ln in html.split('\n') if ln.strip()]
    result: list[str] = []
    level  = 0

    for line in lines:
        opens  = len(re.findall(rf'<(?:{bp})(?:\s[^>]*)?>',  line, re.IGNORECASE))
        closes = len(re.findall(rf'<\/(?:{bp})>',             line, re.IGNORECASE))

        # Lines that START with a closing block tag: dedent before writing
        if re.match(rf'<\/(?:{bp})>', line, re.IGNORECASE):
            level  = max(0, level - 1)
            closes -= 1

        result.append(tab * level + line)
        level = max(0, level + opens - closes)

    return '\n'.join(result)


def _minify_html(html: str) -> str:
    """Collapse pretty-printed HTML back to a single line."""
    if not html or html.startswith('@@@LINK='):
        return html
    return ''.join(ln.strip() for ln in html.split('\n'))


def _compute_fold_regions(document) -> dict[int, int]:
    """Return {start_block_num: end_block_num} for indentation-based fold regions."""
    entries: list[tuple[int, int]] = []
    block = document.begin()
    while block.isValid():
        text   = block.text()
        indent = (len(text) - len(text.lstrip())) if text.strip() else -1
        entries.append((block.blockNumber(), indent))
        block  = block.next()

    regions: dict[int, int] = {}
    n = len(entries)
    for i in range(n - 1):
        num, indent = entries[i]
        if indent < 0:
            continue
        next_indent = -1
        for j in range(i + 1, n):
            if entries[j][1] >= 0:
                next_indent = entries[j][1]
                break
        if next_indent <= indent:
            continue
        end = num
        for j in range(i + 1, n):
            ni = entries[j][1]
            if ni < 0:
                continue
            if ni > indent:
                end = entries[j][0]
            else:
                break
        if end > num:
            regions[num] = end

    return regions


# ── Autocomplete data ─────────────────────────────────────────────────────────

_HTML_TAGS = [
    'a', 'abbr', 'address', 'article', 'aside',
    'b', 'blockquote', 'br', 'button',
    'caption', 'cite', 'code', 'col', 'colgroup',
    'dd', 'del', 'details', 'dfn', 'div', 'dl', 'dt',
    'em',
    'figcaption', 'figure', 'footer',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hr',
    'i', 'img', 'input', 'ins',
    'kbd',
    'label', 'li',
    'main', 'mark',
    'nav',
    'ol',
    'p', 'pre',
    'q',
    's', 'samp', 'section', 'select', 'small', 'span', 'strong',
    'sub', 'summary', 'sup',
    'table', 'tbody', 'td', 'textarea', 'tfoot', 'th', 'thead', 'time', 'tr',
    'u', 'ul',
    'var',
]

_AUTOPAIR_MAP: dict[str, str] = {
    # ASCII pairs
    '{': '}', '[': ']', '(': ')', '"': '"', "'": "'",
    # Chinese / fullwidth pairs
    '【': '】', '《': '》', '（': '）',
    '“': '”',  # " → "
    '‘': '’',  # ' → '
}


# ── HTML syntax highlighter ────────────────────────────────────────────────────

class HtmlHighlighter(QSyntaxHighlighter):
    _TAG     = re.compile(r'</?[a-zA-Z][^>]*/?>')
    _ATTR    = re.compile(r'\b([a-zA-Z\-:]+)(?==)')
    _VAL     = re.compile(r'=("[^"]*"|\'[^\']*\')')
    _COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)
    _ENTITY  = re.compile(r'&[a-zA-Z#\d]+;')

    def __init__(self, doc):
        super().__init__(doc)
        self._tag_fmt     = self._fmt("#0057AE", bold=True)
        self._attr_fmt    = self._fmt("#007C45")
        self._val_fmt     = self._fmt("#C04000")
        self._comment_fmt = self._fmt("#808080", italic=True)
        self._entity_fmt  = self._fmt("#9B2393")

    @staticmethod
    def _fmt(color: str, bold=False, italic=False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:   f.setFontWeight(700)
        if italic: f.setFontItalic(True)
        return f

    def highlightBlock(self, text: str):
        for m in self._COMMENT.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._comment_fmt)
        for m in self._TAG.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._tag_fmt)
            inner, offset = m.group(0), m.start()
            for am in self._ATTR.finditer(inner):
                self.setFormat(offset + am.start(), am.end() - am.start(), self._attr_fmt)
            for am in self._VAL.finditer(inner):
                self.setFormat(offset + am.start(), am.end() - am.start(), self._val_fmt)
        for m in self._ENTITY.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._entity_fmt)


# ── Markdown syntax highlighter ───────────────────────────────────────────────

class MarkdownHighlighter(QSyntaxHighlighter):
    _HEADING  = re.compile(r'^#{1,6}\s+')
    _BOLD     = re.compile(r'\*\*[^*\n]+\*\*|__[^_\n]+__')
    _ITALIC   = re.compile(r'\*[^*\n]+\*|(?<![_\w])_[^_\n]+_(?![_\w])')
    _CODE     = re.compile(r'`[^`\n]+`')
    _LINK     = re.compile(r'\[.*?\]\(.*?\)')
    _LIST     = re.compile(r'^(\s*)([-*+]|\d+\.)\s')
    _QUOTE    = re.compile(r'^>')
    _HRULE    = re.compile(r'^(-{3,}|\*{3,}|_{3,})\s*$')
    _FENCE    = re.compile(r'^```')
    _HTML_TAG = re.compile(r'</?[a-zA-Z][^>]*/?>')

    def __init__(self, doc):
        super().__init__(doc)
        self._h_fmt    = self._fmt("#0057AE", bold=True)
        self._bold_fmt = self._fmt("#111111", bold=True)
        self._ital_fmt = self._fmt("#555555", italic=True)
        self._code_fmt = self._fmt("#C04000")
        self._link_fmt = self._fmt("#0066cc")
        self._list_fmt = self._fmt("#007C45", bold=True)
        self._quote_fmt= self._fmt("#888888", italic=True)
        self._tag_fmt  = self._fmt("#999999")
        self._meta_fmt = self._fmt("#BBBBBB", italic=True)
        self._in_fence = False

    @staticmethod
    def _fmt(color: str, bold=False, italic=False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:   f.setFontWeight(700)
        if italic: f.setFontItalic(True)
        return f

    def highlightBlock(self, text: str):
        # <!--md--> marker line
        if text.strip() == "<!--md-->":
            self.setFormat(0, len(text), self._meta_fmt)
            return

        # Fenced code block tracking
        if self._FENCE.match(text.strip()):
            self._in_fence = not self._in_fence
            self.setFormat(0, len(text), self._code_fmt)
            return
        if self._in_fence:
            self.setFormat(0, len(text), self._code_fmt)
            return

        # Headings (full line)
        if self._HEADING.match(text):
            self.setFormat(0, len(text), self._h_fmt)
        # Horizontal rule
        elif self._HRULE.match(text):
            self.setFormat(0, len(text), self._meta_fmt)
            return
        # Blockquote
        elif self._QUOTE.match(text):
            self.setFormat(0, len(text), self._quote_fmt)

        # List marker
        if m := self._LIST.match(text):
            self.setFormat(m.start(2), m.end(2) - m.start(2), self._list_fmt)

        # Inline: bold before italic to handle **...**
        for pattern, fmt in [
            (self._BOLD,  self._bold_fmt),
            (self._ITALIC,self._ital_fmt),
            (self._CODE,  self._code_fmt),
            (self._LINK,  self._link_fmt),
        ]:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

        # HTML passthrough tags (dim, applied last)
        for m in self._HTML_TAG.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._tag_fmt)


# ── Line number + fold arrow area ─────────────────────────────────────────────

class _LineNumberArea(QWidget):
    def __init__(self, editor: "_CodeEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor._ln_width(), 0)

    def paintEvent(self, event):
        self._editor._paint_ln(event)

    def mousePressEvent(self, event):
        ed = self._editor
        # Only respond to clicks in the fold-arrow zone (right 14 px)
        if event.pos().x() < self.width() - 14:
            return
        y     = event.pos().y()
        block = ed.firstVisibleBlock()
        top   = int(ed.blockBoundingGeometry(block)
                      .translated(ed.contentOffset()).top())
        while block.isValid():
            if block.isVisible():
                bh = int(ed.blockBoundingRect(block).height())
                if top <= y <= top + bh:
                    if block.blockNumber() in ed._fold_regions:
                        ed._toggle_fold(block.blockNumber())
                    break
                top += bh
                if top > self.height():
                    break
            block = block.next()


# ── Code editor ───────────────────────────────────────────────────────────────

class _CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ln_area       = _LineNumberArea(self)
        self._tab_width     = 4
        self._fold_regions: dict[int, int] = {}
        self._folded_lines: set[int]       = set()
        self._autopair_cursors: list[QTextCursor] = []
        self._html_trigger = True

        self._force_complete_mode   = False
        self._force_complete_prefix = ''

        self.blockCountChanged.connect(self._update_ln_width)
        self.updateRequest.connect(self._update_ln_area)
        self.cursorPositionChanged.connect(self._ln_area.update)
        self._update_ln_width(0)
        self._setup_completer()

    # ── Tag autocomplete ───────────────────────────────────────────────────────

    def _setup_completer(self):
        self._completer = QCompleter(_HTML_TAGS, self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setMaxVisibleItems(12)
        self._completer.activated.connect(self._insert_tag_completion)

    def set_html_trigger(self, enabled: bool):
        self._html_trigger = enabled
        if not enabled:
            self._completer.popup().hide()

    def _tag_completion_prefix(self) -> str | None:
        """Return the partial tag name typed after '<', or None if not in that context."""
        if not self._html_trigger:
            return None
        cursor = self.textCursor()
        text   = cursor.block().text()[:cursor.positionInBlock()]
        idx    = text.rfind('<')
        if idx < 0:
            return None
        after = text[idx + 1:]
        # Only opening tags: pure [a-zA-Z0-9]* (no '/', '>', spaces, attrs)
        if re.match(r'^[a-zA-Z0-9]*$', after):
            return after
        return None

    def _show_popup(self):
        """Position and (re)show the completer popup at the current cursor."""
        popup = self._completer.popup()
        cr = self.cursorRect()
        cr.moveTopLeft(self.viewport().mapToParent(cr.topLeft()))
        cr.setWidth(
            max(150,
                popup.sizeHintForColumn(0)
                + popup.verticalScrollBar().sizeHint().width()
                + 4)
        )
        self._completer.complete(cr)
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))

    def _force_completer(self):
        """Enter force-complete mode: open popup with empty prefix (all tags)."""
        self._force_complete_mode   = True
        self._force_complete_prefix = ''
        self._completer.setCompletionPrefix('')
        self._show_popup()

    def _update_completer(self):
        prefix = self._tag_completion_prefix()
        popup  = self._completer.popup()
        if prefix is None:
            if popup.isVisible():
                popup.hide()
            return
        # Skip expensive complete() if prefix hasn't changed and popup is already up
        if prefix == self._completer.completionPrefix() and popup.isVisible():
            return
        self._completer.setCompletionPrefix(prefix)
        if self._completer.completionCount() == 0:
            if popup.isVisible():
                popup.hide()
            return
        cr = self.cursorRect()
        cr.moveTopLeft(self.viewport().mapToParent(cr.topLeft()))
        cr.setWidth(
            max(150,
                self._completer.popup().sizeHintForColumn(0)
                + self._completer.popup().verticalScrollBar().sizeHint().width()
                + 4)
        )
        self._completer.complete(cr)
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))

    def _accept_tag_completion(self):
        popup = self._completer.popup()
        idx   = popup.currentIndex()
        if idx.isValid():
            tag = self._completer.completionModel().data(idx)
            self._insert_tag_completion(tag)
        popup.hide()

    def _insert_tag_completion(self, tag: str):
        self._completer.popup().hide()
        cursor = self.textCursor()
        from_force = self._force_complete_mode
        if from_force:
            prefix = self._force_complete_prefix
            self._force_complete_mode   = False
            self._force_complete_prefix = ''
        else:
            prefix = self._tag_completion_prefix() or ''
        if prefix:
            cursor.movePosition(
                QTextCursor.MoveOperation.PreviousCharacter,
                QTextCursor.MoveMode.KeepAnchor,
                len(prefix),
            )
        tag_lower = tag.lower()
        open_ = '<' if from_force else ''
        if tag_lower in _VOID_ELEMENTS:
            cursor.insertText(f"{open_}{tag}>")
        else:
            cursor.insertText(f"{open_}{tag}></{tag}>")
            pos = cursor.position() - len(f"</{tag}>")
            cursor.setPosition(pos)
            self.setTextCursor(cursor)

    # ── Geometry ───────────────────────────────────────────────────────────────

    def _ln_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 6 + self.fontMetrics().horizontalAdvance("0") * digits + 6 + 14

    def _num_area_w(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 6 + self.fontMetrics().horizontalAdvance("0") * digits

    def _update_ln_width(self, _=0):
        w = self._ln_width()
        self.setViewportMargins(w, 0, 0, 0)
        cr = self.contentsRect()
        self._ln_area.setGeometry(QRect(cr.left(), cr.top(), w, cr.height()))

    def _update_ln_area(self, rect, dy):
        if dy:
            self._ln_area.scroll(0, dy)
        else:
            self._ln_area.update(0, rect.y(), self._ln_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_ln_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._ln_area.setGeometry(
            QRect(cr.left(), cr.top(), self._ln_width(), cr.height())
        )

    # ── Painting ───────────────────────────────────────────────────────────────

    def _paint_ln(self, event):
        painter = QPainter(self._ln_area)
        painter.fillRect(event.rect(), self.palette().alternateBase().color())

        lh         = self.fontMetrics().height()
        num_w      = self._num_area_w()
        fold_x     = num_w + 2

        num_color  = self.palette().text().color()
        num_color.setAlphaF(0.4)
        fold_color = self.palette().text().color()
        fold_color.setAlphaF(0.55)

        block = self.firstVisibleBlock()
        num   = block.blockNumber()
        top   = int(self.blockBoundingGeometry(block)
                      .translated(self.contentOffset()).top())
        bot   = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bot >= event.rect().top():
                painter.setPen(num_color)
                painter.drawText(0, top, num_w, lh,
                                 Qt.AlignmentFlag.AlignRight, str(num + 1))
                if num in self._fold_regions:
                    painter.setPen(fold_color)
                    arrow = "▶" if num in self._folded_lines else "▼"
                    painter.drawText(fold_x, top, 12, lh,
                                     Qt.AlignmentFlag.AlignCenter, arrow)
            block = block.next()
            top   = bot
            bot   = top + int(self.blockBoundingRect(block).height())
            num  += 1

    def paintEvent(self, event):
        super().paintEvent(event)
        self._paint_indent_guides(event)

    def _paint_indent_guides(self, event):
        painter = QPainter(self.viewport())
        painter.setClipRect(event.rect())

        c = self.palette().text().color()
        c.setAlphaF(0.07)
        painter.setPen(c)

        tab_px     = self.tabStopDistance()
        doc_margin = int(self.document().documentMargin())
        offset     = self.contentOffset()

        block = self.firstVisibleBlock()
        while block.isValid():
            if not block.isVisible():
                block = block.next()
                continue
            geom = self.blockBoundingGeometry(block).translated(offset)
            if geom.top() > event.rect().bottom():
                break
            text = block.text()
            if text.strip():
                n_tabs = len(text) - len(text.lstrip('\t'))
                x = tab_px
                while x < n_tabs * tab_px:
                    px = int(doc_margin + x)
                    painter.drawLine(px, int(geom.top()), px, int(geom.bottom()))
                    x += tab_px
            block = block.next()

        painter.end()

    # ── Key handling ───────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        key   = event.key()
        char  = event.text()
        popup = self._completer.popup()

        # ── Force-complete mode ────────────────────────────────────────────────
        if self._force_complete_mode:
            handled = True
            if key == Qt.Key.Key_Tab:
                self._accept_tag_completion()
            elif key == Qt.Key.Key_Escape:
                self._force_complete_mode   = False
                self._force_complete_prefix = ''
                popup.hide()
            elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                pass  # popup's event filter handles navigation
            elif char and char.isalpha():
                super().keyPressEvent(event)
                self._force_complete_prefix += char
                self._completer.setCompletionPrefix(self._force_complete_prefix)
                if self._completer.completionCount() == 0:
                    self._force_complete_mode   = False
                    self._force_complete_prefix = ''
                    popup.hide()
                else:
                    self._show_popup()
            elif key == Qt.Key.Key_Backspace:
                super().keyPressEvent(event)
                if self._force_complete_prefix:
                    self._force_complete_prefix = self._force_complete_prefix[:-1]
                    self._completer.setCompletionPrefix(self._force_complete_prefix)
                    self._show_popup()
                else:
                    self._force_complete_mode = False
                    popup.hide()
            else:
                self._force_complete_mode   = False
                self._force_complete_prefix = ''
                popup.hide()
                handled = False
            if handled:
                return

        # ── Completer popup open ──────────────────────────────────────────────
        if popup.isVisible():
            if key == Qt.Key.Key_Tab:
                self._accept_tag_completion()
                return
            if key == Qt.Key.Key_Escape:
                popup.hide()
                return
            # Return / Up / Down: QCompleter's event-filter handles these;
            # if they somehow slip through, suppress to avoid editor side-effects.
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                       Qt.Key.Key_Up, Qt.Key.Key_Down):
                return

        # ── Tab: autopair skip, then indent ──────────────────────────────────
        if key == Qt.Key.Key_Tab:
            cursor = self.textCursor()
            if not cursor.hasSelection():
                pos = cursor.position()
                for i, ac in enumerate(self._autopair_cursors):
                    if ac.position() == pos:
                        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                        self.setTextCursor(cursor)
                        self._autopair_cursors.pop(i)
                        return
                cursor.insertText('\t')
            else:
                self._indent_block(cursor, indent=True)
            return

        # ── Shift+Space: manually trigger autocomplete ───────────────────────
        if key == Qt.Key.Key_Space and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._force_completer()
            return

        # ── Shift+Tab ─────────────────────────────────────────────────────────
        if key == Qt.Key.Key_Backtab:
            self._indent_block(self.textCursor(), indent=False)
            return

        # ── Return: auto-indent ───────────────────────────────────────────────
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor  = self.textCursor()
            line    = cursor.block().text()
            leading = len(line) - len(line.lstrip('\t'))
            extra   = 0
            m = re.search(r'<(\w+)[^>]*>\s*$', line.rstrip())
            if m and m.group(1).lower() not in _VOID_ELEMENTS:
                extra = 1
            super().keyPressEvent(event)
            if leading + extra:
                self.textCursor().insertText('\t' * (leading + extra))
            # New line always breaks any tag context
            if popup.isVisible():
                popup.hide()
            return

        # ── Auto-pair ─────────────────────────────────────────────────────────
        if char in _AUTOPAIR_MAP:
            close  = _AUTOPAIR_MAP[char]
            cursor = self.textCursor()
            if cursor.hasSelection():
                sel = cursor.selectedText()
                cursor.insertText(f"{char}{sel}{close}")
            else:
                cursor.insertText(f"{char}{close}")
                cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
                self.setTextCursor(cursor)
                ac = QTextCursor(self.document())
                ac.setPosition(cursor.position())
                self._autopair_cursors.append(ac)
            return

        # ── Default ───────────────────────────────────────────────────────────
        super().keyPressEvent(event)
        # Only invoke completer machinery for keys that can affect tag context.
        # Skipping for space, '>', punctuation, arrows, etc. when popup is hidden
        # avoids per-keystroke popup reset/repaint overhead.
        if (popup.isVisible()
                or char == '<'
                or (char and char.isalnum())
                or key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete)):
            self._update_completer()

    def _indent_block(self, cursor: QTextCursor, indent: bool):
        start = cursor.selectionStart()
        end   = cursor.selectionEnd()
        cursor.setPosition(start)
        sb = cursor.blockNumber()
        cursor.setPosition(end)
        eb = cursor.blockNumber()

        cursor.beginEditBlock()
        for i in range(sb, eb + 1):
            blk = self.document().findBlockByNumber(i)
            bc  = QTextCursor(blk)
            bc.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            if indent:
                bc.insertText('\t')
            else:
                if blk.text().startswith('\t'):
                    bc.movePosition(
                        QTextCursor.MoveOperation.NextCharacter,
                        QTextCursor.MoveMode.KeepAnchor, 1,
                    )
                    bc.removeSelectedText()
        cursor.endEditBlock()

    # ── Tab width ──────────────────────────────────────────────────────────────

    def set_tab_width(self, width: int):
        self._tab_width = width
        px = width * self.fontMetrics().horizontalAdvance(' ')
        self.setTabStopDistance(float(px))

    # ── Fold ───────────────────────────────────────────────────────────────────

    def update_fold_regions(self):
        self._fold_regions = _compute_fold_regions(self.document())
        self._ln_area.update()

    def _toggle_fold(self, start: int):
        end     = self._fold_regions.get(start)
        if end is None:
            return
        doc     = self.document()
        folding = start not in self._folded_lines

        if folding:
            self._folded_lines.add(start)
        else:
            self._folded_lines.discard(start)

        for ln in range(start + 1, end + 1):
            blk = doc.findBlockByNumber(ln)
            if blk.isValid():
                blk.setVisible(not folding)
                doc.markContentsDirty(blk.position(), blk.length())

        self.viewport().update()
        self._ln_area.update()

    def _unfold_all(self):
        if not self._folded_lines:
            return
        doc = self.document()
        for start in list(self._folded_lines):
            end = self._fold_regions.get(start, start)
            for ln in range(start + 1, end + 1):
                blk = doc.findBlockByNumber(ln)
                if blk.isValid():
                    blk.setVisible(True)
                    doc.markContentsDirty(blk.position(), blk.length())
        self._folded_lines.clear()
        self.viewport().update()
        self._ln_area.update()

    # ── Continuation indent (word-wrap mode) ───────────────────────────────────

    def _apply_wrap_indents(self):
        """Hanging-indent: leftMargin = N*tab_px pushes all visual lines right;
        textIndent = -N*tab_px pulls the first visual line back to column 0 so
        the leading tabs land at the correct tab stops, and continuation lines
        start at N*tab_px — aligned with the content."""
        tab_px = self.tabStopDistance()
        doc    = self.document()
        cursor = QTextCursor(doc)
        self.blockSignals(True)
        cursor.beginEditBlock()
        block = doc.begin()
        while block.isValid():
            text = block.text()
            n    = len(text) - len(text.lstrip('\t'))
            fmt  = block.blockFormat()
            px   = float(n * tab_px)
            fmt.setLeftMargin(px)
            fmt.setTextIndent(-px)
            cursor.setPosition(block.position())
            cursor.setBlockFormat(fmt)
            block = block.next()
        cursor.endEditBlock()
        self.blockSignals(False)
        self.viewport().update()

    def _clear_wrap_indents(self):
        """Reset all block format margins to zero."""
        doc   = self.document()
        # Short-circuit when nothing has been set.
        block = doc.begin()
        while block.isValid():
            f = block.blockFormat()
            if f.leftMargin() != 0.0 or f.textIndent() != 0.0:
                break
            block = block.next()
        else:
            return  # nothing to clear

        cursor = QTextCursor(doc)
        self.blockSignals(True)
        cursor.beginEditBlock()
        block = doc.begin()
        while block.isValid():
            fmt = block.blockFormat()
            if fmt.leftMargin() != 0.0 or fmt.textIndent() != 0.0:
                fmt.setLeftMargin(0.0)
                fmt.setTextIndent(0.0)
                cursor.setPosition(block.position())
                cursor.setBlockFormat(fmt)
            block = block.next()
        cursor.endEditBlock()
        self.blockSignals(False)


# ── Toolbar ────────────────────────────────────────────────────────────────────

class _ToolbarButton(QPushButton):
    def __init__(self, label: str, tip: str, parent=None):
        super().__init__(label, parent)
        self.setToolTip(tip)
        self.setFixedHeight(20)
        self.setFixedWidth(max(28, len(label) * 9 + 10))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class EditorToolbar(QFrame):
    def __init__(self, editor: QPlainTextEdit, parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(30)
        self._build()

    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(2)

        def btn(label, tip, fn):
            b = _ToolbarButton(label, tip)
            b.clicked.connect(fn)
            row.addWidget(b)
            return b

        def sep():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.VLine)
            line.setFixedWidth(1)
            row.addWidget(line)

        b = btn("B", "粗体 <b>", lambda: self._wrap("<b>", "</b>"))
        b.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))

        b = btn("I", "斜体 <i>", lambda: self._wrap("<i>", "</i>"))
        b.setFont(QFont("Segoe UI", 9, italic=True))

        b = btn("U", "下划线 <u>", lambda: self._wrap("<u>", "</u>"))
        b.setFont(QFont("Segoe UI", 9))

        btn("sup", "上标 <sup>", lambda: self._wrap("<sup>", "</sup>"))
        btn("sub", "下标 <sub>", lambda: self._wrap("<sub>", "</sub>"))
        btn("A色", "文字颜色", self._pick_color)

        sep()

        btn("hw",   '词目 <b class="hw">',      lambda: self._wrap('<b class="hw">', "</b>"))
        btn("/pr/", '音标 <span class="pr">',    lambda: self._wrap('<span class="pr">', "</span>"))
        btn("pos",  '词性 <span class="pos">',   lambda: self._wrap('<span class="pos">', "</span>"))
        btn("例",   '例句 <p class="ex">',       lambda: self._wrap('<p class="ex">', "</p>"))

        sep()

        btn("链接", "插入 entry:// 跳转链接", self._insert_entry_link)
        btn("→重定向", "设为 @@@LINK= 重定向词条", self._insert_redirect)

        sep()

        btn("⊘清除", "清除选中文本的 HTML 标签", self._strip_tags)

        row.addStretch()

    # ── Insert helpers ─────────────────────────────────────────────────────────

    def _wrap(self, open_tag: str, close_tag: str):
        e   = self._editor
        cur = e.textCursor()
        sel = cur.selectedText()
        if sel:
            cur.insertText(f"{open_tag}{sel}{close_tag}")
        else:
            pos = cur.position()
            cur.insertText(f"{open_tag}{close_tag}")
            cur.setPosition(pos + len(open_tag))
            e.setTextCursor(cur)
        e.setFocus()

    def _pick_color(self):
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self._wrap(f'<span style="color:{color.name()}">', "</span>")

    def _insert_entry_link(self):
        cur = self._editor.textCursor()
        sel = cur.selectedText().strip()
        word, ok = QInputDialog.getText(
            self, "插入跳转链接", "目标词条名称:", text=sel
        )
        if ok and word.strip():
            word    = word.strip()
            display = sel or word
            cur.insertText(f'<a href="entry://{word}">{display}</a>')
        self._editor.setFocus()

    def _insert_redirect(self):
        cur = self._editor.textCursor()
        sel = cur.selectedText().strip()
        word, ok = QInputDialog.getText(
            self, "设置重定向", "重定向目标词条:", text=sel
        )
        if ok and word.strip():
            self._editor.setPlainText(f"@@@LINK={word.strip()}")
        self._editor.setFocus()

    def _strip_tags(self):
        cur = self._editor.textCursor()
        sel = cur.selectedText()
        if sel:
            clean = re.sub(r'<[^>]+>', '', sel)
            cur.insertText(clean)
        self._editor.setFocus()


# ── Editor panel ───────────────────────────────────────────────────────────────

class EditorPanel(QWidget):
    content_changed     = Signal(str, str)    # (word, rendered_html) — for preview
    save_requested      = Signal(str, str)    # (word, stored_html)   — for db
    save_status_changed = Signal(str, bool)   # (text, is_warning)
    orphan_save_requested = Signal(str)       # (stored_html,) — Ctrl+S in orphan mode
    mode_changed        = Signal(str)         # "md" | "html"

    def __init__(self, autosave_ms: int = 800, autosave_enabled: bool = False,
                 tab_width: int = 4, parent=None):
        super().__init__(parent)
        self._loaded_word: str | None = None
        self._dirty            = False
        self._autosave_ms      = autosave_ms
        self._autosave_enabled = autosave_enabled
        self._setup_ui()
        self._editor_area.set_tab_width(tab_width)

        self._preview_timer = QTimer(singleShot=True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._emit_preview)

        self._save_timer = QTimer(singleShot=True)
        self._save_timer.setInterval(self._autosave_ms)
        self._save_timer.timeout.connect(self._auto_save)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._editor_area = _CodeEditor()
        self._editor_area.setFont(_make_editor_font("Consolas", 10))
        self._editor_area.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._toolbar = EditorToolbar(self._editor_area)
        layout.addWidget(self._toolbar)

        self._mode: str = "md"
        self._highlighter: QSyntaxHighlighter | None = None
        self._apply_mode("md")  # sets highlighter + placeholder text

        self._editor_area.textChanged.connect(self._on_html_changed)
        layout.addWidget(self._editor_area)

    # ── Public ─────────────────────────────────────────────────────────────────

    def load_entry(self, word: str, html: str):
        self._loaded_word = word
        self._dirty       = False
        stripped = html.strip()
        if stripped.startswith("@@@LINK="):
            text, new_mode = stripped, "html"
        elif is_markdown(html):
            text, new_mode = strip_marker(html), "md"
        elif not stripped:
            text, new_mode = "", self._mode  # keep current mode for blank entries
        else:
            text, new_mode = _format_html(html, '\t'), "html"
        self._editor_area._folded_lines.clear()
        self._editor_area._autopair_cursors.clear()
        self._editor_area.blockSignals(True)
        self._editor_area.setPlainText(text)
        self._editor_area.blockSignals(False)
        self._editor_area._update_ln_width()
        self._editor_area.update_fold_regions()
        if self.word_wrap_enabled():
            self._editor_area._apply_wrap_indents()
        self._set_status("已保存")
        self._apply_mode(new_mode)

    def clear(self):
        self._loaded_word = None
        self._dirty       = False
        self._editor_area.blockSignals(True)
        self._editor_area.clear()
        self._editor_area.blockSignals(False)
        self._editor_area._update_ln_width()
        self._editor_area._fold_regions.clear()
        self._editor_area._folded_lines.clear()
        self._editor_area._autopair_cursors.clear()
        self._editor_area._ln_area.update()
        self._set_status("—")
        self._apply_mode("md")

    def current_word(self) -> str:
        return self._loaded_word or ""

    def current_html(self) -> str:
        """Returns the value to store in the database (stored format)."""
        raw = self._editor_area.toPlainText()
        if raw.strip().startswith("@@@LINK="):
            return raw.strip()
        if self._mode == "md":
            return add_marker(raw)
        return _minify_html(raw)

    @property
    def editor_mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str):
        """Switch editor mode externally ('md' or 'html')."""
        if mode == self._mode:
            return
        self._apply_mode(mode)
        self._emit_preview()

    def raw_editor(self) -> QPlainTextEdit:
        return self._editor_area

    def save_now(self):
        if self._dirty:
            if self._loaded_word is None:
                stored = self.current_html()
                if stored.strip():
                    self.orphan_save_requested.emit(stored)
            else:
                self._auto_save()

    def is_dirty(self) -> bool:
        return self._dirty

    def set_autosave_ms(self, ms: int):
        self._autosave_ms = ms
        self._save_timer.setInterval(ms)

    def set_autosave_enabled(self, enabled: bool):
        self._autosave_enabled = enabled
        if not enabled:
            self._save_timer.stop()

    def set_tab_width(self, width: int):
        self._editor_area.set_tab_width(width)

    def set_html_trigger(self, enabled: bool):
        self._editor_area.set_html_trigger(enabled)

    def set_editor_font(self, family: str, size: float):
        self._editor_area.setFont(_make_editor_font(family, size))
        # Tab stop distance and wrap indents depend on font metrics; refresh both.
        self._editor_area.set_tab_width(self._editor_area._tab_width)
        if self.word_wrap_enabled():
            self._editor_area._apply_wrap_indents()

    def word_wrap_enabled(self) -> bool:
        return self._editor_area.lineWrapMode() != QPlainTextEdit.LineWrapMode.NoWrap

    def set_word_wrap(self, enabled: bool):
        mode = (QPlainTextEdit.LineWrapMode.WidgetWidth if enabled
                else QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor_area.setLineWrapMode(mode)
        if enabled:
            self._editor_area._apply_wrap_indents()
        else:
            self._editor_area._clear_wrap_indents()

    # ── Private ────────────────────────────────────────────────────────────────

    def _on_html_changed(self):
        self._editor_area._unfold_all()
        self._dirty = True
        self._set_status("未保存 ●", warn=True)
        self._preview_timer.start()
        if self._autosave_enabled and self._loaded_word:
            self._save_timer.start()

    def _render_for_preview(self) -> str:
        """Returns rendered HTML for live preview (converts MD if needed)."""
        raw = self._editor_area.toPlainText()
        if raw.strip().startswith("@@@LINK="):
            return raw.strip()
        if self._mode == "md":
            return md_to_html(raw)
        return _minify_html(raw)

    def _emit_preview(self):
        word = self.current_word()
        rendered = self._render_for_preview()
        if word or rendered:
            self.content_changed.emit(word, rendered)

    def _auto_save(self):
        word = self._loaded_word
        if not word:
            return
        stored = self.current_html()
        self.save_requested.emit(word, stored)
        self._dirty = False
        self._set_status("已保存")
        self._editor_area.update_fold_regions()
        if self.word_wrap_enabled():
            self._editor_area._apply_wrap_indents()

    def _apply_mode(self, mode: str):
        doc = self._editor_area.document()
        if self._highlighter is not None:
            self._highlighter.setDocument(None)
            self._highlighter = None
        self._mode = mode
        if mode == "md":
            self._highlighter = MarkdownHighlighter(doc)
            self._editor_area.setPlaceholderText(
                "Markdown 模式：# 标题  **粗体**  *斜体*  [链接](entry://词条)\n"
                "可直接嵌入 HTML 标签，如 <span class=\"zh\">中文</span>"
            )
        else:
            self._highlighter = HtmlHighlighter(doc)
            self._editor_area.setPlaceholderText(
                "HTML 模式：在此输入词条 HTML…\n重定向词条: @@@LINK=目标词条"
            )
        self.mode_changed.emit(mode)

    def _set_status(self, text: str, warn: bool = False):
        self.save_status_changed.emit(text, warn)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Save):
            self.save_now()
        else:
            super().keyPressEvent(event)
