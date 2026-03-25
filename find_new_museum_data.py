from __future__ import annotations

"""
Museum incremental-ingestion helper.

Purpose
-------
Compare an incoming museum-like data source against baseline `museums.csv`
and export only rows that are new by normalized `Museum Name + State` key.

Read vs Test workflow
---------------------
1) Read the code top-to-bottom by section headers:
     - Input parsing and source loading
     - Schema mapping
     - Duplicate-key comparison
     - CLI orchestration in `main()`

2) Test quickly from the project directory:
     - Prompt mode:
         python find_new_museum_data.py
     - Known local schema:
         python find_new_museum_data.py --incoming alternatemuseums.csv --output new_museum_records.csv
     - Online catalog page:
         python find_new_museum_data.py --incoming "https://catalog.data.gov/dataset/public-library-survey-pls-2022"

Design notes
------------
- Uses simple, explainable duplicate logic for team clarity.
- Uses layered parsers to handle real-world sources that are inconsistent.
- Falls back to interactive manual mapping when schema is unknown.
"""

import argparse
from datetime import date
from html.parser import HTMLParser
from io import BytesIO, StringIO
import json
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen
from zipfile import ZipFile

import pandas as pd


STANDARD_REQUIRED = {
    "Museum Name",
    "State (Administrative Location)",
}

ALT_REQUIRED = {
    "DCGISPLACE_NAMES_PTNAME",
    "DCGISADDRESSES_PTADDRESS",
    "MARVW_PLACE_NAME_CATEGORIESCATEGORY",
}

SUPPORTED_RESOURCE_FORMATS = {"csv", "json"}
SUPPORTED_DOWNLOAD_EXTENSIONS = (".csv", ".json", ".zip")
DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


class _HrefParser(HTMLParser):
    """Minimal HTML href extractor for download-link discovery."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)
                break


def normalize_text(series: pd.Series) -> pd.Series:
    """Normalize text for comparison-safe keys (trim, uppercase, fill empty)."""
    return (
        series.astype("string")
        .str.strip()
        .str.upper()
        .fillna("")
    )


def _print_columns(columns: list[str]) -> None:
    """Display available incoming headers as numbered options."""
    print("\nAvailable headers:")
    for idx, name in enumerate(columns, start=1):
        print(f"  {idx:>2}. {name}")


def _prompt_select_columns(columns: list[str]) -> list[str]:
    """Prompt user to keep all columns or a chosen subset by index."""
    _print_columns(columns)
    print(
        "\nChoose which columns to keep (comma-separated numbers), or press Enter to keep all."
    )

    while True:
        raw = input("Columns to keep: ").strip()
        if not raw:
            return columns

        try:
            indexes = [int(part.strip()) for part in raw.split(",") if part.strip()]
        except ValueError:
            print("Please enter valid numbers separated by commas.")
            continue

        if not indexes:
            print("Please choose at least one column.")
            continue

        if any(idx < 1 or idx > len(columns) for idx in indexes):
            print("One or more selections are out of range. Try again.")
            continue

        selected = [columns[idx - 1] for idx in indexes]
        # Preserve order while deduplicating.
        deduped = list(dict.fromkeys(selected))
        return deduped


def _prompt_pick_field(
    field_name: str,
    columns: list[str],
    required: bool,
) -> str | None:
    """Prompt user to map one required/optional target field to an input column."""
    req_text = "required" if required else "optional"
    print(f"\nSelect the column for '{field_name}' ({req_text}).")
    _print_columns(columns)

    while True:
        raw = input(f"{field_name} column number{' (blank to skip)' if not required else ''}: ").strip()
        if not raw and not required:
            return None
        if not raw and required:
            print(f"{field_name} is required. Please select a column.")
            continue
        try:
            idx = int(raw)
        except ValueError:
            print("Please enter a valid number.")
            continue
        if idx < 1 or idx > len(columns):
            print("Selection out of range. Try again.")
            continue
        return columns[idx - 1]


def _prompt_default_state() -> str:
    """Require a default state when incoming source has no state column."""
    print("\nNo state column selected.")
    while True:
        value = input("Enter a default state value to use (e.g., DC): ").strip()
        if value:
            return value
        print("Default state is required to continue.")


def manual_map_incoming_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Interactive fallback mapping for unknown schemas.

    This path is intentionally explicit and beginner-friendly: user sees headers,
    picks what to keep, maps core fields, and can supply a default state.
    """
    print("\nSchema not recognized automatically.")
    print("You can choose headers to keep and map them to required fields.")

    all_columns = list(frame.columns)
    kept_columns = _prompt_select_columns(all_columns)
    working = frame[kept_columns].copy()

    name_col = _prompt_pick_field("Museum Name", kept_columns, required=True)
    state_col = _prompt_pick_field(
        "State (Administrative Location)", kept_columns, required=False
    )
    type_col = _prompt_pick_field("Museum Type", kept_columns, required=False)
    address_col = _prompt_pick_field(
        "Street Address (Administrative Location)", kept_columns, required=False
    )

    if state_col is None:
        default_state = _prompt_default_state()
        state_values = pd.Series(default_state, index=working.index)
    else:
        state_values = working[state_col]

    mapped = pd.DataFrame(
        {
            "Museum Name": working[name_col],
            "State (Administrative Location)": state_values,
            "Museum Type": working[type_col] if type_col else pd.NA,
            "Street Address (Administrative Location)": (
                working[address_col] if address_col else pd.NA
            ),
            "Institution Name": pd.NA,
            "Tax Period": pd.NA,
            "Income": pd.NA,
            "Revenue": pd.NA,
        }
    )

    # Keep user-selected extra columns so they remain available in output if useful.
    extra_cols = [
        col
        for col in kept_columns
        if col not in {name_col, state_col, type_col, address_col}
    ]
    if extra_cols:
        mapped = pd.concat([mapped, working[extra_cols].copy()], axis=1)

    print("\nManual mapping complete. Continuing with duplicate detection.")
    return mapped


