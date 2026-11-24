"""API cho web: các truy vấn gộp nhóm trên bảng triplets.

Chỉ ĐỌC. Mở DB ở chế độ read-only nên không thể làm hỏng dữ liệu, và đọc được
song song với crawler đang ghi (SQLite WAL).

Chỉ số chính (slide 22): net = (số positive − số negative) / tổng số bộ ba.
Mọi ngày tính theo giờ Việt Nam. Mọi endpoint trả kèm n để giao diện biết con số
dựa trên bao nhiêu mẫu — net +1,0 từ 2 câu khác hẳn net +0,3 từ 200 câu.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .scheme import ASPECT_L2, ASPECT_SCHEME, L2_TO_L1, SENTIMENTS

DAY = "substr(datetime(a.published_at, '+7 hours'), 1, 10)"
FROM = """FROM triplets t
          JOIN sentences s ON s.sent_id = t.sent_id
          JOIN articles  a ON a.doc_id  = s.doc_id"""
DATE_RX = r"^\d{4}-\d{2}-\d{2}$"
MOCK_PREFIX = "mock"


# --------------------------------------------------------------------------- #
# Kiểu trả về
# --------------------------------------------------------------------------- #

class Counts(BaseModel):
    n: int
    pos: int
    neg: int
    neu: int
    net: float | None        # None khi n = 0


class Point(Counts):
    day: str


class Series(BaseModel):
    key: str
    n: int
    points: list[Point]


class SeriesOut(BaseModel):
    group: str
    start: str | None
    end: str | None
    series: list[Series]
    all: Series              # gộp mọi bộ ba thỏa bộ lọc


class TargetRow(Counts):
    canonical_id: str
    target_type: str | None


class Cell(Counts):
    canonical_id: str
    aspect_l2: str


class MatrixOut(BaseModel):
    targets: list[str]
    aspects: list[str]
    cells: list[Cell]


class TraceItem(BaseModel):
    triplet_id: int
    sent_id: str
    text: str
    target_text: str
    target_start: int
    target_end: int
    canonical_id: str | None
    aspect_l1: str
    aspect_l2: str
    sentiment: str
    doc_id: str
    title: str
    url: str
    source_name: str
    published_at: str
    day: str


class TraceOut(BaseModel):
    total: int
    items: list[TraceItem]


class ArticleSentence(BaseModel):
    sent_id: str
    sent_idx: int
    text: str
    is_title: bool
    triplets: list[dict]


class ArticleOut(BaseModel):
    doc_id: str
    title: str
    url: str
    source_name: str
    published_at: str | None
    sentences: list[ArticleSentence]


# --------------------------------------------------------------------------- #
# Truy vấn
# --------------------------------------------------------------------------- #

def _net(pos: int, neg: int, n: int) -> float | None:
    return round((pos - neg) / n, 4) if n else None


def _counts(row) -> dict:
    n = row["n"] or 0
    pos, neg, neu = row["pos"] or 0, row["neg"] or 0, row["neu"] or 0
    return {"n": n, "pos": pos, "neg": neg, "neu": neu, "net": _net(pos, neg, n)}


_AGG = """COUNT(*) AS n,
          SUM(t.sentiment = 'positive') AS pos,
          SUM(t.sentiment = 'negative') AS neg,
          SUM(t.sentiment = 'neutral')  AS neu"""


def _where(start=None, end=None, target=None, aspect=None, sentiment=None):
    """Ghép điều kiện lọc. Luôn dùng tham số, không nối chuỗi từ người dùng."""
    cond, args = ["a.published_at IS NOT NULL"], []
    if start:
        cond.append(f"{DAY} >= ?"); args.append(start)
    if end:
        cond.append(f"{DAY} <= ?"); args.append(end)
    if target:
        cond.append("t.canonical_id = ?"); args.append(target)
    if aspect:
        cond.append("t.aspect_l2 = ?"); args.append(aspect)
    if sentiment:
        cond.append("t.sentiment = ?"); args.append(sentiment)
    return " WHERE " + " AND ".join(cond), args


def _check_range(start: str | None, end: str | None) -> None:
    for v in (start, end):
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise HTTPException(422, f"ngày không hợp lệ: {v}")
    if start and end and start > end:
        raise HTTPException(422, "start phải <= end")


def _check_aspect(aspect: str | None) -> None:
    if aspect and aspect not in ASPECT_L2:
        raise HTTPException(422, f"aspect không có trong lược đồ: {aspect}")


def _data_range(conn: sqlite3.Connection) -> tuple[str | None, str | None]:
    r = conn.execute(f"SELECT MIN({DAY}), MAX({DAY}) {FROM} WHERE a.published_at IS NOT NULL").fetchone()
    return r[0], r[1]


def _days(start: str | None, end: str | None) -> list[str]:
    if not start or not end:
        return []
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return [(a + timedelta(d)).isoformat() for d in range((b - a).days + 1)]


def _series(conn, days: list[str], key: str, **flt) -> Series:
    """Một chuỗi theo ngày, điền 0 vào ngày không có dữ liệu để trục thời gian liên tục."""
    w, args = _where(**flt)
    got = {r["day"]: r for r in conn.execute(
        f"SELECT {DAY} AS day, {_AGG} {FROM} {w} GROUP BY day", args)}
    pts, total = [], 0
    for d in days:
        c = _counts(got[d]) if d in got else {"n": 0, "pos": 0, "neg": 0, "neu": 0, "net": None}
        total += c["n"]
        pts.append(Point(day=d, **c))
    return Series(key=key, n=total, points=pts)


# --------------------------------------------------------------------------- #
# Ứng dụng
# --------------------------------------------------------------------------- #

def create_app(db_path: Path | None = None) -> FastAPI:
    path = Path(db_path or config.WEB_DB_PATH)
    app = FastAPI(title="ABSA financial sentiment API", version="0.1.0")

    def get_conn() -> Iterator[sqlite3.Connection]:
        if not path.exists():
            raise HTTPException(503, f"chưa có DB: {path}")
        # FastAPI tạo kết nối ở một luồng và chạy hàm xử lý ở luồng khác, nên phải cho
        # phép dùng chéo luồng. An toàn vì mỗi request có kết nối riêng, chỉ-đọc, dùng tuần tự.
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    Conn = Depends(get_conn)

    @app.get("/api/meta")
    def meta(conn: sqlite3.Connection = Conn) -> dict:
        """Thông tin để dựng bộ lọc, và cờ is_mock để hiện biểu ngữ DỮ LIỆU MẪU."""
        lo, hi = _data_range(conn)
        one = lambda q: conn.execute(q).fetchone()[0]
        n_trip = one("SELECT COUNT(*) FROM triplets")
        n_mock = one(f"SELECT COUNT(*) FROM triplets WHERE model_version LIKE '{MOCK_PREFIX}%'")
        return {
            "is_mock": bool(n_trip) and n_mock == n_trip,
            "db": path.name,
            "start": lo, "end": hi,
            "articles": one("SELECT COUNT(*) FROM articles"),
            "sentences": one("SELECT COUNT(*) FROM sentences"),
            "triplets": n_trip,
            "sentiments": list(SENTIMENTS),
            "aspects": [{"l1": l1, "l2": l2} for l1, v in ASPECT_SCHEME.items() for l2 in v],
            "targets": [dict(r) for r in conn.execute(
                """SELECT canonical_id AS id, target_type AS type, COUNT(*) AS n
                   FROM triplets WHERE canonical_id IS NOT NULL
                   GROUP BY 1, 2 ORDER BY n DESC""")],
        }

    @app.get("/api/targets", response_model=list[TargetRow])
    def targets(
        start: str | None = Query(None, pattern=DATE_RX),
        end: str | None = Query(None, pattern=DATE_RX),
        aspect: str | None = None,
        limit: int = Query(20, ge=1, le=200),
        conn: sqlite3.Connection = Conn,
    ):
        """Xếp hạng chủ thể theo khối lượng, kèm net sentiment."""
        _check_range(start, end); _check_aspect(aspect)
        w, args = _where(start, end, aspect=aspect)
        rows = conn.execute(
            f"""SELECT t.canonical_id, t.target_type, {_AGG} {FROM}
                {w} AND t.canonical_id IS NOT NULL
                GROUP BY 1, 2 ORDER BY n DESC, t.canonical_id LIMIT ?""", args + [limit])
        return [TargetRow(canonical_id=r["canonical_id"], target_type=r["target_type"], **_counts(r))
                for r in rows]

    @app.get("/api/series", response_model=SeriesOut)
    def series(
        group: str = Query("target", pattern="^(target|aspect)$"),
        keys: list[str] = Query(default=[]),
        target: str | None = None,
        aspect: str | None = None,
        start: str | None = Query(None, pattern=DATE_RX),
        end: str | None = Query(None, pattern=DATE_RX),
        top: int = Query(5, ge=1, le=20),
        conn: sqlite3.Connection = Conn,
    ):
        """Chuỗi theo ngày. group=target: mỗi đường một chủ thể; group=aspect: mỗi đường
        một khía cạnh. Bỏ trống `keys` thì lấy `top` khóa có nhiều bộ ba nhất.
        `target`/`aspect` lọc thêm theo chiều còn lại."""
        _check_range(start, end); _check_aspect(aspect)
        lo, hi = _data_range(conn)
        start, end = start or lo, end or hi
        days = _days(start, end)

        col = "t.canonical_id" if group == "target" else "t.aspect_l2"
        if group == "aspect":
            for k in keys:
                _check_aspect(k)
        flt = dict(start=start, end=end, target=target, aspect=aspect)

        if not keys:
            w, args = _where(**flt)
            keys = [r[0] for r in conn.execute(
                f"""SELECT {col} {FROM} {w} AND {col} IS NOT NULL
                    GROUP BY 1 ORDER BY COUNT(*) DESC, 1 LIMIT ?""", args + [top])]

        out = []
        for k in keys:
            f = dict(flt)
            f["target" if group == "target" else "aspect"] = k
            out.append(_series(conn, days, k, **f))
        return SeriesOut(group=group, start=start, end=end, series=out,
                         all=_series(conn, days, "all", **flt))

    @app.get("/api/matrix", response_model=MatrixOut)
    def matrix(
        start: str | None = Query(None, pattern=DATE_RX),
        end: str | None = Query(None, pattern=DATE_RX),
        top: int = Query(12, ge=1, le=50),
        conn: sqlite3.Connection = Conn,
    ):
        """Ma trận nhiệt chủ thể × khía cạnh. Chỉ trả ô có dữ liệu; ô trống để giao diện
        tự vẽ ô xám. `top` giới hạn số chủ thể (theo khối lượng)."""
        _check_range(start, end)
        w, args = _where(start, end)
        tops = [r[0] for r in conn.execute(
            f"""SELECT t.canonical_id {FROM} {w} AND t.canonical_id IS NOT NULL
                GROUP BY 1 ORDER BY COUNT(*) DESC, 1 LIMIT ?""", args + [top])]
        if not tops:
            return MatrixOut(targets=[], aspects=list(ASPECT_L2), cells=[])
        ph = ",".join("?" * len(tops))
        rows = conn.execute(
            f"""SELECT t.canonical_id, t.aspect_l2, {_AGG} {FROM}
                {w} AND t.canonical_id IN ({ph}) GROUP BY 1, 2""", args + tops)
        cells = [Cell(canonical_id=r["canonical_id"], aspect_l2=r["aspect_l2"], **_counts(r))
                 for r in rows]
        return MatrixOut(targets=tops, aspects=list(ASPECT_L2), cells=cells)

    @app.get("/api/trace", response_model=TraceOut)
    def trace(
        target: str | None = None,
        aspect: str | None = None,
        sentiment: str | None = Query(None, pattern="^(positive|negative|neutral)$"),
        start: str | None = Query(None, pattern=DATE_RX),
        end: str | None = Query(None, pattern=DATE_RX),
        limit: int = Query(20, ge=1, le=200),
        offset: int = Query(0, ge=0),
        conn: sqlite3.Connection = Conn,
    ):
        """Truy vết: từ một ô của biểu đồ xuống từng câu gốc, kèm vị trí target để
        giao diện highlight, và bài báo chứa nó. Sắp mới → cũ theo thời điểm thực
        (datetime() quy về UTC; sắp theo chuỗi sẽ sai vì mỗi báo ghi một múi giờ)."""
        _check_range(start, end); _check_aspect(aspect)
        w, args = _where(start, end, target, aspect, sentiment)
        total = conn.execute(f"SELECT COUNT(*) {FROM} {w}", args).fetchone()[0]
        rows = conn.execute(
            f"""SELECT t.id AS triplet_id, t.sent_id, s.text, t.target_text, t.target_start,
                       t.target_end, t.canonical_id, t.aspect_l1, t.aspect_l2, t.sentiment,
                       a.doc_id, a.title, a.url, a.source_name, a.published_at, {DAY} AS day
                {FROM} {w} ORDER BY datetime(a.published_at) DESC, t.id LIMIT ? OFFSET ?""",
            args + [limit, offset])
        return TraceOut(total=total, items=[TraceItem(**dict(r)) for r in rows])

    @app.get("/api/article/{doc_id}", response_model=ArticleOut)
    def article(doc_id: str, conn: sqlite3.Connection = Conn):
        """Cả bài với mọi câu và bộ ba của từng câu, để highlight ngay trong ngữ cảnh."""
        a = conn.execute(
            "SELECT doc_id, title, url, source_name, published_at FROM articles WHERE doc_id = ?",
            (doc_id,)).fetchone()
        if a is None:
            raise HTTPException(404, f"không có bài {doc_id}")
        by_sent: dict[str, list[dict]] = {}
        for r in conn.execute(
            """SELECT t.sent_id, t.id, t.target_text, t.target_start, t.target_end,
                      t.canonical_id, t.aspect_l1, t.aspect_l2, t.sentiment
               FROM triplets t JOIN sentences s ON s.sent_id = t.sent_id
               WHERE s.doc_id = ? ORDER BY t.target_start, t.id""", (doc_id,)):
            d = dict(r); by_sent.setdefault(d.pop("sent_id"), []).append(d)
        sents = [ArticleSentence(sent_id=r["sent_id"], sent_idx=r["sent_idx"], text=r["text"],
                                 is_title=bool(r["is_title"]),
                                 triplets=by_sent.get(r["sent_id"], []))
                 for r in conn.execute(
                     """SELECT sent_id, sent_idx, text, is_title FROM sentences
                        WHERE doc_id = ? ORDER BY sent_idx""", (doc_id,))]
        return ArticleOut(**dict(a), sentences=sents)

    # Giao diện: phục vụ web/ ở gốc, đăng ký SAU các route /api để không che chúng.
    if config.WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")

    return app
