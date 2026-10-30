import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from xml.etree import ElementTree

from researchradar.coordination import (Bus, WorkerSpec, WorkerState,
                                        make_tasks, research_stage2)
from researchradar.frozen import load_frozen
from researchradar.model import Material, Message
from researchradar.planning import qwen_alternative, validate_alternative
from researchradar.scientific import (Arxiv, Crossref, deduplicate,
                                      normalize_arxiv, normalize_crossref)
from researchradar.sources import GoogleNewsRSS


class Broken:
    def search(self, query, limit):
        raise RuntimeError("offline source failure")


class Stage2Tests(unittest.TestCase):
    def test_task_plan_and_overlapping_competencies(self):
        self.assertEqual(len(make_tasks("agent systems", "task allocation")), 5)
        self.assertEqual(len(make_tasks("agent systems", "agent systems")), 4)
        with self.assertRaises(ValueError):
            make_tasks(" ")

    def test_both_mechanisms_complete_same_frozen_work(self):
        results = [asyncio.run(research_stage2("agent systems", load_frozen(),
                   mechanism=method, alternative="task allocation"))
                   for method in ("centralized", "contract-net")]
        for result in results:
            self.assertEqual(result["metrics"]["completed_tasks"], 5)
            self.assertEqual(len(result["materials"]["scientific"]), 3)
            self.assertEqual(len(result["materials"]["news"]), 1)
            self.assertTrue(all(x["phase"] == "stopped" for x in result["agents"].values()))
            self.assertTrue(all(x["provenance"] == "synthetic_fixture"
                                for rows in result["materials"].values() for x in rows))
        self.assertEqual(results[0]["metrics"]["messages"], 10)
        self.assertGreater(results[1]["metrics"]["messages"], 10)
        self.assertEqual(results[1]["metrics"]["message_kinds"]["accept"], 5)
        self.assertEqual(results[1]["metrics"]["message_kinds"]["reject"], 8)
        self.assertEqual(results[0]["materials"], results[1]["materials"])

    def test_failed_source_preserves_other_materials(self):
        sources = load_frozen() | {"arxiv": Broken()}
        result = asyncio.run(research_stage2("agent systems", sources,
                             mechanism="contract-net", alternative="task allocation"))
        self.assertIn("ax-preprints", result["errors"])
        self.assertEqual(result["metrics"]["reassignments"], 2)
        self.assertEqual(len(result["materials"]["news"]), 1)
        self.assertEqual(len(result["materials"]["scientific"]), 2)

    def test_timeout_cancels_slow_worker_and_reassigns(self):
        workers = (
            WorkerSpec("slow", ("openalex",), {"openalex": 1}, {"openalex": 250}),
            WorkerSpec("fast", ("openalex",), {"openalex": 10}, {"openalex": 1}),
        )
        result = asyncio.run(research_stage2("agent systems", load_frozen(),
                    workers=workers, task_timeout=0.05, deadline_seconds=1))
        self.assertEqual(result["assignments"]["oa-primary"], ["slow", "fast"])
        self.assertEqual(result["metrics"]["completed_tasks"], 1)
        self.assertGreaterEqual(result["metrics"]["message_kinds"]["cancel"], 1)
        self.assertTrue(all(x["phase"] == "stopped" for x in result["agents"].values()))

    def test_authority_and_state_transitions(self):
        state = WorkerState()
        state.enqueue()
        state.enqueue()
        state.finish(True, 0.01)
        self.assertEqual((state.phase, state.queued, state.handled), ("busy", 1, 1))
        state.finish(False, 0.02)
        self.assertEqual((state.phase, state.failures), ("idle", 1))
        state.stop()
        with self.assertRaises(RuntimeError):
            state.enqueue()

        async def check():
            bus = Bus(("worker",))
            with self.assertRaises(PermissionError):
                await bus.send(Message.make("worker", "worker", "task", "r", {}))
        asyncio.run(check())

    def test_crossref_normalization_and_doi_deduplication(self):
        row = {"DOI": "10.1234/EXAMPLE", "title": ["A Study"],
               "author": [{"given": "Ada", "family": "Lovelace"}],
               "published": {"date-parts": [[2025, 2, 3]]},
               "container-title": ["Journal"]}
        item = normalize_crossref(row)
        self.assertEqual(item.authors, ("Ada Lovelace",))
        self.assertEqual(item.published, "2025-02-03")
        duplicate = Material("scientific", "OpenAlex", "W1", "A Study",
                             "https://example.org/1", "2025", doi="https://doi.org/10.1234/example")
        merged = deduplicate([item, duplicate])
        self.assertEqual(len(merged), 1)
        self.assertIn("OpenAlex", merged[0].discovered_in)
        self.assertEqual(len(deduplicate([item, Material("scientific", "Other", "x",
                  "A Study", "https://example.org/x", None)])), 2)

    def test_crossref_http_adapter(self):
        reply = Mock()
        reply.json.return_value = {"message": {"items": [{"DOI": "10.1/x", "title": ["X"]}]}}
        with TemporaryDirectory() as d, patch("researchradar.scientific.requests.get", return_value=reply) as get:
            adapter = Crossref(cache_dir=Path(d))
            self.assertEqual(len(adapter.search("agents")), 1)
            self.assertEqual(adapter.search("agents")[0].provenance, "cache_crossref")
            self.assertEqual(get.call_count, 1)

    def test_arxiv_atom_normalization_and_adapter(self):
        xml = b'''<feed xmlns="http://www.w3.org/2005/Atom">
        <entry><id>https://arxiv.org/abs/2501.01234v2</id><title> Agent Study </title>
        <published>2025-01-02T00:00:00Z</published><summary> Abstract </summary>
        <author><name>A. Author</name></author></entry></feed>'''
        node = ElementTree.fromstring(xml)[0]
        self.assertEqual(normalize_arxiv(node).arxiv_id, "2501.01234")
        reply = Mock(content=xml)
        with TemporaryDirectory() as d, patch("researchradar.scientific.requests.get", return_value=reply) as get:
            adapter = Arxiv(cache_dir=Path(d))
            self.assertEqual(adapter.search("agent systems")[0].authors, ("A. Author",))
            self.assertEqual(adapter.search("agent systems")[0].provenance, "cache_arxiv")
            self.assertEqual(get.call_count, 1)

    def test_rss_cache(self):
        reply = Mock(content=b"<rss><channel><item><title>News</title><link>https://example.org/n</link></item></channel></rss>")
        with TemporaryDirectory() as d, patch("researchradar.sources.requests.get", return_value=reply) as get:
            adapter = GoogleNewsRSS(cache_dir=Path(d))
            self.assertEqual(len(adapter.search("agents")), 1)
            self.assertEqual(adapter.search("agents")[0].provenance, "cache_rss")
            self.assertEqual(get.call_count, 1)

    def test_llm_plan_is_contentful_and_validated(self):
        client = Mock()
        client.complete.return_value = '{"alternative_query":"distributed multi agent task allocation"}'
        self.assertEqual(qwen_alternative("agent coordination", client,
                         input_rate_per_million=0.5, output_rate_per_million=3,
                         request_id="r"), "distributed multi agent task allocation")
        self.assertEqual(client.complete.call_args.kwargs["max_tokens"], 512)
        with self.assertRaises(ValueError):
            validate_alternative("agents", '{"alternative_query":"agents"}')
        with self.assertRaises(ValueError):
            validate_alternative("agents", '{"alternative_query":"x", "route":"override"}')


if __name__ == "__main__":
    unittest.main()
