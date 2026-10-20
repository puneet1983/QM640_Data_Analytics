"""Retrieve company classifications with a lookup tool; use an LLM only to evaluate."""

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from ai.tools.company_data import FIELDS, company_key, read_companies, save_results
from ai.tools.company_lookup import LookupFailure, create_lookup
from ai.tools.settings import load_settings

PROJECT = Path(__file__).resolve().parents[2]


class ClassificationError(ValueError):
    """A controlled diagnostic safe to save without raw server payloads."""


def evaluate_batch(client, records, model, config):
    """Evaluate many records in one request and match decisions by explicit ID."""
    try:
        response = client.chat.completions.create(
            model=model,
            max_completion_tokens=config["llm"]["max_completion_tokens"],
            messages=[
                {"role": "system", "content": config["llm"]["prompt"]},
                {"role": "user", "content": json.dumps({"records": records})},
            ],
            response_format={"type": "json_schema", "json_schema": {
                "name": "company_evaluation", "strict": True,
                "schema": config["llm"]["schema"],
            }},
        )
    except ValueError as error:
        raise ClassificationError("Evaluation: SDK could not parse the response") from error
    if not response.choices or response.choices[0].finish_reason != "stop":
        raise ClassificationError("Evaluation: incomplete response")
    try:
        payload = json.loads(response.choices[0].message.content or "")
    except (ValueError, TypeError) as error:
        raise ClassificationError("Evaluation: invalid JSON response") from error
    if not isinstance(payload, dict) or set(payload) != {"evaluations"} or not isinstance(payload["evaluations"], list):
        raise ClassificationError("Evaluation: invalid batch response")
    expected = {"record_id", "identity_match", "classification_supported", "needs_review", "reason"}
    expected_ids = {record["record_id"] for record in records}
    decisions = {}
    for decision in payload["evaluations"]:
        if not isinstance(decision, dict) or set(decision) != expected:
            raise ClassificationError("Evaluation: invalid decision fields")
        record_id = decision["record_id"]
        if not isinstance(record_id, str) or record_id not in expected_ids or record_id in decisions:
            raise ClassificationError("Evaluation: unknown or duplicate record ID")
        if any(type(decision[key]) is not bool for key in expected - {"reason", "record_id"}):
            raise ClassificationError("Evaluation: invalid decision flags")
        if not isinstance(decision["reason"], str):
            raise ClassificationError("Evaluation: invalid explanation")
        decisions[record_id] = decision
    if set(decisions) != expected_ids:
        raise ClassificationError("Evaluation: missing record IDs; no batch decisions accepted")
    return decisions


def empty_row(company, model, config):
    return {**company, "INDUSTRY": "", "SECTOR": "", "TAXONOMY": "",
           "STATUS": "needs_review", "SOURCE_URLS": "[]", "REASON": "Missing symbol or company name",
           "CLASSIFIED_AT_UTC": datetime.now(timezone.utc).isoformat(),
           "MODEL": model, "AGENT_VERSION": config["cache_version"]}


def classify_batch(client, lookup, companies, model, config):
    rows = [empty_row(company, model, config) for company in companies]
    records = []
    for index, (company, row) in enumerate(zip(companies, rows)):
        if not all(company.values()):
            continue
        candidate = lookup.search(company)
        row.update(TAXONOMY=candidate["taxonomy"],
                   SOURCE_URLS=json.dumps([candidate["source_url"]] if candidate["source_url"] else []))
        source_symbol = candidate.get("symbol", "").upper()
        name_only = not source_symbol and config["lookup"].get("allow_name_only_match", False)
        if source_symbol != company["NSE_SYMBOL"].strip().upper() and not name_only:
            row["REASON"] = "Lookup: source symbol is missing or differs from requested symbol"
            continue
        missing = [key for key in ("company_name", "industry", "sector") if not candidate.get(key)]
        partial_allowed = (config["lookup"].get("allow_partial", False)
                           and candidate.get("company_name")
                           and (candidate.get("industry") or candidate.get("sector")))
        if missing and not partial_allowed:
            row["REASON"] = "Lookup: missing source fields: " + ", ".join(missing)
            continue
        records.append({"record_id": str(index), "requested_company": company, "source_record": candidate})
    if not records:
        return rows
    decisions = evaluate_batch(client, records, model, config)
    for record in records:
        decision = decisions[record["record_id"]]
        row = rows[int(record["record_id"])]
        candidate = record["source_record"]
        # Only retrieval supplies labels; batch output cannot replace them.
        if decision["identity_match"] and decision["classification_supported"]:
            row.update(INDUSTRY=candidate["industry"], SECTOR=candidate["sector"])
            if (not decision["needs_review"] and candidate.get("industry") and candidate.get("sector")
                    and not candidate.get("identity_requires_review") and candidate.get("symbol")):
                row["STATUS"] = "classified"
        row["REASON"] = decision["reason"]
        missing = [key for key in ("industry", "sector") if not candidate.get(key)]
        if missing:
            row["REASON"] += " Source lacks: " + ", ".join(missing) + "."
        if not candidate.get("symbol"):
            row["REASON"] += " Source ticker not confirmed; name-only match requires review."
    return rows


