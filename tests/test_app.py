"""Offline regression checks for key original DeepRake V1 flows."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as deeprake


class DeepRakeV1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name)
        self.patches = [
            patch.object(deeprake, "OUT", self.out),
            patch.object(deeprake, "RESULTS_JSONL", self.out / "search_results.jsonl"),
            patch.object(deeprake, "NEXT_QUERIES", self.out / "next_queries.txt"),
            patch.object(deeprake, "PIVOT_STATE", self.out / "pivot_state.jsonl"),
        ]
        for item in self.patches:
            item.start()
        self.client = deeprake.app.test_client()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_original_bookmarklet_is_preserved(self):
        result = self.client.get("/dorks")
        self.assertEqual(result.status_code, 200)
        page = result.get_data(as_text=True)
        self.assertIn("http://localhost:5000/api/results", page)
        self.assertIn("Quantum-Dig Bookmarklet", page)
        self.assertNotIn("/quantum-relay", page)

    def test_harvest_and_pivot(self):
        sample = [{"title": "Water quality report", "snippet": "Environmental monitoring data", "url": "https://example.org/report"}]
        result = self.client.post("/api/results", json=sample)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["appended"], 1)
        self.assertEqual(json.loads(deeprake.RESULTS_JSONL.read_text().splitlines()[0])["url"], sample[0]["url"])

        result = self.client.post("/api/pivot")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json["ok"])
        self.assertTrue(deeprake.NEXT_QUERIES.exists())

        result = self.client.get("/api/harvest/download")
        self.assertEqual(result.status_code, 200)
        self.assertIn("https://example.org/report", result.get_data(as_text=True))
        result.close()

        result = self.client.post("/api/clear")
        self.assertTrue(result.json["ok"])
        self.assertEqual(deeprake.RESULTS_JSONL.read_text(), "")
        self.assertEqual(deeprake.NEXT_QUERIES.read_text(), "")


if __name__ == "__main__":
    unittest.main()
