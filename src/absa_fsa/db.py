"""SQLite: lưu bài, câu, và trạng thái crawl.

Khử trùng lặp dựa vào ràng buộc UNIQUE trên articles.url — đây là khóa cứng,
không phụ thuộc mốc thời gian (vài feed có timestamp sai).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from . import config

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS articles (
    doc_id        TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    source_name   TEXT NOT NULL,
    lang          TEXT NOT NULL CHECK (lang IN ('vi','en')),
    url           TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    body          TEXT NOT NULL,
    summary       TEXT,
    section       TEXT,
    published_at  TEXT,
    fetched_at    TEXT NOT NULL,
    n_sentences   INTEGER NOT NULL DEFAULT 0,
    n_chars       INTEGER NOT NULL DEFAULT 0,
    content_sha1  TEXT,
    is_backfill   INTEGER NOT NULL DEFAULT 0,
    in_scope      INTEGER            -- NULL = chưa qua model
);

CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source    ON articles(source);

CREATE TABLE IF NOT EXISTS sentences (
    sent_id    TEXT PRIMARY KEY,
    doc_id     TEXT NOT NULL REFERENCES articles(doc_id) ON DELETE CASCADE,
    sent_idx   INTEGER NOT NULL,
    text       TEXT NOT NULL,
    char_len   INTEGER NOT NULL,
    is_title   INTEGER NOT NULL DEFAULT 0,
    lang       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending | done
    UNIQUE (doc_id, sent_idx)
);

CREATE INDEX IF NOT EXISTS idx_sentences_doc    ON sentences(doc_id);
CREATE INDEX IF NOT EXISTS idx_sentences_status ON sentences(status);

-- Bộ ba model trả về. Một câu có thể có 0..n dòng; 0 dòng = ngoài phạm vi.
-- Offset target_start/target_end tính trên đúng chuỗi sentences.text.
CREATE TABLE IF NOT EXISTS triplets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_id       TEXT NOT NULL REFERENCES sentences(sent_id) ON DELETE CASCADE,
    target_text   TEXT NOT NULL,
    target_start  INTEGER NOT NULL,
    target_end    INTEGER NOT NULL,
    canonical_id  TEXT,              -- SBV, VN-INDEX, VND, HPG... NULL nếu chưa chuẩn hóa được
    target_type   TEXT CHECK (target_type IN ('company','agency','currency','index')),
    aspect_l1     TEXT NOT NULL,
    aspect_l2     TEXT NOT NULL,
    sentiment     TEXT NOT NULL CHECK (sentiment IN ('positive','negative','neutral')),
    model_version TEXT,
    CHECK (target_start >= 0 AND target_end > target_start)
);

CREATE INDEX IF NOT EXISTS idx_triplets_sent   ON triplets(sent_id);
CREATE INDEX IF NOT EXISTS idx_triplets_target ON triplets(canonical_id, aspect_l2);

CREATE TABLE IF NOT EXISTS crawl_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    is_backfill   INTEGER NOT NULL DEFAULT 0,
    n_feed_items  INTEGER NOT NULL DEFAULT 0,
    n_new         INTEGER NOT NULL DEFAULT 0,
    n_skipped     INTEGER NOT NULL DEFAULT 0,
    n_failed      INTEGER NOT NULL DEFAULT 0,
    n_sentences   INTEGER NOT NULL DEFAULT 0,
    note          TEXT
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or config.DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------- #

def url_exists(conn: sqlite3.Connection, url: str) -> bool:
    return conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone() is not None


def known_urls(conn: sqlite3.Connection) -> set[str]:
    """Nạp sẵn toàn bộ URL để lọc feed không cần truy vấn từng cái."""
    return {r[0] for r in conn.execute("SELECT url FROM articles")}


def insert_article(conn: sqlite3.Connection, art: dict) -> bool:
    """Trả False nếu bài đã tồn tại (URL trùng)."""
    cur = conn.execute(
        """INSERT OR IGNORE INTO articles
           (doc_id, source, source_name, lang, url, title, body, summary, section,
            published_at, fetched_at, n_sentences, n_chars, content_sha1, is_backfill)
           VALUES (:doc_id, :source, :source_name, :lang, :url, :title, :body, :summary,
                   :section, :published_at, :fetched_at, :n_sentences, :n_chars,
                   :content_sha1, :is_backfill)""",
        art,
    )
    return cur.rowcount > 0


def insert_sentences(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    cur = conn.executemany(
        """INSERT OR IGNORE INTO sentences
           (sent_id, doc_id, sent_idx, text, char_len, is_title, lang)
           VALUES (:sent_id, :doc_id, :sent_idx, :text, :char_len, :is_title, :lang)""",
        rows,
    )
    return cur.rowcount


def insert_triplets(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    cur = conn.executemany(
        """INSERT INTO triplets
           (sent_id, target_text, target_start, target_end, canonical_id, target_type,
            aspect_l1, aspect_l2, sentiment, model_version)
           VALUES (:sent_id, :target_text, :target_start, :target_end, :canonical_id,
                   :target_type, :aspect_l1, :aspect_l2, :sentiment, :model_version)""",
        rows,
    )
    return cur.rowcount


def start_run(conn: sqlite3.Connection, is_backfill: bool) -> int:
    cur = conn.execute(
        "INSERT INTO crawl_runs (started_at, is_backfill) VALUES (?, ?)",
        (utcnow(), int(is_backfill)),
    )
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, **stats) -> None:
    conn.execute(
        """UPDATE crawl_runs SET finished_at = ?, n_feed_items = ?, n_new = ?,
               n_skipped = ?, n_failed = ?, n_sentences = ?, note = ?
           WHERE run_id = ?""",
        (utcnow(), stats.get("n_feed_items", 0), stats.get("n_new", 0),
         stats.get("n_skipped", 0), stats.get("n_failed", 0),
         stats.get("n_sentences", 0), stats.get("note"), run_id),
    )


def is_first_run(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
    return row[0] == 0


def stats(conn: sqlite3.Connection) -> dict:
    out: dict = {}
    out["articles"] = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    out["sentences"] = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    out["by_source"] = [
        dict(r) for r in conn.execute(
            """SELECT source, lang, COUNT(*) AS n,
                      SUM(is_backfill) AS backfill,
                      MIN(published_at) AS oldest, MAX(published_at) AS newest
               FROM articles GROUP BY source, lang ORDER BY n DESC"""
        )
    ]
    out["runs"] = [
        dict(r) for r in conn.execute(
            "SELECT * FROM crawl_runs ORDER BY run_id DESC LIMIT 5"
        )
    ]
    return out
