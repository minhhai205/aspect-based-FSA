"""Sinh DB dữ liệu mẫu mô phỏng đầu ra của model.

KHÔNG phải kết quả của model thật. Nhãn do luật từ khóa đưa ra, chỉ dùng để thử
giao diện. Đừng đưa số liệu từ DB này vào báo cáo.

Cách làm:
  - Lấy câu và bài THẬT từ DB crawl (giữ nguyên văn bản, link, ngày đăng).
  - Dò thực thể bằng từ điển (lexicon.py), gán khía cạnh + cảm xúc bằng luật.
  - Các ngày nằm trong khoảng dữ liệu thật giữ nguyên số bài thật (kể cả ngày thưa).
  - Các ngày TRƯỚC khoảng đó được lấp bằng bản sao bài thật với ngày giả
    (doc_id có hậu tố ~mK, URL có #mK) để biểu đồ theo thời gian có đủ điểm.
  - Cảm xúc dao động theo "tâm lý ngày" (bước ngẫu nhiên) để đường biểu đồ có xu hướng,
    nhưng không bao giờ đảo cực của câu có tín hiệu rõ (xem _noisy).

Ghi ra DB riêng (config.MOCK_DB_PATH), không đụng vào DB crawl thật.
"""

from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config, db
from .lexicon import Entity, find_mentions
from .scheme import ASPECT_L2, L2_TO_L1, SENTIMENTS

VN_TZ = timezone(timedelta(hours=7))
MODEL_VERSION = "mock-rules-v1"

# --------------------------------------------------------------------------- #
# Luật gán nhãn
# --------------------------------------------------------------------------- #

_POS = ("rise", "rose", "rising", "increas", "grew", "grow", "gain", "surg", "strong",
        "record", "higher", "rebound", "recover", "improv", "boost", "profit", "expand",
        "optimis", "approv", "support", "upgrad", "success", "positive", "accelerat",
        "upbeat", "robust", "bullish", "strengthen", "exceed", "outperform")
_NEG = ("fall", "fell", "drop", "declin", "decreas", "slump", "plung", "weak", "lower",
        "loss", "pressure", "concern", "risk", "shortfall", "slow", "uncertain",
        "negative", "bearish", "sell-off", "selling", "tumbl", "retreat", "worsen",
        "deficit", "lowest", "tighten", "volatil", "shrink", "warn")

# Tách mệnh đề ở từ đối lập để một câu có thể có hai cảm xúc ngược nhau
_CONTRAST = re.compile(r"\b(?:but|while|whereas|however|although|though|yet)\b|;", re.I)

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (l2, re.compile(rx, re.I)) for l2, rx in (
        ("Kết quả kinh doanh", r"revenue|profit|earnings|net income|turnover|quarterly"),
        ("Nợ và huy động vốn", r"bond|debt|loan|borrow|issuance|capital rais|raise capital"),
        ("Diễn biến giá cổ phiếu", r"share price|stock price|\bshares\b|ceiling|floor price|\([A-Z]{3}\)\s*(?:fell|rose|dropped|gained|surged|declined|climbed|slid|jumped)|(?:fell|rose|gained|dropped|declined|surged|climbed|slid|jumped)\s+\d"),
        ("Giao dịch của nhà đầu tư", r"foreign investor|net buy|net sell|net sold|net bought|inflow|outflow|investors? (?:bought|sold)"),
        ("Sự kiện doanh nghiệp", r"merger|acqui|appoint|resign|chairman|\bceo\b|\bipo\b|listing|restructur|dividend|licen[cs]e|agreement|memorandum|signed|launch"),
        ("Diễn biến thị trường chung", r"vn-?index|\bpoints?\b|liquidity|trading session|capitali[sz]ation|benchmark|bourse"),
        ("Tăng trưởng và lạm phát", r"\bgdp\b|growth|inflation|\bcpi\b|industrial production|retail sales"),
        ("Chính sách tiền tệ và lãi suất", r"interest rate|policy rate|monetary|refinanc|credit|lending rate|deposit rate"),
        ("Tỷ giá", r"exchange rate|\bdong\b|\busd\b|dollar|forex|foreign reserves|reference rate"),
        ("Thương mại và đầu tư", r"export|import|\btrade\b|\bfdi\b|foreign direct|investment"),
        ("Quy định và chính sách tài khóa", r"\btax|budget|decree|regulation|circular|\blaw\b|fiscal|public investment|disburse"),
    )
)

