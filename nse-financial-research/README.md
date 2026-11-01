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

## Official research workflow — data acquisition + three analytical notebooks (November 2026)

This workflow separates **statistical investigation**, **development-stage model selection**, and **frozen final predictive evaluation**. Data acquisition remains upstream. The three analytical notebooks must be executed **01 → 02 → 03** against the **same source extract**.

### Notebook inventory

| Notebook | Role | Main outputs |
| --- | --- | --- |
| [Download_Selected_NSE_XML_2022_2024.ipynb](notebooks/Download_Selected_NSE_XML_2022_2024.ipynb) | Selected NSE XML download workflow; supplementary or alternate collection route. | Source XML files. |
| [Nifty500_End_to_End_2022Q1_2025Q4_Runtime_Manifest.ipynb](notebooks/Nifty500_End_to_End_2022Q1_2025Q4_Runtime_Manifest.ipynb) | Main Nifty 500 acquisition, manifest generation, XBRL parsing, provenance and quarterly panel construction. The name's 2022Q1–2025Q4 range is intended acquisition scope, **not verified analytical coverage**. | XML, manifest and standardized financial panel outputs. |
| **[01_Data_Preparation_and_Statistical_Tests.ipynb](notebooks/01_Data_Preparation_and_Statistical_Tests.ipynb)** | **EDA, statistical inference and preliminary RQ1–RQ4 assessment**: quality checks, exact next-quarter PAT growth, descriptive diagnostics, sample-size planning, RQ1 joint associations, RQ2 coefficient tests, RQ3 temporal suitability diagnostics, RQ4 nested engineered-feature OLS test with company-clustered uncertainty. **No predictive model ranking or holdout feature-gain claim**. | `statistical_outputs/prepared_company_quarters.csv`, `statistical_outputs/handoff_manifest.json`, `statistical_outputs/statistical_tests/` (including RQ1–RQ4 statistical results). |
| **[02_Model_Training_and_Validation.ipynb](notebooks/02_Model_Training_and_Validation.ipynb)** | **Leakage-aware model training, tuning and validation**: historical median baseline, Linear Regression, Ridge, Random Forest, Gradient Boosting. All selection uses training/validation periods only; held-out test targets are not used in optimization. | `model_outputs/validation_trials.csv`, `validation_predictions.csv`, `selection_manifest.json`, fitted training-stage pipelines. |
| **[03_Final_Model_Evaluation_and_Research_Questions.ipynb](notebooks/03_Final_Model_Evaluation_and_Research_Questions.ipynb)** | **Frozen final RQ1–RQ4 evidence**: refit validation-selected candidates on train+validation; one-time final holdout scoring; baseline comparison (RQ1), permutation importance (RQ2), preselected candidate comparison (RQ3), matched algorithm feature-set comparison (RQ4), exploratory company-block intervals and reporting tables. Never retune using test results. | `final_evaluation_outputs/heldout_model_metrics.csv`, `heldout_predictions.csv`, `RQ1_baseline_comparison.csv`, `RQ2_permutation_importance.csv`, `RQ3_model_comparison.csv`, `RQ4_feature_set_comparison.csv`, `RQ_final_evidence_summary.csv`. |
| [Nifty500_Statistical_Analysis.ipynb](notebooks/Nifty500_Statistical_Analysis.ipynb) | **Legacy combined** EDA/ML workflow; implementation reference, not the canonical final run order. | Legacy outputs; do not combine with canonical results without cross-checks. |
| [Nifty500_Statistical_Analysis_With_Tests.ipynb](notebooks/Nifty500_Statistical_Analysis_With_Tests.ipynb) | **Legacy combined** ML + statistical-tests workflow; use only to cross-check or recover earlier experiments. | Legacy outputs; do not cite as current authoritative evidence without fresh execution. |

### Canonical inputs, dependencies and execution

