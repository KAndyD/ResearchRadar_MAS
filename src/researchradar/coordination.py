"""Multi-task research with explicit centralized and Contract Net protocols."""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

from .model import Material, Message
from .scientific import deduplicate
from .sources import Source


@dataclass(frozen=True)
class WorkTask:
    id: str
    kind: str
    query: str
    limit: int = 3


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    capabilities: tuple[str, ...]
    expected_ms: dict[str, float]
    actual_ms: dict[str, float]
    advertised_load: int = 0
    private_load: int = 0
    available: bool = True


@dataclass
class WorkerState:
    phase: str = "idle"
    queued: int = 0
    handled: int = 0
    failures: int = 0
    busy_seconds: float = 0.0

    def enqueue(self) -> None:
        if self.phase == "stopped":
            raise RuntimeError("stopped worker")
        self.queued += 1
        self.phase = "busy"

    def finish(self, success: bool, busy_seconds: float) -> None:
        if self.queued < 1 or self.phase != "busy":
            raise RuntimeError("invalid worker completion")
        self.queued -= 1
        self.handled += int(success)
        self.failures += int(not success)
        self.busy_seconds += busy_seconds
        self.phase = "busy" if self.queued else "idle"

    def stop(self) -> None:
        if self.phase == "stopped":
            return
        self.phase = "stopped"


class Bus:
    """Only permitted directed protocol messages enter recipient queues."""

    MANAGER_TO_WORKER = {"task", "cfp", "accept", "reject", "cancel", "shutdown"}
    WORKER_TO_MANAGER = {"proposal", "refuse", "result", "failure"}

    def __init__(self, workers: tuple[str, ...]):
        self.queues: dict[str, asyncio.Queue[Message]] = {
            name: asyncio.Queue() for name in ("coordinator", *workers)}
        self.trace: list[dict[str, Any]] = []
        self.started = perf_counter()

    async def send(self, message: Message) -> None:
        allowed = ((message.sender == "coordinator" and message.recipient != "coordinator"
                    and message.kind in self.MANAGER_TO_WORKER)
                   or (message.recipient == "coordinator" and message.sender != "coordinator"
                       and message.kind in self.WORKER_TO_MANAGER))
        if not allowed or message.sender not in self.queues or message.recipient not in self.queues:
            raise PermissionError("protocol route not permitted")
        if not message.request_id or not isinstance(message.payload, dict):
            raise ValueError("invalid protocol message")
        self.trace.append({"elapsed_ms": round((perf_counter() - self.started) * 1000, 6),
                           "at": datetime.now(timezone.utc).isoformat(),
                           "id": message.id, "sender": message.sender,
                           "recipient": message.recipient, "kind": message.kind,
                           "task_id": message.payload.get("task_id"),
                           "correlation_id": message.correlation_id})
        await self.queues[message.recipient].put(message)


