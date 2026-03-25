# Museums Combined Notebook — Methods Study Guide

## Start Here (Non-Coder Friendly)

If you have never touched code before, read this section first.

- Think of this project as two tools working together:
- the notebook (`MuseumNotes_combined.ipynb`) is for analysis and charts,
- the script (`find_new_museum_data.py`) is for finding only new records.
- A **dataset** is just a table of rows and columns (like a spreadsheet).
- A **schema** means the column names and column meanings.
- The project takes incoming data that may not match our schema, reshapes it, checks quality, then compares it to the baseline list.
- Final output is a CSV containing only records that were not already in baseline.

### What problem this solves in plain language

Without this workflow, a person would manually copy/paste rows, rename columns by hand, and guess which rows are duplicates.
This project automates that safely:

1. read incoming data from file/web,
2. align columns into a common format,
3. handle missing or messy values,
4. compare against baseline,
5. export only the truly new rows.

### What you can do even if you do not code

- Run one command and answer prompts.
- Review row counts printed at the end.
- Open the output CSV and verify the records look correct.
- Share the output file with your team.

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

## Quick glossary (plain English)

- **Baseline:** the reference file we compare against (`museums.csv`).
- **Incoming source:** the new dataset we want to evaluate.
- **Mapping:** matching source columns to required project columns.
- **Missing value:** blank/unknown data (`NA` in tables).
- **Duplicate detection:** checking if a record already exists using a comparison key.
- **Key fields:** the minimum columns required to identify a record (`Museum Name` + state).
- **Output contract:** the rules that define what gets written to the output CSV.

## How the commented script matches this guide

Open `find_new_museum_data.py` and read in this order:

1. Module docstring at top: purpose, quick test commands, design notes.
2. Input parsing helpers: source reading + fallback parsers.
3. Schema mapping functions: standard, alternate, and manual interactive mapping.
4. Duplicate-key functions: normalization + new-record filtering.
5. `main()`: full flow from arguments to output CSV.

This structure is intentional so a reader can go section-by-section in the guide,
then find the matching code section immediately.

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

The required script for incremental ingestion is `find_new_museum_data.py`.
It compares an incoming source to baseline `museums.csv` and writes only unseen rows.

### What we implemented (important features)

- Multi-source ingestion: local file, direct URL, webpage URL with CSV/JSON/ZIP download links, `catalog.data.gov/dataset/...` page, or `data.gov` search mode.
- Webpage mode includes a numbered chooser so users can select which discovered files to pull.
- Layered parsing fallback for messy sources: CSV strict -> CSV auto-delimiter -> CSV skip-bad-lines -> JSON -> HTML table.
- ZIP support: reads CSV/JSON members inside archive sources.
- Schema mapping paths:
  - standard museums schema,
  - alternate DC schema,
  - **interactive manual mapping** for unknown schemas.
- Interactive manual mapping now does all of the following:
  - lists available headers,
  - lets user choose which columns to keep,
  - prompts for required/optional field mapping,
  - asks for default state if no state column is selected,
  - keeps selected extra columns in output.
- Duplicate detection remains explainable: normalized `Museum Name + State (Administrative Location)` key.

### Engineer replication runbook (step-by-step)

1. Open a terminal in the project directory that contains:

- `find_new_museum_data.py`
- `museums.csv` (baseline)
- optional incoming files (`alternatemuseums.csv` or your own source)

1. Use a Python environment with `pandas` installed.

2. Run one of these commands:

- Prompt mode: `python find_new_museum_data.py`
  - Webpage with download links: `python find_new_museum_data.py --incoming "https://example.org/data-downloads" --output new_museum_records.csv`
- Known local file: `python find_new_museum_data.py --incoming alternatemuseums.csv --output new_museum_records.csv`
- Catalog dataset page: `python find_new_museum_data.py --incoming "https://catalog.data.gov/dataset/public-library-survey-pls-2022" --output new_museum_records.csv`
- Search mode: `python find_new_museum_data.py --search-query "museum dataset" --max-datasets 10 --output new_museum_records.csv`
- Wikipedia scrape-only dataset mode: `python find_new_museum_data.py --incoming "https://en.wikipedia.org/wiki/List_of_most-visited_museums" --scrape-only-output wikipedia_dataset.csv`

If webpage mode discovers many files, enter file numbers (for example `1,3,5` or `2-4`) to pull only those files, or press Enter to pull all.

1. For unknown schemas, follow prompts:

- select columns to keep,
- map `Museum Name` (required),
- map state/type/address if present,
- provide default state if needed.

1. Verify terminal summary:

- baseline rows,
- incoming rows,
- new rows written,
- output file path.

### Super-simple run path (first-time user)

If you only want the easiest path, do this:

1. Open terminal in the project folder.
2. Run: `python find_new_museum_data.py`
3. Paste a URL or type a local file path when prompted.
4. If you see header prompts, pick column numbers as requested.
5. Wait for final summary and note the output CSV location.
6. Open the CSV in spreadsheet software and review rows.

### Safe loop for testing your own code changes

Use this loop when you change the script and want quick validation:

1. Make one small code change.
2. Run a known-source test:

- `python find_new_museum_data.py --incoming alternatemuseums.csv --output new_museum_records_test.csv`

1. Confirm the script reaches final summary and writes output.
2. Run an unknown-schema/manual test if you changed mapping logic.
3. Compare output row counts before/after your change.
4. Keep the change only if behavior is improved and expected.

### What we validated in this implementation pass

