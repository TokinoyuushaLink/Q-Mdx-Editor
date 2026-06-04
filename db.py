import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional


def _t(label: str, t0: float):
    print(f"[db] {label}: {(time.perf_counter()-t0)*1000:.1f}ms", file=sys.stderr, flush=True)


class DictDB:
    def __init__(self, path: str):
        self.path = path
        t = time.perf_counter()
        self.conn = sqlite3.connect(path, check_same_thread=False); _t("connect", t)
        t = time.perf_counter()
        self.conn.execute("PRAGMA journal_mode=WAL");          _t("WAL pragma", t)
        t = time.perf_counter()
        self.conn.execute("PRAGMA cache_size=-65536")
        self.conn.execute("PRAGMA mmap_size=268435456")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.conn.execute("PRAGMA synchronous=NORMAL");        _t("other pragmas", t)
        t = time.perf_counter()
        self._ensure_schema();                                  _t("ensure_schema", t)

    def _ensure_schema(self):
        cur = self.conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS entries (word TEXT, html TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_word ON entries(word COLLATE NOCASE)"
        )
        self.conn.commit()

    def close(self):
        # Consolidate WAL into the main file so next open is fast
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        self.conn.close()

    # ── Word list ──────────────────────────────────────────────────────────────

    def all_words(self) -> list[str]:
        t = time.perf_counter()
        cur = self.conn.execute(
            "SELECT DISTINCT word FROM entries ORDER BY word COLLATE NOCASE"
        )
        rows = cur.fetchall()
        result = [r[0] for r in rows]
        _t(f"all_words ({len(result)})", t)
        return result

    def search(self, prefix: str, limit: int = 300) -> list[str]:
        if not prefix.strip():
            return self.all_words()
        escaped = prefix.replace("%", "\\%").replace("_", "\\_")
        cur = self.conn.execute(
            "SELECT DISTINCT word FROM entries "
            "WHERE word LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "ORDER BY length(word), word COLLATE NOCASE LIMIT ?",
            (escaped + "%", limit),
        )
        return [r[0] for r in cur.fetchall()]

    def word_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(DISTINCT word) FROM entries"
        ).fetchone()[0]

    # ── Entry CRUD ─────────────────────────────────────────────────────────────

    def get_entry(self, word: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT html FROM entries WHERE word = ? COLLATE NOCASE LIMIT 1", (word,)
        ).fetchone()
        return row[0] if row else None

    def set_entry(self, word: str, html: str):
        with self.conn:
            self.conn.execute(
                "DELETE FROM entries WHERE word = ? COLLATE NOCASE", (word,)
            )
            self.conn.execute(
                "INSERT INTO entries (word, html) VALUES (?, ?)", (word, html)
            )

    def rename_entry(self, old_word: str, new_word: str, html: str):
        with self.conn:
            self.conn.execute(
                "DELETE FROM entries WHERE word = ? COLLATE NOCASE", (old_word,)
            )
            self.conn.execute(
                "DELETE FROM entries WHERE word = ? COLLATE NOCASE", (new_word,)
            )
            self.conn.execute(
                "INSERT INTO entries (word, html) VALUES (?, ?)", (new_word, html)
            )

    def delete_entry(self, word: str):
        with self.conn:
            self.conn.execute(
                "DELETE FROM entries WHERE word = ? COLLATE NOCASE", (word,)
            )

    def all_entries(self) -> list[tuple[str, str]]:
        cur = self.conn.execute(
            "SELECT word, html FROM entries ORDER BY word COLLATE NOCASE"
        )
        return cur.fetchall()

    # ── Meta ───────────────────────────────────────────────────────────────────

    def get_meta(self, key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = ? LIMIT 1", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
            )

    def delete_meta(self, key: str):
        with self.conn:
            self.conn.execute("DELETE FROM meta WHERE key = ?", (key,))
