from __future__ import annotations

import logging
import re
from typing import Iterable, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import Snap

LOGGER = logging.getLogger(__name__)

SNAP_LINK_PATTERN = re.compile(r"/(?:snap/)(\d+)")


def _dedupe_snaps(snaps: Iterable[Snap]) -> list[Snap]:
    seen = set()
    unique: list[Snap] = []
    for snap in snaps:
        if snap.url in seen:
            continue
        seen.add(snap.url)
        unique.append(snap)
    return unique


def _extract_image(link_tag) -> str | None:
    img = link_tag.find("img") if link_tag else None
    if not img:
        return None
    for attr in ("data-original", "data-src", "src"):
        if img.get(attr):
            return img[attr]
    return None


def parse_snap_listing(html: str, base_url: str) -> list[Snap]:
    """Parse the Musinsa snap search results and return snap stubs."""

    soup = BeautifulSoup(html, "html.parser")
    snaps: List[Snap] = []

    card_selectors = [
        "li.snap-article",
        "li.snap_item",
        "li.li_snap",
        "div.snap-list__item",
        "div.sc-list-item",
        "div.snap-grid-item",
        "ul.snap_list li",
    ]

    cards = []
    for selector in card_selectors:
        cards.extend(soup.select(selector))
    if not cards:
        cards = soup.find_all("a", href=SNAP_LINK_PATTERN)

    for card in cards:
        link = card if card.name == "a" else card.find("a", href=SNAP_LINK_PATTERN)
        if not link:
            continue
        href = link.get("href")
        if not href:
            continue
        match = SNAP_LINK_PATTERN.search(href)
        snap_id = match.group(1) if match else None
        url = urljoin(base_url, href)
        thumbnail = _extract_image(link)
        if thumbnail:
            thumbnail = urljoin(base_url, thumbnail)

        title_node = card.select_one(".title, .tit, .snap_txt, .info-title, .list_info") or link
        title = title_node.get_text(strip=True) if title_node else None
        if not title and thumbnail:
            title = link.get("title") or link.get("aria-label")

        author_node = card.select_one(".user-nick, .writer, .user, .info-user")
        author = author_node.get_text(strip=True) if author_node else None

        snaps.append(
            Snap(id=snap_id, url=url, title=title, image_url=thumbnail, author=author)
        )

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
        title_meta = _extract_meta_content(soup, "og:title")
        heading = soup.select_one("h2.title, h1.title, .snap_tit, .article_tit")
        snap.title = title_meta or (heading.get_text(strip=True) if heading else None)

    if not snap.image_url:
        snap.image_url = _extract_meta_content(soup, "og:image") or _extract_primary_image(
            soup, base_url
        )

    description = _extract_meta_content(soup, "og:description")
    if description:
        snap.description = description

    author = soup.select_one(".writer, .author, .profile-txt, .profile_info, .user-nick")
    if author:
        snap.author = author.get_text(strip=True)

    date_node = soup.select_one(".date, .post-date, time, .reg-date")
    if date_node and not snap.taken_at:
        snap.taken_at = date_node.get_text(strip=True)

    if not snap.id:
        canonical = _extract_meta_content(soup, "og:url")
        match = SNAP_LINK_PATTERN.search(canonical or snap.url)
        snap.id = match.group(1) if match else None

    tags = _extract_tags(soup)
    snap.tags = tags

    return snap


def _extract_primary_image(soup: BeautifulSoup, base_url: str) -> str | None:
    containers = [
        "div.article-photo", "div.photo", "div.detail_img", "div.img-list", "div.snap-photo",
    ]
    for selector in containers:
        for node in soup.select(selector):
            img = node.find("img")
            if not img:
                continue
            for attr in ("data-original", "data-src", "src"):
                if img.get(attr):
                    return urljoin(base_url, img[attr])
    fallback = soup.find("img", attrs={"src": re.compile("snap")})
    if fallback and fallback.get("src"):
        return urljoin(base_url, fallback["src"])
    return None


def _extract_tags(soup: BeautifulSoup) -> list[str]:
    candidates = []

    for selector in [
        ".tag",
        ".tags",
        ".hash-tag",
        "a[href*='tag=']",
        "a[class*='tag']",
        "#hashtag a",
        "ul.article-tag-list a",
        "div.styling_tag a",
        "div.tag_list a",
    ]:
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
