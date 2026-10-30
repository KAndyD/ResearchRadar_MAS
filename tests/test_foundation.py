import asyncio
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from researchradar.engine import Router, research
from researchradar.llm import BudgetedOpenRouter
from researchradar.model import AgentState, Message, Phase, ResearchRequest
from researchradar.sources import FixtureSource, normalize_openalex, normalize_gdelt


class BrokenSource:
    def search(self, query, limit):
        raise RuntimeError("source unavailable")


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

    def test_one_source_failure_preserves_partial_result(self):
        result = asyncio.run(research("multi-agent systems",
                                      FixtureSource("scientific"), BrokenSource()))
        self.assertEqual(len(result["materials"]["scientific"]), 1)
        self.assertEqual(result["materials"]["news"], [])
        self.assertIn("news", result["errors"])
        self.assertEqual(result["agents"]["journalist"]["phase"], "failed")

    def test_overlapping_candidate_can_be_registered(self):
        result = asyncio.run(research("multi-agent systems",
                                      FixtureSource("scientific"), FixtureSource("news"),
                                      {"backup": ("scientific", BrokenSource())}))
        self.assertEqual(result["agents"]["scientist"]["phase"], "done")
        self.assertNotIn("backup", result["agents"])

    def test_duplicate_worker_reply_cannot_replace_other_task(self):
        class DuplicatingRouter(Router):
            duplicated = False

            async def send(self, message):
                await super().send(message)
                if message.kind == "result" and message.sender in {"scientist", "journalist"} and not self.duplicated:
                    self.duplicated = True
                    await self.queues["coordinator"].put(message)

        with patch("researchradar.engine.Router", DuplicatingRouter):
            with self.assertRaisesRegex(ValueError, "unrelated worker response"):
                asyncio.run(research("multi-agent systems", FixtureSource("scientific"),
                                     FixtureSource("news")))

    def test_cli_demo_writes_structured_result_without_api(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "demo.json"
            run = subprocess.run([sys.executable, "-m", "researchradar.cli",
                                  "multi-agent systems", "--mode", "demo",
                                  "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "demo")
            self.assertEqual(len(data["trace"]), 6)

    def test_budget_prevents_paid_call(self):
        with TemporaryDirectory() as directory, patch("researchradar.llm.local_key", return_value="dummy"):
            client = BudgetedOpenRouter(budget_usd=0, ledger_path=Path(directory) / "usage.db")
            with self.assertRaisesRegex(RuntimeError, "budget"):
                client.complete(request_id="r", agent="coordinator", purpose="smoke",
                                prompt="hello", input_rate_per_million=1,
                                output_rate_per_million=1)
            self.assertEqual(client.records(), [])


if __name__ == "__main__":
    unittest.main()
