"""Mediated resource negotiation after the existing scientific/news search."""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any
from uuid import uuid4

from .model import Message
from .resources import VerificationBudget


@dataclass(frozen=True)
class CheckRequest:
    id: str
    owner: str
    operation: str
    materials: tuple[dict, ...]
    public_priority: int
    full_value: float
    partial_value: float
    reservation_value: float = 1.0
    full_units: int = 2
    min_units: int = 1

    def __post_init__(self) -> None:
        if (not self.id or not self.owner or self.operation not in
                {"bibliography", "headline_review", "topic_link"}
                or not self.materials or self.public_priority < 1
                or self.full_units < self.min_units or self.min_units < 1
                or self.full_value < self.partial_value or self.partial_value < 0
                or self.reservation_value < 0):
            raise ValueError("invalid check request")

    def value(self, units: int) -> float:
        return self.full_value if units >= self.full_units else (
            self.partial_value if units >= self.min_units else 0.0)


def derive_checks(research: dict) -> tuple[CheckRequest, ...]:
    """Turn retrieved materials into limited, evidence-aware verification work."""
    materials = research.get("materials", {})
    scientific = list(materials.get("scientific", []))
    news = list(materials.get("news", []))
    checks = []
    if scientific:
        paper = next((x for x in scientific if x.get("abstract")), scientific[0])
        checks.append(CheckRequest("science-check", "science", "bibliography", (paper,),
                                   2, 6.0, 4.0))
    if news:
        checks.append(CheckRequest("news-check", "news", "headline_review", (news[0],),
                                   2, 6.0, 3.0))
    if scientific and news:
        checks.append(CheckRequest("link-check", "link", "topic_link",
                                   (scientific[0], news[0]), 3, 8.0, 5.0))
    return tuple(checks)


class NegotiationBus:
    MANAGER_TO_AGENT = {"offer", "commit", "cancel", "shutdown"}
    AGENT_TO_MANAGER = {"request", "accept", "counter", "reject", "result", "failure"}

    def __init__(self, owners: tuple[str, ...], run_id: str):
        self.queues = {name: asyncio.Queue() for name in ("mediator", *owners)}
        self.run_id = run_id
        self.started = perf_counter()
        self.trace: list[dict[str, Any]] = []

    async def send(self, message: Message) -> None:
        allowed = ((message.sender == "mediator" and message.recipient != "mediator"
                    and message.kind in self.MANAGER_TO_AGENT) or
                   (message.recipient == "mediator" and message.sender != "mediator"
                    and message.kind in self.AGENT_TO_MANAGER))
        if (not allowed or message.sender not in self.queues
                or message.recipient not in self.queues or message.request_id != self.run_id
                or not isinstance(message.payload, dict)):
            raise PermissionError("negotiation route or run invalid")
        self.trace.append({"elapsed_ms": round((perf_counter() - self.started) * 1000, 5),
                           "id": message.id, "sender": message.sender,
                           "recipient": message.recipient, "kind": message.kind,
                           "check_id": message.payload.get("check_id"),
                           "round": message.payload.get("round"),
                           "units": message.payload.get("units"),
                           "reason": message.payload.get("reason"),
                           "correlation_id": message.correlation_id})
        await self.queues[message.recipient].put(message)


def _terms(value: str) -> set[str]:
    words = {word.strip(".,:;!?()[]{}\"'–—").lower() for word in value.split()}
    return {x for x in words if len(x) > 3 and x not in
            {"study", "research", "news", "synthetic", "about", "with", "from"}}


def perform_check(check: CheckRequest, units: int) -> dict:
    """Work is limited to available metadata, abstract, and headline evidence."""
    rows = check.materials
    refs = [{"source": x.get("source"), "source_id": x.get("source_id"),
             "url": x.get("url"), "provenance": x.get("provenance"),
             "text_scope": x.get("text_scope")} for x in rows]
    if check.operation == "bibliography":
        paper = rows[0]
        inspected = bool(units >= check.full_units and paper.get("abstract"))
        return {"assessment": "abstract_inspected" if inspected else "metadata_checked",
                "scope": "abstract" if inspected else "metadata",
                "evidence_refs": refs,
                "details": {"has_doi": bool(paper.get("doi")),
                            "has_arxiv_id": bool(paper.get("arxiv_id")),
                            "has_authors": bool(paper.get("authors")),
                            "excerpt": str(paper.get("abstract"))[:180] if inspected else None}}
    if check.operation == "headline_review":
        news = rows[0]
        return {"assessment": "claim_unverified", "scope": "headline",
                "evidence_refs": refs,
                "details": {"has_date": bool(news.get("published")),
                            "headline": news.get("title") if units >= check.full_units else None,
                            "reason": "no article body or independent claim evidence"}}
    paper, news = rows
    basis = str(paper.get("title", ""))
    if units >= check.full_units and paper.get("abstract"):
        basis += " " + str(paper["abstract"])
    shared = sorted(_terms(basis) & _terms(str(news.get("title", ""))))
    return {"assessment": "thematic_candidate" if shared else "insufficient_evidence",
            "scope": "title_and_abstract" if units >= check.full_units else "titles",
            "evidence_refs": refs,
            "details": {"shared_terms": shared,
                        "reason": "topic overlap does not establish a direct citation or factual support"}}


