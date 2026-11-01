# NSE Standalone Financial Research - Google Colab

## Company industry and sector agent

A lookup tool retrieves company industry/sector labels, and a Groq evaluator
checks the company identity and evidence before saving the mapping and source URL.
See [setup and run instructions](ai/README.md). AI code is organized into
`ai/agent`, `ai/tools`, and `ai/github`, with tests in `ai/tests`.

Study period: April 1, 2022 to December 31, 2024 (11 quarters).

## Setup

Extract this ZIP before uploading its contents to a GitHub repository.
GitHub's Upload files page does not unpack ZIP archives.
Upload the contents of nse-financial-research, including hidden files.
No repository URL is hardcoded. Open each notebook from Colab's GitHub tab
using your own repository URL, or upload the notebook directly to Colab.

## Current notebook inventory and research workflow (November 2026)

The [notebooks directory](notebooks/) currently contains the following five
Jupyter notebooks. They serve overlapping stages rather than forming a strict
five-step execution sequence.

| Notebook | Research stage | Purpose |
| --- | --- | --- |
| [Download_Selected_NSE_XML_2022_2024.ipynb](notebooks/Download_Selected_NSE_XML_2022_2024.ipynb) | Data acquisition | Download selected NSE financial-result XML files for the 2022–2024 collection period. |
| [Nifty500_End_to_End_2022Q1_2025Q4_Runtime_Manifest.ipynb](notebooks/Nifty500_End_to_End_2022Q1_2025Q4_Runtime_Manifest.ipynb) | End-to-end acquisition and extraction | Download the official Nifty 500 list, construct the 2022Q1–2025Q4 download manifest, download source XBRL, parse financial facts with provenance, build standalone quarterly data and a coverage report, and perform preliminary descriptive analysis. The dates in the notebook name describe its intended workflow; they do not imply that all quarters were obtained. |
| [Nifty500_Statistical_Analysis.ipynb](notebooks/Nifty500_Statistical_Analysis.ipynb) | Earlier combined analytical workflow | Data quality, feature engineering, EDA, sample-size planning, chronological modeling, regression model comparisons, predictive importance, and feature-set comparison. |
| [Nifty500_Statistical_Analysis_With_Tests.ipynb](notebooks/Nifty500_Statistical_Analysis_With_Tests.ipynb) | Earlier combined analytical workflow with tests | Extends the combined analysis with statistical inference, regression diagnostics, and RQ1–RQ4 testing. It overlaps with the separate interim-report notebook below; results should be checked for consistency before reuse. |
| [01_Data_Preparation_and_Statistical_Tests.ipynb](notebooks/01_Data_Preparation_and_Statistical_Tests.ipynb) | Interim-report EDA and statistical inference | Audits/cleans the analysis dataset, builds exact next-quarter PAT-growth targets and engineered features, performs EDA and sample-size planning, runs OLS joint and coefficient tests with clustering/multiple-testing controls, and exports statistical diagnostics and model-handoff data. **This is the statistical notebook referenced in the October 2026 interim report.** |

### Recommended research execution path

1. **Collect and extract NSE data:** Use the end-to-end Nifty 500 notebook as the
   primary acquisition/extraction workflow. The selected-XML download notebook
   is an alternative or complementary collection workflow, *not* an additional
   mandatory step if the source XML is already present.
2. **Prepare the analysis panel and run EDA/statistics:** Run
   `01_Data_Preparation_and_Statistical_Tests.ipynb` using its documented
   analytical input, `Nifty500_Standalone_Quarterly_Available.csv`.
   Its outputs include `statistical_outputs/prepared_company_quarters.csv`
   and `statistical_outputs/handoff_manifest.json`.
3. **Develop and validate prediction models:** Review the existing modeling
   experiments in `Nifty500_Statistical_Analysis.ipynb` and
   `Nifty500_Statistical_Analysis_With_Tests.ipynb`. The interim report
   proposes separating the reproducible predictive work into
   `02_Model_Experiments_and_Performance.ipynb`; **that proposed notebook
   is not currently one of the five files in this directory**.
4. **Write final research findings:** Report the baseline comparison, held-out
   MAE/RMSE/R², feature importance, model comparison (RQ3), and reported-only
   versus engineered-feature comparison (RQ4) only after verifying actual
   execution and chronological, leakage-safe validation.

**Status caveat:** The October 2026 interim report establishes statistical
results only; it explicitly defers forecasting effectiveness, predictive feature
importance, RQ3 model rankings, and RQ4 feature-set benefit. Code present in
earlier combined notebooks is not by itself evidence that a final experiment
was successfully executed or validated.

### Historical setup instructions

The earlier run-order instructions below refer to an older, staged Colab
workflow (`02_extract_financials.ipynb`,
`03_validate_and_review_scope.ipynb`, and
`04_build_research_panel.ipynb`). These filenames are **not among the five
notebooks currently listed** in `notebooks/`; retain the instructions as
historical context, not as the current reproducible run order.

## Legacy Colab run order (historical; see current workflow above)

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
