from __future__ import annotations

from typing import Protocol
from pathlib import Path
import hashlib
import json
import os
import random
import time
from dataclasses import asdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
import requests

from .model import Material


class SourceError(RuntimeError):
    pass


class Source(Protocol):
    def search(self, query: str, limit: int) -> list[Material]: ...


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _rss_date(value: object) -> str | None:
    text = _text(value)
    if not text:
        return None
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def normalize_openalex(row: dict, provenance: str = "live_api") -> Material | None:
    title = _text(row.get("display_name"))
    url = _text(row.get("id"))
    if not title or not url:
        return None
    abstract = None
    index = row.get("abstract_inverted_index")
    if isinstance(index, dict):
        positions = [(int(p), word) for word, pp in index.items()
                     if isinstance(pp, list) for p in pp if isinstance(p, int)]
        abstract = " ".join(w for _, w in sorted(positions)) or None
    doi = _text(row.get("doi")) or None
    authors = tuple(name for author in row.get("authorships", [])
                    if isinstance(author, dict) and isinstance(author.get("author"), dict)
                    if (name := _text(author["author"].get("display_name"))))
    location = row.get("primary_location") or {}
    venue = _text((location.get("source") or {}).get("display_name")) if isinstance(location, dict) else ""
    return Material("scientific", "OpenAlex", url, title, url,
                    _text(row.get("publication_date")) or None,
                    abstract, doi, "abstract" if abstract else "metadata", provenance,
                    authors, venue or None, None, ("OpenAlex",))


def normalize_gdelt(row: dict, provenance: str = "live_api") -> Material | None:
    title, url = _text(row.get("title")), _text(row.get("url"))
    if not title or not url:
        return None
    date = _text(row.get("seendate")) or None
    return Material("news", "GDELT", url, title, url, date,
                    None, None, "headline", provenance)


class OpenAlex:
    def search(self, query: str, limit: int = 3) -> list[Material]:
        try:
            response = requests.get("https://api.openalex.org/works", params={
                "search": query, "per-page": limit,
                "select": "id,display_name,publication_date,doi,abstract_inverted_index,authorships,primary_location"},
                timeout=15, headers={"User-Agent": "ResearchRadar-MAS/0.1 (academic demo)"})
            response.raise_for_status()
            rows = response.json()["results"]
            if not isinstance(rows, list):
                raise ValueError("results is not a list")
            return [item for row in rows if isinstance(row, dict)
                    if (item := normalize_openalex(row))]
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            raise SourceError(f"OpenAlex: {type(exc).__name__}") from exc


class GDELT:
    def __init__(self, cache_dir: Path | None = None, retries: int = 1,
                 sleeper=time.sleep, ttl_seconds: int = 900):
        root = os.getenv("LOCALAPPDATA")
        self.cache_dir = cache_dir if cache_dir is not None else (
            Path(root) / "ResearchRadar_MAS" / "gdelt-cache" if root else None)
        self.retries = retries
        self.sleeper = sleeper
        self.ttl_seconds = ttl_seconds

    def _cache_file(self, query: str, limit: int) -> Path | None:
        if self.cache_dir is None:
            return None
        key = hashlib.sha256(f"{query}\0{limit}".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.json"

    def search(self, query: str, limit: int = 3) -> list[Material]:
        cache_file = self._cache_file(query, limit)
        if cache_file and cache_file.exists() and time.time() - cache_file.stat().st_mtime < self.ttl_seconds:
            try:
                rows = json.loads(cache_file.read_text(encoding="utf-8"))
                return [Material(**(row | {"provenance": "cache_gdelt"})) for row in rows]
            except (ValueError, TypeError):
                pass
        params = {"query": query, "mode": "artlist", "format": "json",
                  "maxrecords": min(max(limit, 1), 250), "timespan": "3months"}
        for attempt in range(self.retries + 1):
            try:
                response = requests.get("https://api.gdeltproject.org/api/v2/doc/doc",
                                        params=params, timeout=15)
                if response.status_code == 429:
                    if attempt < self.retries:
                        delay = _retry_delay(response.headers.get("Retry-After"), attempt)
                        if delay is None:
                            raise SourceError("GDELT: HTTP 429; Retry-After exceeds local wait limit")
                        self.sleeper(delay)
                        continue
                    raise SourceError("GDELT: HTTP 429 rate limited")
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise SourceError("GDELT: invalid response format")
                rows = body.get("articles", [])
                if not isinstance(rows, list):
                    raise SourceError("GDELT: invalid articles format")
                items = [item for row in rows if isinstance(row, dict)
                         if (item := normalize_gdelt(row))]
                if cache_file:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(json.dumps([asdict(x) for x in items]), encoding="utf-8")
                return items
            except (requests.RequestException, ValueError, TypeError) as exc:
                raise SourceError(f"GDELT: {type(exc).__name__}") from exc
        raise AssertionError("unreachable")


def _retry_delay(header: str | None, attempt: int) -> float | None:
    if header:
        try:
            seconds = max(0.0, float(header))
        except ValueError:
            try:
                seconds = max(0.0, (parsedate_to_datetime(header) -
                                    datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                seconds = None
        if seconds is not None:
            return seconds if seconds <= 30 else None
    return min(10.0, 2 ** attempt + random.uniform(0, 0.25))


class GoogleNewsRSS:
    """Public search feed; stores only title, link and publication date."""

    def __init__(self, cache_dir: Path | None = None, ttl_seconds: int = 900):
        root = os.getenv("LOCALAPPDATA")
        self.cache_dir = cache_dir if cache_dir is not None else (
            Path(root) / "ResearchRadar_MAS" / "rss-cache" if root else None)
        self.ttl_seconds = ttl_seconds

    def search(self, query: str, limit: int = 3) -> list[Material]:
        cache_file = None
        if self.cache_dir:
            key = hashlib.sha256(f"{query}\0{limit}".encode()).hexdigest()
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists() and time.time() - cache_file.stat().st_mtime < self.ttl_seconds:
                try:
                    rows = json.loads(cache_file.read_text(encoding="utf-8"))
                    return [Material(**(row | {"provenance": "cache_rss"})) for row in rows]
                except (ValueError, TypeError):
                    pass
        try:
            response = requests.get("https://news.google.com/rss/search", params={
                "q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}, timeout=15)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
            items = []
            for node in root.findall("./channel/item"):
                title = _text(node.findtext("title"))
                url = _text(node.findtext("link"))
                if not title or not url:
                    continue
                items.append(Material("news", "Google News RSS", url, title, url,
                                      _rss_date(node.findtext("pubDate")),
                                      None, None, "headline", "live_rss"))
                if len(items) >= limit:
                    break
            if cache_file:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps([asdict(x) for x in items]), encoding="utf-8")
            return items
        except (requests.RequestException, ElementTree.ParseError) as exc:
            raise SourceError(f"Google News RSS: {type(exc).__name__}") from exc


class FixtureSource:
    def __init__(self, kind: str):
        self.kind = kind

    def search(self, query: str, limit: int = 3) -> list[Material]:
        # Invented fixtures are visibly labeled and never presented as real findings.
        if self.kind == "scientific":
            rows = [{"id": "fixture:openalex:1", "display_name": "Synthetic scientific example",
                     "publication_date": "2025-01-01"}]
            return [x for row in rows[:limit]
                    if (x := normalize_openalex(row, "synthetic_fixture"))]
        rows = [{"url": "fixture:gdelt:1", "title": "Synthetic news example",
                 "seendate": "20250101T000000Z"}]
        return [x for row in rows[:limit]
                if (x := normalize_gdelt(row, "synthetic_fixture"))]
