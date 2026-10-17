# Company industry and sector agent

## Folder structure

```text
ai/
  agent/             Groq company classification agent
  tools/             CSV reading, company deduplication and checkpoints
  github/            GitHub templates and automation resources
  tests/             Offline agent tests
  requirements.txt   AI dependencies
  README.md          Setup and usage
```

This local Python agent reads `NSE_SYMBOL` and `COMPANY_NAME` from the extracted
financial CSV. It uses Groq's Responses API with required browser search, followed
by a separate structured JSON extraction request. Groq does not support browser
search and structured outputs in the same request. Only symbol and name are
submitted from your data, not the financial rows.
The source CSV is never modified.

## Run in PowerShell

Use Python 3.10 or later. From the workspace root:

```powershell
cd nse-financial-research
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# No credentials, API calls, or output writes are needed for a dry run.
.\.venv\Scripts\python.exe -m ai.agent.classify_companies --dry-run

# Read the key without echoing it or placing its value in command history.
$key = Read-Host 'Groq API key' -AsSecureString
$env:GROQ_API_KEY = [System.Net.NetworkCredential]::new('', $key).Password

# First inspect a small sample. API model and search usage incur charges.
.\.venv\Scripts\python.exe -m ai.agent.classify_companies --limit 5

# Resume and classify remaining companies.
.\.venv\Scripts\python.exe -m ai.agent.classify_companies
```

A Groq API key with model and browser-search access is required. The default model
is `openai/gpt-oss-120b`; use `--model openai/gpt-oss-20b` for the smaller supported
model, or set `GROQ_MODEL` to either model ID. Each company needs two API requests
(research and extraction), plus any SDK retries and browser tool usage.

The `openai` Python package remains as the OpenAI-compatible client library.
All requests use `https://api.groq.com/openai/v1` with your Groq key; an OpenAI key
is not used. The model's `openai/` prefix identifies GPT-OSS hosted by Groq.
`Groq_api_key` is also accepted as an environment variable alias for `GROQ_API_KEY`.
`.env` files are not loaded; set variables in the shell. Do not put credentials
in source files. Existing version-1 OpenAI classifications are reprocessed when
encountered because this agent uses version `2-groq`.

## Input, results, and resuming

Paths default to the project directory, regardless of your working directory:

- Input: `output/final_extracted_data/company_quarterly_financials_extracted.csv`.
- Output: `output/company_classification/company_industry_mapping.csv`.
- Override paths with `--input PATH --output PATH`.

The output has one record per normalized symbol/name pair, with `INDUSTRY`,
`SECTOR`, `TAXONOMY`, `STATUS`, `REASON`, `SOURCE_URLS` (a JSON array), UTC timestamp,
model, and agent version. Join it back to financial rows using both symbol and
name, normalizing symbol case and company name whitespace/case as the agent does.
Different names for the same symbol remain separate identities to avoid silently
merging renamed or mismatched companies.

The agent prefers exact NSE labels, then BSE. Business-description classifications
are explicitly marked and require review. Taxonomies can differ: review and
harmonize labels before using them for sector comparisons. `classified` means the
agent reported sufficient evidence and its cited URLs appeared in tool metadata;
it is not independent verification that those sources support the labels.
Missing identity or source evidence leaves labels blank. Classifications describe
the lookup date, not necessarily the historical financial reporting period.

When Groq exposes links only in generated research text, those links and labels
are retained but the record is always `needs_review`, with an explicit provenance
note in `REASON`. These are model-reported links, not independently verified tool
citations. Extraction cannot add URLs absent from the research response.

Results checkpoint after each company. Repeat the same command to skip completed
and review records for the same model/version. Error records retry automatically;
`--retry-review` also retries uncertain records. `--limit` caps new lookups per
run, including review retries. Use a new output path to deliberately refresh all
classifications. Do not run concurrent processes against the same output file.
Existing output rows remain in the checkpoint even when absent from a new input.

API authentication, quota, model and network failures stop the run after saving
the checkpoint. Other per-company failures receive `error` status. No key or
server error payload is written to output. Generated results are Git-ignored.

## Offline verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s ai/tests -p 'test_classify_companies.py' -v
```

These tests use mock responses to check deduplication, URL provenance handling,
uncertain identities, dry-run behavior, input protection, and resume behavior.
They do not measure model accuracy. Before a full run, manually review the
five-company sample against its cited sources, including an ambiguous identity.

API references: [Groq Responses API](https://console.groq.com/docs/responses-api),
[browser search](https://console.groq.com/docs/tool-use/built-in-tools/browser-search),
and [structured outputs](https://console.groq.com/docs/structured-outputs).
