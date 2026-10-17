# Company industry and sector mapping

The lookup tool retrieves structured company data. Groq only evaluates whether
that record matches the input company and contains a usable classification.
The LLM cannot generate or replace industry/sector labels. Accepted labels are
copied exactly from the lookup response; missing or rejected evidence leaves them
blank with `needs_review`. Partial records can retain an industry with a blank
sector and always require review. Review decisions are not independent verification of
source accuracy or historical applicability.

Groq evaluates groups of companies in one request (default: 10). Source lookups
still happen per symbol. With 1,142 eligible companies and a batch size of 10,
there are at most 115 Groq requests before SDK retries, rather than 1,142. Batching
shares the prompt overhead; token usage still grows with company count, so fewer
requests do not imply a proportional reduction in token charges.

## Structure

- `agent/classify_companies.py`: orchestrates retrieval, evaluation and CSV output.
- `tools/company_lookup.py`: configurable HTTP JSON company search by symbol.
- `tools/wikipedia_lookup.py`: Wikipedia search and literal infobox extraction.
- `tools/web_search_lookup.py`: DDGS search and extraction of labelled web fields.
- `tools/fallback_lookup.py`: ordered fallback and selection of one source record.
- `tools/company_data.py`: CSV input, normalization, deduplication and checkpoints.
- `config.json`: paths, endpoint, JSON field mappings, model and environment names.
- `prompts/evaluate_company.txt`: evaluation instructions.
- `schemas/evaluation.json`: boolean decisions and reason; no classification labels.
- `tests/`: offline contracts with mocked lookup and LLM responses.
- `github/`: reserved GitHub resources; no workflow is enabled.

## Configuration

Edit `ai/config.json`. `lookup.provider` defaults to `fallback`, trying DDGS
DuckDuckGo, DDGS Bing, and Wikipedia in the configured `lookup.providers` order.
DDGS is an open-source metasearch library; no extra search API key is needed.
Search engines and websites may still block or rate-limit requests. An individual
tool failure falls through to the next tool. If all tools fail, the run stops.

The selector prefers source-confirmed matching tickers, then more complete labels.
It stops at a complete ticker-matched record. It never combines labels from
different pages. Generic web classifications are marked as unharmonized and
always require review. `lookup.web_search` controls queries, result limits, HTML
field labels and optional CSS `value_selectors`. Table and definition-list fields
are extracted literally; snippets and prose are not converted into classifications.
Pages requiring JavaScript or lacking labelled fields may yield no usable record.

To use Wikipedia alone, set `lookup.provider` to `wikipedia`. It searches
English Wikipedia by company name and reads explicit infobox fields. No extra
search API key is required. Search and HTML endpoints, query template, result
limit, headers, infobox selector, field labels and ticker pattern are configurable
under `lookup.wikipedia`. Set an identifying User-Agent and contact in its headers
for your deployment. Wikipedia access has not been verified live in this session.

Wikipedia classifications are recorded as `Wikipedia infobox`, not NSE labels.
Many pages expose industry but no sector. With `lookup.allow_partial` enabled,
the evaluator checks available evidence; missing fields stay blank and force
`needs_review`. If no NSE ticker is found, `allow_name_only_match` permits name
evaluation but also forces review. Explicitly mismatched tickers are rejected.
Values are never guessed or copied between industry and sector.

Google's official Custom Search JSON API is closed to new customers. DDGS also
documents a `google` backend, which is a separate third-party search path whose
availability is not guaranteed. The default pipeline uses DuckDuckGo, Bing and
Wikipedia. See [DDGS backends](https://github.com/deedy5/ddgs) and
[Google's service notice](https://developers.google.com/custom-search/v1/overview).

To use the previous NSE lookup, set `lookup.provider` to `http_json` and disable
`allow_partial` and `allow_name_only_match` for strict matching. Its endpoint is:
`https://www.nseindia.com/api/quote-equity?symbol=...`.
The configured JSON paths are `info.symbol`, `info.companyName`,
`industryInfo.industry` and `industryInfo.sector`. The endpoint and payload schema
have not been verified live in this session. This is a website endpoint, not a
promised stable data service: access can be blocked or the payload can change.
Failures are reported explicitly and stop the run; no labels are inferred as a
fallback. Missing mapped fields are reported for review and do not invoke the LLM.
Adjust the endpoint and field paths if using a different structured data service.

Sector and industry remain separate levels; basic industry is not substituted.
The configured tool retrieves a source record; the LLM evaluates its company name against
both input symbol and company name. There are no built-in company classifications
or industry name mappings.

The LLM defaults to Groq-hosted `openai/gpt-oss-120b`. `llm.base_url`, `llm.model`,
key environment names, timeout and retries are configurable. The `openai` Python
package is used as an API-compatible client; it sends requests to the configured
Groq endpoint. The key is read from `GROQ_API_KEY` or `Groq_api_key`, never from a
source file. `.env` files are not loaded automatically.

## Run from nse-financial-research

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$key = Read-Host 'Groq API key' -AsSecureString
$env:GROQ_API_KEY = [System.Net.NetworkCredential]::new('', $key).Password
.\.venv\Scripts\python.exe -m ai.agent.classify_companies --dry-run
.\.venv\Scripts\python.exe -m ai.agent.classify_companies --limit 1
.\.venv\Scripts\python.exe -m ai.agent.classify_companies --batch-size 10 --limit 20
```

Pass another CSV with `--input 'path\input.csv'`. It must contain `NSE_SYMBOL` and
`COMPANY_NAME`. Override the destination with `--output 'path\mapping.csv'`.
Use `--config 'path\config.json'` for another configuration; prompt/schema paths
are relative to that file. Default input/output paths in config are relative to
the project. Relative CLI input/output overrides use your working directory.
`--model MODEL` or `GROQ_MODEL` overrides the configured model; it must support
strict structured output through Chat Completions.

`--batch-size` overrides `llm.batch_size`. `--limit` still limits companies, not
batches. Dry-run prints an upper bound on Groq request count. Set
`llm.max_completion_tokens` to control the output token budget per request.
If a larger batch exceeds the model's context or output budget, reduce its size.
SDK retries remain bounded by `llm.max_retries`. Missing, duplicate or unexpected
record IDs reject the entire batch, and reordered results are matched by ID.
Failed batches stop and are checkpointed for retry; the agent does not silently
split them into extra paid requests.

Output defaults to `output/company_classification/company_industry_mapping.csv`.
It includes labels, source URL, taxonomy, review status, explanation, UTC timestamp,
model and configuration fingerprint. One record is created per normalized
symbol/name pair. The financial input is never modified. Source classifications
are current at lookup time, not necessarily historical classifications.

A run checkpoints after each batch. Repeat without `--limit` to process all
remaining companies. Completed/review records skip when model and configuration
fingerprint match; errors retry. `--retry-review` retries review records too.
Classification configuration/prompt/schema changes invalidate the checkpoint
fingerprint, so previous pipeline versions are reprocessed. Changing only batch
size, output token budget, timeout or retry count preserves completed records.
Do not run two processes against one output.
Stop any previous process before rerunning edited code. No live retrieval or LLM
accuracy has been verified by the offline tests.

## Offline tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s ai/tests -p 'test_classify_companies.py' -v
```

References: [NSE classification](https://www.nseindia.com/static/products-services/industry-classification)
and [Groq structured output](https://console.groq.com/docs/structured-outputs).
