from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .model import AgentState, Material, Message, Phase, ResearchRequest, ResearchTask
from .sources import Source


ROUTES = {
    ("coordinator", "scientist", "task"),
    ("coordinator", "journalist", "task"),
    ("scientist", "coordinator", "result"),
    ("scientist", "coordinator", "error"),
    ("journalist", "coordinator", "result"),
    ("journalist", "coordinator", "error"),
    ("coordinator", "synthesizer", "task"),
    ("synthesizer", "coordinator", "result"),
}


class Router:
    def __init__(self):
        self.queues = {name: asyncio.Queue() for name in
                       ("coordinator", "scientist", "journalist", "synthesizer")}
        self.trace: list[dict[str, Any]] = []

    async def send(self, message: Message) -> None:
        if (message.sender, message.recipient, message.kind) not in ROUTES:
            raise PermissionError("message route not permitted")
        if not isinstance(message.payload, dict) or not message.request_id:
            raise ValueError("invalid message")
        self.trace.append({"at": datetime.now(timezone.utc).isoformat(),
                           "event": "message", "id": message.id,
                           "sender": message.sender, "recipient": message.recipient,
                           "kind": message.kind, "request_id": message.request_id,
                           "correlation_id": message.correlation_id})
        await self.queues[message.recipient].put(message)


class SearchAgent:
    def __init__(self, name: str, source: Source, router: Router):
        self.name, self.source, self.router = name, source, router
        self.state = AgentState()

    async def run(self) -> None:
        message = await self.router.queues[self.name].get()
        self.state.change(Phase.BUSY)
        try:
            if message.kind != "task" or message.sender != "coordinator":
                raise ValueError("unexpected task")
            query = str(message.payload["query"])
            materials = await asyncio.to_thread(self.source.search, query, 3)
            self.state.handled += 1
            self.state.change(Phase.DONE)
            reply = Message.make(self.name, "coordinator", "result",
                                 message.request_id,
                                 {"materials": [m.as_dict() for m in materials]}, message.id)
        except Exception as exc:
            self.state.last_error = f"{type(exc).__name__}: {exc}"
            self.state.change(Phase.FAILED)
            reply = Message.make(self.name, "coordinator", "error",
                                 message.request_id,
                                 {"error": self.state.last_error}, message.id)
        await self.router.send(reply)


class SynthesisAgent:
    def __init__(self, router: Router):
        self.router = router
        self.state = AgentState()

    async def run(self) -> None:
        message = await self.router.queues["synthesizer"].get()
        self.state.change(Phase.BUSY)
        publications = message.payload.get("scientific", [])
        news = message.payload.get("news", [])
        # Only metadata is available. This agent refuses to infer causal links or claims.
        summary = (f"Найдено научных записей: {len(publications)}; новостей: {len(news)}. "
                   "Содержательные выводы и связь между источниками не установлены: "
                   "доступны только метаданные, заголовки и отдельные аннотации.")
        self.state.handled += 1
        self.state.change(Phase.DONE)
        await self.router.send(Message.make("synthesizer", "coordinator", "result",
                            message.request_id, {"summary": summary}, message.id))


class Coordinator:
    def __init__(self, router: Router):
        self.router = router
        self.state = AgentState()

    async def run(self, request: ResearchRequest) -> dict[str, Any]:
        self.state.change(Phase.BUSY)
        # The task assignment policy is isolated for laboratory 2 replacement.
        tasks = [ResearchTask("science", request.id, "scientific", request.question),
                 ResearchTask("news", request.id, "news", request.question)]
        for task, recipient in zip(tasks, ("scientist", "journalist"), strict=True):
            await self.router.send(Message.make("coordinator", recipient, "task",
                                               request.id, asdict(task)))
        materials: dict[str, list[dict]] = {"scientific": [], "news": []}
        errors: dict[str, str] = {}
        for _ in tasks:
            message = await self.router.queues["coordinator"].get()
            kind = "scientific" if message.sender == "scientist" else "news"
            if message.kind == "error":
                errors[kind] = str(message.payload["error"])
            else:
                materials[kind] = message.payload["materials"]
        # Deduplication uses stable source identifiers, never semantic similarity.
        for kind in materials:
            materials[kind] = list({(m["source"], m["source_id"]): m
                                    for m in materials[kind]}.values())
        await self.router.send(Message.make("coordinator", "synthesizer", "task",
                                            request.id, materials))
        synthesis = await self.router.queues["coordinator"].get()
        self.state.handled += 1
        self.state.change(Phase.DONE)
        return {"request": asdict(request), "tasks": [asdict(t) for t in tasks],
                "materials": materials, "errors": errors,
                "summary": synthesis.payload["summary"]}


async def research(question: str, scientific: Source, news: Source) -> dict[str, Any]:
    request = ResearchRequest(question)
    router = Router()
    coordinator = Coordinator(router)
    scientist = SearchAgent("scientist", scientific, router)
    journalist = SearchAgent("journalist", news, router)
    synthesizer = SynthesisAgent(router)
    workers = [asyncio.create_task(a.run()) for a in (scientist, journalist, synthesizer)]
    result = await coordinator.run(request)
    await asyncio.gather(*workers)
    result["agents"] = {"coordinator": asdict(coordinator.state),
                        "scientist": asdict(scientist.state),
                        "journalist": asdict(journalist.state),
                        "synthesizer": asdict(synthesizer.state)}
    result["trace"] = router.trace
    return result