def is_url(value: str) -> bool:
    """Return True when source is an HTTP(S) URL."""
    return value.startswith("http://") or value.startswith("https://")


def fetch_url_bytes(url: str) -> bytes:
    """Fetch URL bytes using a browser-like user-agent header."""
    request = Request(url, headers=DEFAULT_HTTP_HEADERS)
    with urlopen(request) as response:
        return response.read()


def _looks_like_download_url(url: str) -> bool:
    """Heuristic: True when URL path/query indicates direct CSV/JSON/ZIP content."""
    lowered = url.lower()
    parsed = urlparse(lowered)

    if parsed.path.endswith(SUPPORTED_DOWNLOAD_EXTENSIONS):
        return True

    query = parse_qs(parsed.query)
    for key in ("format", "filetype", "type"):
        values = query.get(key, [])
        if any(v in {"csv", "json", "zip"} for v in values):
            return True

    return any(ext in lowered for ext in SUPPORTED_DOWNLOAD_EXTENSIONS)


def discover_download_links_from_webpage(page_url: str) -> list[str]:
    """
    Discover CSV/JSON/ZIP links from a webpage URL.

    Relative links are resolved using the page URL.
    """
    html_bytes = fetch_url_bytes(page_url)

    html_text = html_bytes.decode("utf-8", errors="replace")

    parser = _HrefParser()
    parser.feed(html_text)

    candidate_links: list[str] = []
    for href in parser.hrefs:
        absolute = urljoin(page_url, href)
        if not is_url(absolute):
            continue
        if _looks_like_download_url(absolute):
            candidate_links.append(absolute)

    # Preserve order and dedupe.
    return list(dict.fromkeys(candidate_links))


def _prompt_select_resource_urls(urls: list[str], label: str) -> list[str]:
    """
    Let user choose which discovered resource URLs to pull.

    Input format:
    - Enter: keep all
    - Comma list: 1,3,5
    - Ranges: 1-3,7
    - q: cancel
    """
    if len(urls) <= 1:
        return urls

    print(f"\n{label} discovered: {len(urls):,}")
    for idx, resource_url in enumerate(urls, start=1):
        print(f"  {idx:>3}. {resource_url}")

    print("\nChoose files to pull by number (e.g., 1,3,5 or 1-4).")
    print("Press Enter to pull all, or type 'q' to cancel.")

    while True:
        raw = input("Files to pull: ").strip().lower()
        if raw == "":
            return urls
        if raw in {"q", "quit", "exit"}:
            raise SystemExit("Cancelled by user.")

        try:
            selected_indexes: list[int] = []
            for token in raw.split(","):
                token = token.strip()
                if not token:
                    continue
                if "-" in token:
                    start_text, end_text = token.split("-", 1)
                    start = int(start_text.strip())
                    end = int(end_text.strip())
                    if start > end:
                        start, end = end, start
                    selected_indexes.extend(list(range(start, end + 1)))
                else:
                    selected_indexes.append(int(token))

            if not selected_indexes:
                print("Please choose at least one file index.")
                continue

            if any(idx < 1 or idx > len(urls) for idx in selected_indexes):
                print("One or more selections are out of range. Try again.")
                continue

            selected_urls = [urls[idx - 1] for idx in selected_indexes]
            return list(dict.fromkeys(selected_urls))
        except ValueError:
            print("Invalid selection format. Use values like 1,3,5 or 1-4.")


