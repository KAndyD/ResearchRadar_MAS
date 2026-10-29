import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests

from researchradar.llm import BudgetedOpenRouter


class Reply:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self.body = body or {}
        self.headers = headers or {}

    def json(self):
        return self.body


def body(content="4", cost=0.0002):
    usage = {"prompt_tokens": 10, "completion_tokens": 8}
    if cost is not None:
        usage["cost"] = cost
    return {"id": "gen-123", "usage": usage,
            "choices": [{"message": {"content": content}}]}


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "usage.db"
        self.key = patch("researchradar.llm.local_key", return_value="sensitive-test-key")
        self.key.start()
        self.addCleanup(self.key.stop)

    def client(self, **kwargs):
        return BudgetedOpenRouter(ledger_path=self.path, sleeper=lambda _: None, **kwargs)

    def call(self, client, **kwargs):
        return client.complete(request_id="research-1", agent="coordinator", purpose="test",
                               prompt="2+2", max_tokens=32,
                               input_rate_per_million=1, output_rate_per_million=1,
                               **kwargs)

    @patch("researchradar.llm.requests.post", return_value=Reply(body=body()))
    def test_success_is_durable_and_idempotent(self, post):
        client = self.client()
        self.assertEqual(self.call(client, call_id="fixed"), "4")
        row = self.client().records()[0]
        self.assertEqual((row["status"], row["provider_id"], row["actual_usd"]),
                         ("succeeded", "gen-123", 0.0002))
        self.assertEqual(client.summary().actual_usd, 0.0002)
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            self.call(client, call_id="fixed")
        self.assertEqual(post.call_count, 1)
        self.assertNotIn("sensitive-test-key", str(row))

    @patch("researchradar.llm.requests.post", return_value=Reply(body=body(cost=None)))
    def test_missing_usage_cost_is_uncertain(self, _post):
        self.call(self.client())
        summary = self.client().summary()
        self.assertEqual(summary.actual_usd, 0)
        self.assertEqual(summary.uncertain_calls, 1)
        self.assertGreater(summary.uncertain_estimate_usd, 0)
        self.assertEqual(self.client().records()[0]["missing_cost_reason"], "usage.cost absent")

    @patch("researchradar.llm.requests.post", return_value=Reply(body={
        "id": "gen-no-usage", "choices": [{"message": {"content": "4"}}]}))
    def test_absent_usage_keeps_estimate(self, _post):
        self.assertEqual(self.call(self.client()), "4")
        row = self.client().records()[0]
        self.assertIsNone(row["actual_usd"])
        self.assertEqual(row["missing_cost_reason"], "usage.cost absent")

    @patch("researchradar.llm.requests.post", return_value=Reply(body=body(content="")))
    def test_empty_response_keeps_actual_expense(self, _post):
        with self.assertRaisesRegex(RuntimeError, "empty"):
            self.call(self.client())
        row = self.client().records()[0]
        self.assertEqual(row["status"], "empty_response")
        self.assertEqual(row["actual_usd"], 0.0002)

    @patch("researchradar.llm.requests.post", side_effect=requests.Timeout("secret in raw exception"))
    def test_timeout_keeps_uncertain_cost_and_hides_exception(self, _post):
        with self.assertRaisesRegex(RuntimeError, "expense unknown") as caught:
            self.call(self.client())
        row = self.client().records()[0]
        self.assertEqual(row["status"], "unknown_after_timeout")
        self.assertIsNone(row["actual_usd"])
        self.assertNotIn("secret", str(caught.exception) + str(row))

    @patch("researchradar.llm.requests.post", return_value=Reply(status=401))
    def test_http_error_keeps_record(self, _post):
        with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
            self.call(self.client())
        self.assertEqual(self.client().records()[0]["error_type"], "HTTP401")

    @patch("researchradar.llm.requests.post", side_effect=[
        Reply(status=429, headers={"Retry-After": "0"}), Reply(body=body())])
    def test_rate_limit_retry_is_one_accounting_record(self, post):
        self.assertEqual(self.call(self.client()), "4")
        row = self.client().records()[0]
        self.assertEqual(row["attempts"], 2)
        self.assertEqual(self.client().summary().total_calls, 1)
        self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
