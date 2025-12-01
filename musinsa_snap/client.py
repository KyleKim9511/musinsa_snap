from __future__ import annotations

import logging
import time
from typing import Optional
from urllib.parse import urlencode, urljoin

import requests

LOGGER = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://www.musinsa.com/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0 Safari/537.36"
)


def _build_headers(base_url: str) -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": base_url,
    }


class MusinsaClient:
    """HTTP client for Musinsa search and snap detail pages."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        delay: float = 0.5,
        session: Optional[requests.Session] = None,
        timeout: int = 10,
        retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self._session = session or requests.Session()
        self._session.headers.update(_build_headers(self.base_url))

    def fetch(self, path: str, *, params: Optional[dict[str, str]] = None) -> str:
        url = urljoin(self.base_url, path)
        if params:
            url = f"{url}?{urlencode(params)}"
        for attempt in range(self.retries + 1):
            LOGGER.debug("Fetching %s (attempt %s)", url, attempt + 1)
            response = self._session.get(url, timeout=self.timeout)
            if response.status_code == 404:
                response.raise_for_status()
            if response.ok:
                time.sleep(self.delay)
                return response.text
            LOGGER.warning("Request to %s failed with %s", url, response.status_code)
            time.sleep(self.delay)
        response.raise_for_status()
        return response.text

    def fetch_listing(self, *, keyword: str, page: int = 1, gender: str | None = None) -> str:
        params = {"keyword": keyword, "page": str(page)}
        if gender:
            params["gf"] = gender
        return self.fetch("search/snap", params=params)

    def fetch_detail(self, path: str) -> str:
        if path.startswith("http"):
            relative_path = path.replace(self.base_url, "", 1)
        else:
            relative_path = path.lstrip("/")
        return self.fetch(relative_path)

    def fetch_binary(self, url: str) -> bytes:
        LOGGER.debug("Downloading binary content from %s", url)
        response = self._session.get(url, timeout=self.timeout)
        response.raise_for_status()
        time.sleep(self.delay)
        return response.content