def _parse_index_selection(raw: str, max_size: int) -> list[int]:
    """Parse index selections like '1,3,5' or '2-4' into 1-based indexes."""
    selected_indexes: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if start > end:
                start, end = end, start
            selected_indexes.extend(list(range(start, end + 1)))
        else:
            selected_indexes.append(int(token))

    if not selected_indexes:
        raise ValueError("No selections provided.")
    if any(idx < 1 or idx > max_size for idx in selected_indexes):
        raise ValueError("Selection out of range.")

    # Preserve order while deduplicating.
    return list(dict.fromkeys(selected_indexes))


def _is_wikipedia_url(url: str) -> bool:
    """Return True when URL host belongs to Wikipedia."""
    if not is_url(url):
        return False
    return "wikipedia.org" in urlparse(url).netloc.lower()


def scrape_wikipedia_tables(page_url: str) -> pd.DataFrame:
    """
    Scrape tabular data from a Wikipedia page and let user choose tables.

    Returns a combined DataFrame from selected table(s).
    """
    html_bytes = fetch_url_bytes(page_url)
    html_text = html_bytes.decode("utf-8", errors="replace")
    tables = pd.read_html(StringIO(html_text))
    non_empty_tables = [table for table in tables if not table.empty]

    if not non_empty_tables:
        raise ValueError(f"No non-empty HTML tables were found on: {page_url}")

    print(f"\nWikipedia tables found: {len(non_empty_tables):,}")
    for idx, table in enumerate(non_empty_tables, start=1):
        preview_cols = [str(col) for col in list(table.columns)[:6]]
        print(f"  {idx:>3}. rows={len(table):,}, cols={len(table.columns):,}, sample_cols={preview_cols}")

    if len(non_empty_tables) == 1:
        selected_tables = [non_empty_tables[0]]
    else:
        print("\nChoose table numbers to use (e.g., 1,3 or 2-4).")
        print("Press Enter to use table 1, or type 'q' to cancel.")
        while True:
            raw = input("Tables to use: ").strip().lower()
            if raw == "":
                selected_tables = [non_empty_tables[0]]
                break
            if raw in {"q", "quit", "exit"}:
                raise SystemExit("Cancelled by user.")
            try:
                selected_indexes = _parse_index_selection(raw, len(non_empty_tables))
                selected_tables = [non_empty_tables[idx - 1] for idx in selected_indexes]
                break
            except ValueError:
                print("Invalid selection format. Use values like 1,3 or 2-4.")

    combined = pd.concat(selected_tables, ignore_index=True, sort=False)
    print(f"Wikipedia tables selected: {len(selected_tables):,}")
    print(f"Wikipedia combined rows: {len(combined):,}")
    return combined


def load_raw_from_resource_urls(urls: list[str], label: str) -> pd.DataFrame:
    """Load raw tables from resource URLs and combine successful parses."""
    frames: list[pd.DataFrame] = []
    skipped = 0

    for resource_url in urls:
        try:
            frame = read_table(resource_url)
            if not frame.empty:
                frames.append(frame)
            else:
                skipped += 1
        except Exception:
            skipped += 1

    if not frames:
        raise ValueError(f"{label} were discovered, but none could be parsed.")

    combined = pd.concat(frames, ignore_index=True, sort=False)
    print(f"{label} found: {len(urls):,}")
    print(f"{label} used: {len(frames):,}")
    print(f"{label} skipped: {skipped:,}")
    return combined


