import asyncio
import unittest

from researchradar.engine import Router, research
from researchradar.llm import BudgetedOpenRouter
from researchradar.model import AgentState, Message, Phase, ResearchRequest
from researchradar.sources import FixtureSource, normalize_openalex, normalize_gdelt


class FoundationTests(unittest.TestCase):
    def test_state_transitions(self):
        state = AgentState()
        self.assertEqual(state.phase, Phase.IDLE)
        with self.assertRaises(ValueError):
            state.change(Phase.DONE)
        state.change(Phase.BUSY)
        state.change(Phase.DONE)
        with self.assertRaises(ValueError):
            state.change(Phase.BUSY)

    def test_request_validation(self):
        with self.assertRaises(ValueError):
            ResearchRequest(" ")

    def test_router_delivers_and_enforces_authority(self):
        async def check():
            router = Router()
            valid = Message.make("coordinator", "scientist", "task", "r1", {"query": "x"})
            await router.send(valid)
            self.assertEqual(await router.queues["scientist"].get(), valid)
            self.assertEqual(len(router.trace), 1)
            with self.assertRaises(PermissionError):
                await router.send(Message.make("journalist", "scientist", "task", "r1", {}))
        asyncio.run(check())

    def test_normalization_missing_fields(self):
        self.assertIsNone(normalize_openalex({"id": "x"}))
        self.assertIsNone(normalize_gdelt({"title": "x"}))
        item = normalize_openalex({"id": "x", "display_name": "T",
                                   "abstract_inverted_index": {"World": [1], "Hello": [0]}})
        self.assertEqual(item.abstract, "Hello World")
        self.assertEqual(item.text_scope, "abstract")

    def test_offline_multi_agent_research(self):
        result = asyncio.run(research("multi-agent systems",
                                      FixtureSource("scientific"), FixtureSource("news")))
        self.assertEqual(len(result["tasks"]), 2)
        self.assertEqual(len(result["materials"]["scientific"]), 1)
        self.assertEqual(len(result["materials"]["news"]), 1)
        self.assertEqual(len(result["trace"]), 6)
        self.assertTrue(all(agent["phase"] == "done" for agent in result["agents"].values()))
        self.assertTrue(all(m["provenance"] == "synthetic_fixture"
                            for rows in result["materials"].values() for m in rows))

    def test_budget_prevents_paid_call(self):
        client = BudgetedOpenRouter(budget_usd=0)
        with self.assertRaisesRegex(RuntimeError, "budget"):
            client.complete(request_id="r", agent="coordinator", purpose="smoke",
                            prompt="hello", input_rate_per_million=1,
                            output_rate_per_million=1)
        self.assertEqual(client.ledger, [])


if __name__ == "__main__":
    unittest.main()
