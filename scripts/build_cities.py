#!/usr/bin/env python3
"""
Build a comprehensive cities dataset for GeoFreak.

Sources:
  - GeoNames cities15000 (all cities with population > 15,000)
  - Cross-referenced with countries.csv for capital status

Target: ~600 cities including:
  - All cities with 1M+ population
  - Top ~10 cities per country (or all if fewer)
  - All national capitals

Output:
  - static/data/cities.csv
  - Updates countries.csv top_cities column
"""

import csv
import io
import json
import os
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "static" / "data"
CITIES_CSV = DATA_DIR / "cities.csv"
COUNTRIES_CSV = DATA_DIR / "countries.csv"

GEONAMES_URL = "https://download.geonames.org/export/dump/cities15000.zip"

# GeoNames column definitions (TSV)
GEONAMES_COLS = [
    "geonameid", "name", "asciiname", "alternatenames",
    "latitude", "longitude", "feature_class", "feature_code",
    "country_code", "cc2", "admin1_code", "admin2_code",
    "admin3_code", "admin4_code", "population", "elevation",
    "dem", "timezone", "modification_date",
]

# Country codes (ISO2) to ISO3 mapping — we'll build from countries.csv
# Feature codes for capitals: PPLC = capital, PPLG = seat of government
CAPITAL_FEATURE_CODES = {"PPLC", "PPLG"}


def download_geonames() -> pd.DataFrame:
    """Download and parse GeoNames cities15000."""
    cache_path = DATA_DIR / "cities15000.txt"

    if cache_path.exists():
        print("  ✓ Using cached GeoNames data")
    else:
        print("  ⬇ Downloading GeoNames cities15000…")
        resp = requests.get(GEONAMES_URL, timeout=120)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extract("cities15000.txt", DATA_DIR)
        print(f"    ✓ Downloaded ({cache_path.stat().st_size / 1e6:.1f} MB)")

    df = pd.read_csv(
        cache_path,
        sep="\t",
        header=None,
        names=GEONAMES_COLS,
        dtype={"population": int, "latitude": float, "longitude": float},
        keep_default_na=False,
        quoting=csv.QUOTE_NONE,
        on_bad_lines="skip",
    )
    print(f"    Total GeoNames entries: {len(df)}")
    return df


def load_countries() -> pd.DataFrame:
    """Load countries dataset."""
    if not COUNTRIES_CSV.exists():
        raise FileNotFoundError(f"countries.csv not found at {COUNTRIES_CSV}")
    return pd.read_csv(COUNTRIES_CSV, keep_default_na=False)


def build_iso2_to_iso3(countries_df: pd.DataFrame) -> dict:
    """Build ISO2 -> ISO3 mapping."""
    mapping = {}
    for _, row in countries_df.iterrows():
        iso2 = row.get("iso_a2", "").strip()
        iso3 = row.get("iso_a3", "").strip()
        if iso2 and iso3:
            mapping[iso2] = iso3
    return mapping


def build_capitals_set(countries_df: pd.DataFrame) -> dict:
    """Build a set of (iso3, capital_name) for capital identification."""
    capitals = {}
    for _, row in countries_df.iterrows():
        iso3 = row.get("iso_a3", "").strip()
        capital = row.get("capital", "").strip()
        if iso3 and capital:
            capitals[iso3] = capital.lower()
    return capitals