def load_and_map_from_resource_urls(urls: list[str], label: str) -> pd.DataFrame:
    """Load and map a list of resource URLs, combining successful parses."""
    mapped_frames: list[pd.DataFrame] = []
    skipped = 0

    for resource_url in urls:
        try:
            frame = read_table(resource_url)
            mapped_frames.append(map_incoming_frame(frame))
        except Exception:
            skipped += 1

    if not mapped_frames:
        raise ValueError(
            f"{label} were discovered, but none matched supported museum schemas."
        )

    combined = pd.concat(mapped_frames, ignore_index=True, sort=False)
    print(f"{label} found: {len(urls):,}")
    print(f"{label} used: {len(mapped_frames):,}")
    print(f"{label} skipped: {skipped:,}")
    return combined


def read_zip_source(source: str) -> pd.DataFrame:
    """Read ZIP source and parse first usable CSV/JSON member(s)."""
    if is_url(source):
        zip_bytes = fetch_url_bytes(source)
    else:
        zip_bytes = Path(source).read_bytes()

    parse_errors: list[str] = []

    with ZipFile(BytesIO(zip_bytes)) as zf:
        members = [name for name in zf.namelist() if not name.endswith("/")]

        csv_members = [name for name in members if name.lower().endswith(".csv")]
        json_members = [name for name in members if name.lower().endswith(".json")]

        parsed_frames: list[pd.DataFrame] = []
        csv_encodings = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]

        for member in csv_members:
            member_error: str | None = None
            with zf.open(member) as fh:
                raw_bytes = fh.read()

            for encoding in csv_encodings:
                try:
                    frame = pd.read_csv(
                        BytesIO(raw_bytes),
                        low_memory=False,
                        encoding=encoding,
                    )
                    if not frame.empty:
                        parsed_frames.append(frame)
                    member_error = None
                    break
                except Exception as exc:
                    member_error = f"{member} [encoding={encoding}]: {exc}"

            if member_error:
                parse_errors.append(member_error)

        if parsed_frames:
            combined = pd.concat(parsed_frames, ignore_index=True, sort=False)
            print(f"ZIP members detected: {len(members):,}")
            print(f"CSV members parsed: {len(parsed_frames):,}")
            return combined

        for member in json_members:
            try:
                with zf.open(member) as fh:
                    frame = pd.read_json(fh)
                if not frame.empty:
                    return frame
            except Exception as exc:
                parse_errors.append(f"{member}: {exc}")

    summary = "\n- " + "\n- ".join(parse_errors[:8]) if parse_errors else ""
    raise ValueError(
        "ZIP source was found, but no CSV/JSON members could be parsed."
        f"\nSource: {source}"
        f"\nParse attempts:{summary}"
    )


def read_table(source: str) -> pd.DataFrame:
    """
    Parse incoming source using resilient fallbacks.

    Order of attempts:
    1) ZIP member parsing (if `.zip` appears in source)
    2) CSV variants (strict, auto-delimiter, skip-bad-lines)
    3) JSON
    4) HTML table extraction
    """
    source_lower = source.lower()

    if ".zip" in source_lower:
        return read_zip_source(source)

    if source_lower.endswith(".json"):
        return pd.read_json(source)

    csv_attempt_errors: list[str] = []

    csv_attempts = [
        {"low_memory": False},
        {"engine": "python", "sep": None},
        {
            "engine": "python",
            "sep": None,
            "on_bad_lines": "skip",
        },
    ]

    for kwargs in csv_attempts:
        try:
            frame = pd.read_csv(source, **kwargs)
            if frame.empty:
                continue
            return frame
        except Exception as exc:
            csv_attempt_errors.append(f"read_csv{kwargs} -> {exc}")

    try:
        frame = pd.read_json(source)
        if not frame.empty:
            return frame
    except Exception as exc:
        csv_attempt_errors.append(f"read_json -> {exc}")

    try:
        html_tables = pd.read_html(source)
        if html_tables:
            return html_tables[0]
    except Exception as exc:
        csv_attempt_errors.append(f"read_html -> {exc}")

    error_summary = "\n- " + "\n- ".join(csv_attempt_errors[:6])
    raise ValueError(
        "Could not parse incoming source as CSV, JSON, or HTML table. "
        "This often means the URL points to a webpage/download wrapper instead of raw data."
        f"\nSource: {source}"
        f"\nAttempts:{error_summary}"
    )


