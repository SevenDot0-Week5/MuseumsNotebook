from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import urlopen

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


def normalize_text(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.strip()
        .str.upper()
        .fillna("")
    )


def is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def read_table(source: str) -> pd.DataFrame:
    source_lower = source.lower()

    if source_lower.endswith(".json"):
        return pd.read_json(source)

    if source_lower.endswith(".csv"):
        return pd.read_csv(source, low_memory=False)

    try:
        return pd.read_csv(source, low_memory=False)
    except Exception:
        return pd.read_json(source)


def search_data_gov_resources(query: str, max_datasets: int) -> list[str]:
    api_url = (
        "https://catalog.data.gov/api/3/action/package_search"
        f"?q={quote_plus(query)}&rows={max_datasets}"
    )

    with urlopen(api_url) as response:
        payload = json.loads(response.read().decode("utf-8"))

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


def load_standard(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    missing = STANDARD_REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(
            f"Missing required standard columns in {path.name}: {sorted(missing)}"
        )
    return frame


def map_incoming_frame(frame: pd.DataFrame) -> pd.DataFrame:

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

    raise ValueError(
        "Incoming file schema not recognized. Expected either museums.csv-like columns "
        "or alternatemuseums.csv-like columns."
    )


def load_and_map_incoming_source(source: str) -> pd.DataFrame:
    frame = read_table(source)
    return map_incoming_frame(frame)


def load_and_map_from_data_gov_search(query: str, max_datasets: int) -> pd.DataFrame:
    urls = search_data_gov_resources(query=query, max_datasets=max_datasets)
    if not urls:
        raise ValueError("No CSV/JSON resources found from data.gov search results.")

    mapped_frames: list[pd.DataFrame] = []
    skipped = 0

    for url in urls:
        try:
            mapped_frames.append(load_and_map_incoming_source(url))
        except Exception:
            skipped += 1

    if not mapped_frames:
        raise ValueError(
            "Resources were found online, but none matched supported museum schemas."
        )

    combined = pd.concat(mapped_frames, ignore_index=True, sort=False)
    print(f"Online resources found: {len(urls):,}")
    print(f"Online resources used: {len(mapped_frames):,}")
    print(f"Online resources skipped: {skipped:,}")
    return combined


def prompt_for_incoming_source() -> str:
    print("No incoming source provided.")
    print("Enter a URL (preferred) or a local file path for incoming museum data.")
    print("Examples:")
    print("- https://example.org/museums.csv")
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
    names = normalize_text(frame.get("Museum Name", pd.Series(dtype="string")))
    states = normalize_text(
        frame.get("State (Administrative Location)", pd.Series(dtype="string"))
    )
    return names + "||" + states


def find_new_records(base_df: pd.DataFrame, incoming_df: pd.DataFrame) -> pd.DataFrame:
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
            "alternatemuseums.csv schema. If omitted, you will be prompted."
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    base_path = Path(args.base)
    output_path = Path(args.output)

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