- Known-schema run completed using `alternatemuseums.csv` and wrote new records successfully.
- Unknown-schema run completed using a custom CSV and exercised interactive header selection + manual mapping prompts.
- In both runs, script reached final summary and wrote output CSV without runtime errors.

### Key arguments

- `--base`: baseline CSV path (default `museums.csv`)
- `--incoming`: URL or local path for incoming data (including webpage URLs that list downloadable CSV/JSON/ZIP files)
- `--search-query`: online query for `data.gov` discovery mode
- `--max-datasets`: max datasets to inspect in search mode
- `--output`: destination CSV for new records (default `new_museum_records.csv`)
- `--scrape-only-output`: write a raw scraped dataset CSV directly (no dedupe/mapping), useful for Wikipedia/webpage research datasets
- `--output-folder`: folder for generated datasets when output names are plain filenames (default `generated_datasets`)
- `--flat-output-folder`: disable date subfolders and write directly into `--output-folder`

By default, generated files are organized into `generated_datasets/YYYY-MM-DD/` unless you pass an explicit path with a directory.

### Why this logic (and why this is useful)

This section explains not just what the script does, but why it was designed this way.

1. **Two operating modes (incremental vs scrape-only)**

- Incremental mode (`--output`) is for operational workflows: map incoming data to museum schema, compare to baseline, write only new rows.
- Scrape-only mode (`--scrape-only-output`) is for exploration/research: pull raw tables from web sources (like Wikipedia) and export directly.
- Why split modes? Because operational dedupe rules and exploratory scraping goals are different, and combining them can cause confusion or silent data loss.

1. **Layered parsing strategy**

- Real-world links are inconsistent: direct CSV, ZIP archives, JSON APIs, or HTML wrapper pages.
- The script attempts parsing in controlled layers so failure in one format does not end the run prematurely.
- Why this over a single parser? A single parser is simpler to code but fails frequently in practice.

1. **Interactive selection for discovered files**

- When a page exposes many download links, users choose only relevant files.
- Why this over auto-pulling everything? Pulling everything can be slow, noisy, and may ingest irrelevant tables.

1. **Interactive schema mapping for unknown structures**

- Unknown columns are mapped with prompts instead of hard-failing.
- Why this over strict schema-only mode? Strict mode is safer for automation, but it blocks exploratory and public-data workflows.

1. **Date-stamped output folders (`generated_datasets/YYYY-MM-DD/`)**

- Keeps each run grouped by day for reproducibility and auditability.
- Reduces accidental overwrite risk from repeated experiments.
- Makes cleanup and review simpler (you can inspect or archive by date).
- Why this over one flat output folder? Flat folders are simpler, but they make run history harder to track.
- If you prefer flat output, use `--flat-output-folder`.

### Output-folder examples

- Default dated output:
  - `python find_new_museum_data.py --incoming alternatemuseums.csv --output new_rows.csv`
  - Writes to: `generated_datasets/<today>/new_rows.csv`
- Flat output folder:
  - `python find_new_museum_data.py --incoming alternatemuseums.csv --output new_rows.csv --flat-output-folder`
  - Writes to: `generated_datasets/new_rows.csv`
- Explicit path (always respected):
  - `python find_new_museum_data.py --incoming alternatemuseums.csv --output exports/my_run/new_rows.csv`
  - Writes to exactly: `exports/my_run/new_rows.csv`

### Recommended team conventions

Use this baseline policy so everyone on the team produces predictable, reviewable outputs.

1. **File naming pattern**

- Incremental outputs: `<source>_new_rows_<short-purpose>.csv`
- Scrape-only outputs: `<source>_raw_<topic>.csv`
- Keep names lowercase with underscores for easier shell usage.

1. **When to use dated folders (default)**

- Use dated folders for experiments, demos, and onboarding runs.
- Use dated folders when multiple teammates are running the script in the same repo.
- Benefit: preserves run history and avoids accidental overwrite.

1. **When to use flat output (`--flat-output-folder`)**

- Use flat mode for stable pipelines that always overwrite a canonical output name.
- Use flat mode only when downstream automation expects one fixed filename.

1. **Retention and cleanup cadence**

- Daily/active work: keep last 3–7 dated run folders.
- Weekly: archive or delete older dated folders not referenced by reports.
- Before demo/hand-off: keep one final dated folder and remove temporary test files.

1. **Review checklist before sharing outputs**

- Confirm the run used the expected source URL/path.
- Confirm row count and column count look reasonable.
- Confirm folder/date and filename follow team naming pattern.
- Confirm no temporary test files are included.

### Wikipedia notes

- Wikipedia table scraping requires `lxml` in your Python environment.
- If a page has multiple tables, the script shows them and lets you choose which table numbers to include.
- In scrape-only mode, output is a direct dataset export from selected tables.

### Output contract

- Output CSV contains only rows that have non-empty normalized `Museum Name` and `State (Administrative Location)`.
- Rows already present in baseline by normalized key are excluded.
- Script prints run metadata for reproducibility and auditability.

### Troubleshooting quick list

- **No new rows:** records may already exist in baseline or key fields are blank.
- **Prompt asks for manual mapping:** incoming schema is not recognized automatically (expected behavior).
- **Page URL parse issue:** verify URL is a public dataset page with CSV/JSON resources.
- **Sparse search results:** tune `--search-query` and/or increase `--max-datasets`.

### Non-coder troubleshooting (decision guide)

- If you see prompts asking for column numbers, this is normal for unknown schemas.
- If output has `0` new rows, first check whether the incoming data is already in baseline.
- If a URL fails, try downloading that data locally and pass the local file instead.
- If columns look wrong in output, rerun and choose different mapping columns.

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
