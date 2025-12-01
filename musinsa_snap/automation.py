from __future__ import annotations

import csv
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from .client import DEFAULT_BASE_URL, MusinsaClient
from .models import Snap
from .parser import SNAP_LINK_PATTERN, parse_snap_detail

LOGGER = logging.getLogger(__name__)

SNAP_CARD_SELECTOR = "a[href*='/snap/'], a[href*='/mz/snap/'], li.snap_item a, li.snap-article a, div.snap-list__item a"
SEARCH_INPUT_CANDIDATES = [
    "css:input[name='q']",
    "css:input[name='query']",
    "css:input[id*='search']",
    "css:input[placeholder*='검색']",
    "css:input[type='search']",
    "css:input.search-input",
    "css:form.search input",
]
SNAP_TAB_CANDIDATES = [
    "css:a[role='tab'][href*='snap']",
    "css:a[href*='type=snap']",
    "css:a[href*='search/snap']",
    "xpath://a[contains(., 'SNAP') or contains(., '스냅/코디') or contains(., '스냅')]",
    "xpath://button[contains(., 'SNAP') or contains(., '스냅/코디') or contains(., '스냅')]",
]
RESULT_CONTAINER_CANDIDATES = [
    "css:ul.snap_list",
    "css:ul.search-result",
    "css:div.snap-list",
    "css:section#searchList",
    "css:div.sc-list",
]
GENDER_FILTERS = {
    "M": [
        "xpath://button[contains(., '남') or contains(., '남성') or contains(., '남자')]",
        "xpath://a[contains(., '남자')]",
        "xpath://label[contains(., '남자') or contains(., '남성')]",
    ],
    "F": [
        "xpath://button[contains(., '여') or contains(., '여성') or contains(., '여자')]",
        "xpath://a[contains(., '여자')]",
        "xpath://label[contains(., '여자') or contains(., '여성')]",
    ],
}
RECOMMEND_URL = "https://www.musinsa.com/main/musinsa/recommend?gf={gender}"


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
        raise ValueError(f"{file_path.name} must contain a list of queries or query objects")

    if not queries:
        raise ValueError(f"No queries found in {file_path.name}")
    return queries


