"""Luồng crawl: feed -> lọc link mới -> tải bài -> bóc -> tách câu -> DB."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config, db
from .config import Source
from .extract import extract
from .feeds import parse_feed
from .fetch import Fetcher
from .textnorm import normalize, split_sentences

log = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0.0"


# --------------------------------------------------------------------------- #
# Định danh
# --------------------------------------------------------------------------- #

def make_doc_id(source_slug: str, url: str, published_at: datetime | None) -> str:
    """Ổn định giữa các lần chạy: cùng URL -> cùng doc_id."""
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    day = published_at.astimezone(timezone.utc).strftime("%Y%m%d") if published_at else "00000000"
    return f"{source_slug}_{day}_{h}"


def make_sent_id(doc_id: str, idx: int) -> str:
    return f"{doc_id}#{idx}"


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Crawl
# --------------------------------------------------------------------------- #

def build_sentences(doc_id: str, title: str, body: str, lang: str) -> list[dict]:
    """Câu đầu tiên là tiêu đề, sau đó là các câu trong thân bài.

    Offset của câu tính trên chính `body` đã chuẩn hóa — không chuẩn hóa lại
    sau bước này, nếu không span sẽ lệch.
    """
    rows: list[dict] = []
    idx = 0
    if title:
        rows.append({
            "sent_id": make_sent_id(doc_id, idx), "doc_id": doc_id, "sent_idx": idx,
            "text": title, "char_len": len(title), "is_title": 1, "lang": lang,
        })
        idx += 1
    for s, e in split_sentences(body):
        txt = body[s:e]
        rows.append({
            "sent_id": make_sent_id(doc_id, idx), "doc_id": doc_id, "sent_idx": idx,
            "text": txt, "char_len": len(txt), "is_title": 0, "lang": lang,
        })
        idx += 1
    return rows


def _ingest(
    conn: sqlite3.Connection,
    fetcher: Fetcher,
    src: Source,
    url: str,
    published_at: datetime | None,
    summary: str,
    title_hint: str,
    is_backfill: bool,
    seen: set[str],
    st: dict,
) -> bool:
    """Tải một bài, bóc nội dung, tách câu, lưu DB. Dùng chung cho crawl RSS và lấy lùi sitemap."""
    html = fetcher.get(url)
    if not html:
        st["failed"] += 1
        return False

    art = extract(html, url)
    title = art.title or title_hint
    body = normalize(art.body)
    if not art.ok and not body:
        log.warning("[%s] bóc rỗng: %s", src.slug, url)
        st["failed"] += 1
        return False

    doc_id = make_doc_id(src.slug, url, published_at)
    sents = build_sentences(doc_id, title, body, src.lang)
    row = {
        "doc_id": doc_id,
        "source": src.slug,
        "source_name": src.name,
        "lang": src.lang,
        "url": url,
        "title": title,
        "body": body,
        "summary": summary,
        "section": src.section,
        "published_at": published_at.isoformat() if published_at else None,
        "fetched_at": db.utcnow(),
        "n_sentences": len(sents),
        "n_chars": len(body),
        "content_sha1": sha1(body),
        "is_backfill": int(is_backfill),
    }
    if not db.insert_article(conn, row):
        st["skipped"] += 1
        return False
    db.insert_sentences(conn, sents)
    seen.add(url)
    st["new"] += 1
    st["sentences"] += len(sents)
    log.info("[%s] + %s (%d câu)", src.slug, title[:62], len(sents))
    return True


def crawl_source(
    conn: sqlite3.Connection,
    fetcher: Fetcher,
    src: Source,
    seen: set[str],
    is_backfill: bool,
    limit: int = 0,
) -> dict:
    st = {"feed_items": 0, "new": 0, "skipped": 0, "failed": 0, "sentences": 0}

    raw = fetcher.get(src.feed_url, check_robots=False)
    if not raw:
        log.error("[%s] không tải được feed", src.slug)
        return st

    items = parse_feed(raw)
    st["feed_items"] = len(items)
    log.info("[%s] feed có %d bài", src.slug, len(items))

    todo = [it for it in items if it.url not in seen]
    st["skipped"] = len(items) - len(todo)
    if limit:
        todo = todo[:limit]

    for it in todo:
        _ingest(conn, fetcher, src, it.url, it.published_at, it.summary, it.title, is_backfill, seen, st)

    conn.commit()
    return st


def crawl(sources: list[Source] | None = None, limit: int = 0) -> dict:
    sources = sources or config.SOURCES
    total = {"feed_items": 0, "new": 0, "skipped": 0, "failed": 0, "sentences": 0}

    with db.session() as conn:
        backfill = db.is_first_run(conn)
        if backfill:
            log.info("Lần chạy đầu -> lấy hết bài đang có trong feed, gắn cờ is_backfill")
        run_id = db.start_run(conn, backfill)
        seen = db.known_urls(conn)
        fetcher = Fetcher()

        for src in sources:
            # Nguồn mới thêm vào DB đã có dữ liệu: lần đầu của riêng nó kéo về cả cửa sổ feed (cũ),
            # nên cũng phải gắn is_backfill như lần chạy đầu của cả hệ thống.
            first = backfill or not conn.execute("SELECT 1 FROM articles WHERE source = ? LIMIT 1", (src.slug,)).fetchone()
            if first and not backfill:
                log.info("[%s] nguồn mới -> lần đầu, gắn cờ is_backfill", src.slug)
            st = crawl_source(conn, fetcher, src, seen, first, limit)
            for k in total:
                total[k] += st[k]

        db.finish_run(
            conn, run_id,
            n_feed_items=total["feed_items"], n_new=total["new"],
            n_skipped=total["skipped"], n_failed=total["failed"],
            n_sentences=total["sentences"],
            note="backfill" if backfill else "incremental",
        )
    total["is_backfill"] = backfill
    return total


def backfill(sources: list[Source] | None = None, days: int = 30, limit: int = 0) -> dict:
    """Lấy lùi `days` ngày gần nhất qua sitemap, cho những nguồn có khai báo sitemap.

    RSS chỉ giữ vài chục bài mới nhất nên không lùi được; sitemap thì chứa cả lịch sử.
    Bài đã có (theo URL) bị bỏ qua. Bài lấy lùi gắn is_backfill=1.
    """
    from . import sitemap
    from datetime import timedelta

    sources = [s for s in (sources or config.SOURCES) if s.sitemap]
    total = {"feed_items": 0, "new": 0, "skipped": 0, "failed": 0, "sentences": 0}
    since = datetime.now(timezone.utc) - timedelta(days=days)

    with db.session() as conn:
        run_id = db.start_run(conn, True)
        seen = db.known_urls(conn)
        seen_norm = {sitemap.norm_url(u) for u in seen}
        fetcher = Fetcher()
        for src in sources:
            items = sitemap.recent(fetcher, src, since)
            todo = [i for i in items if sitemap.norm_url(i.url) not in seen_norm]
            total["feed_items"] += len(items)
            total["skipped"] += len(items) - len(todo)
            if limit:
                todo = todo[:limit]
            log.info("[%s] sitemap có %d bài trong %d ngày, %d bài chưa có -> tải", src.slug, len(items), days, len(todo))
            st = {"feed_items": 0, "new": 0, "skipped": 0, "failed": 0, "sentences": 0}
            for n, it in enumerate(todo, 1):
                if _ingest(conn, fetcher, src, it.url, it.published_at, "", "", True, seen, st):
                    seen_norm.add(sitemap.norm_url(it.url))
                if n % 20 == 0:
                    conn.commit()                      # lưu dần, lỡ dừng giữa chừng không mất công
                    log.info("[%s] tiến độ %d/%d (mới %d, lỗi %d)", src.slug, n, len(todo), st["new"], st["failed"])
            conn.commit()
            for k in ("new", "skipped", "failed", "sentences"):
                total[k] += st[k]
        db.finish_run(conn, run_id, n_feed_items=total["feed_items"], n_new=total["new"],
                      n_skipped=total["skipped"], n_failed=total["failed"],
                      n_sentences=total["sentences"], note=f"sitemap-backfill {days}d")
    return total


# --------------------------------------------------------------------------- #
# Xuất JSON
# --------------------------------------------------------------------------- #

# Trường trong file câu — ĐẦU VÀO CỦA MODEL.
# Cố tình không có: char_len (= len(text)), status (trạng thái nội bộ),
# url/source/published_at (đã có trong data/absa.db, model không dùng).
SENTENCE_FIELDS = ("sent_id", "doc_id", "sent_idx", "text", "lang", "is_title")


def _sentence_row(r) -> dict:
    return {
        "sent_id": r["sent_id"],
        "doc_id": r["doc_id"],
        "sent_idx": r["sent_idx"],
        "text": r["text"],
        "lang": r["lang"],
        "is_title": bool(r["is_title"]),
    }


def export_jsonl(
    day: str | None = None,
    out_dir: Path | None = None,
    split_by_article: bool = True,
) -> dict:
    """Xuất câu — ĐẦU VÀO CỦA MODEL.

    split_by_article=True  -> mỗi bài một file <doc_id>.json, nội dung là
                              mảng JSON thụt lề (dễ đọc; file nhỏ, 2-20 KB
                              nên không cần đọc theo dòng)
    split_by_article=False -> gộp vào sentences.jsonl, mỗi dòng một câu
                              (file lớn, giữ JSONL để đọc theo dòng)
    day = 'YYYY-MM-DD' theo giờ VN; None = xuất tất cả.
    """
    out_dir = out_dir or (config.EXPORT_DIR / (day or "all"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Ngày tính theo giờ VN. Mỗi báo ghi published_at ở múi giờ khác nhau
    # (VnEconomy dùng UTC, VietnamNews dùng +07:00) nên phải quy đổi,
    # không được cắt chuỗi thô.
    VN_DAY = "substr(datetime(a.published_at, '+7 hours'), 1, 10)"

    where, params = "", ()
    if day:
        where = f"WHERE {VN_DAY} = ?"
        params = (day,)

    sql = f"""SELECT s.sent_id, s.doc_id, s.sent_idx, s.text, s.lang, s.is_title
              FROM sentences s JOIN articles a USING (doc_id)
              {where} ORDER BY a.published_at, s.doc_id, s.sent_idx"""

    n_sent = 0
    docs: set[str] = set()

    with db.session() as conn:
        if split_by_article:
            # gom theo bài rồi ghi cả mảng một lần, để thụt lề đúng
            by_doc: dict[str, list[dict]] = {}
            for r in conn.execute(sql, params):
                by_doc.setdefault(r["doc_id"], []).append(_sentence_row(r))
                n_sent += 1
            for doc_id, rows in by_doc.items():
                (out_dir / f"{doc_id}.json").write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                docs.add(doc_id)
        else:
            with open(out_dir / "sentences.jsonl", "w", encoding="utf-8") as f:
                for r in conn.execute(sql, params):
                    docs.add(r["doc_id"])
                    f.write(json.dumps(_sentence_row(r), ensure_ascii=False) + "\n")
                    n_sent += 1

    return {
        "dir": str(out_dir),
        "articles": len(docs),
        "sentences": n_sent,
        "files": len(docs) if split_by_article else 1,
    }
