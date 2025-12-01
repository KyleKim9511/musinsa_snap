from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Iterable

from .client import MusinsaClient, BASE_URL
from .models import Snap
from .parser import parse_snap_detail, parse_snap_listing

LOGGER = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )


def write_jsonl(snaps: Iterable[Snap], output: Path) -> None:
    with output.open("w", encoding="utf-8") as fp:
        for snap in snaps:
            fp.write(json.dumps(snap.to_dict(), ensure_ascii=False) + "\n")


def collect_snaps(
    *, start_page: int, end_page: int, limit: int | None, client: MusinsaClient
) -> list[Snap]:
    results: list[Snap] = []

    for page in range(start_page, end_page + 1):
        LOGGER.info("Fetching listing page %s", page)
        listing_html = client.fetch_listing(page)
        stubs = parse_snap_listing(listing_html, client.base_url)
        LOGGER.info("Found %s entries on page %s", len(stubs), page)

        for stub in stubs:
            if limit and len(results) >= limit:
                LOGGER.info("Reached limit of %s snaps", limit)
                return results
            try:
                detail_html = client.fetch_detail(stub.url)
                snap = parse_snap_detail(detail_html, client.base_url, existing=stub)
                results.append(snap)
            except Exception as exc:  # pragma: no cover - network errors
                LOGGER.warning("Skipping %s due to %s", stub.url, exc)
                continue
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Musinsa snap photos and tags")
    parser.add_argument("--start-page", type=int, default=1, help="첫 페이지 (기본값: 1)")
    parser.add_argument("--end-page", type=int, default=1, help="마지막 페이지 (기본값: 1)")
    parser.add_argument("--limit", type=int, default=None, help="수집할 최대 스냅 수")
    parser.add_argument("--delay", type=float, default=0.5, help="요청 간 대기 시간(초)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("snaps.jsonl"),
        help="저장할 JSON Lines 파일 경로",
    )
    parser.add_argument("--verbose", action="store_true", help="디버그 로그 출력")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)

    client = MusinsaClient(delay=args.delay, base_url=BASE_URL)
    snaps = collect_snaps(
        start_page=args.start_page,
        end_page=args.end_page,
        limit=args.limit,
        client=client,
    )

    write_jsonl(snaps, args.output)
    LOGGER.info("Saved %s snaps to %s", len(snaps), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