def safe_slug(text: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z가-힣_-]+", "_", text)
    return slug.strip("_") or "snap"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _find_first(driver: webdriver.Chrome, selectors: Sequence[str], timeout: int = 5):
    wait = WebDriverWait(driver, timeout)
    for raw in selectors:
        try:
            if raw.startswith("xpath:"):
                selector = raw.replace("xpath:", "", 1)
                locator = (By.XPATH, selector)
            elif raw.startswith("css:"):
                selector = raw.replace("css:", "", 1)
                locator = (By.CSS_SELECTOR, selector)
            else:
                locator = (By.CSS_SELECTOR, raw)
            element = wait.until(EC.visibility_of_element_located(locator))
            return element
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
        json_path: Path = Path("snaps.json"),
        max_per_query: int | None = None,
        scroll_delay: float = 1.5,
        client_delay: float = 0.3,
        headless: bool = False,
        gender: str = "M",
    ) -> None:
        self.tags_file = tags_file
        self.output_dir = output_dir
        self.csv_path = csv_path
        self.json_path = json_path
        self.max_per_query = max_per_query
        self.scroll_delay = scroll_delay
        self.client = MusinsaClient(delay=client_delay)
        self.headless = headless
        self.gender = gender
        self._records: list[dict[str, str | None]] = []

    def _build_driver(self) -> webdriver.Chrome:
        options = ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_window_size(1440, 900)
        driver.implicitly_wait(5)
        return driver

    def run(self) -> None:
        queries = load_queries(self.tags_file)
        driver = self._build_driver()
        try:
            for query in queries:
                self.process_query(driver, query)
        finally:
            driver.quit()
        self._write_json()

    def process_query(self, driver: webdriver.Chrome, query: Query) -> None:
        LOGGER.info("Processing query '%s'", query.query)
        driver.get(RECOMMEND_URL.format(gender=self.gender))
        self._fill_search(driver, query.query)
        self._click_snap_tab(driver)
        self._apply_gender_filter(driver)
        self._click_first_snap(driver)
        detail_urls = self._collect_snap_links(driver, limit=self.max_per_query)
        LOGGER.info("Found %s snap links for %s", len(detail_urls), query.label)

        rows = []
        for link in detail_urls:
            snap = self._fetch_snap(driver, link)
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
        self._records.extend(rows)

    def _fill_search(self, driver: webdriver.Chrome, query: str) -> None:
        input_box = _find_first(driver, SEARCH_INPUT_CANDIDATES, timeout=8)
        if not input_box:
            raise RuntimeError("검색창을 찾을 수 없습니다.")
        input_box.clear()
        input_box.send_keys(query)
        input_box.send_keys(Keys.ENTER)
        # 검색 결과가 표시될 때까지 컨테이너를 기다린다.
        container = _find_first(driver, RESULT_CONTAINER_CANDIDATES, timeout=10)
        if not container:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))

    def _click_snap_tab(self, driver: webdriver.Chrome) -> None:
        tab = _find_first(driver, SNAP_TAB_CANDIDATES, timeout=6)
        if tab:
            tab.click()
            container = _find_first(driver, RESULT_CONTAINER_CANDIDATES, timeout=10)
            if not container:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        else:
            LOGGER.warning("SNAP 탭을 찾지 못했습니다. 전체 결과에서 진행합니다.")

    def _apply_gender_filter(self, driver: webdriver.Chrome) -> None:
        filters = GENDER_FILTERS.get(self.gender.upper())
        if not filters:
            return
        for selector in filters:
            handle = _find_first(driver, [selector], timeout=4)
            if handle:
                try:
                    handle.click()
                    _find_first(driver, RESULT_CONTAINER_CANDIDATES, timeout=6)
                    return
                except Exception:
                    continue

    def _click_first_snap(self, driver: webdriver.Chrome) -> None:
        first_card = _find_first(driver, [SNAP_CARD_SELECTOR])
        if first_card:
            driver.execute_script("arguments[0].scrollIntoView(true);", first_card)
            first_card.click()
            time.sleep(1)
            driver.back()
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        else:
            LOGGER.warning("첫 번째 SNAP 이미지를 찾지 못했습니다.")

    def _collect_snap_links(self, driver: webdriver.Chrome, *, limit: int | None = None) -> list[str]:
        target = limit or 10
        seen: set[str] = set()
        ordered: list[str] = []
        no_new_rounds = 0

        while True:
            links = driver.find_elements(By.CSS_SELECTOR, SNAP_CARD_SELECTOR)
            for link in links:
                href = link.get_attribute("href")
                if not href or not SNAP_LINK_PATTERN.search(href):
                    continue
                absolute = urljoin(DEFAULT_BASE_URL, href)
                if absolute in seen:
                    continue
                seen.add(absolute)
                ordered.append(absolute)
                if len(ordered) >= target:
                    break
            if len(ordered) >= target:
                break

            previous_count = len(seen)
            driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
            time.sleep(self.scroll_delay)
            if len(seen) == previous_count:
                no_new_rounds += 1
            else:
                no_new_rounds = 0
            if no_new_rounds >= 3:
                break
        return ordered[:target]

    def _fetch_snap(self, driver: webdriver.Chrome, url: str):
        current = driver.current_window_handle
        try:
            driver.switch_to.new_window("tab")
            driver.get(url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
            html = driver.page_source
            snap = parse_snap_detail(html, self.client.base_url, existing=Snap(id=None, url=url))
            if (not snap.tags) or (not snap.image_url):
                snap = self._enrich_with_driver(driver, snap)
            return snap
        except Exception as exc:  # pragma: no cover - network issues
            LOGGER.warning("%s 에서 스냅을 불러오지 못했습니다: %s", url, exc)
            return None
        finally:
            try:
                driver.close()
                driver.switch_to.window(current)
            except Exception:
                pass

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

    def _enrich_with_driver(self, driver: webdriver.Chrome, snap: Snap) -> Snap:
        """Fill missing tags or image URLs directly from the rendered page.

        일부 페이지는 동적 로딩으로 인해 파서가 빈 태그/이미지를 반환할 수 있으므로
        셀레니움 드라이버가 로드한 DOM을 한 번 더 살펴본다.
        """

        try:
            if not snap.tags:
                tag_nodes = driver.find_elements(By.CSS_SELECTOR, "a.tag, a[class*='tag'], .styling_tag a, .article-tag-list a")
                tags: list[str] = []
                seen: set[str] = set()
                for node in tag_nodes:
                    text = (node.text or "").strip().lstrip("#")
                    if not text:
                        continue
                    normalized = text.lower()
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    tags.append(text)
                snap.tags = tags

            if not snap.image_url:
                image = _find_first(
                    driver,
                    [
                        "css:div.article-photo img",
                        "css:div.photo img",
                        "css:div.detail_img img",
                        "css:div.snap-photo img",
                        "css:img[src*='snap']",
                    ],
                    timeout=4,
                )
                if image and image.get_attribute("src"):
                    snap.image_url = image.get_attribute("src")
        except Exception:
            LOGGER.debug("DOM enrichment skipped due to parsing error", exc_info=True)
        return snap

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

    def _write_json(self) -> None:
        ensure_parent(self.json_path)
        existing: list[dict[str, str | None]] = []
        if self.json_path.exists():
            try:
                existing = json.loads(self.json_path.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        payload = existing + self._records
        self.json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_cli_args(argv: Sequence[str] | None = None):
    import argparse

    parser = argparse.ArgumentParser(description="Automate Musinsa SNAP scraping with Selenium")
    parser.add_argument(
        "--tags-file",
        type=Path,
        default=Path("musinsa_snap_clooecter.json"),
        help="검색에 사용할 태그 JSON 파일 경로",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("downloads"), help="이미지 저장 디렉토리")
    parser.add_argument("--csv", type=Path, default=Path("snaps.csv"), help="CSV 저장 경로")
    parser.add_argument("--json", type=Path, default=Path("snaps.json"), help="JSON 저장 경로")
    parser.add_argument("--limit", type=int, default=None, help="태그별 최대 스냅 수")
    parser.add_argument("--scroll-delay", type=float, default=1.5, help="스크롤 사이 대기 시간(초)")
    parser.add_argument("--request-delay", type=float, default=0.3, help="HTTP 요청 간 대기 시간(초)")
    parser.add_argument("--headless", action="store_true", help="헤드리스 모드 사용")
    parser.add_argument("--gender", choices=["M", "F"], default="M", help="필터할 성별")
    parser.add_argument("--verbose", action="store_true", help="디버그 로그 표시")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_cli_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="[%(levelname)s] %(message)s")
    automation = SnapAutomation(
        tags_file=args.tags_file,
        output_dir=args.output_dir,
        csv_path=args.csv,
        json_path=args.json,
        max_per_query=args.limit,
        scroll_delay=args.scroll_delay,
        client_delay=args.request_delay,
        headless=args.headless,
        gender=args.gender,
    )
    automation.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
