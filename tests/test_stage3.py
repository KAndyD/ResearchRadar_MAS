import asyncio
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from researchradar.coordination import research_stage2
from researchradar.frozen import load_frozen
from researchradar.model import Message
from researchradar.negotiation import (CheckRequest, Mediator, NegotiationBus,
                                       derive_checks, perform_check, review_research)
from researchradar.resources import VerificationBudget
from tools.run_negotiation_experiments import run as run_experiments


class Stage3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.research = asyncio.run(research_stage2("multi agent systems", load_frozen(),
                                alternative="distributed task allocation"))

    def test_requests_derive_from_scientific_and_news_materials(self):
        checks = derive_checks(self.research)
        self.assertEqual({x.owner for x in checks}, {"science", "news", "link"})
        self.assertTrue(all(x.materials for x in checks))
        self.assertTrue(all(x.materials[0]["provenance"] == "synthetic_fixture"
                            for x in checks))

    def test_moderate_shortage_changes_real_checks_and_keeps_limit(self):
        baseline = asyncio.run(review_research(self.research, mode="baseline", credits=3))
        negotiation = asyncio.run(review_research(self.research, mode="negotiation", credits=3))
        self.assertEqual(baseline["plan"], {"science": 2, "news": 1, "link": 0})
        self.assertEqual(negotiation["plan"], {"science": 1, "news": 1, "link": 1})
        self.assertNotIn("link", baseline["checks"])
        self.assertEqual(negotiation["checks"]["link"]["evidence"]["assessment"],
                         "insufficient_evidence")
        self.assertEqual(negotiation["resource"]["spent"], 3)
        self.assertEqual(negotiation["resource"]["held"], 0)
        self.assertEqual(negotiation["metrics"]["counteroffers"], 3)
        self.assertEqual(negotiation["metrics"]["jain_normalized_satisfaction"], 1)
        self.assertEqual(baseline["metrics"]["jain_normalized_satisfaction"], 0.6)
        self.assertGreater(negotiation["metrics"]["messages"], baseline["metrics"]["messages"])
        self.assertEqual(negotiation["metrics"]["budget_violations"], 0)
        self.assertEqual(negotiation["metrics"]["slot_violations"], 0)
        self.assertTrue(all(x["phase"] == "finished"
                            for x in negotiation["resource"]["reservations"].values()))

    def test_sufficient_budget_has_no_concessions(self):
        baseline = asyncio.run(review_research(self.research, mode="baseline", credits=6))
        negotiation = asyncio.run(review_research(self.research, mode="negotiation", credits=6))
        self.assertEqual(baseline["plan"], negotiation["plan"])
        self.assertEqual(negotiation["metrics"]["counteroffers"], 0)
        self.assertGreater(negotiation["metrics"]["messages"], baseline["metrics"]["messages"])

    def test_strong_shortage_and_silent_agent_terminate(self):
        severe = asyncio.run(review_research(self.research, mode="negotiation", credits=2))
        self.assertEqual(sum(severe["plan"].values()), 2)
        silent = asyncio.run(review_research(self.research, mode="negotiation", credits=3,
                                             silent_owners=frozenset({"link"}), timeout=0.01))
        self.assertGreaterEqual(silent["metrics"]["arbitrations"], 1)
        self.assertEqual(silent["plan"]["link"], 0)
        self.assertLessEqual(silent["resource"]["spent"], 3)
        self.assertEqual(silent["resource"]["held"], 0)

    def test_evidence_claims_stay_within_available_text(self):
        science, news, link = derive_checks(self.research)
        self.assertEqual(perform_check(news, 2)["assessment"], "claim_unverified")
        self.assertIsNone(perform_check(science, 1)["details"]["excerpt"])
        self.assertEqual(perform_check(science, 2)["scope"], "abstract")
        self.assertNotIn("confirmed", perform_check(link, 2)["assessment"])

    def test_partial_search_results_and_zero_budget(self):
        partial = dict(self.research)
        partial["materials"] = {"scientific": self.research["materials"]["scientific"],
                                "news": []}
        review = asyncio.run(review_research(partial, mode="negotiation", credits=2))
        self.assertEqual(len(review["requests"]), 1)
        self.assertEqual(review["metrics"]["completed_checks"], 1)
        zero = asyncio.run(review_research(self.research, mode="negotiation", credits=0))
        self.assertEqual(zero["metrics"]["completed_checks"], 0)
        self.assertEqual(zero["resource"]["spent"], 0)
        self.assertEqual(zero["metrics"]["jain_normalized_satisfaction"], 0)

    def test_ledger_atomic_capacity_idempotence_and_release(self):
        async def exercise():
            ledger = VerificationBudget(1)
            outcomes = await asyncio.gather(ledger.reserve("a", "a", "agent-a", 1),
                                            ledger.reserve("b", "b", "agent-b", 1))
            self.assertEqual(sum(outcomes), 1)
            winner = "a" if outcomes[0] else "b"
            owner = "agent-a" if outcomes[0] else "agent-b"
            self.assertTrue(await ledger.reserve(winner, winner, owner, 1))
            with self.assertRaises(ValueError):
                await ledger.reserve(winner, "other", owner, 1)
            self.assertFalse(await ledger.start(winner, "stranger"))
            self.assertTrue(await ledger.cancel(winner, owner))
            self.assertFalse(await ledger.cancel(winner, owner))
            self.assertEqual(ledger.snapshot()["held"], 0)
            self.assertTrue(await ledger.reserve("retry", winner, owner, 1))
            self.assertTrue(await ledger.cancel("retry", owner))
            self.assertTrue(await ledger.reserve("fresh", "fresh", "agent-c", 1))
            self.assertTrue(await ledger.start("fresh", "agent-c"))
            self.assertFalse(await ledger.start("fresh", "agent-c"))
            self.assertTrue(await ledger.authorized("fresh", "fresh", "agent-c", 1))
            self.assertFalse(await ledger.authorized("fresh", "other", "agent-c", 1))
            self.assertTrue(await ledger.finish("fresh", "agent-c"))
            self.assertFalse(await ledger.finish("fresh", "agent-c"))
            self.assertEqual(ledger.snapshot()["spent"], 1)
            self.assertEqual(ledger.snapshot()["active"], 0)
            other = VerificationBudget(2)
            self.assertTrue(await other.reserve("slow", "slow", "agent", 2))
            self.assertTrue(await other.start("slow", "agent"))
            self.assertTrue(await other.abort("slow", "agent"))
            self.assertEqual(other.snapshot()["active"], 0)
            self.assertEqual(other.snapshot()["held"], 0)
            self.assertEqual(other.snapshot()["spent"], 2)
        asyncio.run(exercise())

    def test_bus_permissions_and_correlation(self):
        async def exercise():
            bus = NegotiationBus(("science",), "run")
            with self.assertRaises(PermissionError):
                await bus.send(Message.make("science", "science", "counter", "run", {}))
            with self.assertRaises(PermissionError):
                await bus.send(Message.make("science", "mediator", "counter", "wrong", {}))
            check = derive_checks(self.research)[0]
            mediator = Mediator((check,), bus, VerificationBudget(2), 0.01)
            await bus.send(Message.make("science", "mediator", "accept", "run",
                                        {"check_id": check.id, "round": 2}, "wrong-offer"))
            result = await mediator._collect({"accept"}, {"science": "valid-offer"}, 2)
            self.assertFalse(result)
            self.assertEqual(mediator.invalid_messages, 1)
            await bus.send(Message.make("science", "mediator", "counter", "run",
                                        {"check_id": check.id, "round": 1}, "valid-offer"))
            result = await mediator._collect({"counter"}, {"science": "valid-offer"}, 2)
            self.assertFalse(result)
            self.assertEqual(mediator.invalid_messages, 2)
        asyncio.run(exercise())

    def test_compatibility_with_both_assignment_policies(self):
        for mechanism in ("centralized", "contract-net"):
            research = asyncio.run(research_stage2("agents", load_frozen(),
                                    mechanism=mechanism))
            result = asyncio.run(review_research(research, mode="negotiation", credits=3))
            self.assertEqual(result["metrics"]["completed_checks"], 3)
            self.assertEqual(result["metrics"]["budget_violations"], 0)

    def test_stalled_checks_do_not_leave_reserved_slots(self):
        result = asyncio.run(review_research(self.research, mode="baseline",
                                             credits=3, delay_ms=100, timeout=0.01))
        self.assertEqual(result["resource"]["held"], 0)
        self.assertEqual(result["resource"]["active"], 0)
        self.assertEqual(result["metrics"]["completed_checks"], 0)
        self.assertLessEqual(result["resource"]["spent"], 3)

    def test_paired_experiment_outputs_are_recomputable(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            asyncio.run(run_experiments(1, output))
            with (output / "raw.csv").open(encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 10)
            self.assertEqual(len({(x["scenario"], x["seed"], x["mode"]) for x in rows}), 10)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            paired = json.loads((output / "paired.json").read_text(encoding="utf-8"))
            self.assertEqual(len(summary), 10)
            self.assertEqual(len(paired), 5)
            for row in rows:
                item = next(x for x in summary if x["scenario"] == row["scenario"]
                            and x["mode"] == row["mode"])
                self.assertAlmostEqual(float(row["estimated_utility"]),
                                       item["estimated_utility_mean"], places=5)
                self.assertEqual(int(row["budget_violations"]), 0)
                self.assertEqual(int(row["slot_violations"]), 0)
            for item in paired:
                group = {x["mode"]: x for x in rows if x["scenario"] == item["scenario"]}
                self.assertAlmostEqual(float(group["negotiation"]["estimated_utility"])
                    - float(group["baseline"]["estimated_utility"]),
                    item["estimated_utility_difference_mean"], places=5)
            self.assertEqual(len(list((output / "traces").glob("*.json"))), 10)
            self.assertEqual(len(list(output.glob("*.svg"))), 4)


if __name__ == "__main__":
    unittest.main()