# Khía cạnh hợp lý cho từng loại target
_ALLOWED: dict[str, set[str]] = {
    "company": {"Kết quả kinh doanh", "Sự kiện doanh nghiệp", "Nợ và huy động vốn",
                "Diễn biến giá cổ phiếu", "Giao dịch của nhà đầu tư"},
    "index": {"Diễn biến thị trường chung", "Giao dịch của nhà đầu tư"},
    "currency": {"Tỷ giá"},
    "agency": {"Tăng trưởng và lạm phát", "Chính sách tiền tệ và lãi suất",
               "Thương mại và đầu tư", "Quy định và chính sách tài khóa"},
}
_DEFAULT_BY_ID = {
    "SBV": "Chính sách tiền tệ và lãi suất",
    "MOF": "Quy định và chính sách tài khóa",
    "SSC": "Quy định và chính sách tài khóa",
    "MOIT": "Thương mại và đầu tư",
    "NSO": "Tăng trưởng và lạm phát",
}
_DEFAULT_BY_TYPE = {
    "company": "Sự kiện doanh nghiệp",
    "index": "Diễn biến thị trường chung",
    "currency": "Tỷ giá",
    "agency": "Quy định và chính sách tài khóa",
}


def _clause(text: str, pos: int) -> str:
    cuts = [0] + [m.end() for m in _CONTRAST.finditer(text)] + [len(text)]
    for a, b in zip(cuts, cuts[1:]):
        if a <= pos < b:
            return text[a:b]
    return text


def _cue_sentiment(clause: str) -> str:
    toks = re.findall(r"[a-z\-]+", clause.lower())
    pos = sum(t.startswith(_POS) for t in toks)
    neg = sum(t.startswith(_NEG) for t in toks)
    return "positive" if pos > neg else "negative" if neg > pos else "neutral"


def _aspects(low: str, ent: Entity) -> list[str]:
    allowed = _ALLOWED[ent.type]
    hits: list[str] = []
    for l2, rx in _RULES:
        if l2 in allowed and l2 not in hits and rx.search(low):
            hits.append(l2)
            if len(hits) == 2:
                break
    if not hits:
        hits = [_DEFAULT_BY_ID.get(ent.canonical_id) or _DEFAULT_BY_TYPE[ent.type]]
    return hits


def base_triplets(text: str) -> list[dict]:
    """Bộ ba theo luật cho một câu. Mỗi thực thể chỉ lấy lần nhắc đầu tiên."""
    out: list[dict] = []
    seen: set[str] = set()
    low = text.lower()
    for s, e, ent in find_mentions(text):
        if ent.canonical_id in seen:
            continue
        seen.add(ent.canonical_id)
        senti = _cue_sentiment(_clause(text, s))
        for l2 in _aspects(low, ent):
            out.append({
                "target_text": text[s:e], "target_start": s, "target_end": e,
                "canonical_id": ent.canonical_id, "target_type": ent.type,
                "aspect_l1": L2_TO_L1[l2], "aspect_l2": l2, "sentiment": senti,
            })
    return out


def _noisy(sentiment: str, mood: float, rnd: random.Random) -> str:
    """Thêm dao động theo tâm lý ngày mà không làm nhãn mâu thuẫn với câu.

    Câu trung tính (không có từ tín hiệu) có thể bị kéo về tích cực/tiêu cực theo
    tâm lý ngày. Câu có tín hiệu rõ chỉ có thể bị hạ về trung tính, KHÔNG bao giờ
    bị đảo cực: "fell 2.8 per cent" mà gán positive thì xem truy vết là thấy sai ngay.
    """
    if sentiment == "neutral":
        if rnd.random() >= 0.60:
            return "neutral"
        p = max(0.05, 0.40 + 0.35 * mood)
        n = max(0.05, 0.40 - 0.35 * mood)
        return rnd.choices(SENTIMENTS, weights=(p, n, 0.20))[0]
    return "neutral" if rnd.random() < 0.15 else sentiment