class ReviewAgent:
    def __init__(self, check: CheckRequest, bus: NegotiationBus,
                 budget: VerificationBudget, *, silent: bool = False,
                 delay_ms: float = 1.0):
        self.check, self.bus, self.budget = check, bus, budget
        self.silent, self.delay_ms = silent, delay_ms

    async def run(self) -> None:
        q = self.bus.queues[self.check.owner]
        await self.bus.send(Message.make(self.check.owner, "mediator", "request",
            self.bus.run_id, {"check_id": self.check.id, "units": self.check.full_units,
                              "public_priority": self.check.public_priority}))
        while True:
            message = await q.get()
            if message.kind == "shutdown":
                return
            if message.kind == "offer":
                if not self.silent:
                    await self._answer(message)
            elif message.kind == "commit":
                await self._execute(message)
            elif message.kind == "cancel":
                await self.budget.cancel(message.payload["agreement_id"], self.check.owner)

    async def _answer(self, offer: Message) -> None:
        units = offer.payload["units"]
        round_number = offer.payload["round"]
        board = offer.payload.get("unserved", 0)
        reason = None
        if round_number == 1 and units == self.check.full_units and board >= 2 and (
                self.check.partial_value / max(self.check.full_value, 0.001) >= 0.6):
            kind, desired, reason = "counter", self.check.min_units, "concede_for_peers"
        elif round_number == 1 and units == 0 and (
                self.check.partial_value >= self.check.reservation_value):
            kind, desired, reason = "counter", self.check.min_units, "partial_check"
        elif units >= self.check.min_units and (
                self.check.value(units) >= self.check.reservation_value):
            kind, desired = "accept", units
        else:
            kind, desired, reason = "reject", 0, "below_reservation_or_no_capacity"
        await self.bus.send(Message.make(self.check.owner, "mediator", kind,
            self.bus.run_id, {"check_id": self.check.id, "round": round_number,
                              "units": desired, "bid": self.check.value(desired),
                              "reason": reason}, offer.id))

    async def _execute(self, commit: Message) -> None:
        agreement = commit.payload["agreement_id"]
        units = commit.payload["units"]
        if not await self.budget.start(agreement, self.check.owner):
            await self.bus.send(Message.make(self.check.owner, "mediator", "failure",
                self.bus.run_id, {"check_id": self.check.id,
                                  "reason": "no active reservation"}, commit.id))
            return
        began = perf_counter()
        try:
            if not await self.budget.authorized(agreement, self.check.id,
                                                self.check.owner, units):
                raise PermissionError("verification operation lacks authorization")
            await asyncio.sleep(max(0, self.delay_ms) * units / 1000)
            if not await self.budget.authorized(agreement, self.check.id,
                                                self.check.owner, units):
                raise PermissionError("verification authorization expired")
            evidence = perform_check(self.check, units)
            await self.budget.finish(agreement, self.check.owner)
            await self.bus.send(Message.make(self.check.owner, "mediator", "result",
                self.bus.run_id, {"check_id": self.check.id, "agreement_id": agreement,
                                  "units": units, "evidence": evidence,
                                  "check_ms": round((perf_counter() - began) * 1000, 5)},
                commit.id))
        except Exception as error:
            await self.budget.abort(agreement, self.check.owner)
            await self.bus.send(Message.make(self.check.owner, "mediator", "failure",
                self.bus.run_id, {"check_id": self.check.id,
                                  "reason": type(error).__name__},
                commit.id))


