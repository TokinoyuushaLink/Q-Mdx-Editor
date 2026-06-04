"""MDX ↔ SQLite conversion — reuses the same logic as mdx2db.py from the Mac app."""

import re
import sqlite3
import struct
from pathlib import Path
from typing import Callable, Optional

from md_convert import is_markdown, strip_marker, md_to_html

CSS_LINK_RE = re.compile(
    r'<link[^>]+rel=["\']stylesheet["\'][^>]*/?\>', re.IGNORECASE
)


def _patch_lzo():
    try:
        import mdict_utils.base.readmdict as _rdm
        if _rdm.lzo is not None:
            return
        import mdict_utils.base.lzo as _lzo_py

        class _LzoAdapter:
            @staticmethod
            def decompress(data: bytes) -> bytes:
                decompressed_size = struct.unpack(">I", data[1:5])[0]
                return _lzo_py.decompress(data[5:], initSize=decompressed_size)

        _rdm.lzo = _LzoAdapter
    except Exception:
        pass


def import_mdx(
    mdx_path: str,
    db_path: str,
    progress: Optional[Callable[[int], None]] = None,
) -> int:
    _patch_lzo()
    from mdict_utils.base.readmdict import MDX

    mdx = Path(mdx_path)
    css_path = mdx.with_suffix(".css")
    css_content: Optional[str] = None
    if css_path.exists():
        css_content = css_path.read_text(encoding="utf-8", errors="ignore")

    reader = MDX(str(mdx))

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS entries")
    cur.execute("DROP TABLE IF EXISTS meta")
    cur.execute("CREATE TABLE entries (word TEXT, html TEXT)")
    cur.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("PRAGMA journal_mode=WAL")

    if css_content:
        cur.execute("INSERT INTO meta VALUES (?, ?)", ("css", css_content))

    count = 0
    batch: list[tuple[str, str]] = []

    for key, val in reader.items():
        word = key.decode("utf-8", "ignore") if isinstance(key, bytes) else key
        html = val.decode("utf-8", "ignore") if isinstance(val, bytes) else val
        word = word.strip()
        if not word:
            continue
        html = CSS_LINK_RE.sub("", html)
        batch.append((word, html))
        count += 1
        if len(batch) >= 2000:
            cur.executemany("INSERT INTO entries VALUES (?, ?)", batch)
            batch.clear()
            if progress:
                progress(count)

    if batch:
        cur.executemany("INSERT INTO entries VALUES (?, ?)", batch)

    cur.execute("CREATE INDEX idx_word ON entries(word COLLATE NOCASE)")
    conn.commit()
    conn.close()
    return count


def export_mdx(
    db_path: str,
    mdx_path: str,
    title: str = "",
    description: str = "",
    progress: Optional[Callable[[int], None]] = None,
) -> int:
    from mdict_utils.base.writemdict import MDictWriter

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT word, html FROM entries ORDER BY word COLLATE NOCASE"
    ).fetchall()
    conn.close()

    entries: dict[str, str] = {}
    for i, (word, html) in enumerate(rows):
        if is_markdown(html):
            html = md_to_html(strip_marker(html))
        entries[word] = html
        if progress and i % 1000 == 0:
            progress(i)

    writer = MDictWriter(
        entries,
        title=title or "Dictionary",
        description=description or "",
    )
    with open(mdx_path, "wb") as f:
        writer.write(f)

    return len(entries)
