"""Inject one local fault into real lab3 search, bus, or budget interfaces.

This probe also runs against the exact lab3-v1.1 source snapshot on PYTHONPATH.
No live services or LLM calls are available here.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import researchradar.coordination as coordination
from researchradar.frozen import load_frozen
from researchradar.model import Material, Message
from researchradar.resources import VerificationBudget


def marker(kind: str) -> dict:
    return Material(kind, "OpenAlex" if kind == "scientific" else "Google News RSS",
                    "FAULT-MATERIAL", "Injected false result", "https://example.invalid/fault",
                    None, provenance="synthetic_fixture").as_dict()


async def exercise(scenario: str, seed: int) -> dict:
    events: list[dict] = []
    buses = []
    started = perf_counter()
    if scenario == "forbidden_delegate":
        bus = coordination.Bus(("a", "b"))
        try:
            await bus.send(Message.make("a", "b", "task", "run", {"task_id": "cycle"}))
            accepted = True
        except PermissionError:
            accepted = False
        return {"accepted_forbidden": accepted, "trace": bus.trace,
                "fault_events": [{"action": "worker_to_worker_task", "accepted": accepted}],
                "wall_ms": (perf_counter() - started) * 1000}
    if scenario == "resource_owner":
        budget = VerificationBudget(2, 1)
        await budget.reserve("agreement", "request", "science", 2)
        await budget.start("agreement", "science")
        foreign_finish = await budget.finish("agreement", "news")
        own_finish = await budget.finish("agreement", "science")
        state = budget.snapshot()
        return {"accepted_forbidden": foreign_finish,
                "own_finish": own_finish, "resource": state,
                "trace": [], "fault_events": [{"action": "foreign_finish",
                                               "accepted": foreign_finish}],
                "wall_ms": (perf_counter() - started) * 1000}

    original_bus = coordination.Bus
    target = "oa-primary"

    class InjectedBus(original_bus):
        def __init__(self, workers, *args, **kwargs):
            super().__init__(workers, *args, **kwargs)
            self.injected = False
            buses.append(self)

        async def send(self, message):
            if (not self.injected and message.sender == "coordinator"
                    and message.payload.get("task_id") == target
                    and message.kind in {"task", "accept"}
                    and scenario in {"wrong_run_result", "malformed_result",
                                     "source_mismatch", "forged_shutdown",
                                     "wrong_correlation"}):
                self.injected = True
                if scenario == "forged_shutdown":
                    fault = Message.make("coordinator", message.recipient, "shutdown",
                                         "foreign-run", {})
                    try:
                        await super().send(fault)
                        blocked = False
                    except (PermissionError, ValueError):
                        blocked = True
                    events.append({"action": scenario, "sender": fault.sender,
                                   "recipient": fault.recipient,
                                   "request_id": fault.request_id, "blocked": blocked})
                    await super().send(message)
                    return
                await super().send(message)
                material = ([{"source_id": "missing-required-fields"}]
                            if scenario == "malformed_result" else
                            [marker("news" if scenario == "source_mismatch" else "scientific")])
                fault = Message.make(message.recipient, "coordinator", "result",
                    "foreign-run" if scenario == "wrong_run_result" else message.request_id,
                    {"task_id": target, "materials": material},
                    "wrong-correlation" if scenario == "wrong_correlation" else message.id)
                try:
                    await super().send(fault)
                    blocked = False
                except (PermissionError, ValueError):
                    blocked = True
                events.append({"action": scenario, "sender": fault.sender,
                               "request_id": fault.request_id,
                               "correlation_id": fault.correlation_id,
                               "task_id": target, "blocked": blocked})
                return
            await super().send(message)

    sources = load_frozen(Path("data/frozen_sources.json"))
    if scenario == "source_429":
        class FailedSource:
            def search(self, query, limit=3):
                raise RuntimeError("simulated HTTP 429")
        sources["arxiv"] = FailedSource()
        events.append({"action": "source_429", "component": "arxiv.search"})

    original_score = coordination.Worker.score

    def altered_score(worker, task):
        if scenario == "malicious_bid" and worker.spec.name == "scholar_b" and task.id == target:
            events.append({"action": "malicious_bid", "worker": worker.spec.name,
                           "score_ms": -100})
            return -100.0
        return original_score(worker, task)

    mechanism = "contract-net" if scenario == "malicious_bid" else "centralized"
    # Seed controls the same small worker delay variation in both variants.
    specs = tuple(coordination.WorkerSpec(x.name, x.capabilities, x.expected_ms,
                  {k: v + (seed % 3) for k, v in x.actual_ms.items()},
                  x.advertised_load, x.private_load, x.available)
                  for x in coordination.default_workers())
    with patch.object(coordination, "Bus", InjectedBus), patch.object(
            coordination.Worker, "score", altered_score):
        try:
            result = await coordination.research_stage2("multi agent systems", sources,
                mechanism=mechanism, workers=specs, task_timeout=0.12,
                deadline_seconds=1.5)
            crash = None
        except Exception as exc:
            result = None
            crash = type(exc).__name__
    bus = buses[0]
    rows = [] if result is None else sum(result["materials"].values(), [])
    return {"crash": crash,
            "completed_tasks": 0 if result is None else result["metrics"]["completed_tasks"],
            "task_count": 4,
            "errors": {} if result is None else result["errors"],
            "assignments": {} if result is None else result["assignments"],
            "reassignments": 0 if result is None else result["metrics"]["reassignments"],
            "invalid_messages": 0 if result is None else result["metrics"]["late_or_invalid_messages"],
            "messages": len(bus.trace) if result is None else result["metrics"]["messages"],
            "accepted_fault_material": any(x["source_id"] == "FAULT-MATERIAL" for x in rows),
            "scientific_count": 0 if result is None else len(result["materials"]["scientific"]),
            "news_count": 0 if result is None else len(result["materials"]["news"]),
            "agents_stopped": result is not None and all(
                x["phase"] == "stopped" for x in result["agents"].values()),
            "fault_events": events, "trace": bus.trace,
            "wall_ms": (perf_counter() - started) * 1000}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(exercise(args.scenario, args.seed))
    result.update({"scenario": args.scenario, "seed": args.seed,
                   "module_path": str(Path(coordination.__file__).resolve())})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.scenario, "crash", result.get("crash"), "completed",
          result.get("completed_tasks"), "fault_accepted",
          result.get("accepted_fault_material", result.get("accepted_forbidden")))


if __name__ == "__main__":
    main()
