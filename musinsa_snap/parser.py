from __future__ import annotations

import logging
import re
from typing import Iterable, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import Snap

LOGGER = logging.getLogger(__name__)

SNAP_LINK_PATTERN = re.compile(r"/(?:mz/)?snap/(\d+)")


def _dedupe_snaps(snaps: Iterable[Snap]) -> list[Snap]:
    seen = set()
    unique: list[Snap] = []
    for snap in snaps:
        if snap.url in seen:
            continue
        seen.add(snap.url)
        unique.append(snap)
    return unique


def parse_snap_listing(html: str, base_url: str) -> list[Snap]:
    """Parse the Musinsa snap listing page and return snap stubs.

    This parser searches for anchor tags linking to ``/snap/<id>`` or
    ``/mz/snap/<id>``. The link text, nested ``img`` alt text, and src are used
    when available.
    """

    soup = BeautifulSoup(html, "html.parser")
    snaps: List[Snap] = []
    for link in soup.find_all("a", href=SNAP_LINK_PATTERN):
        href = link.get("href")
        if not href:
            continue
        match = SNAP_LINK_PATTERN.search(href)
        snap_id = match.group(1) if match else None
        url = urljoin(base_url, href)
        image_tag = link.find("img")
        title = link.get("title") or (image_tag.get("alt") if image_tag else None)
        thumbnail = image_tag.get("src") if image_tag else None
        if thumbnail:
            thumbnail = urljoin(base_url, thumbnail)
        snaps.append(Snap(id=snap_id, url=url, title=title, image_url=thumbnail))
    return _dedupe_snaps(snaps)


def _extract_meta_content(soup: BeautifulSoup, property_name: str) -> str | None:
    tag = soup.find("meta", property=property_name)
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def parse_snap_detail(html: str, base_url: str, *, existing: Snap | None = None) -> Snap:
    """Parse a snap detail page to enrich a :class:`Snap` instance."""

    soup = BeautifulSoup(html, "html.parser")
    snap = existing or Snap(id=None, url=base_url)

    if not snap.title:
        snap.title = _extract_meta_content(soup, "og:title") or soup.title.string if soup.title else None

    if not snap.image_url:
        snap.image_url = _extract_meta_content(soup, "og:image")

    description = _extract_meta_content(soup, "og:description")
    if description:
        snap.description = description

    author = soup.select_one(".writer, .author, .profile-txt, .profile_info")
    if author:
        snap.author = author.get_text(strip=True)

    date_node = soup.select_one(".date, .post-date, time")
    if date_node and not snap.taken_at:
        snap.taken_at = date_node.get_text(strip=True)

    if not snap.id:
        canonical = _extract_meta_content(soup, "og:url")
        match = SNAP_LINK_PATTERN.search(canonical or snap.url)
        snap.id = match.group(1) if match else None

    tags = _extract_tags(soup)
    snap.tags = tags

    return snap


def _extract_tags(soup: BeautifulSoup) -> list[str]:
    candidates = []

    for selector in [".tag", ".tags", ".hash-tag", "a[href*='tag=']", "a[class*='tag']"]:
        for node in soup.select(selector):
            text = node.get_text(strip=True)
            if not text:
                continue
            parts = [part.strip() for part in re.split(r"[#\s]+", text) if part.strip()]
            candidates.extend(parts)

    unique = []
    seen = set()
    for tag in candidates:
        normalized = tag.lstrip("#")
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            unique.append(normalized)
    return unique
