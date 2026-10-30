"""Clearly marked, frozen synthetic sources for offline tests and experiments."""
from __future__ import annotations

import json
from pathlib import Path

from .model import Material


class FrozenSource:
    def __init__(self, rows: list[dict]):
        self.rows = [Material(**row) for row in rows]

    def search(self, query: str, limit: int = 3) -> list[Material]:
        return self.rows[:limit]


def load_frozen(path: Path | None = None) -> dict[str, FrozenSource]:
    if path is None:
        path = Path(__file__).resolve().parents[2] / "data" / "frozen_sources.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: FrozenSource(rows) for key, rows in data.items() if key != "description"}
