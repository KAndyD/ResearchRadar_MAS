from __future__ import annotations

from typing import Protocol
import requests

from .model import Material


class SourceError(RuntimeError):
    pass


class Source(Protocol):
    def search(self, query: str, limit: int) -> list[Material]: ...


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


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
    return Material("scientific", "OpenAlex", url, title, url,
                    _text(row.get("publication_date")) or None,
                    abstract, doi, "abstract" if abstract else "metadata", provenance)


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
                "select": "id,display_name,publication_date,doi,abstract_inverted_index"},
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
    def search(self, query: str, limit: int = 3) -> list[Material]:
        try:
            response = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params={
                "query": query, "mode": "artlist", "format": "json", "maxrecords": limit},
                timeout=15, headers={"User-Agent": "ResearchRadar-MAS/0.1 (academic demo)"})
            response.raise_for_status()
            rows = response.json().get("articles", [])
            if not isinstance(rows, list):
                raise ValueError("articles is not a list")
            return [item for row in rows if isinstance(row, dict)
                    if (item := normalize_gdelt(row))]
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            raise SourceError(f"GDELT: {type(exc).__name__}") from exc


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