def search_data_gov_resources(query: str, max_datasets: int) -> list[str]:
    """Search data.gov (CKAN) and collect CSV/JSON resource URLs."""
    api_url = (
        "https://catalog.data.gov/api/3/action/package_search"
        f"?q={quote_plus(query)}&rows={max_datasets}"
    )

    payload = json.loads(fetch_url_bytes(api_url).decode("utf-8"))

    if not payload.get("success"):
        raise ValueError("data.gov search API returned an unsuccessful response.")

    results = payload.get("result", {}).get("results", [])
    resource_urls: list[str] = []

    for dataset in results:
        for resource in dataset.get("resources", []):
            fmt = str(resource.get("format", "")).strip().lower()
            url = resource.get("url")
            if fmt in SUPPORTED_RESOURCE_FORMATS and isinstance(url, str) and url:
                resource_urls.append(url)

    return resource_urls


def extract_dataset_id_from_data_gov_url(url: str) -> str | None:
    """Extract dataset id from catalog.data.gov dataset-page URL, if present."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.strip("/").split("/") if part]

    if "catalog.data.gov" not in host:
        return None

    if len(path_parts) >= 2 and path_parts[0] == "dataset":
        return path_parts[1]

    return None


def resources_from_data_gov_dataset_id(dataset_id: str) -> list[str]:
    """Resolve a dataset id to CSV/JSON resource URLs via CKAN package_show."""
    api_url = (
        "https://catalog.data.gov/api/3/action/package_show"
        f"?id={quote_plus(dataset_id)}"
    )

    payload = json.loads(fetch_url_bytes(api_url).decode("utf-8"))

    if not payload.get("success"):
        raise ValueError(
            f"data.gov package_show API returned unsuccessful response for dataset: {dataset_id}"
        )

    dataset = payload.get("result", {})
    resource_urls: list[str] = []

    for resource in dataset.get("resources", []):
        fmt = str(resource.get("format", "")).strip().lower()
        url = resource.get("url")
        if fmt in SUPPORTED_RESOURCE_FORMATS and isinstance(url, str) and url:
            resource_urls.append(url)

    return resource_urls


def load_and_map_from_data_gov_dataset_url(dataset_url: str) -> pd.DataFrame:
    """Load all compatible resources from a catalog dataset page and map them."""
    dataset_id = extract_dataset_id_from_data_gov_url(dataset_url)
    if not dataset_id:
        raise ValueError(f"Could not extract dataset id from URL: {dataset_url}")

    urls = resources_from_data_gov_dataset_id(dataset_id)
    if not urls:
        raise ValueError(
            "No CSV/JSON resources were found for this catalog.data.gov dataset page."
        )

    return load_and_map_from_resource_urls(urls, label="Dataset resources")


def load_standard(path: Path) -> pd.DataFrame:
    """Load baseline museums CSV and verify required key columns exist."""
    frame = pd.read_csv(path, low_memory=False)
    missing = STANDARD_REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(
            f"Missing required standard columns in {path.name}: {sorted(missing)}"
        )
    return frame


def map_incoming_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Map incoming frame into project schema.

    Flow:
    - If already standard schema, return as-is.
    - If alternate DC schema, map known columns.
    - Otherwise, use interactive manual mapping.
    """

    if STANDARD_REQUIRED.issubset(frame.columns):
        return frame

    if ALT_REQUIRED.issubset(frame.columns):
        mapped = pd.DataFrame(
            {
                "Museum Name": frame["DCGISPLACE_NAMES_PTNAME"],
                "Museum Type": frame["MARVW_PLACE_NAME_CATEGORIESCATEGORY"],
                "State (Administrative Location)": "DC",
                "Street Address (Administrative Location)": frame[
                    "DCGISADDRESSES_PTADDRESS"
                ],
                "Institution Name": pd.NA,
                "Tax Period": pd.NA,
                "Income": pd.NA,
                "Revenue": pd.NA,
            }
        )
        return mapped

    return manual_map_incoming_frame(frame)


def load_and_map_incoming_source(source: str) -> pd.DataFrame:
    """Load one source and map it to target schema (handles dataset-page URLs)."""
    dataset_id = extract_dataset_id_from_data_gov_url(source) if is_url(source) else None
    if dataset_id:
        return load_and_map_from_data_gov_dataset_url(source)

    # If this is a webpage URL (not a direct data file), discover downloadable resources.
    if is_url(source) and not _looks_like_download_url(source):
        discovered_links = discover_download_links_from_webpage(source)
        if discovered_links:
            chosen_links = _prompt_select_resource_urls(
                discovered_links,
                label="Webpage download links",
            )
            return load_and_map_from_resource_urls(
                chosen_links,
                label="Webpage download links",
            )

    frame = read_table(source)
    return map_incoming_frame(frame)