class Worker:
    def __init__(self, spec: WorkerSpec, sources: dict[str, Source], bus: Bus,
                 request_id: str):
        self.spec, self.sources, self.bus = spec, sources, bus
        self.request_id = request_id
        self.state = WorkerState()
        self._semaphore = asyncio.Semaphore(1)
        self._jobs: set[asyncio.Task] = set()
        self._assigned_jobs: dict[str, asyncio.Task] = {}
        self._offers: dict[str, str] = {}

    def score(self, task: WorkTask) -> float | None:
        if not self.spec.available or task.kind not in self.spec.capabilities or task.kind not in self.sources:
            return None
        return self.spec.expected_ms[task.kind] * (1 + self.spec.private_load + self.state.queued)

    async def run(self) -> None:
        queue = self.bus.queues[self.spec.name]
        while True:
            message = await queue.get()
            if message.kind == "shutdown":
                break
            if message.request_id != self.request_id:
                continue
            task_id = message.payload.get("task_id")
            if message.kind == "cfp":
                task = WorkTask(**message.payload["task"])
                score = self.score(task)
                kind = "proposal" if score is not None else "refuse"
                if score is not None:
                    self._offers[task_id] = message.id
                await self.bus.send(Message.make(self.spec.name, "coordinator", kind,
                    self.request_id, {"task_id": task_id, "score_ms": score}, message.id))
            elif message.kind == "reject":
                self._offers.pop(task_id, None)
            elif message.kind == "cancel":
                job = self._assigned_jobs.get(message.payload.get("assignment_id"))
                if job is not None:
                    job.cancel()
            elif message.kind in {"task", "accept"}:
                if message.kind == "accept" and self._offers.pop(task_id, None) != message.correlation_id:
                    await self._fail(message, "unmatched offer")
                    continue
                task = WorkTask(**message.payload["task"])
                if self.score(task) is None:
                    await self._fail(message, "capability unavailable")
                    continue
                self.state.enqueue()
                job = asyncio.create_task(self._execute(task, message))
                self._jobs.add(job)
                job.add_done_callback(self._jobs.discard)
                self._assigned_jobs[message.id] = job
                job.add_done_callback(lambda _, mid=message.id: self._assigned_jobs.pop(mid, None))
        if self._jobs:
            await asyncio.gather(*self._jobs, return_exceptions=True)
        self.state.stop()

    async def _fail(self, message: Message, reason: str) -> None:
        await self.bus.send(Message.make(self.spec.name, "coordinator", "failure",
                            self.request_id, {"task_id": message.payload["task_id"],
                                              "error": reason}, message.id))

    async def _execute(self, task: WorkTask, assignment: Message) -> None:
        success = False
        started = perf_counter()
        try:
            async with self._semaphore:
                delay = self.spec.actual_ms.get(task.kind, 0) / 1000
                if delay:
                    await asyncio.sleep(delay)
                rows = await asyncio.to_thread(self.sources[task.kind].search, task.query, task.limit)
            success = True
            payload = {"task_id": task.id, "materials": [x.as_dict() for x in rows]}
            kind = "result"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            payload = {"task_id": task.id, "error": f"{type(exc).__name__}: {exc}"}
            kind = "failure"
        finally:
            self.state.finish(success, perf_counter() - started)
        await self.bus.send(Message.make(self.spec.name, "coordinator", kind,
                            self.request_id, payload, assignment.id))

    async def cancel(self) -> None:
        for job in tuple(self._jobs):
            job.cancel()
        if self._jobs:
            await asyncio.gather(*self._jobs, return_exceptions=True)


def default_workers() -> tuple[WorkerSpec, ...]:
    """Six independently queued workers with overlapping source competencies."""
    return (
        WorkerSpec("scholar_a", ("openalex", "crossref"),
                   {"openalex": 30, "crossref": 45}, {"openalex": 24, "crossref": 38}),
        WorkerSpec("scholar_b", ("openalex", "crossref"),
                   {"openalex": 40, "crossref": 30}, {"openalex": 34, "crossref": 26}),
        WorkerSpec("preprint_a", ("arxiv", "openalex"),
                   {"arxiv": 32, "openalex": 52}, {"arxiv": 29, "openalex": 45}),
        WorkerSpec("preprint_b", ("arxiv", "crossref"),
                   {"arxiv": 43, "crossref": 50}, {"arxiv": 39, "crossref": 44}),
        WorkerSpec("news_a", ("news",), {"news": 28}, {"news": 24}),
        WorkerSpec("news_b", ("news",), {"news": 39}, {"news": 34}),
    )


def make_tasks(question: str, alternative: str | None = None) -> list[WorkTask]:
    question = question.strip()
    if not question:
        raise ValueError("research question is empty")
    tasks = [WorkTask("oa-primary", "openalex", question),
             WorkTask("cr-bibliography", "crossref", question),
             WorkTask("ax-preprints", "arxiv", question),
             WorkTask("news-primary", "news", question)]
    if alternative and alternative.strip() and alternative.strip().lower() != question.lower():
        tasks.append(WorkTask("oa-alternative", "openalex", alternative.strip()))
    return tasks


