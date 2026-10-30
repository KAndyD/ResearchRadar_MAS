"""Scientific metadata adapters and conservative exact-identifier deduplication."""
from __future__ import annotations

from dataclasses import replace, asdict
from html import unescape
from pathlib import Path
from threading import Lock
from time import monotonic, sleep, time
from urllib.parse import quote
from xml.etree import ElementTree as ET
import hashlib
import json
import os
import re

import requests

from .model import Material
from .sources import SourceError

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


def _cache_root() -> Path | None:
    root = os.getenv("LOCALAPPDATA")
    return Path(root) / "ResearchRadar_MAS" / "source-cache" if root else None


def _cached(path: Path | None, ttl: int) -> list[Material] | None:
    if path and path.exists() and time() - path.stat().st_mtime < ttl:
        try:
            return [Material(**row) for row in json.loads(path.read_text(encoding="utf-8"))]
        except (ValueError, TypeError):
            return None
    return None


def _store(path: Path | None, rows: list[Material]) -> None:
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([asdict(row) for row in rows], ensure_ascii=False), encoding="utf-8")


def _path(root: Path | None, source: str, query: str, limit: int) -> Path | None:
    if root is None:
        return None
    digest = hashlib.sha256(f"{source}\0{query}\0{limit}".encode()).hexdigest()
    return root / f"{digest}.json"


def _clean(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def normalize_crossref(row: dict, provenance: str = "live_api") -> Material | None:
    doi = _clean(row.get("DOI"))
    titles = row.get("title") or []
    title = _clean(titles[0]) if isinstance(titles, list) and titles else ""
    if not doi or not title:
        return None
    authors = tuple(name for a in row.get("author", []) if isinstance(a, dict)
                    if (name := " ".join(filter(None, (_clean(a.get("given")), _clean(a.get("family")))))))
    date_parts = (row.get("published") or row.get("issued") or {}).get("date-parts", [])
    published = "-".join(str(x).zfill(2) if i else str(x) for i, x in enumerate(date_parts[0])) if date_parts else None
    venues = row.get("container-title") or []
    venue = _clean(venues[0]) if isinstance(venues, list) and venues else None
    abstract = _clean(unescape(re.sub(r"<[^>]+>", " ", row.get("abstract") or ""))) or None
    url = _clean(row.get("URL")) or f"https://doi.org/{quote(doi, safe='/')}"
    return Material("scientific", "Crossref", doi, title, url, published, abstract,
                    doi, "abstract" if abstract else "metadata", provenance,
                    authors, venue, None, ("Crossref",))


class Crossref:
    """Public REST search; optional caller-provided email enables the polite pool."""

    def __init__(self, cache_dir: Path | None = None, ttl_seconds: int = 86400):
        self.cache_dir = cache_dir if cache_dir is not None else _cache_root()
        self.ttl_seconds = ttl_seconds

    def search(self, query: str, limit: int = 3) -> list[Material]:
        path = _path(self.cache_dir, "crossref", query, limit)
        if (cached := _cached(path, self.ttl_seconds)) is not None:
            return [replace(x, provenance="cache_crossref") for x in cached]
        params = {"query.bibliographic": query, "rows": min(max(limit, 1), 20)}
        if email := os.getenv("CROSSREF_EMAIL"):
            params["mailto"] = email
        try:
            response = requests.get("https://api.crossref.org/works", params=params,
                                    timeout=15, headers={"User-Agent": "ResearchRadar-MAS/0.2 (metadata research)"})
            response.raise_for_status()
            rows = response.json()["message"]["items"]
            if not isinstance(rows, list):
                raise ValueError("invalid Crossref items")
            result = [item for row in rows if isinstance(row, dict)
                      if (item := normalize_crossref(row))][:limit]
            _store(path, result)
            return result
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            raise SourceError(f"Crossref: {type(exc).__name__}") from exc


def normalize_arxiv(entry: ET.Element, provenance: str = "live_api") -> Material | None:
    url = _clean(entry.findtext(f"{ATOM}id"))
    title = _clean(entry.findtext(f"{ATOM}title"))
    if not url or not title:
        return None
    arxiv_id = url.rsplit("/abs/", 1)[-1].split("v", 1)[0] if "/abs/" in url else url.rsplit("/", 1)[-1]
    authors = tuple(_clean(node.findtext(f"{ATOM}name")) for node in entry.findall(f"{ATOM}author"))
    abstract = _clean(entry.findtext(f"{ATOM}summary")) or None
    doi = _clean(entry.findtext(f"{ARXIV}doi")) or None
    return Material("scientific", "arXiv", arxiv_id, title, url,
                    _clean(entry.findtext(f"{ATOM}published")) or None, abstract,
                    doi, "abstract" if abstract else "metadata", provenance,
                    tuple(x for x in authors if x), None, arxiv_id, ("arXiv",))


class Arxiv:
    """Atom API; one request at a time and at least three seconds between calls."""

    def __init__(self, cache_dir: Path | None = None, ttl_seconds: int = 86400):
        self.cache_dir = cache_dir if cache_dir is not None else _cache_root()
        self.ttl_seconds = ttl_seconds
        self._lock = Lock()
        self._last_request = 0.0

    def search(self, query: str, limit: int = 3) -> list[Material]:
        path = _path(self.cache_dir, "arxiv", query, limit)
        if (cached := _cached(path, self.ttl_seconds)) is not None:
            return [replace(x, provenance="cache_arxiv") for x in cached]
        terms = re.findall(r"[\w-]+", query, flags=re.UNICODE)[:8]
        if not terms:
            raise ValueError("empty arXiv query")
        try:
            with self._lock:
                delay = 3.0 - (monotonic() - self._last_request)
                if delay > 0:
                    sleep(delay)
                response = requests.get("https://export.arxiv.org/api/query", params={
                    "search_query": " AND ".join(f"all:{term}" for term in terms), "start": 0,
                    "max_results": min(max(limit, 1), 20)}, timeout=20,
                    headers={"User-Agent": "ResearchRadar-MAS/0.2 (metadata research)"})
                self._last_request = monotonic()
            response.raise_for_status()
            root = ET.fromstring(response.content)
            result = [item for entry in root.findall(f"{ATOM}entry")
                      if (item := normalize_arxiv(entry))][:limit]
            _store(path, result)
            return result
        except (requests.RequestException, ET.ParseError) as exc:
            raise SourceError(f"arXiv: {type(exc).__name__}") from exc


def deduplicate(rows: list[Material]) -> list[Material]:
    """Merge only exact DOI or source/primary ID; retain every discovered source."""
    result: list[Material] = []
    by_key: dict[tuple[str, str], int] = {}
    for item in rows:
        doi = (item.doi or "").lower().removeprefix("https://doi.org/").strip()
        key = ("doi", doi) if doi else (item.source.lower(), item.source_id.lower())
        if key in by_key:
            pos = by_key[key]
            old = result[pos]
            result[pos] = replace(old, discovered_in=tuple(dict.fromkeys(
                (*old.discovered_in, old.source, *item.discovered_in, item.source))))
        else:
            by_key[key] = len(result)
            result.append(replace(item, discovered_in=item.discovered_in or (item.source,)))
    return result
