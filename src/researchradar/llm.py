"""Opt-in OpenRouter client. No paid call is made by ordinary demos or tests."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import requests


MODEL = "qwen/qwen3.5-35b-a3b"
BASE = "https://openrouter.ai/api/v1"


def local_key() -> str | None:
    key = os.getenv("OPENROUTER_API_KEY")
    if key:
        return key
    root = os.getenv("LOCALAPPDATA")
    if not root:
        return None
    path = Path(root) / "ResearchRadar_MAS" / ".env"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.partition("=")[2].strip().strip('"').strip("'") or None
    return None


@dataclass
class Usage:
    request_id: str
    agent: str
    purpose: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None
    estimated_usd: float
    success: bool
    at: str


class BudgetedOpenRouter:
    def __init__(self, budget_usd: float = 0.10, per_call_usd: float = 0.05):
        self.budget_usd = budget_usd
        self.per_call_usd = per_call_usd
        self.spent_or_reserved = 0.0
        self.ledger: list[Usage] = []

    def complete(self, *, request_id: str, agent: str, purpose: str,
                 prompt: str, max_tokens: int = 128,
                 input_rate_per_million: float,
                 output_rate_per_million: float) -> str:
        if max_tokens < 1 or max_tokens > 512 or len(prompt) > 4000:
            raise ValueError("prompt or output limit exceeds smoke-test bounds")
        # Conservative character-to-token bound, then reserve before sending.
        estimated = (len(prompt.encode("utf-8")) * input_rate_per_million +
                     max_tokens * output_rate_per_million) / 1_000_000
        if estimated > self.per_call_usd or self.spent_or_reserved + estimated > self.budget_usd:
            raise RuntimeError("local LLM budget exceeded before request")
        key = local_key()
        if not key:
            raise RuntimeError("OpenRouter key unavailable in local configuration")
        self.spent_or_reserved += estimated
        usage = Usage(request_id, agent, purpose, MODEL, 0, 0, None, estimated,
                      False, datetime.now(timezone.utc).isoformat())
        try:
            response = requests.post(f"{BASE}/chat/completions", json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "usage": {"include": True}}, timeout=30,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"})
            response.raise_for_status()
            body = response.json()
            stats = body.get("usage") or {}
            usage.prompt_tokens = int(stats.get("prompt_tokens") or 0)
            usage.completion_tokens = int(stats.get("completion_tokens") or 0)
            cost = stats.get("cost")
            usage.cost_usd = float(cost) if cost is not None else None
            if usage.cost_usd is not None:
                self.spent_or_reserved += usage.cost_usd - estimated
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty or malformed LLM response")
            usage.success = True
            return content
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"OpenRouter request failed: {type(exc).__name__}") from None
        finally:
            # No secret, prompts or raw response enter the ledger.
            self.ledger.append(usage)

    def save_ledger(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([asdict(x) for x in self.ledger], indent=2),
                        encoding="utf-8")
