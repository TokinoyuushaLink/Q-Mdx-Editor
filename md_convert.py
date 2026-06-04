from __future__ import annotations
import markdown as _md

_MD_MARKER = "<!--md-->"
_EXTENSIONS = ["extra", "nl2br", "sane_lists"]
_MD_INSTANCE = _md.Markdown(extensions=_EXTENSIONS)


def is_markdown(text: str) -> bool:
    return text.startswith(_MD_MARKER)


def strip_marker(text: str) -> str:
    return text.removeprefix(_MD_MARKER).lstrip("\n")


def add_marker(text: str) -> str:
    if not text.strip():
        return ""
    return f"{_MD_MARKER}\n{text}"


def md_to_html(text: str) -> str:
    if not text.strip():
        return ""
    _MD_INSTANCE.reset()
    return _MD_INSTANCE.convert(text)
