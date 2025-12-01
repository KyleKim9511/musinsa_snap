from __future__ import annotations

import logging
import time
from typing import Optional
from urllib.parse import urljoin

import requests

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.musinsa.com/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0 Safari/537.36"
)


def _build_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": BASE_URL,
    }


class MusinsaClient:
    """Lightweight HTTP client with polite defaults for Musinsa requests."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        *,
        delay: float = 0.5,
        session: Optional[requests.Session] = None,
        timeout: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.delay = delay
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(_build_headers())

    def fetch(self, path: str) -> str:
        url = urljoin(self.base_url, path)
        LOGGER.debug("Fetching %s", url)
        response = self._session.get(url, timeout=self.timeout)
        response.raise_for_status()
        time.sleep(self.delay)
        return response.text

    def fetch_listing(self, page: int = 1) -> str:
        path = f"mz/snap?p={page}"
        return self.fetch(path)

    def fetch_detail(self, path: str) -> str:
        if path.startswith("http"):
            relative_path = path.replace(self.base_url, "", 1)
        else:
            relative_path = path.lstrip("/")
        return self.fetch(relative_path)