# --------------------------------------------------------------------------- #
# Dựng DB
# --------------------------------------------------------------------------- #

def _vn_dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(VN_TZ)


def build(days: int = 30, seed: int = 7,
          src_path: Path | None = None, out_path: Path | None = None) -> dict:
    rnd = random.Random(seed)
    src_path = src_path or config.DB_PATH
    out_path = out_path or config.MOCK_DB_PATH
    if src_path.resolve() == out_path.resolve():
        raise ValueError("DB mẫu không được trùng DB crawl thật")

    # --- đọc dữ liệu thật ---
    with db.session(src_path) as s:
        arts = [dict(r) for r in s.execute(
            "SELECT * FROM articles WHERE published_at IS NOT NULL ORDER BY published_at")]
        sents: dict[str, list[dict]] = defaultdict(list)
        for r in s.execute("""SELECT sent_id, doc_id, sent_idx, text, char_len, is_title, lang
                              FROM sentences ORDER BY doc_id, sent_idx"""):
            sents[r["doc_id"]].append(dict(r))
    if not arts:
        raise RuntimeError("DB crawl chưa có bài nào, chạy ./absa crawl trước")

    for a in arts:
        a["_vn"] = _vn_dt(a["published_at"])
        a["_day"] = a["_vn"].date()
        for st in sents[a["doc_id"]]:
            st["_tri"] = base_triplets(st["text"])
        a["_has"] = any(st["_tri"] for st in sents[a["doc_id"]])

    min_real = min(a["_day"] for a in arts)
    max_real = max(a["_day"] for a in arts)
    all_days = [max_real - timedelta(days=d) for d in range(max(days, 1) - 1, -1, -1)]

    # --- tâm lý từng ngày: bước ngẫu nhiên ---
    mood: dict[date, float] = {}
    m = rnd.uniform(-0.3, 0.3)
    for d in all_days:
        m = max(-1.0, min(1.0, 0.8 * m + rnd.gauss(0, 0.35)))
        mood[d] = m

    # --- danh sách bài sẽ ghi: (bài gốc, doc_id mới, ngày, đúng_thật?) ---
    plan: list[tuple[dict, str, date, bool]] = []
    for a in arts:
        plan.append((a, a["doc_id"], a["_day"], True))

    pool = arts
    weights = [3 if a["_has"] else 1 for a in pool]
    copies: Counter[str] = Counter()
    for d in all_days:
        if d >= min_real:
            continue                       # ngày có dữ liệu thật: giữ nguyên
        mean, sd = (14, 4) if d.weekday() >= 5 else (38, 6)
        for _ in range(max(3, round(rnd.gauss(mean, sd)))):
            o = rnd.choices(pool, weights=weights)[0]
            copies[o["doc_id"]] += 1
            plan.append((o, f"{o['doc_id']}~m{copies[o['doc_id']]}", d, False))

    # --- ghi ra DB mẫu ---
    for suffix in ("", "-wal", "-shm"):
        Path(str(out_path) + suffix).unlink(missing_ok=True)

    n_trip = 0
    with db.session(out_path) as conn:
        now = db.utcnow()
        for o, doc_id, day, real in plan:
            if real:
                pub, url = o["published_at"], o["url"]
            else:
                t = o["_vn"]
                pub = datetime(day.year, day.month, day.day, t.hour, t.minute, t.second,
                               tzinfo=VN_TZ).isoformat()
                url = f"{o['url']}#{doc_id.rsplit('~', 1)[1]}"
            row = {k: o[k] for k in ("source", "source_name", "lang", "title", "body",
                                     "summary", "section", "n_sentences", "n_chars",
                                     "content_sha1")}
            row.update(doc_id=doc_id, url=url, published_at=pub,
                       fetched_at=now, is_backfill=0)
            db.insert_article(conn, row)

            srows, trows = [], []
            for st in sents[o["doc_id"]]:
                sid = f"{doc_id}#{st['sent_idx']}"
                srows.append((sid, doc_id, st["sent_idx"], st["text"], st["char_len"],
                              st["is_title"], st["lang"], "done"))
                for t in st["_tri"]:
                    trows.append({**{k: v for k, v in t.items() if k != "sentiment"},
                                  "sent_id": sid, "model_version": MODEL_VERSION,
                                  "sentiment": _noisy(t["sentiment"], mood[day], rnd)})
            conn.executemany(
                """INSERT INTO sentences
                   (sent_id, doc_id, sent_idx, text, char_len, is_title, lang, status)
                   VALUES (?,?,?,?,?,?,?,?)""", srows)
            n_trip += db.insert_triplets(conn, trows)
            conn.execute("UPDATE articles SET in_scope = ? WHERE doc_id = ?",
                         (int(bool(trows)), doc_id))

        return _report(conn, all_days, min_real, max_real, len(arts))