def classify(client, lookup, company, model, config):
    """Convenience wrapper for evaluating a single company."""
    return classify_batch(client, lookup, [company], model, config)[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT / "ai/config.json")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--batch-size", type=int, help="Companies per Groq evaluation request")
    parser.add_argument("--limit", type=int, help="Maximum new company lookups this run")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retry-review", action="store_true")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.batch_size is not None and args.batch_size < 1:
        parser.error("--batch-size must be positive")
    try:
        config = load_settings(args.config)
        batch_size = args.batch_size or config["llm"]["batch_size"]
        input_path = args.input or PROJECT / config["input"]
        output_path = args.output or PROJECT / config["output"]
        if input_path.resolve() == output_path.resolve():
            parser.error("Output must differ from the input CSV")
        model = args.model or os.getenv(config["llm"]["model_env"]) or config["llm"]["model"]
        row_count, companies = read_companies(input_path)
        results = {}
        if output_path.exists():
            with output_path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != FIELDS:
                    raise ValueError("Existing output has an incompatible schema; choose a new --output")
                results = {company_key(row): row for row in reader}
        def completed(company):
            previous = results.get(company_key(company), {})
            statuses = ("classified",) if args.retry_review else ("classified", "needs_review")
            return (previous.get("STATUS") in statuses and previous.get("MODEL") == model
                    and previous.get("AGENT_VERSION") == config["cache_version"])
        pending = [company for company in companies if not completed(company)]
        selected = pending[:args.limit] if args.limit else pending
        print(f"Input rows: {row_count}; unique companies: {len(companies)}; "
              f"pending: {len(pending)}; this run: {len(selected)}", flush=True)
        batches = (len(selected) + batch_size - 1) // batch_size
        print(f"Batch size: {batch_size}; Groq requests: at most {batches}, excluding SDK retries", flush=True)
        if args.dry_run or not selected:
            return 0
        api_key = next((os.getenv(name) for name in config["llm"]["api_key_env"] if os.getenv(name)), None)
        if not api_key:
            parser.error("Set an API key environment variable listed in config.llm.api_key_env")
        from openai import OpenAI, APIError
        client = OpenAI(api_key=api_key, base_url=config["llm"]["base_url"],
                        timeout=config["llm"]["timeout_seconds"], max_retries=config["llm"]["max_retries"])
        lookup = create_lookup(config["lookup"])
        for offset in range(0, len(selected), batch_size):
            group = selected[offset:offset + batch_size]
            print(f"[Batch {offset // batch_size + 1}/{batches}] Retrieving {len(group)} companies", flush=True)
            try:
                rows = classify_batch(client, lookup, group, model, config)
            except (APIError, ValueError, KeyError, TypeError) as error:
                detail = str(error) if isinstance(error, (ClassificationError, LookupFailure)) else type(error).__name__
                print(f"Batch failed: {detail}", flush=True)
                for company in group:
                    row = empty_row(company, model, config)
                    row.update(STATUS="error", REASON="Batch failed; retry required: " + detail)
                    results[company_key(company)] = row
                save_results(output_path, results.values())
                # No automatic splitting into individual calls: avoid surprise costs.
                return 1
            for row in rows:
                results[company_key(row)] = row
            save_results(output_path, results.values())
        print(f"Saved: {output_path}")
        return 0
    except ImportError:
        parser.error("Install dependencies: pip install -r requirements.txt")
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
