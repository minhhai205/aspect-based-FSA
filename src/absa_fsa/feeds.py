"""Đọc RSS/Atom: lấy link, tiêu đề, ngày đăng."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .textnorm import normalize

log = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"
VN_TZ = timezone(timedelta(hours=7))

# "19/11/2026 18:43" hoặc "2026-11-19 18:43:00"
_DMY = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?")
_YMD = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?")


@dataclass(slots=True)
class FeedItem:
    url: str
    title: str
    published_at: datetime | None
    summary: str = ""


def parse_date(raw: str | None) -> datetime | None:
    """Đọc ngày từ feed. Chịu được RFC-822, ISO, và các định dạng lệch chuẩn."""
    if not raw:
        return None
    raw = raw.strip()

    try:  # RFC-822: "Thu, 19 Nov 2026 17:00:00 +0700" (kể cả năm 2 chữ số)
        d = parsedate_to_datetime(raw)
        if d is not None:
            return d if d.tzinfo else d.replace(tzinfo=VN_TZ)
    except (TypeError, ValueError):
        pass

    try:  # ISO-8601
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=VN_TZ)
    except ValueError:
        pass

    for rx, order in ((_YMD, "ymd"), (_DMY, "dmy")):
        m = rx.search(raw)
        if not m:
            continue
        g = [int(x) if x else 0 for x in m.groups()]
        y, mo, da = (g[0], g[1], g[2]) if order == "ymd" else (g[2], g[1], g[0])
        try:
            return datetime(y, mo, da, g[3], g[4], g[5], tzinfo=VN_TZ)
        except ValueError:
            continue

    log.debug("không đọc được ngày: %r", raw[:60])
    return None


def clamp_future(d: datetime | None, max_skew_hours: int = 12) -> datetime | None:
    """Vài feed có mốc ở tương lai do lệch đồng hồ server -> kéo về hiện tại."""
    if d is None:
        return None
    now = datetime.now(timezone.utc)
    if d > now + timedelta(hours=max_skew_hours):
        log.debug("mốc tương lai %s -> kéo về now", d.isoformat())
        return now
    return d


def _text(el: ET.Element, *names: str) -> str:
    for n in names:
        v = el.findtext(n)
        if v and v.strip():
            return v.strip()
    return ""


def parse_feed(raw: bytes) -> list[FeedItem]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        log.warning("feed không phải XML hợp lệ: %s", exc)
        return []

    items = root.findall(".//item")
    if items:
        out = []
        for it in items:
            url = _text(it, "link", "guid")
            if not url.startswith("http"):
                continue
            out.append(FeedItem(
                url=url,
                title=normalize(_text(it, "title")),
                published_at=clamp_future(parse_date(
                    it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")
                )),
                summary=normalize(_text(it, "description")),
            ))
        return out

    # Atom
    out = []
    for en in root.findall(f".//{ATOM}entry"):
        link = en.find(f"{ATOM}link")
        url = (link.get("href") if link is not None else "") or ""
        if not url.startswith("http"):
            continue
        out.append(FeedItem(
            url=url,
            title=normalize(_text(en, f"{ATOM}title")),
            published_at=clamp_future(parse_date(
                en.findtext(f"{ATOM}published") or en.findtext(f"{ATOM}updated")
            )),
            summary=normalize(_text(en, f"{ATOM}summary")),
        ))
    return out
