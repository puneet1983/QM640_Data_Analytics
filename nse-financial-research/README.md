# NSE Standalone Financial Research - Google Colab

## Company industry and sector agent

A local Groq agent reads company symbols and names from the extracted CSV and
creates a separate industry/sector mapping with web source links and review flags.
See [setup and run instructions](ai/README.md). AI code is organized into
`ai/agent`, `ai/tools`, and `ai/github`, with tests in `ai/tests`.

Study period: April 1, 2022 to December 31, 2024 (11 quarters).

## Setup

Extract this ZIP before uploading its contents to a GitHub repository.
GitHub's Upload files page does not unpack ZIP archives.
Upload the contents of nse-financial-research, including hidden files.
No repository URL is hardcoded. Open each notebook from Colab's GitHub tab
using your own repository URL, or upload the notebook directly to Colab.

## Run order

1. notebooks/Download_Selected_NSE_XML_2022_2024.ipynb:
   upload data/manifests/download_manifest.csv when prompted. XML files
   are saved under /content/drive/MyDrive/nse_xml_2022_2024.
   Skip downloading if this folder already contains your downloaded files.
2. notebooks/02_extract_financials.ipynb:
   reads that XML folder and saves extraction tables to
   /content/drive/MyDrive/nse-financial-research/data/interim.
3. notebooks/03_validate_and_review_scope.ipynb:
   reads the extracted quarterly CSV and saves quality reports to
   /content/drive/MyDrive/nse-financial-research/outputs/quality.
4. notebooks/04_build_research_panel.ipynb:
   saves available-quarter and complete-quarter standalone datasets to
   /content/drive/MyDrive/nse-financial-research/data/processed.

Allow Google Drive access when Colab prompts. Run notebooks in order.
Notebook settings are the operational configuration. configs/pipeline.yaml
documents matching defaults; the notebooks do not load it automatically.

## Existing data

To reuse your existing company_quarterly_financials_extracted.csv, put it in
the Drive data/interim folder above and start at notebook 03.
The current manifest is copied from the existing screened download manifest.
Its download coverage can be broader than the study window; extraction and
panel selection apply the study dates. Retain the original manifest unchanged.

## Research scope

The complete sample size is computed each run, never fixed at 707.
Missing quarters are not filled with zeros. Conflicting company-quarter rows
must be reviewed before panel construction. Complete coverage is not proof
of correct financial mapping or a sufficient statistical research design.
Original units and source evidence remain in extraction outputs.
Sector mapping, hypothesis-specific variables, statistical models, and
paper tables remain future work; this archive does not pretend to implement them.

## Repository and Drive storage

The repository stores notebooks, code, configuration, and documentation.
Drive stores large XML files, extraction outputs, and research datasets.
The .gitkeep files preserve empty folders in GitHub. Do not commit bulk data,
credentials, or notebook execution outputs. No XML files are bundled here.
