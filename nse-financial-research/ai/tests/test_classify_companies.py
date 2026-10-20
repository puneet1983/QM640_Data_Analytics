"""Offline retrieval and evaluation contracts; no live API calls."""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai.agent.classify_companies import ClassificationError, classify, classify_batch, main
from ai.tools.company_data import read_companies, save_results
from ai.tools.company_lookup import CompanyLookup, LookupFailure
from ai.tools.settings import load_settings

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"


class CompanyAgentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "input.csv"
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows([
                ["NSE_SYMBOL", "COMPANY_NAME"], ["ABC", "ABC Limited"],
                [" abc ", " ABC  LIMITED "], ["ABC", "Different Legal Entity"],
            ])
        self.config = load_settings(CONFIG_PATH)
        self.config["lookup"]["allow_partial"] = False
        self.config["lookup"]["allow_name_only_match"] = False
        self.model = self.config["llm"]["model"]
        self.company = {"NSE_SYMBOL": "ABC", "COMPANY_NAME": "ABC Limited"}
        self.candidate = {"symbol": "ABC", "company_name": "ABC Limited",
                          "industry": "Source Industry", "sector": "Source Sector",
                          "taxonomy": "NSE", "source_url": "https://source.example/api?symbol=ABC"}
        self.lookup = Mock()
        self.lookup.search.return_value = self.candidate

    def client(self, **overrides):
        result = {"record_id": "0", "identity_match": True, "classification_supported": True,
                  "needs_review": False, "reason": "Fixture record matches"}
        result.update(overrides)
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content=json.dumps({"evaluations": [result]})))])
        return client

    def classify(self, client=None):
        return classify(client or self.client(), self.lookup, self.company, self.model, self.config)

    def test_source_labels_are_copied_exactly(self):
        self.candidate["industry"] = "An arbitrary source label"
        row = self.classify()
        self.assertEqual(row["INDUSTRY"], self.candidate["industry"])
        self.assertEqual(row["SECTOR"], self.candidate["sector"])
        self.assertEqual(row["STATUS"], "classified")

    def test_llm_cannot_replace_industry(self):
        with self.assertRaisesRegex(ClassificationError, "invalid decision fields"):
            self.classify(self.client(industry="Invented Industry"))

    def test_wrong_source_symbol_skips_llm(self):
        self.candidate["symbol"] = "OTHER"
        client = self.client()
        row = self.classify(client)
        self.assertEqual(row["INDUSTRY"], "")
        self.assertEqual(row["STATUS"], "needs_review")
        client.chat.completions.create.assert_not_called()

    def test_missing_source_sector_skips_llm(self):
        self.candidate["sector"] = ""
        client = self.client()
        row = self.classify(client)
        self.assertIn("sector", row["REASON"])
        client.chat.completions.create.assert_not_called()

    def test_rejected_identity_withholds_labels(self):
        row = self.classify(self.client(identity_match=False))
        self.assertEqual(row["INDUSTRY"], "")
        self.assertEqual(row["STATUS"], "needs_review")

    def test_partial_source_keeps_industry_and_requires_review(self):
        self.config["lookup"]["allow_partial"] = True
        self.candidate["sector"] = ""
        row = self.classify()
        self.assertEqual(row["INDUSTRY"], self.candidate["industry"])
        self.assertEqual(row["SECTOR"], "")
        self.assertEqual(row["STATUS"], "needs_review")

    def test_name_only_source_cannot_be_classified_without_review(self):
        self.config["lookup"]["allow_name_only_match"] = True
        self.candidate["symbol"] = ""
        row = self.classify()
        self.assertEqual(row["STATUS"], "needs_review")
        self.assertIn("name-only", row["REASON"])

    def test_wikipedia_extracts_industry_without_inventing_sector(self):
        from ai.tools.wikipedia_lookup import WikipediaLookup
        lookup = WikipediaLookup(self.config["lookup"], Mock())
        html = '''<table class="infobox"><tr><th>Industry</th><td>Banking<sup>[1]</sup></td></tr>
                  <tr><th>Traded as</th><td>NSE: ABC</td></tr></table>'''
        record = lookup.parse_page(html, "ABC Limited", "https://en.wikipedia.org/wiki/ABC")
        self.assertEqual(record["industry"], "Banking")
        self.assertEqual(record["sector"], "")
        self.assertEqual(record["symbol"], "ABC")
        self.assertEqual(record["taxonomy"], "Wikipedia infobox")

    def test_wikipedia_does_not_copy_input_ticker_to_missing_source(self):
        from ai.tools.wikipedia_lookup import WikipediaLookup
        lookup = WikipediaLookup(self.config["lookup"], Mock())
        record = lookup.parse_page('<table class="infobox"><tr><th>Industry</th><td>Banking</td></tr></table>',
                                   "ABC Limited", "https://en.wikipedia.org/wiki/ABC")
        self.assertEqual(record["symbol"], "")
        self.assertTrue(record["identity_requires_review"])

    def test_review_keeps_source_labels(self):
        row = self.classify(self.client(needs_review=True))
        self.assertEqual(row["INDUSTRY"], self.candidate["industry"])
        self.assertEqual(row["STATUS"], "needs_review")

    def test_evaluation_does_not_request_search(self):
        client = self.client()
        self.classify(client)
        call = client.chat.completions.create.call_args.kwargs
        self.assertNotIn("tools", call)
        self.assertEqual(call["messages"][0]["content"], self.config["llm"]["prompt"])

    def test_invalid_json_gets_useful_error(self):
        client = self.client()
        client.chat.completions.create.return_value.choices[0].message.content = "not JSON"
        with self.assertRaisesRegex(ClassificationError, "invalid JSON"):
            self.classify(client)

    def batch_client(self, decisions):
        client = self.client()
        client.chat.completions.create.return_value.choices[0].message.content = json.dumps({"evaluations": decisions})
        return client

    def decision(self, record_id, **overrides):
        return {"record_id": record_id, "identity_match": True,
                "classification_supported": True, "needs_review": False,
                "reason": "Fixture evaluation", **overrides}

    def test_batch_calls_llm_once_and_handles_reordered_results(self):
        other = {"NSE_SYMBOL": "XYZ", "COMPANY_NAME": "XYZ Limited"}
        self.lookup.search.side_effect = [self.candidate,
            {**self.candidate, "symbol": "XYZ", "company_name": "XYZ Limited", "industry": "Other Industry"}]
        client = self.batch_client([self.decision("1", identity_match=False), self.decision("0")])
        rows = classify_batch(client, self.lookup, [self.company, other], self.model, self.config)
        client.chat.completions.create.assert_called_once()
        self.assertEqual(rows[0]["INDUSTRY"], self.candidate["industry"])
        self.assertEqual(rows[1]["INDUSTRY"], "")
        self.assertEqual(rows[1]["STATUS"], "needs_review")

    def test_missing_batch_id_rejects_entire_response(self):
        client = self.batch_client([])
        with self.assertRaisesRegex(ClassificationError, "missing record IDs"):
            self.classify(client)

    def test_duplicate_batch_id_rejected(self):
        client = self.batch_client([self.decision("0"), self.decision("0")])
        with self.assertRaisesRegex(ClassificationError, "duplicate record ID"):
            self.classify(client)

    def test_unknown_batch_id_rejected(self):
        with self.assertRaisesRegex(ClassificationError, "unknown or duplicate"):
            self.classify(self.batch_client([self.decision("unrequested")]))

    def test_invalid_candidates_do_not_use_llm(self):
        self.candidate["sector"] = ""
        client = self.client()
        classify_batch(client, self.lookup, [self.company, self.company], self.model, self.config)
        client.chat.completions.create.assert_not_called()

    def test_nonpositive_batch_size_rejected(self):
        with self.assertRaises(SystemExit) as error:
            main(["--batch-size", "0", "--dry-run"])
        self.assertEqual(error.exception.code, 2)

    def test_batch_size_changes_keep_checkpoint_valid(self):
        custom = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        custom["llm"]["batch_size"] += 1
        for field in ("prompt_file", "schema_file"):
            custom["llm"][field] = str(CONFIG_PATH.parent / custom["llm"][field])
        custom_path = self.path.with_name("config.json")
        custom_path.write_text(json.dumps(custom), encoding="utf-8")
        # Use the same absolute resource paths in both configurations.
        alternate = load_settings(custom_path)
        custom["llm"]["batch_size"] -= 1
        custom_path.write_text(json.dumps(custom), encoding="utf-8")
        baseline = load_settings(custom_path)
        self.assertEqual(alternate["cache_version"], baseline["cache_version"])

    def test_lookup_encodes_symbols_and_reads_configured_fields(self):
        settings = {**self.config["lookup"], "session_url": "", "delay_seconds": 0,
                    "fields": {"symbol": "company.code", "company_name": "company.name",
                               "industry": "labels.i", "sector": "labels.s"}}
        session = Mock()
        session.get.return_value = Mock(status_code=200)
        session.get.return_value.json.return_value = {
            "company": {"code": "A&B", "name": "Fixture"},
            "labels": {"i": "Fetched I", "s": "Fetched S"}}
        record = CompanyLookup(settings, session).search({"NSE_SYMBOL": "A&B"})
        self.assertEqual(record["industry"], "Fetched I")
        self.assertIn("symbol=A%26B", session.get.call_args.args[0])

    def test_lookup_block_is_explicit(self):
        session = Mock()
        session.get.return_value = Mock(status_code=403)
        with self.assertRaisesRegex(LookupFailure, "HTTP 403"):
            CompanyLookup(self.config["lookup"], session).search(self.company)

    def test_fallback_continues_after_a_tool_fails(self):
        from ai.tools.fallback_lookup import FallbackLookup
        blocked, working = Mock(), Mock()
        blocked.search.side_effect = LookupFailure("source unavailable")
        working.search.return_value = self.candidate
        result = FallbackLookup([("blocked", blocked), ("working", working)]).search(self.company)
        self.assertEqual(result, self.candidate)
        working.search.assert_called_once_with(self.company)

    def test_fallback_does_not_merge_labels_across_sources(self):
        from ai.tools.fallback_lookup import FallbackLookup
        first, second = Mock(), Mock()
        first.search.return_value = {**self.candidate, "sector": "", "source_url": "https://first.example"}
        second.search.return_value = {**self.candidate, "industry": "", "source_url": "https://second.example"}
        result = FallbackLookup([("first", first), ("second", second)]).search(self.company)
        self.assertEqual(result["sector"], "")
        self.assertEqual(result["source_url"], "https://first.example")

    def test_fallback_skips_wrong_source_symbol(self):
        from ai.tools.fallback_lookup import FallbackLookup
        wrong, right = Mock(), Mock()
        wrong.search.return_value = {**self.candidate, "symbol": "OTHER"}
        right.search.return_value = self.candidate
        result = FallbackLookup([("wrong", wrong), ("right", right)]).search(self.company)
        self.assertEqual(result["symbol"], self.company["NSE_SYMBOL"])

    def test_web_parser_extracts_only_explicit_source_labels(self):
        from ai.tools.web_search_lookup import WebSearchLookup
        config = {**self.config["lookup"], "backend": "duckduckgo"}
        lookup = WebSearchLookup(config, Mock())
        html = '''<h1>ABC Limited (NSE: ABC)</h1><table>
                  <tr><td>Industry</td><td>Retrieved Industry</td></tr>
                  <tr><td>Sector</td><td>Retrieved Sector</td></tr></table>'''
        result = lookup.parse_page(html, "https://source.example/profile")
        self.assertEqual(result["industry"], "Retrieved Industry")
        self.assertEqual(result["sector"], "Retrieved Sector")
        self.assertEqual(result["symbol"], "ABC")
        self.assertTrue(result["identity_requires_review"])

    def test_web_parser_does_not_infer_labels_from_prose(self):
        from ai.tools.web_search_lookup import WebSearchLookup
        config = {**self.config["lookup"], "backend": "bing"}
        result = WebSearchLookup(config, Mock()).parse_page(
            "<h1>ABC Limited</h1><p>A large banking company.</p>", "https://source.example")
        self.assertEqual(result["industry"], "")
        self.assertEqual(result["sector"], "")

    def test_deduplication_preserves_distinct_names(self):
        count, companies = read_companies(self.path)
        self.assertEqual((count, len(companies)), (3, 2))

    def test_dry_run_does_not_write(self):
        output = self.path.with_name("mapping.csv")
        self.assertEqual(main(["--input", str(self.path), "--output", str(output), "--dry-run"]), 0)
        self.assertFalse(output.exists())

    def test_rejects_input_overwrite(self):
        with self.assertRaises(SystemExit) as error:
            main(["--input", str(self.path), "--output", str(self.path)])
        self.assertEqual(error.exception.code, 2)

    def test_resume_skips_completed_records(self):
        output = self.path.with_name("mapping.csv")
        _, companies = read_companies(self.path)
        rows = []
        for company in companies:
            rows.append({**self.classify(), **company})
        save_results(output, rows)
        self.assertEqual(main(["--input", str(self.path), "--output", str(output),
                               "--model", self.model]), 0)


if __name__ == "__main__":
    unittest.main()
