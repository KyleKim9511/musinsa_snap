from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Iterable

from .client import DEFAULT_BASE_URL, MusinsaClient
from .models import Snap
from .parser import parse_snap_detail, parse_snap_listing

LOGGER = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )


def write_json(snaps: Iterable[Snap], output: Path) -> None:
    data = [snap.to_dict() for snap in snaps]
    with output.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)


def write_csv(snaps: Iterable[Snap], output: Path) -> None:
    fieldnames = [
        "id",
        "url",
        "title",
        "author",
        "image_url",
        "taken_at",
        "description",
        "tags",
    ]
    with output.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for snap in snaps:
            row = snap.to_dict()
            row["tags"] = ", ".join(snap.tags)
            writer.writerow(row)


def collect_snaps(
    *,
    keyword: str,
    start_page: int,
    end_page: int,
    limit: int | None,
    gender: str | None,
    client: MusinsaClient,
) -> list[Snap]:
    results: list[Snap] = []

    for page in range(start_page, end_page + 1):
        LOGGER.info("Fetching listing page %s", page)
        listing_html = client.fetch_listing(keyword=keyword, page=page, gender=gender)
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
    parser.add_argument("keyword", help="검색 키워드 (예: 나이키)")
    parser.add_argument("--start-page", type=int, default=1, help="첫 페이지 (기본값: 1)")
    parser.add_argument("--end-page", type=int, default=1, help="마지막 페이지 (기본값: 1)")
    parser.add_argument("--limit", type=int, default=None, help="수집할 최대 스냅 수")
    parser.add_argument("--gender", choices=["M", "F"], default=None, help="성별 필터 (M 또는 F)")
    parser.add_argument("--delay", type=float, default=0.5, help="요청 간 대기 시간(초)")
    parser.add_argument(
        "--base-url",
        type=str,
        default=DEFAULT_BASE_URL,
        help="무신사 기본 도메인 (기본값: www.musinsa.com)",
    )
    parser.add_argument("--retries", type=int, default=2, help="요청 재시도 횟수")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=Path("snaps.json"),
        help="저장할 JSON 파일 경로",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=None,
        help="CSV로도 저장하려면 경로를 지정",
    )
    parser.add_argument("--verbose", action="store_true", help="디버그 로그 출력")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)

    client = MusinsaClient(delay=args.delay, base_url=args.base_url, retries=args.retries)
    snaps = collect_snaps(
        keyword=args.keyword,
        start_page=args.start_page,
        end_page=args.end_page,
        limit=args.limit,
        gender=args.gender,
        client=client,
    )

    write_json(snaps, args.json_out)
    LOGGER.info("Saved %s snaps to %s", len(snaps), args.json_out)
    if args.csv_out:
        write_csv(snaps, args.csv_out)
        LOGGER.info("Saved CSV to %s", args.csv_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