def select_cities(geonames_df: pd.DataFrame, countries_df: pd.DataFrame) -> pd.DataFrame:
    """Select ~600 most important cities."""
    iso2_to_iso3 = build_iso2_to_iso3(countries_df)
    capitals_map = build_capitals_set(countries_df)

    # Add ISO3 column
    geonames_df["iso_a3"] = geonames_df["country_code"].map(iso2_to_iso3)

    # Filter out entries without a valid ISO3
    df = geonames_df[geonames_df["iso_a3"].notna() & (geonames_df["iso_a3"] != "")].copy()

    # Mark capitals
    def is_capital(row):
        iso3 = row["iso_a3"]
        if row["feature_code"] in CAPITAL_FEATURE_CODES:
            return True
        cap_name = capitals_map.get(iso3, "")
        if cap_name and (
            row["name"].lower() == cap_name
            or row["asciiname"].lower() == cap_name
        ):
            return True
        return False

    df["is_capital"] = df.apply(is_capital, axis=1)

    # Strategy:
    # 1. All capitals (always include)
    # 2. All cities with population >= 1,000,000
    # 3. Top N cities per country to get ~600 total

    capitals = df[df["is_capital"]].copy()
    big_cities = df[df["population"] >= 1_000_000].copy()

    # Combine mandatory cities
    mandatory_ids = set(capitals["geonameid"].tolist() + big_cities["geonameid"].tolist())
    print(f"    Capitals found: {len(capitals)}")
    print(f"    Cities with 1M+ pop: {len(big_cities)}")
    print(f"    Mandatory (unique): {len(mandatory_ids)}")

    # Now add top cities per country
    # Sort all cities by population descending
    df_sorted = df.sort_values("population", ascending=False)

    selected_ids = set(mandatory_ids)
    # For each country, ensure we have up to 10 cities
    for iso3, group in df_sorted.groupby("iso_a3"):
        country_selected = [gid for gid in group["geonameid"] if gid in selected_ids]
        remaining = group[~group["geonameid"].isin(selected_ids)]

        needed = max(0, 10 - len(country_selected))
        if needed > 0:
            top_extra = remaining.head(needed)
            selected_ids.update(top_extra["geonameid"].tolist())

    # Build final dataframe
    result = df[df["geonameid"].isin(selected_ids)].copy()
    result = result.sort_values(["iso_a3", "population"], ascending=[True, False])

    # Get country names
    country_names = dict(zip(countries_df["iso_a3"], countries_df["name"]))
    result["country_name"] = result["iso_a3"].map(country_names).fillna("")

    # Select and rename columns
    final = result[["geonameid", "name", "asciiname", "latitude", "longitude",
                     "country_code", "iso_a3", "country_name", "population",
                     "is_capital", "feature_code", "timezone", "elevation", "dem"]].copy()
    final = final.rename(columns={
        "latitude": "lat",
        "longitude": "lon",
        "country_code": "iso_a2",
    })

    # Convert is_capital to bool
    final["is_capital"] = final["is_capital"].astype(bool)

    print(f"    Final city count: {len(final)}")
    return final


def update_countries_csv(cities_df: pd.DataFrame, countries_df: pd.DataFrame) -> pd.DataFrame:
    """Update top_cities and most_populated_city in countries.csv."""
    # Build top_cities JSON per country
    top_cities_map = {}
    most_populated_map = {}
    capital_pop_map = {}

    for iso3, group in cities_df.groupby("iso_a3"):
        sorted_group = group.sort_values("population", ascending=False)
        cities_list = []
        for _, row in sorted_group.head(10).iterrows():
            cities_list.append({
                "name": row["name"],
                "population": int(row["population"]),
                "lat": round(float(row["lat"]), 4),
                "lon": round(float(row["lon"]), 4),
                "is_capital": bool(row["is_capital"]),
            })
        top_cities_map[iso3] = json.dumps(cities_list, ensure_ascii=False)

        # Most populated city (by population)
        if len(sorted_group) > 0:
            most_populated_map[iso3] = sorted_group.iloc[0]["name"]

        # Capital population
        cap = sorted_group[sorted_group["is_capital"]]
        if len(cap) > 0:
            capital_pop_map[iso3] = int(cap.iloc[0]["population"])

    # Update countries_df
    for idx, row in countries_df.iterrows():
        iso3 = row["iso_a3"]
        if iso3 in top_cities_map:
            countries_df.at[idx, "top_cities"] = top_cities_map[iso3]
        if iso3 in most_populated_map:
            countries_df.at[idx, "most_populated_city"] = most_populated_map[iso3]
        if iso3 in capital_pop_map:
            countries_df.at[idx, "capital_population"] = capital_pop_map[iso3]

    return countries_df


def main():
    print("🏙️  GeoFreak Cities Dataset Builder")
    print("=" * 50)

    print("\n📦 Step 1: Load GeoNames data")
    geonames_df = download_geonames()

    print("\n📊 Step 2: Load countries data")
    countries_df = load_countries()
    print(f"    Countries: {len(countries_df)}")

    print("\n🔍 Step 3: Select important cities")
    cities_df = select_cities(geonames_df, countries_df)

    # Stats
    n_capitals = cities_df["is_capital"].sum()
    n_million = (cities_df["population"] >= 1_000_000).sum()
    n_countries_covered = cities_df["iso_a3"].nunique()
    print(f"\n📈 Stats:")
    print(f"    Total cities: {len(cities_df)}")
    print(f"    Capitals: {n_capitals}")
    print(f"    1M+ cities: {n_million}")
    print(f"    Countries covered: {n_countries_covered}")

    print("\n💾 Step 4: Save cities.csv")
    cities_df.to_csv(CITIES_CSV, index=False)
    print(f"    ✓ Saved to {CITIES_CSV}")

    print("\n🔄 Step 5: Update countries.csv with top_cities")
    countries_df = update_countries_csv(cities_df, countries_df)
    countries_df.to_csv(COUNTRIES_CSV, index=False)
    print(f"    ✓ Updated {COUNTRIES_CSV}")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
