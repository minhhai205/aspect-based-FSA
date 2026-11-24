"""Đọc sitemap XML: danh sách URL kèm ngày đăng.

Dùng để lấy lùi các ngày mà RSS không còn giữ (RSS chỉ có vài chục bài mới nhất).
Ngày lấy từ <lastmod> kèm múi giờ trong sitemap. Đã đối chiếu với ngày RSS lưu trong DB:
114/114 bài VnEconomy EN và 40/40 bài Vietnam News trùng đến từng phút.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import Source
from .fetch import Fetcher

log = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))
_URL = re.compile(r"<url>(.*?)</url>", re.S)
_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.S)
_LASTMOD = re.compile(r"<lastmod>\s*(.*?)\s*</lastmod>", re.S)


@dataclass(slots=True)
class SitemapItem:
    url: str
    published_at: datetime


def norm_url(u: str) -> str:
    """Dạng chuẩn để so trùng: bỏ #fragment và dấu / cuối."""
    return u.split("#", 1)[0].rstrip("/")


def parse(xml: str) -> list[SitemapItem]:
    out: list[SitemapItem] = []
    for blk in _URL.findall(xml):
        loc, lm = _LOC.search(blk), _LASTMOD.search(blk)
        if not (loc and lm):
            continue
        try:
            d = datetime.fromisoformat(lm.group(1).strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        out.append(SitemapItem(loc.group(1).strip(), d if d.tzinfo else d.replace(tzinfo=VN_TZ)))
    return out


def _months(since: datetime, until: datetime) -> list[tuple[int, int]]:
    y, m = since.astimezone(VN_TZ).year, since.astimezone(VN_TZ).month
    ey, em = until.astimezone(VN_TZ).year, until.astimezone(VN_TZ).month
    out = []
    while (y, m) <= (ey, em):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def recent(fetcher: Fetcher, src: Source, since: datetime,
           until: datetime | None = None) -> list[SitemapItem]:
    """Các bài của `src` đăng trong [since, until], cũ trước mới sau, đã bỏ trùng và lọc theo url_regex."""
    until = until or datetime.now(timezone.utc)
    rx = re.compile(src.url_regex) if src.url_regex else None
    best: dict[str, SitemapItem] = {}
    for y, m in _months(since, until):
        url = src.sitemap.format(y=y, m=m)          # tháng không đệm số 0: news-2026-9
        raw = fetcher.get(url)
        if not raw:
            log.warning("[%s] không tải được sitemap %s", src.slug, url)
            continue
        got = parse(raw.decode("utf-8", "replace"))
        log.info("[%s] sitemap %s: %d URL", src.slug, url.rsplit("/", 1)[-1], len(got))
        for it in got:
            if not (since <= it.published_at <= until):
                continue
            if rx and not rx.search(it.url):
                continue
            best.setdefault(norm_url(it.url), it)
    return sorted(best.values(), key=lambda i: i.published_at)