def load_raw_incoming_source(source: str) -> pd.DataFrame:
    """
    Load one source as a raw dataset without applying museum schema mapping.

    Useful for scrape-only workflows (e.g., Wikipedia dataset creation).
    """
    dataset_id = extract_dataset_id_from_data_gov_url(source) if is_url(source) else None
    if dataset_id:
        urls = resources_from_data_gov_dataset_id(dataset_id)
        if not urls:
            raise ValueError(
                "No CSV/JSON resources were found for this catalog.data.gov dataset page."
            )
        return load_raw_from_resource_urls(urls, label="Dataset resources")

    if is_url(source) and _is_wikipedia_url(source):
        return scrape_wikipedia_tables(source)

    if is_url(source) and not _looks_like_download_url(source):
        discovered_links = discover_download_links_from_webpage(source)
        if discovered_links:
            chosen_links = _prompt_select_resource_urls(
                discovered_links,
                label="Webpage download links",
            )
            return load_raw_from_resource_urls(
                chosen_links,
                label="Webpage download links",
            )

    return read_table(source)


def build_output_path(
    file_name_or_path: str,
    output_folder: str,
    use_dated_subfolder: bool,
) -> Path:
    """
    Build an output path for generated datasets.

        Behavior:
    - If caller passes a plain filename (no directory), file is placed in
      output_folder/YYYY-MM-DD/filename.
    - If caller passes a path with a directory (or absolute path), that explicit path is used.

    Why this design:
    - Date-based folders make repeated runs easy to audit and compare.
    - We avoid accidental overwrites from multiple experiments in one day.
    - Explicit paths still win when callers need full control.
    """
    raw_path = Path(file_name_or_path)

    # Respect explicit user intent first: absolute/relative-with-folder paths
    # should not be rewritten.
    if raw_path.is_absolute() or raw_path.parent != Path("."):
        final_path = raw_path
    else:
        # For plain filenames, organize outputs by run date for easy review,
        # traceability, and low-friction cleanup.
        run_folder = Path(output_folder)
        if use_dated_subfolder:
            run_folder = run_folder / date.today().isoformat()
        final_path = run_folder / raw_path

    final_path.parent.mkdir(parents=True, exist_ok=True)
    return final_path


def load_and_map_from_data_gov_search(query: str, max_datasets: int) -> pd.DataFrame:
    """Search data.gov, load discovered resources, and combine mapped frames."""
    urls = search_data_gov_resources(query=query, max_datasets=max_datasets)
    if not urls:
        raise ValueError("No CSV/JSON resources found from data.gov search results.")

    return load_and_map_from_resource_urls(urls, label="Online resources")


def prompt_for_incoming_source() -> str:
    """Prompt for incoming URL/path in interactive mode when --incoming is omitted."""
    print("No incoming source provided.")
    print("Enter a URL (preferred) or a local file path for incoming museum data.")
    print("Examples:")
    print("- https://example.org/museums.csv")
    print("- https://catalog.data.gov/dataset/public-library-survey-pls-2022")
    print("- alternatemuseums.csv")

    while True:
        user_input = input("Incoming URL/path (or 'q' to quit): ").strip()
        if not user_input:
            print("Please enter a URL or file path.")
            continue
        if user_input.lower() in {"q", "quit", "exit"}:
            raise SystemExit("Cancelled by user.")
        return user_input


def build_match_key(frame: pd.DataFrame) -> pd.Series:
    """Build normalized duplicate key from museum name + state."""
    names = normalize_text(frame.get("Museum Name", pd.Series(dtype="string")))
    states = normalize_text(
        frame.get("State (Administrative Location)", pd.Series(dtype="string"))
    )
    return names + "||" + states


def find_new_records(base_df: pd.DataFrame, incoming_df: pd.DataFrame) -> pd.DataFrame:
    """Return incoming rows with valid key fields that are not already in baseline."""
    base_keys = set(build_match_key(base_df))
    incoming_keys = build_match_key(incoming_df)

    incoming = incoming_df.copy()
    incoming["_match_key"] = incoming_keys

    has_basic_info = (
        normalize_text(incoming["Museum Name"]).ne("")
        & normalize_text(incoming["State (Administrative Location)"]).ne("")
    )
    is_new = ~incoming["_match_key"].isin(base_keys)

    result = incoming[has_basic_info & is_new].drop(columns=["_match_key"])
    return result