def _report(conn, all_days, min_real, max_real, n_real) -> dict:
    q = lambda sql, *a: conn.execute(sql, a).fetchall()
    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]

    rep: dict = {}
    rep["articles"] = one("SELECT COUNT(*) FROM articles")
    rep["articles_real"] = n_real
    rep["sentences"] = one("SELECT COUNT(*) FROM sentences")
    rep["triplets"] = one("SELECT COUNT(*) FROM triplets")
    rep["sent_with_triplet"] = one("SELECT COUNT(DISTINCT sent_id) FROM triplets")
    rep["sent_multi"] = one(
        "SELECT COUNT(*) FROM (SELECT sent_id FROM triplets GROUP BY sent_id HAVING COUNT(*) > 1)")
    rep["sent_conflict"] = one(
        """SELECT COUNT(*) FROM (SELECT sent_id FROM triplets
           GROUP BY sent_id
           HAVING SUM(sentiment='positive') > 0 AND SUM(sentiment='negative') > 0)""")
    rep["real_range"] = (min_real.isoformat(), max_real.isoformat())
    rep["days"] = [dict(r) for r in q(
        """SELECT substr(datetime(a.published_at,'+7 hours'),1,10) AS day,
                  COUNT(DISTINCT a.doc_id) AS articles,
                  COUNT(t.id) AS triplets
           FROM articles a
           LEFT JOIN sentences s ON s.doc_id = a.doc_id
           LEFT JOIN triplets t ON t.sent_id = s.sent_id
           GROUP BY day ORDER BY day""")]
    rep["top_targets"] = [tuple(r) for r in q(
        "SELECT canonical_id, COUNT(*) FROM triplets GROUP BY 1 ORDER BY 2 DESC LIMIT 8")]
    rep["by_aspect"] = [tuple(r) for r in q(
        "SELECT aspect_l2, COUNT(*) FROM triplets GROUP BY 1 ORDER BY 2 DESC")]
    rep["by_sentiment"] = {r[0]: r[1] for r in q(
        "SELECT sentiment, COUNT(*) FROM triplets GROUP BY 1")}

    # --- kiểm tra độc lập, bằng SQL trên chính dữ liệu đã ghi ---
    bad_span = one(
        """SELECT COUNT(*) FROM triplets t JOIN sentences s USING (sent_id)
           WHERE substr(s.text, t.target_start + 1, t.target_end - t.target_start)
                 != t.target_text""")
    bad_aspect = sum(1 for r in q("SELECT aspect_l1, aspect_l2 FROM triplets")
                     if r[1] not in ASPECT_L2 or L2_TO_L1[r[1]] != r[0])
    orphan = one("""SELECT COUNT(*) FROM triplets t
                    LEFT JOIN sentences s USING (sent_id) WHERE s.sent_id IS NULL""")
    rep["errors"] = {"span_lệch": bad_span, "aspect_sai": bad_aspect, "mồ_côi": orphan}
    return rep
