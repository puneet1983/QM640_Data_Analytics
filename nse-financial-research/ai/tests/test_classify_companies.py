"""Offline contract tests; these do not evaluate real model accuracy."""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai.agent.classify_companies import classify, main
from ai.tools.company_data import read_companies, save_results

MODEL = "openai/gpt-oss-120b"


class CompanyAgentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "input.csv"
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerows([
                ["NSE_SYMBOL", "COMPANY_NAME"],
                ["ABC", "ABC Limited"],
                [" abc ", " ABC  LIMITED "],
                ["ABC", "Different Legal Entity"],
            ])

    def fake_client(self, *, confirmed=True, sources=None, metadata=True):
        url = "https://www.nseindia.com/example"
        result = {"industry": "Example Industry", "sector": "Example Sector",
                  "taxonomy": "NSE", "identity_confirmed": confirmed,
                  "needs_review": False, "reason": "Fixture evidence",
                  "source_urls": sources if sources is not None else [url]}
        response = SimpleNamespace(
            status="completed", output_text=json.dumps(result),
        )
        research = SimpleNamespace(
            status="completed", output_text=f"Fixture research with source: {url}",
            model_dump=lambda: {"output": [{"type": "browser_search_call",
                "action": {"sources": [{"url": url}]}}]} if metadata else {"output": []},
        )
        client = Mock()
        client.responses.create.side_effect = [research, response]
        return client

    def test_deduplication_preserves_distinct_names(self):
        count, companies = read_companies(self.path)
        self.assertEqual(count, 3)
        self.assertEqual(len(companies), 2)

    def test_unsupported_urls_withhold_labels(self):
        client = self.fake_client(sources=["https://invented.example/company"])
        row = classify(client, {"NSE_SYMBOL": "ABC", "COMPANY_NAME": "ABC Limited"}, MODEL)
        self.assertEqual(row["STATUS"], "needs_review")
        self.assertEqual(row["INDUSTRY"], "")
        self.assertEqual(json.loads(row["SOURCE_URLS"]), [])

    def test_uncertain_identity_withholds_labels(self):
        row = classify(self.fake_client(confirmed=False),
                       {"NSE_SYMBOL": "ABC", "COMPANY_NAME": "ABC Limited"}, MODEL)
        self.assertEqual(row["SECTOR"], "")
        self.assertEqual(row["STATUS"], "needs_review")

    def test_search_separate_from_structured_extraction(self):
        client = self.fake_client()
        row = classify(client, {"NSE_SYMBOL": "ABC", "COMPANY_NAME": "ABC Limited"}, MODEL)
        self.assertEqual(row["STATUS"], "classified")
        research, extraction = [call.kwargs for call in client.responses.create.call_args_list]
        self.assertEqual(research["tool_choice"], "required")
        self.assertEqual(research["extra_body"]["tools"], [{"type": "browser_search"}])
        self.assertNotIn("text", research)
        self.assertNotIn("tools", extraction)
        self.assertTrue(extraction["text"]["format"]["strict"])
        self.assertNotIn("include", research)
        self.assertNotIn("store", research)

    def test_text_only_sources_require_review(self):
        row = classify(self.fake_client(metadata=False),
                       {"NSE_SYMBOL": "ABC", "COMPANY_NAME": "ABC Limited"}, MODEL)
        self.assertEqual(row["STATUS"], "needs_review")
        self.assertEqual(row["INDUSTRY"], "Example Industry")
        self.assertIn("unverified", row["REASON"])

    def test_incomplete_research_stops_before_extraction(self):
        client = self.fake_client()
        client.responses.create.side_effect = [SimpleNamespace(status="incomplete", output_text="")]
        with self.assertRaises(ValueError):
            classify(client, {"NSE_SYMBOL": "ABC", "COMPANY_NAME": "ABC Limited"}, MODEL)
        self.assertEqual(client.responses.create.call_count, 1)

    def test_dry_run_has_no_output_or_input_changes(self):
        before = self.path.read_bytes()
        output = self.path.with_name("results.csv")
        self.assertEqual(main(["--input", str(self.path), "--output", str(output), "--dry-run"]), 0)
        self.assertFalse(output.exists())
        self.assertEqual(before, self.path.read_bytes())

    def test_rejects_overwriting_input(self):
        with self.assertRaises(SystemExit) as error:
            main(["--input", str(self.path), "--output", str(self.path)])
        self.assertEqual(error.exception.code, 2)

    def test_resume_skips_completed_without_api_key(self):
        output = self.path.with_name("results.csv")
        _, companies = read_companies(self.path)
        rows = [classify(self.fake_client(), company, MODEL) for company in companies]
        save_results(output, rows)
        before = output.read_bytes()
        self.assertEqual(main(["--input", str(self.path), "--output", str(output),
                               "--model", MODEL]), 0)
        self.assertEqual(before, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