class Coordinator:
    def __init__(self, bus: Bus, workers: dict[str, Worker], request_id: str,
                 mechanism: str, bid_timeout: float, task_timeout: float):
        self.bus, self.workers, self.request_id = bus, workers, request_id
        self.mechanism = mechanism
        self.bid_timeout, self.task_timeout = bid_timeout, task_timeout
        self.channels: dict[str, asyncio.Queue[Message]] = {}
        self.receiver: asyncio.Task | None = None
        self.assigned_load: Counter[str] = Counter()
        self.late_messages = 0
        self.reassignments = 0
        self.coordination_seconds = 0.0
        self.assignments: dict[str, list[str]] = {}

    async def _receive(self) -> None:
        while True:
            message = await self.bus.queues["coordinator"].get()
            channel = self.channels.get(message.payload.get("task_id"))
            if channel is None:
                self.late_messages += 1
            else:
                await channel.put(message)

    def _candidates(self, task: WorkTask, excluded: set[str]) -> list[Worker]:
        return [w for w in self.workers.values() if w.spec.name not in excluded
                and w.spec.available and task.kind in w.spec.capabilities
                and task.kind in w.sources]

    async def _select(self, task: WorkTask, excluded: set[str],
                      channel: asyncio.Queue[Message]) -> tuple[Worker | None, str | None]:
        started = perf_counter()
        candidates = self._candidates(task, excluded)
        if not candidates:
            return None, None
        if self.mechanism == "centralized":
            chosen = min(candidates, key=lambda w: (
                w.spec.expected_ms[task.kind] * (1 + w.spec.advertised_load
                                                 + self.assigned_load[w.spec.name]),
                w.spec.name))
            self.coordination_seconds += perf_counter() - started
            return chosen, None
        cfps: dict[str, str] = {}
        for worker in candidates:
            message = Message.make("coordinator", worker.spec.name, "cfp", self.request_id,
                                   {"task_id": task.id, "task": asdict(task)})
            cfps[worker.spec.name] = message.id
            await self.bus.send(message)
        offers: dict[str, tuple[float, str]] = {}
        deadline = perf_counter() + self.bid_timeout
        responded: set[str] = set()
        while len(responded) < len(candidates) and (remaining := deadline - perf_counter()) > 0:
            try:
                message = await asyncio.wait_for(channel.get(), remaining)
            except TimeoutError:
                break
            if (message.sender not in cfps or message.sender in responded
                    or message.correlation_id != cfps[message.sender]
                    or message.kind not in {"proposal", "refuse"}):
                self.late_messages += 1
                continue
            responded.add(message.sender)
            if message.kind == "proposal" and isinstance(message.payload.get("score_ms"), (int, float)):
                offers[message.sender] = (float(message.payload["score_ms"]), cfps[message.sender])
        chosen_name = min(offers, key=lambda name: (offers[name][0], name)) if offers else None
        for name in offers:
            if name != chosen_name:
                await self.bus.send(Message.make("coordinator", name, "reject", self.request_id,
                                                {"task_id": task.id}, cfps[name]))
        self.coordination_seconds += perf_counter() - started
        return (self.workers[chosen_name], offers[chosen_name][1]) if chosen_name else (None, None)

    async def _one(self, task: WorkTask) -> tuple[str, list[Material], str | None]:
        channel: asyncio.Queue[Message] = asyncio.Queue()
        self.channels[task.id] = channel
        excluded: set[str] = set()
        try:
            while True:
                worker, offer_id = await self._select(task, excluded, channel)
                if worker is None:
                    return task.id, [], "no eligible proposal or available worker"
                name = worker.spec.name
                self.assignments.setdefault(task.id, []).append(name)
                assignment = Message.make("coordinator", name,
                    "accept" if self.mechanism == "contract-net" else "task",
                    self.request_id, {"task_id": task.id, "task": asdict(task)}, offer_id)
                self.assigned_load[name] += 1
                await self.bus.send(assignment)
                deadline = perf_counter() + self.task_timeout
                timed_out = False
                while (remaining := deadline - perf_counter()) > 0:
                    try:
                        message = await asyncio.wait_for(channel.get(), remaining)
                    except TimeoutError:
                        timed_out = True
                        break
                    if (message.sender != name or message.correlation_id != assignment.id
                            or message.kind not in {"result", "failure"}):
                        self.late_messages += 1
                        continue
                    self.assigned_load[name] -= 1
                    if message.kind == "result":
                        return task.id, [Material(**x) for x in message.payload["materials"]], None
                    excluded.add(name)
                    self.reassignments += 1
                    break
                if timed_out or perf_counter() >= deadline and name not in excluded:
                    await self.bus.send(Message.make("coordinator", name, "cancel",
                        self.request_id, {"task_id": task.id,
                                          "assignment_id": assignment.id}, assignment.id))
                    self.assigned_load[name] -= 1
                    excluded.add(name)
                    self.reassignments += 1
                    continue
                if name not in excluded:
                    self.assigned_load[name] -= 1
                    excluded.add(name)
                    self.reassignments += 1
        finally:
            self.channels.pop(task.id, None)

    async def run(self, tasks: list[WorkTask], deadline_seconds: float) -> dict[str, Any]:
        self.receiver = asyncio.create_task(self._receive())
        jobs = {task.id: asyncio.create_task(self._one(task)) for task in tasks}
        finished: dict[str, tuple[list[Material], str | None]] = {}
        try:
            done, pending = await asyncio.wait(jobs.values(), timeout=deadline_seconds)
            for job in done:
                task_id, materials, error = job.result()
                finished[task_id] = (materials, error)
            for job in pending:
                job.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            self.receiver.cancel()
            await asyncio.gather(self.receiver, return_exceptions=True)
        ordered = {task.id: finished[task.id] for task in tasks if task.id in finished}
        return {"completed": ordered, "timed_out": [task.id for task in tasks if task.id not in finished]}


