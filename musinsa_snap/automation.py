from __future__ import annotations

import asyncio
import csv
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urljoin

from playwright.async_api import Page, async_playwright

from .client import DEFAULT_BASE_URL, MusinsaClient
from .parser import SNAP_LINK_PATTERN, parse_snap_detail

LOGGER = logging.getLogger(__name__)

SNAP_CARD_SELECTOR = "a[href*='/snap/'], a[href*='/mz/snap/']"
SEARCH_INPUT_CANDIDATES = [
    "input[name='q']",
    "input[name='query']",
    "input[id*='search']",
    "input[placeholder*='검색']",
    "input[type='search']",
]
SNAP_TAB_CANDIDATES = [
    "a[role='tab'][href*='snap']",
    "a[href*='type=snap']",
    "a:has-text('SNAP')",
    "a:has-text('스냅')",
]


@dataclass
class Query:
    label: str
    query: str


def load_queries(file_path: Path) -> list[Query]:
    if not file_path.exists():
        raise FileNotFoundError(f"Query file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)

    queries: list[Query] = []
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                queries.append(Query(label=entry, query=entry))
            elif isinstance(entry, dict) and "query" in entry:
                label = entry.get("label") or entry["query"]
                queries.append(Query(label=label, query=entry["query"]))
    else:
        raise ValueError("musinsa_TAG.json must contain a list of queries or query objects")

    if not queries:
        raise ValueError("No queries found in musinsa_TAG.json")
    return queries


def safe_slug(text: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z가-힣_-]+", "_", text)
    return slug.strip("_") or "snap"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


async def _find_first(page: Page, selectors: Sequence[str]):
    for selector in selectors:
        try:
            handle = page.locator(selector).first
            await handle.wait_for(state="visible", timeout=4000)
            return handle
        except Exception:
            continue
    return None


class SnapAutomation:
    def __init__(
        self,
        *,
        tags_file: Path,
        output_dir: Path = Path("downloads"),
        csv_path: Path = Path("snaps.csv"),
        max_per_query: int | None = None,
        scroll_delay: float = 1.5,
        client_delay: float = 0.3,
        headless: bool = True,
    ) -> None:
        self.tags_file = tags_file
        self.output_dir = output_dir
        self.csv_path = csv_path
        self.max_per_query = max_per_query
        self.scroll_delay = scroll_delay
        self.client = MusinsaClient(delay=client_delay)
        self.headless = headless

    async def run(self) -> None:
        queries = load_queries(self.tags_file)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page(locale="ko-KR")
            for query in queries:
                await self.process_query(page, query)
            await browser.close()

    async def process_query(self, page: Page, query: Query) -> None:
        LOGGER.info("Processing query '%s'", query.query)
        await page.goto(DEFAULT_BASE_URL, wait_until="networkidle")
        await self._fill_search(page, query.query)
        await self._click_snap_tab(page)
        await self._click_first_snap(page)
        detail_urls = await self._collect_snap_links(page, limit=self.max_per_query)
        LOGGER.info("Found %s snap links for %s", len(detail_urls), query.label)

        rows = []
        for link in detail_urls:
            snap = self._fetch_snap(link)
            if not snap:
                continue
            image_path = self._download_image(snap.image_url, query.label, snap.id)
            rows.append(
                {
                    "query": query.label,
                    "id": snap.id,
                    "url": snap.url,
                    "title": snap.title,
                    "author": snap.author,
                    "taken_at": snap.taken_at,
                    "tags": ",".join(snap.tags),
                    "image_path": str(image_path) if image_path else None,
                }
            )
        self._append_csv(rows)

    async def _fill_search(self, page: Page, query: str) -> None:
        input_box = await _find_first(page, SEARCH_INPUT_CANDIDATES)
        if not input_box:
            raise RuntimeError("검색창을 찾을 수 없습니다.")
        await input_box.fill("")
        await input_box.type(query)
        await input_box.press("Enter")
        await page.wait_for_load_state("networkidle")

    async def _click_snap_tab(self, page: Page) -> None:
        tab = await _find_first(page, SNAP_TAB_CANDIDATES)
        if tab:
            await tab.click()
            await page.wait_for_load_state("networkidle")
        else:
            LOGGER.warning("SNAP 탭을 찾지 못했습니다. 전체 결과에서 진행합니다.")

    async def _click_first_snap(self, page: Page) -> None:
        first_card = await _find_first(page, [SNAP_CARD_SELECTOR])
        if first_card:
            await first_card.scroll_into_view_if_needed()
            await first_card.click()
            await page.wait_for_load_state("networkidle")
            await page.go_back()
        else:
            LOGGER.warning("첫 번째 SNAP 이미지를 찾지 못했습니다.")

    async def _collect_snap_links(self, page: Page, *, limit: int | None = None) -> list[str]:
        seen: set[str] = set()
        no_new_rounds = 0

        while True:
            links = await page.query_selector_all(SNAP_CARD_SELECTOR)
            for link in links:
                href = await link.get_attribute("href")
                if not href:
                    continue
                if not SNAP_LINK_PATTERN.search(href):
                    continue
                absolute = urljoin(DEFAULT_BASE_URL, href)
                if absolute not in seen:
                    seen.add(absolute)
            if limit and len(seen) >= limit:
                break

            previous_count = len(seen)
            await page.evaluate("window.scrollBy(0, document.body.scrollHeight);")
            await page.wait_for_timeout(int(self.scroll_delay * 1000))
            if len(seen) == previous_count:
                no_new_rounds += 1
            else:
                no_new_rounds = 0
            if no_new_rounds >= 3:
                break
        return list(seen)[:limit] if limit else list(seen)

    def _fetch_snap(self, url: str):
        try:
            html = self.client.fetch_detail(url)
            return parse_snap_detail(html, self.client.base_url)
        except Exception as exc:  # pragma: no cover - network issues
            LOGGER.warning("%s 에서 스냅을 불러오지 못했습니다: %s", url, exc)
            return None

    def _download_image(self, image_url: str | None, query_label: str, snap_id: str | None) -> Path | None:
        if not image_url:
            return None
        ext = Path(image_url).suffix or ".jpg"
        filename = f"{safe_slug(query_label)}-{snap_id or 'snap'}{ext}"
        output_path = self.output_dir / safe_slug(query_label) / filename
        ensure_parent(output_path)
        try:
            content = self.client.fetch_binary(image_url)
            output_path.write_bytes(content)
            return output_path
        except Exception as exc:  # pragma: no cover - network issues
            LOGGER.warning("이미지 다운로드 실패 (%s): %s", image_url, exc)
            return None

    def _append_csv(self, rows: Iterable[dict[str, str | None]]) -> None:
        ensure_parent(self.csv_path)
        is_new = not self.csv_path.exists()
        with self.csv_path.open("a", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(
                fp,
                fieldnames=["query", "id", "url", "title", "author", "taken_at", "tags", "image_path"],
            )
            if is_new:
                writer.writeheader()
            for row in rows:
                writer.writerow(row)


def build_cli_args(argv: Sequence[str] | None = None):
    import argparse

    parser = argparse.ArgumentParser(description="Automate Musinsa SNAP scraping with Playwright")
    parser.add_argument(
        "--tags-file",
        type=Path,
        default=Path("musinsa_TAG.json"),
        help="검색에 사용할 태그 JSON 파일 경로",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("downloads"), help="이미지 저장 디렉토리")
    parser.add_argument("--csv", type=Path, default=Path("snaps.csv"), help="CSV 저장 경로")
    parser.add_argument("--limit", type=int, default=None, help="태그별 최대 스냅 수")
    parser.add_argument("--scroll-delay", type=float, default=1.5, help="스크롤 사이 대기 시간(초)")
    parser.add_argument("--request-delay", type=float, default=0.3, help="HTTP 요청 간 대기 시간(초)")
    parser.add_argument("--headless", action="store_true", help="헤드리스 모드 사용")
    parser.add_argument("--verbose", action="store_true", help="디버그 로그 표시")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_cli_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="[%(levelname)s] %(message)s")
    automation = SnapAutomation(
        tags_file=args.tags_file,
        output_dir=args.output_dir,
        csv_path=args.csv,
        max_per_query=args.limit,
        scroll_delay=args.scroll_delay,
        client_delay=args.request_delay,
        headless=args.headless,
    )
    asyncio.run(automation.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