1. Acquire and standardize financial filings using the upstream data-collection notebooks. The canonical analytical input for this study is **`Nifty500_Standalone_Quarterly_Available.csv`**. The interim report's observed extract contains 3,824 records for 426 companies covering reporting quarter ends June 2022–December 2024. Later downloads do **not** automatically extend that observed sample.
2. **Notebook 01:** In Google Colab, upload the input to `/content/Nifty500_Standalone_Quarterly_Available.csv`, or place it at `outputs/nifty500_analysis/Nifty500_Standalone_Quarterly_Available.csv` relative to notebook execution. Run top to bottom. Notebook 01 saves `statistical_outputs/` next to that input. The statistical test stage uses **development periods only**; the expanded RQ3/RQ4 tests must be freshly executed before their new outputs are cited.
3. **Notebook 02:** Place `statistical_outputs/` alongside your notebook working directory (or under `/content/`) and run top to bottom. It validates the SHA-256 of Notebook 01's prepared data and freezes the primary model plus RQ3/RQ4 comparators in `model_outputs/selection_manifest.json`. It does **not** report final test performance.
4. **Notebook 03:** With both `statistical_outputs/` and `model_outputs/` in the **same parent folder**, run top to bottom. It verifies hashes, refits frozen candidate configurations using train+validation, and evaluates the reserved test quarters. All predictive results belong to the exported `final_evaluation_outputs/` files.

**Environment:** Python 3.10+ with `pandas`, `numpy`, `scipy`, `matplotlib`, `scikit-learn`, `joblib` and Jupyter/IPython. For consistent reproducibility, pin package versions in your final execution environment and include a runtime manifest.

**Colab caveat:** Files saved in temporary `/content` storage disappear on session reset. Copy the output folders to persistent storage before closing the runtime. Never store API credentials in GitHub.

### Research-question boundaries

| Research question | Notebook 01: statistical evidence | Notebooks 02–03: predictive evidence |
| --- | --- | --- |
| **RQ1** — Can quarterly financial results predict next-quarter PAT growth? | Cluster-robust joint association test; association does **not** imply forecasting accuracy. | Compare frozen primary model to a historical-median baseline on held-out periods. |
| **RQ2** — Which variables contribute most? | Cluster-robust coefficient tests, confidence intervals, Holm multiplicity correction. | Permutation importance for the selected model; predictive reliance is **not** causal significance. |
| **RQ3** — Which model predicts most accurately? | Temporal/residual diagnostics assess possible model assumptions, **not** model ranking. | Compare identically held-out predictions from validation-selected candidate algorithms; distinguish descriptive test ranking from selection. |
| **RQ4** — Do engineered variables add value? | Company-clustered nested OLS joint test on matched complete-case development rows; tests incremental **in-sample association**. | Same-algorithm reported-only versus enhanced feature-set comparison on held-out data. If a constant baseline wins, feature-value inference for that family is not meaningful. |

### Scientific limitations and reporting status

- The existing October 2026 interim results (RQ1/RQ2 statistical tests) do not establish predictive performance. Added Notebook 01 RQ3/RQ4 code and the new notebooks **have not been verified by a clean run against the complete source CSV as part of this README update**. Do not report new numerical findings until execution and review.
- Current data have a very short held-out temporal horizon, an unbalanced company panel and extreme PAT-growth values driven by near-zero denominators. Company-block bootstrap intervals are **exploratory** because they do not capture few-quarter common time shocks.
- Confirm filing dates, source XBRL tag/unit consistency, index coverage and restatements before interpreting outcomes as feasible real-time forecasts.
- Model selection and feature-set decisions must be fixed on development data. Do not choose a new winner after seeing test metrics; report adverse or inconclusive results transparently.
- The canonical analytical notebooks do not automatically download raw XBRL filings. They consume a preconstructed standardized CSV, with source audit/provenance recorded by the upstream pipeline.

### Legacy combined notebooks and historical Colab setup

The two `Nifty500_Statistical_Analysis*.ipynb` notebooks predate the three-stage workflow and contain overlapping analysis code. They are retained for traceability and regression comparisons, not as mandatory stages. The older run-order instructions below also mention `02_extract_financials.ipynb`, `03_validate_and_review_scope.ipynb` and `04_build_research_panel.ipynb`, which are not present among the current files listed in `notebooks/`. Those instructions are historical, not the canonical execution path.

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
The original archive instructions below predate the three-stage analytical notebooks.
Refer to the official workflow above for current statistical and modeling code;
no current numerical results are asserted until the notebooks are executed.

## Repository and Drive storage

The repository stores notebooks, code, configuration, and documentation.
Drive stores large XML files, extraction outputs, and research datasets.
The .gitkeep files preserve empty folders in GitHub. Do not commit bulk data,
credentials, or notebook execution outputs. No XML files are bundled here.
