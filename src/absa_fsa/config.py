"""Cấu hình và danh sách nguồn."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Đọc .env đơn giản, không cần thư viện ngoài."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv(ROOT / ".env")


def _p(key: str, default: str) -> Path:
    v = Path(os.environ.get(key, default))
    return v if v.is_absolute() else ROOT / v


DB_PATH = _p("ABSA_DB_PATH", "data/absa.db")
EXPORT_DIR = _p("ABSA_EXPORT_DIR", "data/exports")

USER_AGENT = os.environ.get(
    "ABSA_USER_AGENT",
    "absa-fsa-research/0.1 (academic project; contact via repo)",
)
REQUEST_DELAY = float(os.environ.get("ABSA_REQUEST_DELAY", "1.0"))
TIMEOUT = int(os.environ.get("ABSA_TIMEOUT", "20"))
# 0 = không giới hạn
MAX_ARTICLES_PER_FEED = int(os.environ.get("ABSA_MAX_ARTICLES_PER_FEED", "0"))


@dataclass(frozen=True, slots=True)
class Source:
    slug: str           # định danh ngắn, dùng trong doc_id
    name: str           # tên hiển thị
    lang: str           # "en" | "vi"
    feed_url: str
    section: str = ""


# Hiện làm 2 nguồn tiếng Anh trước. Danh sách tiếng Việt xem doc/nguon-du-lieu.md
SOURCES: list[Source] = [
    Source(
        slug="vneconomy_en",
        name="VnEconomy English",
        lang="en",
        feed_url="https://en.vneconomy.vn/economy.rss",
        section="economy",
    ),
    Source(
        slug="vietnamnews",
        name="Vietnam News (VNA)",
        lang="en",
        feed_url="https://vietnamnews.vn/rss/economy.rss",
        section="economy",
    ),
]

SOURCES_BY_SLUG = {s.slug: s for s in SOURCES}
