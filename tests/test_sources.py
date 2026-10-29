import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from researchradar.sources import GDELT, SourceError


class Reply:
    def __init__(self, status=200, rows=None, headers=None, malformed=False):
        self.status_code = status
        self.rows = rows if rows is not None else []
        self.headers = headers or {}
        self.malformed = malformed

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"articles": "bad" if self.malformed else self.rows}


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)

    @patch("researchradar.sources.requests.get", side_effect=[
        Reply(status=429, headers={"Retry-After": "0"}),
        Reply(rows=[{"url": "https://example.org/news", "title": "Headline"}])])
    def test_gdelt_retries_then_caches(self, get):
        source = GDELT(cache_dir=self.cache, sleeper=lambda _: None)
        self.assertEqual(len(source.search("research", 2)), 1)
        self.assertEqual(source.search("research", 2)[0].provenance, "cache_gdelt")
        self.assertEqual(get.call_count, 2)

    @patch("researchradar.sources.requests.get", return_value=Reply(status=429))
    def test_gdelt_rate_limit_is_bounded(self, get):
        with self.assertRaisesRegex(SourceError, "429"):
            GDELT(cache_dir=self.cache, sleeper=lambda _: None, retries=1).search("x")
        self.assertEqual(get.call_count, 2)

    @patch("researchradar.sources.requests.get", return_value=Reply(
        status=429, headers={"Retry-After": "120"}))
    def test_gdelt_respects_long_retry_after_without_early_retry(self, get):
        with self.assertRaisesRegex(SourceError, "Retry-After"):
            GDELT(cache_dir=self.cache, sleeper=lambda _: None, retries=1).search("x")
        self.assertEqual(get.call_count, 1)

    @patch("researchradar.sources.requests.get", return_value=Reply(malformed=True))
    def test_gdelt_format_error(self, _get):
        with self.assertRaisesRegex(SourceError, "invalid articles"):
            GDELT(cache_dir=self.cache).search("x")


if __name__ == "__main__":
    unittest.main()