def parse_args() -> argparse.Namespace:
    """Define CLI options for baseline/source modes and output behavior."""
    parser = argparse.ArgumentParser(
        description=(
            "Find new museum records by comparing an incoming CSV to an existing "
            "museums.csv baseline and write only unseen records to a new CSV."
        )
    )
    parser.add_argument(
        "--base",
        default="museums.csv",
        help="Path to baseline museums CSV (default: museums.csv)",
    )
    parser.add_argument(
        "--incoming",
        default="",
        help=(
            "Path or URL to incoming museum-like data. Supports museums.csv schema or "
            "alternatemuseums.csv schema. Can also be a webpage URL containing CSV/JSON/ZIP "
            "download links. If omitted, you will be prompted."
        ),
    )
    parser.add_argument(
        "--search-query",
        default="",
        help=(
            "Optional internet search query for data.gov. If provided, the script "
            "fetches matching CSV/JSON resources online and compares them to baseline."
        ),
    )
    parser.add_argument(
        "--max-datasets",
        type=int,
        default=10,
        help="Maximum number of data.gov datasets to inspect in search mode (default: 10).",
    )
    parser.add_argument(
        "--output",
        default="new_museum_records.csv",
        help="Path to output CSV for new records (default: new_museum_records.csv)",
    )
    parser.add_argument(
        "--output-folder",
        default="generated_datasets",
        help=(
            "Folder used for generated datasets when output args are plain filenames "
            "(default: generated_datasets, with date-based subfolders unless disabled)."
        ),
    )
    parser.add_argument(
        "--flat-output-folder",
        action="store_true",
        help=(
            "Disable date-based subfolders and write plain-filename outputs directly "
            "inside --output-folder."
        ),
    )
    parser.add_argument(
        "--scrape-only-output",
        default="",
        help=(
            "Optional path to write a raw scraped dataset (no dedupe/museum mapping). "
            "Works well for Wikipedia pages and webpage download indexes."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """
    Orchestrate load -> map -> compare -> export.

    Reading tip: this function is the best high-level summary of script behavior.
    Testing tip: run this script from terminal using one of the examples in the
    module docstring and verify the printed counts + output file path.
    """
    args = parse_args()

    # Configure output strategy once so every write path follows the same rule.
    use_dated_subfolder = not args.flat_output_folder

    output_path = build_output_path(
        args.output,
        args.output_folder,
        use_dated_subfolder=use_dated_subfolder,
    )

    # Mode A: scrape-only dataset creation (no museum mapping/dedupe).
    if args.scrape_only_output.strip():
        incoming_source = args.incoming.strip() or prompt_for_incoming_source()
        raw_df = load_raw_incoming_source(incoming_source)
        scrape_output_path = build_output_path(
            args.scrape_only_output.strip(),
            args.output_folder,
            use_dated_subfolder=use_dated_subfolder,
        )
        raw_df.to_csv(scrape_output_path, index=False)
        print(f"Incoming source: {incoming_source}")
        print(f"Raw scraped rows: {len(raw_df):,}")
        print(f"Raw scraped columns: {len(raw_df.columns):,}")
        print(f"Scrape-only output file: {scrape_output_path.resolve()}")
        return

    # Mode B: museum-incremental mode (map -> compare -> write only new rows).
    base_path = Path(args.base)
    base_df = load_standard(base_path)

    if args.search_query.strip():
        incoming_df = load_and_map_from_data_gov_search(
            query=args.search_query.strip(),
            max_datasets=args.max_datasets,
        )
        incoming_source_label = f"data.gov search: {args.search_query.strip()}"
    else:
        incoming_source = args.incoming.strip() or prompt_for_incoming_source()
        incoming_df = load_and_map_incoming_source(incoming_source)
        incoming_source_label = incoming_source

    new_records = find_new_records(base_df, incoming_df)
    new_records.to_csv(output_path, index=False)

    print(f"Baseline rows: {len(base_df):,}")
    print(f"Incoming source: {incoming_source_label}")
    print(f"Incoming rows: {len(incoming_df):,}")
    print(f"New rows written: {len(new_records):,}")
    print(f"Output file: {output_path.resolve()}")


if __name__ == "__main__":
    main()
