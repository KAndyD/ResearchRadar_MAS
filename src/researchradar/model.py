from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import StrEnum
from typing import Any
from uuid import uuid4


class Phase(StrEnum):
    IDLE = "idle"
    BUSY = "busy"
    DONE = "done"
    FAILED = "failed"


ALLOWED = {
    Phase.IDLE: {Phase.BUSY},
    Phase.BUSY: {Phase.DONE, Phase.FAILED},
    Phase.DONE: set(),
    Phase.FAILED: set(),
}


@dataclass
class AgentState:
    phase: Phase = Phase.IDLE
    handled: int = 0
    last_error: str | None = None

    def change(self, phase: Phase) -> None:
        if phase not in ALLOWED[self.phase]:
            raise ValueError(f"invalid transition: {self.phase} -> {phase}")
        self.phase = phase


@dataclass(frozen=True)
class ResearchRequest:
    question: str
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("question is empty")


@dataclass(frozen=True)
class ResearchTask:
    id: str
    request_id: str
    kind: str
    query: str


@dataclass(frozen=True)
class Message:
    id: str
    sender: str
    recipient: str
    kind: str
    request_id: str
    payload: dict[str, Any]
    correlation_id: str | None = None

    @classmethod
    def make(cls, sender: str, recipient: str, kind: str,
             request_id: str, payload: dict[str, Any],
             correlation_id: str | None = None) -> Message:
        return cls(str(uuid4()), sender, recipient, kind, request_id,
                   payload, correlation_id)


@dataclass(frozen=True)
class Material:
    kind: str
    source: str
    source_id: str
    title: str
    url: str
    published: str | None
    abstract: str | None = None
    doi: str | None = None
    text_scope: str = "metadata"
    provenance: str = "live_api"
    authors: tuple[str, ...] = ()
    venue: str | None = None
    arxiv_id: str | None = None
    discovered_in: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

