"""Optional RSS/Atom news with short metadata snippets and deduplication."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from time import monotonic
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit
from xml.etree.ElementTree import ParseError

import httpx
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]
from defusedxml.ElementTree import fromstring  # type: ignore[import-untyped]
from pydantic import HttpUrl, ValidationError

from f1_pitwall.intelligence.models import NewsFeed, NewsItem


class NewsProvider(Protocol):
    def latest(self, limit: int = 30) -> NewsFeed: ...


class RssNewsProvider:
    """Configured feeds only; never scrape article bodies or invent missing news."""

    def __init__(
        self,
        feeds: tuple[str, ...] = (),
        client: httpx.Client | None = None,
        tags: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.feeds = feeds
        self.client = client or httpx.Client(timeout=15, follow_redirects=True)
        self.tags = tags or {}
        self._cached: tuple[float, NewsFeed] | None = None

    def close(self) -> None:
        self.client.close()

    def latest(self, limit: int = 30) -> NewsFeed:
        if not 1 <= limit <= 100:
            raise ValueError("news limit must be 1..100")
        if self._cached and monotonic() - self._cached[0] < 300:
            return self._cached[1].model_copy(update={"items": self._cached[1].items[:limit]})
        if not self.feeds:
            return NewsFeed(items=(), warnings=("No news feeds configured.",))
        items = []
        warnings = []
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        for feed in self.feeds:
            try:
                response = self.client.get(feed, headers={"User-Agent": "F1VirtualPitWall/0.2"})
                response.raise_for_status()
                if len(response.content) > 2_000_000:
                    raise ValueError("feed too large")
                root = fromstring(response.content)
                for entry in root.iter():
                    if entry.tag.rsplit("}", 1)[-1] not in {"item", "entry"}:
                        continue
                    fields = {child.tag.rsplit("}", 1)[-1]: child for child in entry}
                    title = "".join(fields["title"].itertext()).strip() if "title" in fields else ""
                    link = fields.get("link")
                    url = (link.get("href") or link.text or "").strip() if link is not None else ""
                    split = urlsplit(url)
                    if not title or split.scheme not in {"https", "http"} or not split.netloc:
                        continue
                    canonical = urlunsplit(
                        (
                            split.scheme,
                            split.netloc.lower(),
                            split.path.rstrip("/"),
                            "&".join(
                                part
                                for part in split.query.split("&")
                                if part and not part.lower().startswith("utm_")
                            ),
                            "",
                        )
                    )
                    title_key = re.sub(r"\W+", "", title.casefold())
                    if canonical in seen_urls or title_key in seen_titles:
                        continue
                    published = None
                    for key in ("pubDate", "published", "updated"):
                        if key in fields and fields[key].text:
                            try:
                                raw = fields[key].text or ""
                                published = (
                                    parsedate_to_datetime(raw)
                                    if key == "pubDate"
                                    else datetime.fromisoformat(raw)
                                ).astimezone(UTC)
                            except (ValueError, TypeError):
                                pass
                            break
                    description = fields.get("description")
                    if description is None:
                        description = fields.get("summary")
                    snippet = None
                    if description is not None:
                        snippet = re.sub(r"<[^>]+>", "", unescape("".join(description.itertext())))
                        snippet = " ".join(snippet.split())[:300] or None
                    lowered = title.casefold()
                    categories = {
                        "PENALTY": ("penalty", "penalties"),
                        "TRANSFER": ("signs", "transfer"),
                        "QUALIFYING": ("qualifying", "pole"),
                        "FIA": ("fia",),
                        "TECHNICAL": ("upgrade", "technical"),
                        "WEATHER": ("rain", "weather"),
                        "RACE": ("race", "grand prix"),
                        "DRIVER": ("driver",),
                        "TEAM": ("team",),
                    }
                    category = next(
                        (
                            key
                            for key, words in categories.items()
                            if any(re.search(r"\b" + word + r"\b", lowered) for word in words)
                        ),
                        "GENERAL",
                    )

                    def tagged(kind: str, lowered: str = lowered) -> tuple[str, ...]:
                        return tuple(
                            identifier
                            for label, identifier in self.tags.get(kind, {}).items()
                            if re.search(r"\b" + re.escape(label.casefold()) + r"\b", lowered)
                        )

                    items.append(
                        NewsItem(
                            headline=title,
                            source=split.netloc.lower(),
                            url=HttpUrl(canonical),
                            published_at=published,
                            snippet=snippet,
                            category=category,
                            driver_tags=tagged("driver"),
                            team_tags=tagged("team"),
                            event_tags=tagged("event"),
                        )
                    )
                    seen_urls.add(canonical)
                    seen_titles.add(title_key)
            except (httpx.HTTPError, ValueError, ParseError, DefusedXmlException, ValidationError):
                warnings.append(f"News feed unavailable: {urlsplit(feed).netloc}")
        result = NewsFeed(
            items=tuple(
                sorted(
                    items,
                    key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC),
                    reverse=True,
                )
            ),
            warnings=tuple(warnings),
        )
        self._cached = (monotonic(), result)
        return result.model_copy(update={"items": result.items[:limit]})