async def research_stage2(question: str, sources: dict[str, Source], *,
                          mechanism: str = "centralized", alternative: str | None = None,
                          workers: tuple[WorkerSpec, ...] | None = None,
                          bid_timeout: float = 0.15, task_timeout: float = 0.5,
                          deadline_seconds: float = 5.0) -> dict[str, Any]:
    if mechanism not in {"centralized", "contract-net"}:
        raise ValueError("unknown coordination mechanism")
    tasks = make_tasks(question, alternative)
    specs = workers or default_workers()
    request_id = str(uuid4())
    bus = Bus(tuple(spec.name for spec in specs))
    agents = {spec.name: Worker(spec, sources, bus, request_id) for spec in specs}
    runners = [asyncio.create_task(worker.run()) for worker in agents.values()]
    manager = Coordinator(bus, agents, request_id, mechanism, bid_timeout, task_timeout)
    started = perf_counter()
    try:
        outcome = await manager.run(tasks, deadline_seconds)
    finally:
        for worker in agents.values():
            await worker.cancel()
        for name in agents:
            await bus.send(Message.make("coordinator", name, "shutdown", request_id, {}))
        await asyncio.gather(*runners, return_exceptions=True)
    elapsed = perf_counter() - started
    scientific = [row for _, (rows, _) in outcome["completed"].items()
                  for row in rows if row.kind == "scientific"]
    news = [row for _, (rows, _) in outcome["completed"].items()
            for row in rows if row.kind == "news"]
    errors = {task_id: error for task_id, (_, error) in outcome["completed"].items() if error}
    errors.update({task_id: "research deadline exceeded" for task_id in outcome["timed_out"]})
    counts = Counter(event["kind"] for event in bus.trace if event["kind"] != "shutdown")
    return {"question": question, "mechanism": mechanism, "tasks": [asdict(x) for x in tasks],
            "materials": {"scientific": [x.as_dict() for x in deduplicate(scientific)],
                          "news": [x.as_dict() for x in deduplicate(news)]},
            "errors": errors, "assignments": manager.assignments,
            "agents": {name: asdict(worker.state) for name, worker in agents.items()},
            "trace": bus.trace, "metrics": {
                "wall_seconds": elapsed, "coordination_seconds": manager.coordination_seconds,
                "messages": sum(counts.values()), "message_kinds": dict(counts),
                "completed_tasks": len(tasks) - len(errors), "task_count": len(tasks),
                "reassignments": manager.reassignments,
                "late_or_invalid_messages": manager.late_messages}}
