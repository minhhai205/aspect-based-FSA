"""Bóc tiêu đề và thân bài từ HTML.

Dùng một thuật toán chung cho mọi báo: bỏ các khối không phải nội dung, rồi
chọn khối cha có nhiều chữ nhất trong các thẻ <p>. Báo điện tử VN và các
báo tiếng Anh về VN đều dựng thân bài bằng <p> khá chuẩn nên cách này chạy tốt;
nếu gặp báo lệch chuẩn thì vá riêng bằng SITE_RULES.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from .textnorm import normalize

log = logging.getLogger(__name__)

# Thẻ chắc chắn không phải nội dung bài
_DROP_TAGS = (
    "script", "style", "noscript", "iframe", "svg", "form", "button",
    "nav", "header", "footer", "aside", "figure", "figcaption", "video", "audio",
)

# class/id mang mấy từ này thì bỏ cả khối
_DROP_HINTS = (
    "related", "comment", "sidebar", "advert", "banner", "social", "share",
    "newsletter", "subscribe", "tag", "breadcrumb", "menu", "nav", "footer",
    "header", "popup", "modal", "recommend", "tinlienquan", "box-tin",
)

_MIN_PARA_LEN = 40     # đoạn ngắn hơn coi như chú thích ảnh / nhãn
_MIN_BODY_LEN = 200    # bài ngắn hơn coi như bóc hỏng


@dataclass(slots=True)
class Article:
    title: str
    body: str
    paragraphs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.body) >= _MIN_BODY_LEN


def _para_text(tag: Tag) -> str:
    """Text của một thẻ: chuẩn hóa rồi gộp xuống dòng thành dấu cách.

    Trong một <p> thì xuống dòng chỉ là cách xuống dòng của HTML, không phải
    ranh giới đoạn -> giữ lại sẽ làm tách câu cắt nhầm giữa câu.
    """
    return " ".join(normalize(tag.get_text(" ")).split())


def _looks_like_junk(tag: Tag) -> bool:
    attrs = getattr(tag, "attrs", None) or {}
    cls = attrs.get("class") or []
    if not isinstance(cls, list):
        cls = [cls]
    ident = f"{' '.join(str(c) for c in cls)} {attrs.get('id') or ''}".lower()
    return any(h in ident for h in _DROP_HINTS)


def _clean(soup: BeautifulSoup) -> None:
    for t in soup.find_all(_DROP_TAGS):
        t.decompose()
    # decompose() khối cha làm thẻ con còn trong danh sách thành rỗng
    # -> phải bỏ qua thẻ đã bị gỡ
    for t in soup.find_all(True):
        if not isinstance(t, Tag) or getattr(t, "decomposed", False):
            continue
        if _looks_like_junk(t):
            t.decompose()


def _pick_title(soup: BeautifulSoup) -> str:
    for sel in ('meta[property="og:title"]', 'meta[name="twitter:title"]'):
        m = soup.select_one(sel)
        if m and m.get("content"):
            return " ".join(normalize(m["content"]).split())
    h1 = soup.find("h1")
    if h1:
        return _para_text(h1)
    if soup.title:
        return _para_text(soup.title)
    return ""


def _pick_body(soup: BeautifulSoup) -> list[str]:
    """Chọn khối cha gom được nhiều chữ nhất từ các thẻ <p>."""
    paras = [p for p in soup.find_all("p")
             if len(_para_text(p)) >= _MIN_PARA_LEN]
    if not paras:
        return []

    score: dict[int, int] = {}
    owner: dict[int, Tag] = {}
    for p in paras:
        parent = p.parent
        depth = 0
        while isinstance(parent, Tag) and depth < 3:
            key = id(parent)
            score[key] = score.get(key, 0) + len(p.get_text(" "))
            owner[key] = parent
            parent = parent.parent
            depth += 1

    if not score:
        return []
    best = owner[max(score, key=score.__getitem__)]

    out: list[str] = []
    seen: set[str] = set()
    for p in best.find_all("p"):
        txt = _para_text(p)
        if len(txt) >= _MIN_PARA_LEN and txt not in seen:
            seen.add(txt)
            out.append(txt)
    return out


def extract(raw_html: bytes | str, url: str = "") -> Article:
    soup = BeautifulSoup(raw_html, "lxml")
    title = _pick_title(soup)
    _clean(soup)
    paragraphs = _pick_body(soup)
    body = "\n".join(paragraphs)
    art = Article(title=title, body=body, paragraphs=paragraphs)
    if not art.ok:
        log.debug("bóc nội dung yếu (%d ký tự): %s", len(body), url)
    return art
