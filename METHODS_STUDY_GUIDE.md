# Museums Combined Notebook — Methods Study Guide

## Important Before You Start (Quick Essentials)

- **Required files in the same project area:** `museums.csv`, `alternatemuseums.csv`, and `state_pop_data.csv`.
- **Required Python packages:** `pandas`, `matplotlib`, `seaborn`, and `ipywidgets`.
- **What this notebook guarantees:** it alerts on high missingness, keeps key grouping fields populated with `NA`, and avoids crashing on dirty date/currency values.
- **Most important output to check first:** the missing-data alert + top missingness summary table in the `clean_copy` preparation step.
- **Key assumption:** alternate-source records are mapped into the main schema and may use placeholders (`NA`, `Unknown Address`, `NaT`) when source values are missing.
- **Common pitfall:** if widgets or plots do not render, rerun setup cells from top to bottom after installing dependencies.

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

The project now includes `find_new_museum_data.py` for detecting **new museum records** relative to `museums.csv` and exporting them to a separate CSV.

### What the script does (plain language)

1. Loads your baseline museum dataset (`museums.csv`).
2. Gets incoming data from one of three sources:

- a local path,
- a direct URL,
- or an internet `data.gov` search query.

1. Maps incoming data into a compatible museum schema when needed.
2. Builds a normalized match key from `Museum Name + State (Administrative Location`.
3. Keeps only rows that are valid and not already in baseline.
4. Writes those rows to a new CSV.

### Input modes you can use

- **Interactive prompt mode** (asks user for URL/path):
- `python find_new_museum_data.py`
- **Direct incoming source mode**:
- `python find_new_museum_data.py --incoming "https://example.org/museums.csv"`
- `python find_new_museum_data.py --incoming alternatemuseums.csv`
- **Internet search mode (`data.gov`)**:
- `python find_new_museum_data.py --search-query "museum dataset" --max-datasets 10`

### Important arguments

- `--base`: baseline CSV to compare against (default: `museums.csv`)
- `--incoming`: URL or local file path for incoming data
- `--search-query`: query string for online search (uses `data.gov` API)
- `--max-datasets`: cap on online datasets checked in search mode
- `--output`: output CSV path for newly detected records (default: `new_museum_records.csv`)

### Schema support details

The script supports two incoming schemas:

1. **museums-style schema** (already includes columns like `Museum Name` and `State (Administrative Location)`).
2. **alternate DC schema** (columns like `DCGISPLACE_NAMES_PTNAME`, `DCGISADDRESSES_PTADDRESS`, `MARVW_PLACE_NAME_CATEGORIESCATEGORY`) which are mapped into museums-style columns.

If neither schema matches, the script stops with a clear schema error.

### How duplicate detection works

- Matching key: uppercase/trimmed `Museum Name` + `State (Administrative Location)`.
- A row is treated as new only if:
- both key parts are present, and
- the combined key does not exist in baseline.

### Output behavior

- The script always writes a CSV (possibly empty if no new rows are found).
- It prints a summary with:
- baseline row count,
- incoming source and incoming row count,
- number of new rows written,
- output file location.

### Engineering notes and caveats

- `data.gov` search mode may find many resources; only CSV/JSON resources are attempted.
- Some online resources will be skipped if schema is incompatible.
- Network/API availability affects online modes.
- Current dedupe key is intentionally simple and explainable; for production, consider stronger matching (address + fuzzy name + geocode).

### Troubleshooting quick list

- **No results written:** verify incoming source has valid museum names and state values.
- **Schema error:** check whether incoming columns match one of the two supported schemas.
- **URL fails:** open URL in browser to verify it is accessible and not blocked.
- **Search mode sparse:** increase `--max-datasets` or improve `--search-query` keywords.
