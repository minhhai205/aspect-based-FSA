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
# DB dữ liệu mẫu, tách riêng khỏi DB crawl thật để không bao giờ lẫn vào nhau
MOCK_DB_PATH = _p("ABSA_MOCK_DB_PATH", "data/mock.db")
# DB mà web đọc. Mặc định là DB mẫu vì DB crawl thật chưa có bộ ba nào (chưa có model).
# Khi model ghép vào xong thì đổi sang data/absa.db trong .env.
WEB_DB_PATH = _p("ABSA_WEB_DB", "data/mock.db")
WEB_DIR = ROOT / "web"

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
    # Sitemap theo tháng, để lấy lùi những ngày RSS không còn giữ. {y}={năm}, {m}=tháng KHÔNG đệm 0.
    sitemap: str = ""
    # Chỉ lấy URL khớp biểu thức này (loại trang chủ, mục PR, đời sống...).
    url_regex: str = ""


# Hiện làm 2 nguồn tiếng Anh trước. Danh sách tiếng Việt xem doc/nguon-du-lieu.md
SOURCES: list[Source] = [
    Source(
        slug="vneconomy_en",
        name="VnEconomy English",
        lang="en",
        feed_url="https://en.vneconomy.vn/economy.rss",
        section="economy",
        sitemap="https://en.vneconomy.vn/sitemap/news-{y}-{m}.xml",
        url_regex=r"^https://en\.vneconomy\.vn/[^/]+\.htm$",
    ),
    Source(
        slug="vietnamnews",
        name="Vietnam News (VNA)",
        lang="en",
        feed_url="https://vietnamnews.vn/rss/economy.rss",
        section="economy",
        sitemap="https://vietnamnews.vn/sitemaps/news-{y}-{m}.xml",
        url_regex=r"^https://vietnamnews\.vn/economy/\d+/",
    ),    Source(
        slug="sggp_en",
        name="Saigon Giai Phong English",
        lang="en",
        feed_url="https://en.sggp.org.vn/rss/business-3.rss",
        section="business",
        # Không khai báo sitemap: URL của SGGP không có tên mục, lấy sitemap sẽ kéo về cả trang
        # (quốc tế, đời sống, TP.HCM...), chỉ ~4-14% liên quan. RSS mục business đủ trải 14 ngày.
    ),
]

SOURCES_BY_SLUG = {s.slug: s for s in SOURCES}