class Mediator:
    def __init__(self, checks: tuple[CheckRequest, ...], bus: NegotiationBus,
                 budget: VerificationBudget, timeout: float):
        self.checks, self.bus, self.budget, self.timeout = checks, bus, budget, timeout
        self.invalid_messages = 0
        self.arbitrations = 0

    async def _collect(self, kinds: set[str], expected: dict[str, str | None],
                       round_number: int | None = None) -> dict[str, Message]:
        found = {}
        deadline = perf_counter() + self.timeout
        queue = self.bus.queues["mediator"]
        while len(found) < len(expected) and (left := deadline - perf_counter()) > 0:
            try:
                message = await asyncio.wait_for(queue.get(), left)
            except TimeoutError:
                break
            if (message.sender not in expected or message.sender in found
                    or message.kind not in kinds
                    or message.correlation_id != expected[message.sender]
                    or round_number is not None and message.payload.get("round") != round_number
                    or message.payload.get("check_id") !=
                    next(x.id for x in self.checks if x.owner == message.sender)):
                self.invalid_messages += 1
                continue
            found[message.sender] = message
        return found

    def _baseline(self, available: int, candidates: set[str]) -> dict[str, int]:
        plan = {x.owner: 0 for x in self.checks}
        for check in self.checks:
            if check.owner not in candidates:
                continue
            units = (check.full_units if available >= check.full_units else
                     check.min_units if available >= check.min_units else 0)
            plan[check.owner] = units
            available -= units
        return plan

    def _first_offer(self) -> dict[str, int]:
        plan = {x.owner: 0 for x in self.checks}
        available = self.budget.credits
        for check in sorted(self.checks, key=lambda x: (-x.public_priority, x.id)):
            if available >= check.full_units:
                plan[check.owner] = check.full_units
                available -= check.full_units
        return plan

    async def _offers(self, plan: dict[str, int], round_number: int) -> dict[str, Message]:
        unserved = sum(units == 0 for units in plan.values())
        offers = {}
        for check in self.checks:
            offer = Message.make("mediator", check.owner, "offer", self.bus.run_id,
                {"check_id": check.id, "round": round_number,
                 "units": plan[check.owner], "unserved": unserved})
            offers[check.owner] = offer
            await self.bus.send(offer)
        return await self._collect({"accept", "counter", "reject"},
                                   {owner: offer.id for owner, offer in offers.items()},
                                   round_number)

    def _revise(self, initial: dict[str, int], responses: dict[str, Message]) -> dict[str, int]:
        if len(responses) < len(self.checks):
            self.arbitrations += 1
            return self._baseline(self.budget.credits, set(responses))
        plan = {x.owner: 0 for x in self.checks}
        for check in self.checks:
            message = responses[check.owner]
            if message.kind == "accept" and message.payload.get("units") == initial[check.owner]:
                plan[check.owner] = initial[check.owner]
        available = self.budget.credits - sum(plan.values())
        candidates = []
        for check in self.checks:
            message = responses[check.owner]
            if (message.kind == "counter" and
                    message.payload.get("units") == check.min_units and
                    isinstance(message.payload.get("bid"), (int, float)) and
                    0 <= message.payload["bid"] <= check.full_value):
                candidates.append((message.payload["bid"] * check.public_priority,
                                   check.owner, check))
            elif message.kind == "counter":
                self.invalid_messages += 1
        for _, _, check in sorted(candidates, key=lambda x: (-x[0], x[1])):
            if available >= check.min_units:
                plan[check.owner] = check.min_units
                available -= check.min_units
        return plan

    async def run(self, mode: str) -> dict:
        submitted = await self._collect({"request"}, {x.owner: None for x in self.checks})
        active = set(submitted)
        began = perf_counter()
        if mode == "baseline":
            plan = self._baseline(self.budget.credits, active)
            rounds = 0
        else:
            first = self._first_offer()
            for owner in first:
                if owner not in active:
                    first[owner] = 0
            replies = await self._offers(first, 1)
            revised = self._revise(first, replies)
            decisions = await self._offers(revised, 2)
            plan = {x.owner: revised[x.owner] if (
                x.owner in decisions and decisions[x.owner].kind == "accept" and
                decisions[x.owner].payload.get("units") == revised[x.owner]) else 0
                for x in self.checks}
            if any(revised[x.owner] and not plan[x.owner] for x in self.checks):
                self.arbitrations += 1
            rounds = 2
        negotiation_ms = (perf_counter() - began) * 1000
        agreements = {}
        commits = {}
        for check in self.checks:
            units = plan[check.owner]
            if not units:
                continue
            agreement_id = f"agreement:{self.bus.run_id}:{check.id}"
            if not await self.budget.reserve(agreement_id, check.id, check.owner, units):
                self.invalid_messages += 1
                continue
            agreements[check.owner] = agreement_id
            commit = Message.make("mediator", check.owner, "commit", self.bus.run_id,
                {"check_id": check.id, "agreement_id": agreement_id, "units": units})
            commits[check.owner] = commit
            await self.bus.send(commit)
        replies = await self._collect({"result", "failure"},
                                      {owner: commit.id for owner, commit in commits.items()})
        for owner, agreement in agreements.items():
            if owner not in replies:
                await self.budget.abort(agreement, owner)
        results = {owner: message.payload for owner, message in replies.items()
                   if message.kind == "result"}
        return {"plan": plan, "agreements": agreements, "results": results,
                "rounds": rounds, "negotiation_ms": negotiation_ms,
                "invalid_messages": self.invalid_messages,
                "arbitrations": self.arbitrations}


