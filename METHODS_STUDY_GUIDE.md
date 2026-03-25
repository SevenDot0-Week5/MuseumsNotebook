# Museums Combined Notebook — Methods Study Guide

## Important Before You Start (Quick Essentials)

- **Required files in the same project area:** `museums.csv`, `alternatemuseums.csv`, and `state_pop_data.csv`.
- **Required Python packages:** `pandas`, `matplotlib`, `seaborn`, and `ipywidgets`.
- **What this notebook guarantees:** it alerts on high missingness, keeps key grouping fields populated with `NA`, and avoids crashing on dirty date/currency values.
- **Most important output to check first:** the missing-data alert + top missingness summary table in the `clean_copy` preparation step.
- **Key assumption:** alternate-source records are mapped into the main schema and may use placeholders (`NA`, `Unknown Address`, `NaT`) when source values are missing.
- **Common pitfall:** if widgets or plots do not render, rerun setup cells from top to bottom after installing dependencies.

## Team quick talk track (60 seconds)

We built two connected pieces: a resilient analysis notebook and a companion ingestion script.
The notebook standardizes mixed museum data, surfaces missingness early, and keeps charts/tables running even with imperfect inputs.
The script handles local files, direct URLs, `catalog.data.gov` dataset pages, and search-based `data.gov` discovery, then writes only new records compared with baseline.
The design goal was reliability + explainability: clear schema mapping, explicit quality checks, and simple duplicate logic the team can reason about.

## Goal

This guide explains the methods used in `MuseumNotes_combined.ipynb` so you can study both **what** each stage does and **why** it is done that way.

## 1) Multi-source ingestion

The notebook loads three files:

- `museums.csv` (primary museum dataset)
- `alternatemuseums.csv` (alternate source with different schema)
- `state_pop_data.csv` (state population enrichment)

### Method used: local path discovery

A helper function searches common local paths and nearby folders using `Path` and `rglob`, so the notebook is portable across machines.

## 2) Schema alignment for alternate data

`alternatemuseums.csv` does not use the same column names as the primary museum file.

### Method used: field mapping

The notebook maps alternate columns into the core schema:

- name -> `Museum Name`
- category -> `Museum Type`
- address -> `Street Address (Administrative Location)`
- state -> forced to `DC` for this source
- finance/date fields -> initialized as missing placeholders

This allows concatenation with `pd.concat(..., sort=False)`.

## 3) Cleaning strategy

### A. Blank normalization

Whitespace-only strings are converted to missing values (`pd.NA`) before quality checks.

### B. Row-level information threshold

Alternate rows are retained only when they include at least 2 of 3 useful fields:

- name
- address
- category

This removes weak/incomplete records while preserving usable data.

### C. Missing-value surfacing

After merge and cleanup, key text columns are normalized and then filled with `NA` for grouping/display so visuals still include available rows.

## 4) Missing-data monitoring

### Method used: threshold alert + summary table

In `clean_copy` preparation:

- a warning prints if any column exceeds 30% missing
- a compact top-10 missingness table is displayed

This makes data quality issues visible early, before analysis cells run.

## 5) Robust type parsing

### Dates

`Tax Period` uses `pd.to_datetime(..., errors='coerce')` so bad formats become `NaT` instead of crashing the notebook.

### Currency

`Income` and `Revenue` are parsed from dollar strings to numeric with `errors='coerce'`, then formatted back for display; missing values are shown as `NA`.

## 6) Analysis patterns used

- `groupby(...).size()` for categorical frequency summaries
- filtered subsets for domain-specific slices (zoo/aquarium)
- horizontal bars for long category lists (better readability)
- pie chart only where intended for share visualization
- heatmap for state x type matrix with log scaling (`log1p`) to reduce skew

## 7) Interactive analysis methods

Using `ipywidgets`:

- dropdown-driven state filtering
- dynamic chart updates via `interactive_output`
- consistent category ordering to make cross-state comparisons stable

## 8) Statistical profile methods

Revenue and income analysis uses:

- numeric coercion from formatted strings
- removal of invalid/non-positive values
- IQR outlier filtering per museum type
- grouped `.describe()` summaries with readable currency formatting

## 9) Why this design works

- Resilient to missing/dirty values
- Portable across environments
- Keeps weak rows visible but labeled instead of silently dropped
- Makes warnings explicit when data quality may affect conclusions

## 10) Suggested study order

1. Read the top notebook guide cell.
2. Study the load + cleaning cells (first 3 code cells).
3. Review missing-data warning output and summary table.
4. Trace one chart pipeline (groupby -> transform -> plot).
5. Compare static and interactive chart approaches.
6. Finish with the stats/outlier section.

## 11) Understanding check (for the reader)

Use this section after reading the notebook to confirm understanding.

### A. Quick checklist

- I can explain why `alternatemuseums.csv` needs schema mapping before concatenation.
- I can describe the row-quality rule (at least 2 of 3 fields: name/address/category).
- I can explain why key grouping columns are filled with `NA` before plotting.
- I can identify what the missing-data alert means and how the threshold works.
- I can explain why `errors='coerce'` is used for date and currency parsing.
- I can describe one difference between static charts and interactive widget charts.

### B. Self-test questions

