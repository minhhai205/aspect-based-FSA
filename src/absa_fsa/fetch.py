"""Tầng HTTP: tuân robots.txt, giãn nhịp theo tên miền, thử lại khi lỗi."""

from __future__ import annotations

import logging
import threading
import time
import urllib.robotparser as robotparser
from urllib.parse import urlparse

import requests

from . import config

log = logging.getLogger(__name__)


class Fetcher:
    """Một phiên HTTP dùng chung, có khóa nhịp riêng cho từng tên miền."""

    def __init__(self, delay: float | None = None, timeout: int | None = None) -> None:
        self.delay = config.REQUEST_DELAY if delay is None else delay
        self.timeout = config.TIMEOUT if timeout is None else timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept-Language": "vi,en;q=0.8",
        })
        self._last: dict[str, float] = {}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._lock = threading.Lock()

    # -- giãn nhịp ---------------------------------------------------------- #
    def _wait(self, host: str) -> None:
        with self._lock:
            prev = self._last.get(host, 0.0)
            gap = time.monotonic() - prev
            if gap < self.delay:
                time.sleep(self.delay - gap)
            self._last[host] = time.monotonic()

    # -- robots.txt --------------------------------------------------------- #
    def _robots_for(self, url: str) -> robotparser.RobotFileParser | None:
        parts = urlparse(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host in self._robots:
            return self._robots[host]
        rp: robotparser.RobotFileParser | None = robotparser.RobotFileParser()
        try:
            r = self.session.get(f"{host}/robots.txt", timeout=self.timeout)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            else:
                rp = None  # không có robots.txt -> coi như cho phép
        except requests.RequestException:
            rp = None
        self._robots[host] = rp
        return rp

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        if rp is None:
            return True
        try:
            return rp.can_fetch(config.USER_AGENT, url)
        except Exception:
            return True

    # -- tải ---------------------------------------------------------------- #
    def get(self, url: str, *, check_robots: bool = True, retries: int = 2) -> bytes | None:
        if check_robots and not self.allowed(url):
            log.warning("robots.txt chặn: %s", url)
            return None

        host = urlparse(url).netloc
        for attempt in range(retries + 1):
            self._wait(host)
            try:
                r = self.session.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    return r.content
                if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                log.warning("HTTP %s: %s", r.status_code, url)
                return None
            except requests.RequestException as exc:
                if attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                log.warning("lỗi mạng %s: %s", type(exc).__name__, url)
                return None
        return None
