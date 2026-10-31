"""Opt-in OpenRouter client with a durable, conservative expense ledger."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from contextlib import contextmanager
import os
from pathlib import Path
import random
import sqlite3
import time
from uuid import uuid4

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


def default_ledger_path() -> Path:
    root = os.getenv("LOCALAPPDATA")
    if not root:
        raise RuntimeError("LOCALAPPDATA is required for a durable LLM ledger")
    return Path(root) / "ResearchRadar_MAS" / "usage.sqlite3"


@dataclass(frozen=True)
class ExpenseSummary:
    actual_usd: float
    uncertain_estimate_usd: float
    uncertain_calls: int
    total_calls: int


class BudgetedOpenRouter:
    def __init__(self, budget_usd: float = 8.0, per_call_usd: float = 0.05,
                 ledger_path: Path | None = None, max_retries: int = 1,
                 sleeper=time.sleep):
        self.budget_usd = budget_usd
        self.per_call_usd = per_call_usd
        self.path = ledger_path or default_ledger_path()
        self.max_retries = max_retries
        if max_retries < 0 or max_retries > 2:
            raise ValueError("max_retries must be between 0 and 2")
        self.sleeper = sleeper
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS calls (
                call_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, agent TEXT NOT NULL,
                purpose TEXT NOT NULL, model TEXT NOT NULL, at TEXT NOT NULL,
                status TEXT NOT NULL, provider_id TEXT, prompt_tokens INTEGER,
                completion_tokens INTEGER, actual_usd REAL, estimated_usd REAL NOT NULL,
                missing_cost_reason TEXT, error_type TEXT, attempts INTEGER NOT NULL DEFAULT 0
            )""")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def summary(self) -> ExpenseSummary:
        with self._db() as db:
            row = db.execute("""SELECT COALESCE(SUM(actual_usd),0),
                COALESCE(SUM(CASE WHEN actual_usd IS NULL THEN estimated_usd ELSE 0 END),0),
                SUM(CASE WHEN actual_usd IS NULL THEN 1 ELSE 0 END), COUNT(*) FROM calls""").fetchone()
        return ExpenseSummary(float(row[0]), float(row[1]), int(row[2]), int(row[3]))

    def records(self) -> list[dict]:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM calls ORDER BY at, call_id")]

    def _update(self, call_id: str, **fields) -> None:
        with self._db() as db:
            db.execute("UPDATE calls SET " + ", ".join(f"{k}=?" for k in fields)
                       + " WHERE call_id=?", (*fields.values(), call_id))

    def complete(self, *, request_id: str, agent: str, purpose: str,
                 prompt: str, max_tokens: int = 512,
                 input_rate_per_million: float,
                 output_rate_per_million: float,
                 system_prompt: str | None = None,
                 call_id: str | None = None) -> str:
        if not request_id or not agent or not purpose:
            raise ValueError("request identity and purpose required")
        if (max_tokens < 1 or max_tokens > 4096 or len(prompt) > 16000
                or system_prompt is not None and len(system_prompt) > 4000):
            raise ValueError("prompt or output limit exceeds bounds")
        if input_rate_per_million < 0 or output_rate_per_million < 0:
            raise ValueError("negative pricing")
        estimated = ((len(prompt.encode("utf-8")) +
                      len((system_prompt or "").encode("utf-8"))) * input_rate_per_million +
                     max_tokens * output_rate_per_million) / 1_000_000
        if estimated > self.per_call_usd:
            raise RuntimeError("per-call LLM budget exceeded before request")
        key = local_key()
        if not key:
            raise RuntimeError("OpenRouter key unavailable in local configuration")
        call_id = call_id or str(uuid4())
        at = datetime.now(timezone.utc).isoformat()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            committed = db.execute("""SELECT COALESCE(SUM(COALESCE(actual_usd,estimated_usd)),0)
                FROM calls""").fetchone()[0]
            if committed + estimated > self.budget_usd:
                raise RuntimeError("local LLM budget exceeded before request")
            try:
                db.execute("""INSERT INTO calls
                    (call_id,request_id,agent,purpose,model,at,status,estimated_usd,missing_cost_reason)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (call_id, request_id, agent, purpose, MODEL, at,
                     "pending", estimated, "awaiting provider response"))
            except sqlite3.IntegrityError:
                raise RuntimeError("duplicate call_id; request not sent") from None
        # The pending record is durable before any network operation.
        for attempt in range(1, self.max_retries + 2):
            self._update(call_id, attempts=attempt)
            try:
                messages = ([{"role": "system", "content": system_prompt}]
                            if system_prompt is not None else [])
                messages.append({"role": "user", "content": prompt})
                response = requests.post(f"{BASE}/chat/completions", json={
                    "model": MODEL,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "reasoning_effort": "none",
                    "usage": {"include": True}}, timeout=30,
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"})
                if response.status_code == 429 and attempt <= self.max_retries:
                    self._update(call_id, status="rate_limited", error_type="HTTP429")
                    delay = _retry_delay(response.headers.get("Retry-After"), attempt)
                    if delay is None:
                        self._update(call_id, status="http_error",
                                     missing_cost_reason="Retry-After exceeds local wait limit")
                        raise RuntimeError("OpenRouter HTTP 429; retry deferred")
                    self.sleeper(delay)
                    continue
                if response.status_code >= 400:
                    self._update(call_id, status="http_error",
                                 error_type=f"HTTP{response.status_code}",
                                 missing_cost_reason="provider did not supply usage")
                    raise RuntimeError(f"OpenRouter HTTP {response.status_code}")
                body = response.json()
                stats = body.get("usage") or {}
                actual = stats.get("cost")
                actual = float(actual) if actual is not None else None
                self._update(call_id, provider_id=body.get("id"),
                             prompt_tokens=stats.get("prompt_tokens"),
                             completion_tokens=stats.get("completion_tokens"),
                             actual_usd=actual,
                             missing_cost_reason=None if actual is not None else "usage.cost absent")
                content = body["choices"][0]["message"].get("content")
                if not isinstance(content, str) or not content.strip():
                    self._update(call_id, status="empty_response", error_type="EmptyContent")
                    raise RuntimeError("OpenRouter returned empty content")
                self._update(call_id, status="succeeded")
                return content
            except requests.Timeout:
                self._update(call_id, status="unknown_after_timeout",
                             error_type="Timeout",
                             missing_cost_reason="request may have executed; no response")
                raise RuntimeError("OpenRouter timeout; expense unknown") from None
            except requests.RequestException as exc:
                self._update(call_id, status="transport_error",
                             error_type=type(exc).__name__,
                             missing_cost_reason="no provider usage received")
                raise RuntimeError(f"OpenRouter transport error: {type(exc).__name__}") from None
            except (ValueError, KeyError, IndexError, TypeError):
                self._update(call_id, status="invalid_response", error_type="InvalidResponse")
                raise RuntimeError("OpenRouter invalid response") from None
        raise AssertionError("unreachable")


def _retry_delay(header: str | None, attempt: int) -> float | None:
    if header:
        try:
            seconds = max(0.0, float(header))
        except ValueError:
            seconds = None
        if seconds is not None:
            return seconds if seconds <= 60 else None
    return min(15.0, 2 ** (attempt - 1) + random.uniform(0, 0.25))