1. Why does the notebook convert blank strings to `pd.NA` before running missingness checks?
2. What problem would happen in grouping/plots if key categorical fields were not filled with `NA`?
3. What does `NaT` represent, and where in this notebook is it introduced?
4. Why is `log1p` used in the heatmap, and what readability issue does it address?
5. In the outlier section, why is IQR filtering applied per museum type instead of globally?

### C. Mini practice tasks

1. Change the missing-data threshold from 30% to 20% and rerun the prep cell. Note which extra columns are now flagged.
2. Temporarily disable `fillna("NA")` for key text fields and rerun one grouping chart. Observe how category totals change.
3. Add a one-line summary print for how many rows have `Museum Name == "NA"` after cleaning.
4. In the heatmap cell, remove annotation filtering (`>= 10`) and compare readability.

### D. What “good understanding” looks like

You can trace a row from raw input -> cleaned/mapped schema -> `clean_copy` -> grouped summary -> chart, and explain each transformation and its purpose.

## 12) Companion script guide: finding new records and writing a CSV

The project includes `find_new_museum_data.py` to detect **new museum records** relative to baseline `museums.csv` and export only new rows.

### What the script does

1. Loads baseline data from `museums.csv` (or `--base`).
2. Ingests incoming data from one of these sources:

- local path,
- direct URL,
- `catalog.data.gov/dataset/...` dataset page URL,
- or `data.gov` search query mode.

1. Maps incoming records into supported schema.

2. Builds duplicate key: `Museum Name + State (Administrative Location)` (normalized case/whitespace).

3. Keeps only rows with required key fields that are not already in baseline.

4. Writes new rows to output CSV.

### Input modes

- **Prompt mode (asks for URL/path):** `python find_new_museum_data.py`
- **Direct incoming source:** `python find_new_museum_data.py --incoming "https://example.org/museums.csv"`
- **Catalog dataset page URL:**
`python find_new_museum_data.py --incoming "https://catalog.data.gov/dataset/public-library-survey-pls-2022"`
- **Search mode (`data.gov` API):**
`python find_new_museum_data.py --search-query "museum dataset" --max-datasets 10`

### Key arguments

- `--base`: baseline CSV path (default `museums.csv`)
- `--incoming`: URL or local path for incoming data
- `--search-query`: online query for `data.gov` dataset discovery
- `--max-datasets`: max datasets to inspect in search mode
- `--output`: destination CSV for new records (default `new_museum_records.csv`)

### Schema + parsing behavior

- Supported incoming schemas:
- museums-style schema (has `Museum Name` and `State (Administrative Location)`),
- alternate DC schema (`DCGISPLACE_NAMES_PTNAME`, `DCGISADDRESSES_PTADDRESS`, `MARVW_PLACE_NAME_CATEGORIESCATEGORY`).
- For non-raw URLs and messy files, parser attempts are layered:
- CSV (strict),
- CSV (auto delimiter),
- CSV (auto delimiter + skip bad lines),
- JSON,
- HTML table extraction.
- If all attempts fail, script returns a detailed parse diagnostic.

### Catalog.data.gov page support

- If `--incoming` is a `catalog.data.gov/dataset/...` page URL, the script:

1. extracts dataset id,
2. calls CKAN `package_show`,
3. collects CSV/JSON resource URLs,
4. processes those resources through the same schema mapping + dedupe flow.

### What gets written

- Output CSV contains only rows that:
- have non-empty normalized `Museum Name` and `State (Administrative Location)`, and
- are not already in baseline by normalized key.
- Script prints baseline count, incoming source label, incoming row count, new-row count, and output location.

### Practical caveats

- Many online datasets are non-museum schemas; those resources are skipped.
- Network/API instability can affect URL and search modes.
- Duplicate detection is intentionally simple for explainability; production matching can extend keying with address/fuzzy matching.

### Troubleshooting quick list

- **No new rows:** incoming records may already exist in baseline or key fields may be empty.
- **Schema not recognized:** incoming columns do not match supported schemas.
- **Page URL parse issue:** confirm URL is a dataset page and resources are public.
- **Sparse search results:** tune `--search-query` and increase `--max-datasets`.

## 13) 2-minute live demo script (say this in the meeting)

### A. Open (15–20 seconds)

"We built this in two layers: a notebook for robust analysis and a script for incremental ingestion. The notebook handles cleaning and interpretation; the script finds only new records and writes a clean CSV for downstream work."

### B. Why we designed it this way (20–30 seconds)

"We wanted resilience and transparency. Data comes in different shapes and with missing values, so we made schema mapping explicit, added missing-data alerts, and used safe parsing so bad values become `NA`/`NaT` instead of breaking execution."

### C. Live command demo (40–50 seconds)

Run one of these:

- Prompt mode:
- `python find_new_museum_data.py`
- Catalog dataset page mode:
- `python find_new_museum_data.py --incoming "https://catalog.data.gov/dataset/public-library-survey-pls-2022" --output new_museum_records.csv`

Then narrate:

"The script resolves the source, maps supported schemas, compares incoming rows to baseline using normalized museum name + state, and writes only unseen rows. It prints baseline count, incoming count, new-row count, and output location."

### D. Close (15–20 seconds)

"So the value is: less manual cleanup, clearer quality visibility, and a repeatable process that engineers can automate and analysts can trust."