def jain_satisfaction(checks: tuple[CheckRequest, ...], plan: dict[str, int]) -> float:
    if not checks:
        return 1.0
    values = [plan.get(x.owner, 0) / x.full_units for x in checks]
    denominator = len(values) * sum(x * x for x in values)
    return (sum(values) ** 2 / denominator) if denominator else 0.0


async def review_research(research: dict, *, mode: str = "baseline", credits: int = 3,
                          checks: tuple[CheckRequest, ...] | None = None,
                          silent_owners: frozenset[str] = frozenset(),
                          delay_ms: float = 1.0,
                          timeout: float = 0.05) -> dict:
    if mode not in {"baseline", "negotiation"}:
        raise ValueError("unknown resource policy")
    chosen = checks if checks is not None else derive_checks(research)
    if len({x.owner for x in chosen}) != len(chosen) or len({x.id for x in chosen}) != len(chosen):
        raise ValueError("duplicate owner or check identifier")
    run_id = str(uuid4())
    bus = NegotiationBus(tuple(x.owner for x in chosen), run_id)
    budget = VerificationBudget(credits)
    agents = [ReviewAgent(x, bus, budget, silent=x.owner in silent_owners,
                          delay_ms=delay_ms) for x in chosen]
    runners = [asyncio.create_task(agent.run()) for agent in agents]
    mediator = Mediator(chosen, bus, budget, timeout)
    started = perf_counter()
    try:
        outcome = await mediator.run(mode)
    finally:
        for agent in agents:
            await bus.send(Message.make("mediator", agent.check.owner, "shutdown",
                                        run_id, {}))
        try:
            await asyncio.wait_for(asyncio.gather(*runners, return_exceptions=True),
                                   timeout + 0.05)
        except TimeoutError:
            for runner in runners:
                runner.cancel()
            await asyncio.gather(*runners, return_exceptions=True)
    elapsed = (perf_counter() - started) * 1000
    snapshot = budget.snapshot()
    counts = Counter(x["kind"] for x in bus.trace if x["kind"] != "shutdown")
    completed = outcome["results"]
    utility = sum(check.value(completed[check.owner]["units"])
                  for check in chosen if check.owner in completed)
    plan = {owner: completed[owner]["units"] if owner in completed else 0
            for owner in outcome["plan"]}
    return {"mode": mode, "research_question": research.get("question"),
            "requests": [asdict(x) for x in chosen],
            "plan": plan, "agreements": outcome["agreements"],
            "checks": completed, "trace": bus.trace, "resource": snapshot,
            "metrics": {"wall_ms": elapsed, "negotiation_ms": outcome["negotiation_ms"],
                        "check_ms_sum": sum(x["check_ms"] for x in completed.values()),
                        "messages": sum(counts.values()), "message_kinds": dict(counts),
                        "rounds": outcome["rounds"],
                        "counteroffers": counts["counter"],
                        "rejections": counts["reject"],
                        "arbitrations": outcome["arbitrations"],
                        "invalid_messages": outcome["invalid_messages"],
                        "requested_units": sum(x.full_units for x in chosen),
                        "granted_units": sum(plan.values()),
                        "completed_checks": len(completed),
                        "denied_checks": len(chosen) - len(completed),
                        "estimated_utility": utility,
                        "jain_normalized_satisfaction": jain_satisfaction(chosen, plan),
                        "budget_violations": int(snapshot["spent"] + snapshot["held"] > credits),
                        "slot_violations": int(snapshot["peak_active"] > snapshot["concurrent_slots"])}}
