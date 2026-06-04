from dataclasses import dataclass, field
from PySide6.QtGui import QPalette, QColor


@dataclass
class Theme:
    key: str
    name: str
    is_dark: bool
    preview_bg: str
    preview_fg: str
    preview_link: str
    preview_muted: str
    palette: QPalette = field(default_factory=QPalette, repr=False)


def _dark_palette() -> QPalette:
    p = QPalette()
    s = p.setColor
    R = QPalette.ColorRole
    G = QPalette.ColorGroup
    s(R.Window,          QColor(0x2b, 0x2b, 0x2b))
    s(R.WindowText,      QColor(0xe0, 0xe0, 0xe0))
    s(R.Base,            QColor(0x1e, 0x1e, 0x1e))
    s(R.AlternateBase,   QColor(0x35, 0x35, 0x35))
    s(R.Text,            QColor(0xe0, 0xe0, 0xe0))
    s(R.BrightText,      QColor(0xff, 0xff, 0xff))
    s(R.Button,          QColor(0x3a, 0x3a, 0x3a))
    s(R.ButtonText,      QColor(0xe0, 0xe0, 0xe0))
    s(R.Highlight,       QColor(0x2a, 0x82, 0xda))
    s(R.HighlightedText, QColor(0xff, 0xff, 0xff))
    s(R.Link,            QColor(0x66, 0x99, 0xff))
    s(R.ToolTipBase,     QColor(0x3a, 0x3a, 0x3a))
    s(R.ToolTipText,     QColor(0xe0, 0xe0, 0xe0))
    s(R.PlaceholderText, QColor(0x80, 0x80, 0x80))
    p.setColor(G.Disabled, R.WindowText, QColor(0x70, 0x70, 0x70))
    p.setColor(G.Disabled, R.Text,       QColor(0x70, 0x70, 0x70))
    p.setColor(G.Disabled, R.ButtonText, QColor(0x70, 0x70, 0x70))
    return p


def _sepia_palette() -> QPalette:
    p = QPalette()
    s = p.setColor
    R = QPalette.ColorRole
    s(R.Window,          QColor(0xf5, 0xf0, 0xe8))
    s(R.WindowText,      QColor(0x3c, 0x32, 0x28))
    s(R.Base,            QColor(0xfb, 0xf7, 0xf0))
    s(R.AlternateBase,   QColor(0xed, 0xe8, 0xdf))
    s(R.Text,            QColor(0x3c, 0x32, 0x28))
    s(R.Button,          QColor(0xe5, 0xdd, 0xd0))
    s(R.ButtonText,      QColor(0x3c, 0x32, 0x28))
    s(R.Highlight,       QColor(0x8b, 0x6b, 0x45))
    s(R.HighlightedText, QColor(0xff, 0xff, 0xff))
    s(R.Link,            QColor(0x7b, 0x5b, 0x35))
    s(R.PlaceholderText, QColor(0x9a, 0x8a, 0x80))
    return p


THEMES: dict[str, Theme] = {
    "light": Theme(
        key="light", name="浅色",
        is_dark=False,
        preview_bg="#ffffff", preview_fg="#1a1a1a",
        preview_link="#0066cc", preview_muted="#666666",
        palette=QPalette(),
    ),
    "dark": Theme(
        key="dark", name="深色",
        is_dark=True,
        preview_bg="#1e1e1e", preview_fg="#e0e0e0",
        preview_link="#6699ff", preview_muted="#aaaaaa",
        palette=_dark_palette(),
    ),
    "sepia": Theme(
        key="sepia", name="护眼",
        is_dark=False,
        preview_bg="#fbf7f0", preview_fg="#3c3228",
        preview_link="#7b5b35", preview_muted="#7a6a60",
        palette=_sepia_palette(),
    ),
}
