"""Regression checks for independent credits and execution slots."""
import asyncio
import unittest
from unittest.mock import patch

from researchradar.model import Message
from researchradar.negotiation import (CheckRequest, NegotiationBus, ReviewAgent,
                                       review_research)
from researchradar.resources import VerificationBudget


def checks(count=2):
    return tuple(CheckRequest(f"request-{i}", f"agent-{i}", "bibliography",
                              ({"title": f"Paper {i}"},), 1, 6.0, 3.0)
                 for i in range(count))


class ResourceRegressionTests(unittest.TestCase):
    def test_two_credit_check_uses_one_slot(self):
        async def exercise():
            budget = VerificationBudget(2, 1)
            self.assertTrue(await budget.reserve("a", "request-a", "agent-a", 2))
            self.assertTrue(await budget.start("a", "agent-a"))
            self.assertEqual(budget.snapshot()["active"], 1)
            self.assertEqual(budget.snapshot()["peak_active"], 1)
            self.assertTrue(await budget.finish("a", "agent-a"))
            self.assertEqual((budget.snapshot()["spent"], budget.snapshot()["held"],
                              budget.snapshot()["active"]), (2, 0, 0))
        asyncio.run(exercise())

    def test_two_one_credit_checks_use_two_slots(self):
        async def exercise():
            budget = VerificationBudget(2, 2)
            self.assertEqual(await asyncio.gather(
                budget.reserve("a", "a", "a", 1),
                budget.reserve("b", "b", "b", 1)), [True, True])
            self.assertEqual(await asyncio.gather(
                budget.start("a", "a"), budget.start("b", "b")), [True, True])
            self.assertEqual((budget.snapshot()["active"], budget.snapshot()["peak_active"]),
                             (2, 2))
            self.assertEqual(await asyncio.gather(
                budget.finish("a", "a"), budget.finish("b", "b")), [True, True])
            self.assertEqual((budget.snapshot()["spent"], budget.snapshot()["held"],
                              budget.snapshot()["active"]), (2, 0, 0))
        asyncio.run(exercise())

    def test_full_protocol_slot_failure_releases_reservation(self):
        result = asyncio.run(review_research({"question": "slot conflict"},
            mode="baseline", credits=4, concurrent_slots=1, checks=checks(),
            delay_ms=25, timeout=0.2))
        self.assertEqual(result["metrics"]["completed_checks"], 1)
        self.assertEqual(sum(x["kind"] == "failure" for x in result["trace"]), 1)
        self.assertEqual((result["resource"]["spent"], result["resource"]["held"],
                          result["resource"]["active"], result["resource"]["peak_active"]),
                         (2, 0, 0, 1))
        self.assertEqual({x["phase"] for x in result["resource"]["reservations"].values()},
                         {"finished", "cancelled"})

    def test_full_protocol_two_credits_one_slot_completes(self):
        result = asyncio.run(review_research({"question": "one full check"},
            mode="baseline", credits=2, concurrent_slots=1, checks=checks(1)))
        self.assertEqual(result["metrics"]["completed_checks"], 1)
        self.assertEqual((result["resource"]["spent"], result["resource"]["held"],
                          result["resource"]["peak_active"]), (2, 0, 1))

    def test_mediator_cleans_failure_if_agent_cancel_does_not(self):
        async def failed_cancel(*_args):
            return False
        with patch.object(VerificationBudget, "cancel", failed_cancel):
            result = asyncio.run(review_research({"question": "slot conflict"},
                mode="baseline", credits=4, concurrent_slots=1, checks=checks(),
                delay_ms=25, timeout=0.2))
        self.assertEqual(result["resource"]["held"], 0)
        self.assertEqual(result["metrics"]["completed_checks"], 1)
        self.assertIn("cancelled", {x["phase"] for x in
                                   result["resource"]["reservations"].values()})

    def test_timeout_after_start_spends_credits_once(self):
        result = asyncio.run(review_research({"question": "timeout"}, mode="baseline",
            credits=2, concurrent_slots=1, checks=checks(1), delay_ms=100,
            timeout=0.01))
        self.assertEqual(result["metrics"]["completed_checks"], 0)
        self.assertEqual((result["resource"]["spent"], result["resource"]["held"],
                          result["resource"]["active"]), (2, 0, 0))
        self.assertEqual(next(iter(result["resource"]["reservations"].values()))["phase"],
                         "failed")

    def test_rejected_finish_never_reports_success(self):
        async def aborted_finish(budget, agreement, owner):
            await budget.abort(agreement, owner)
            return False
        with patch.object(VerificationBudget, "finish", aborted_finish):
            result = asyncio.run(review_research({"question": "finish race"},
                mode="baseline", credits=2, concurrent_slots=1, checks=checks(1)))
        self.assertEqual(result["metrics"]["completed_checks"], 0)
        self.assertEqual(sum(x["kind"] == "result" for x in result["trace"]), 0)
        self.assertEqual(sum(x["kind"] == "failure" for x in result["trace"]), 1)
        self.assertEqual((result["resource"]["spent"], result["resource"]["held"],
                          result["resource"]["active"]), (2, 0, 0))

    def test_repeated_and_wrong_owner_operations_remain_safe(self):
        async def exercise():
            budget = VerificationBudget(2, 1)
            self.assertTrue(await budget.reserve("a", "a", "owner", 2))
            self.assertTrue(await budget.reserve("a", "a", "owner", 2))
            self.assertFalse(await budget.start("a", "other"))
            self.assertFalse(await budget.cancel("a", "other"))
            self.assertTrue(await budget.start("a", "owner"))
            self.assertFalse(await budget.start("a", "owner"))
            self.assertTrue(await budget.finish("a", "owner"))
            self.assertFalse(await budget.finish("a", "owner"))
            self.assertFalse(await budget.abort("a", "owner"))
            self.assertFalse(await budget.cancel("a", "owner"))
            self.assertFalse(await budget.start("a", "owner"))
            self.assertFalse(await budget.reserve("other", "other", "other", 1))
            self.assertEqual((budget.snapshot()["spent"], budget.snapshot()["held"],
                              budget.snapshot()["active"]), (2, 0, 0))
        asyncio.run(exercise())

    def test_parallel_last_slot_and_cancellation(self):
        async def exercise():
            budget = VerificationBudget(4, 1)
            for i in range(4):
                self.assertTrue(await budget.reserve(str(i), str(i), str(i), 1))
            started = await asyncio.gather(*(budget.start(str(i), str(i)) for i in range(4)))
            self.assertEqual(sum(started), 1)
            self.assertEqual(budget.snapshot()["active"], 1)
            for i, did_start in enumerate(started):
                if did_start:
                    self.assertTrue(await budget.finish(str(i), str(i)))
                else:
                    self.assertTrue(await budget.cancel(str(i), str(i)))
                    self.assertFalse(await budget.cancel(str(i), str(i)))
            self.assertEqual((budget.snapshot()["spent"], budget.snapshot()["held"],
                              budget.snapshot()["active"], budget.snapshot()["peak_active"]),
                             (1, 0, 0, 1))
        asyncio.run(exercise())

    def test_finish_abort_race_spends_once_and_has_one_terminal_phase(self):
        async def exercise():
            budget = VerificationBudget(2, 1)
            self.assertTrue(await budget.reserve("a", "a", "owner", 2))
            self.assertTrue(await budget.start("a", "owner"))
            outcomes = await asyncio.gather(budget.finish("a", "owner"),
                                            budget.abort("a", "owner"))
            self.assertEqual(sum(outcomes), 1)
            snapshot = budget.snapshot()
            self.assertEqual((snapshot["spent"], snapshot["held"], snapshot["active"]),
                             (2, 0, 0))
            self.assertIn(snapshot["reservations"]["a"]["phase"], {"finished", "failed"})
        asyncio.run(exercise())

    def test_duplicate_commit_cannot_spend_or_report_success_twice(self):
        async def exercise():
            check = checks(1)[0]
            bus = NegotiationBus((check.owner,), "duplicate")
            budget = VerificationBudget(2, 1)
            self.assertTrue(await budget.reserve("agreement", check.id, check.owner, 2))
            runner = asyncio.create_task(ReviewAgent(check, bus, budget).run())
            commit = Message.make("mediator", check.owner, "commit", "duplicate",
                                  {"check_id": check.id, "agreement_id": "agreement",
                                   "units": 2})
            await bus.send(commit)
            await bus.send(commit)
            kinds = [(await asyncio.wait_for(bus.queues["mediator"].get(), .2)).kind
                     for _ in range(3)]
            await bus.send(Message.make("mediator", check.owner, "shutdown", "duplicate", {}))
            await runner
            self.assertEqual(kinds.count("result"), 1)
            self.assertEqual(kinds.count("failure"), 1)
            self.assertEqual((budget.snapshot()["spent"], budget.snapshot()["held"],
                              budget.snapshot()["active"]), (2, 0, 0))
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
