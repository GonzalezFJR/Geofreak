#!/usr/bin/env python3
"""
Download and build all GeoFreak data:
  1. Country dataset (CSV) from RestCountries + Wikipedia-sourced extras
  2. GeoJSON boundaries from Natural Earth (via GitHub)
  3. Flag SVGs from flagcdn / hatscripts/circle-flags

Usage:
    python scripts/download_data.py
"""

import csv
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import requests
import pandas as pd

# ─── Paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "static" / "data"
GEOJSON_DIR = DATA_DIR / "geojson"
FLAGS_DIR = DATA_DIR / "images" / "flags"
CSV_PATH = DATA_DIR / "countries.csv"

for d in [DATA_DIR, GEOJSON_DIR, FLAGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ─── 1. Download GeoJSON ────────────────────────────────────────────────────
GEOJSON_URL = (
    "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
)

# Fallback: Natural Earth 110m from GitHub
NATURAL_EARTH_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
    "ne_110m_admin_0_countries.geojson"
)


def download_geojson():
    """Download world GeoJSON and split into individual country files."""
    all_path = GEOJSON_DIR / "all_countries.geojson"

    if all_path.exists():
        print("  ✓ GeoJSON already exists, skipping download.")
        return

    print("  ⬇ Downloading world GeoJSON…")
    resp = None
    for url in [GEOJSON_URL, NATURAL_EARTH_URL]:
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            break
        except Exception as e:
            print(f"    ⚠ Failed with {url}: {e}")
            resp = None

    if resp is None:
        print("  ✗ Could not download GeoJSON from any source.")
        return

    data = resp.json()

    # Normalise property keys
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        # Ensure ISO_A3 key exists
        if "ISO_A3" not in props:
            for key in ["ISO_A3", "iso_a3", "ADM0_A3", "adm0_a3", "ISO3166-1-Alpha-3"]:
                if key in props:
                    props["ISO_A3"] = props[key]
                    break
        if "ADMIN" not in props:
            for key in ["ADMIN", "admin", "name", "NAME", "GEOUNIT"]:
                if key in props:
                    props["ADMIN"] = props[key]
                    break

    # Save combined file
    with open(all_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"    ✓ Saved combined GeoJSON ({len(data.get('features', []))} features)")

    # Split into individual files
    count = 0
    for feature in data.get("features", []):
        iso = feature.get("properties", {}).get("ISO_A3", "")
        if iso and iso != "-99" and len(iso) == 3:
            fc = {"type": "FeatureCollection", "features": [feature]}
            path = GEOJSON_DIR / f"{iso}.geojson"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(fc, f, ensure_ascii=False)
            count += 1
    print(f"    ✓ Split into {count} individual country files")


# ─── 2. Build country dataset ───────────────────────────────────────────────
REST_COUNTRIES_BASE = "https://restcountries.com/v3.1/all"

# RestCountries limits to 10 fields per request, so we batch them.
REST_FIELDS_BATCHES = [
    "name,cca2,cca3,capital,capitalInfo,region,subregion,continents,latlng,population",
    "cca3,area,languages,currencies,flag,flags,coatOfArms,gini,car,tld",
    "cca3,timezones,borders,landlocked,unMember,independent,startOfWeek,maps",
]


def fetch_restcountries() -> list[dict]:
    """Fetch data from RestCountries API in multiple batches and merge."""
    print("  ⬇ Fetching RestCountries API (batched fields)…")
    merged: dict[str, dict] = {}  # cca3 -> merged data

    for i, fields in enumerate(REST_FIELDS_BATCHES):
        url = f"{REST_COUNTRIES_BASE}?fields={fields}"
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            batch = resp.json()
            print(f"    Batch {i+1}: {len(batch)} entries")
            for entry in batch:
                cca3 = entry.get("cca3", "")
                if not cca3:
                    continue
                if cca3 not in merged:
                    merged[cca3] = {}
                merged[cca3].update(entry)
            time.sleep(0.5)
        except Exception as e:
            print(f"    ⚠ Batch {i+1} failed: {e}")
            raise

    return list(merged.values())


def build_dataset():
    """Build comprehensive countries.csv from RestCountries + supplements."""
    if CSV_PATH.exists():
        print("  ✓ countries.csv already exists, skipping build.")
        return

    raw = fetch_restcountries()
    print(f"    Received {len(raw)} countries")

    rows = []
    for c in raw:
        name_common = c.get("name", {}).get("common", "")
        name_official = c.get("name", {}).get("official", "")

        # ISO codes
        iso_a2 = c.get("cca2", "")
        iso_a3 = c.get("cca3", "")

        # Region
        region = c.get("region", "")
        subregion = c.get("subregion", "")

        # Capital
        capitals = c.get("capital", [])
        capital = capitals[0] if capitals else ""

        # Latlng
        latlng = c.get("latlng", [None, None])
        lat = latlng[0] if len(latlng) > 0 else ""
        lon = latlng[1] if len(latlng) > 1 else ""

        # Capital latlng
        cap_info = c.get("capitalInfo", {}).get("latlng", [None, None])
        capital_lat = cap_info[0] if cap_info and len(cap_info) > 0 else ""
        capital_lon = cap_info[1] if cap_info and len(cap_info) > 1 else ""

        # Population & area
        population = c.get("population", "")
        area = c.get("area", "")

        # Density
        density = ""
        if population and area and area > 0:
            density = round(population / area, 2)

        # Languages
        languages = c.get("languages", {})
        official_languages = json.dumps(list(languages.values()), ensure_ascii=False) if languages else "[]"
        main_language = list(languages.values())[0] if languages else ""
        secondary_language = list(languages.values())[1] if len(languages) > 1 else ""

        # Currencies
        currencies = c.get("currencies", {})
        currency_code = ""
        currency_name = ""
        if currencies:
            first_key = list(currencies.keys())[0]
            currency_code = first_key
            currency_name = currencies[first_key].get("name", "")

        # Flag emoji and URLs
        flag_emoji = c.get("flag", "")
        flag_png = c.get("flags", {}).get("png", "")
        flag_svg = c.get("flags", {}).get("svg", "")

        # Coat of arms
        coat_of_arms_svg = c.get("coatOfArms", {}).get("svg", "")

        # Gini
        gini_data = c.get("gini", {})
        gini = ""
        gini_year = ""
        if gini_data:
            gini_year = max(gini_data.keys())
            gini = gini_data[gini_year]

        # Driving side, TLDs, timezones
        car_side = c.get("car", {}).get("side", "")
        tld = ", ".join(c.get("tld", []))
        timezones = ", ".join(c.get("timezones", []))

        # Borders
        borders = ", ".join(c.get("borders", []))

        # Continent
        continents = c.get("continents", [])
        continent = continents[0] if continents else ""

        # Landlocked
        landlocked = c.get("landlocked", False)

        # UN member
        un_member = c.get("unMember", False)

        # Independent
        independent = c.get("independent", "")

        # Start of week
        start_of_week = c.get("startOfWeek", "")

        # Maps
        google_maps = c.get("maps", {}).get("googleMaps", "")
        osm_maps = c.get("maps", {}).get("openStreetMaps", "")

        row = {
            "iso_a2": iso_a2,
            "iso_a3": iso_a3,
            "name": name_common,
            "name_official": name_official,
            "capital": capital,
            "capital_lat": capital_lat,
            "capital_lon": capital_lon,
            "region": region,
            "subregion": subregion,
            "continent": continent,
            "lat": lat,
            "lon": lon,
            "population": population,
            "area_km2": area,
            "density_per_km2": density,
            "main_language": main_language,
            "secondary_language": secondary_language,
            "official_languages": official_languages,
            "currency_code": currency_code,
            "currency_name": currency_name,
            "gini": gini,
            "gini_year": gini_year,
            "landlocked": landlocked,
            "un_member": un_member,
            "independent": independent,
            "borders": borders,
            "timezones": timezones,
            "tld": tld,
            "car_side": car_side,
            "start_of_week": start_of_week,
            "flag_emoji": flag_emoji,
            "flag_svg_url": flag_svg,
            "flag_png_url": flag_png,
            "coat_of_arms_svg_url": coat_of_arms_svg,
            "google_maps": google_maps,
            "osm_maps": osm_maps,
            "top_cities": "[]",
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df = df.sort_values("name").reset_index(drop=True)

    # ── Enrich with World Bank / supplementary data ──
    df = enrich_with_worldbank(df)

    df.to_csv(CSV_PATH, index=False)
    print(f"    ✓ Saved {len(df)} countries to {CSV_PATH}")


def enrich_with_worldbank(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich dataset with World Bank indicators."""
    indicators = {
        "SP.DYN.CBRT.IN": "birth_rate",          # Birth rate per 1000
        "SM.POP.TOTL.ZS": "immigrant_pct",        # International migrant stock (% of pop)
        "NY.GDP.MKTP.CD": "gdp_usd",              # GDP current USD
        "NY.GDP.PCAP.CD": "gdp_per_capita_usd",   # GDP per capita USD
        "SP.DYN.LE00.IN": "life_expectancy",       # Life expectancy at birth
        "SE.ADT.LITR.ZS": "literacy_rate",         # Literacy rate
        "SP.URB.TOTL.IN.ZS": "urban_population_pct",  # Urban population %
        "EN.ATM.CO2E.PC": "co2_per_capita",        # CO2 emissions per capita
        "SI.POV.GINI": "gini_wb",                  # Gini index (World Bank)
    }

    # Initialize columns
    for col in indicators.values():
        df[col] = ""

    # HDI - we'll add a placeholder; HDI comes from UNDP, not World Bank
    df["hdi"] = ""

    # Additional geographic columns
    df["highest_point"] = ""
    df["lowest_point"] = ""
    df["lat_max"] = ""
    df["lat_min"] = ""
    df["elevation_max_m"] = ""
    df["elevation_min_m"] = ""
    df["religion_major"] = ""
    df["most_populated_city"] = ""
    df["capital_population"] = ""

    print("  ⬇ Fetching World Bank indicators…")
    for indicator_code, col_name in indicators.items():
        try:
            url = f"https://api.worldbank.org/v2/country/all/indicator/{indicator_code}?date=2020:2024&format=json&per_page=20000"
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if len(data) < 2 or not data[1]:
                continue

            # Build a mapping: ISO2 -> most recent value
            values = {}
            for entry in data[1]:
                iso2 = entry.get("countryiso3code", "") or entry.get("country", {}).get("id", "")
                val = entry.get("value")
                year = entry.get("date", "0")
                if val is not None and iso2:
                    if iso2 not in values or year > values[iso2][1]:
                        values[iso2] = (val, year)

            # Map to dataframe
            for iso3, (val, year) in values.items():
                mask = df["iso_a3"] == iso3
                if mask.any():
                    if isinstance(val, float):
                        val = round(val, 4)
                    df.loc[mask, col_name] = val

            print(f"    ✓ {col_name}: {len(values)} values")
            time.sleep(0.3)  # Be nice to API

        except Exception as e:
            print(f"    ⚠ Failed to fetch {indicator_code}: {e}")

    # Use World Bank Gini where RestCountries Gini is missing
    for idx, row in df.iterrows():
        if not row["gini"] and row["gini_wb"]:
            df.at[idx, "gini"] = row["gini_wb"]

    # Fetch HDI from UNDP (simplified - use a static well-known list)
    df = enrich_hdi(df)

    # Fetch top cities from GeoNames-style data
    df = enrich_cities(df)

    return df


def enrich_hdi(df: pd.DataFrame) -> pd.DataFrame:
    """Try to fetch HDI data from UNDP API or use embedded data."""
    # HDI values for major countries (2023/2024 estimates)
    # Source: UNDP Human Development Report
    hdi_data = {
        "NOR": 0.966, "IRL": 0.945, "CHE": 0.962, "ISL": 0.959, "HKG": 0.952,
        "DNK": 0.952, "SWE": 0.947, "DEU": 0.942, "NLD": 0.941, "FIN": 0.940,
        "AUS": 0.946, "SGP": 0.939, "GBR": 0.929, "BEL": 0.937, "NZL": 0.936,
        "CAN": 0.935, "USA": 0.921, "AUT": 0.926, "ISR": 0.919, "JPN": 0.920,
        "LIE": 0.935, "SVN": 0.918, "KOR": 0.929, "LUX": 0.927, "ESP": 0.911,
        "FRA": 0.903, "CZE": 0.900, "MLT": 0.918, "EST": 0.899, "ITA": 0.895,
        "ARE": 0.911, "GRC": 0.893, "CYP": 0.907, "LTU": 0.879, "POL": 0.881,
        "AND": 0.884, "LVA": 0.879, "PRT": 0.874, "SVK": 0.855, "HUN": 0.851,
        "SAU": 0.875, "BHR": 0.888, "CHL": 0.860, "HRV": 0.858, "QAT": 0.855,
        "ARG": 0.849, "BRN": 0.829, "MNE": 0.844, "ROU": 0.827, "PLW": 0.826,
        "KAZ": 0.811, "RUS": 0.822, "BLR": 0.808, "TUR": 0.838, "URY": 0.830,
        "BGR": 0.795, "PAN": 0.805, "MYS": 0.803, "MUS": 0.796, "THA": 0.800,
        "SRB": 0.805, "GEO": 0.802, "CHN": 0.788, "MKD": 0.770, "CRI": 0.806,
        "MEX": 0.781, "CUB": 0.764, "COL": 0.758, "BIH": 0.768, "AZE": 0.745,
        "ARM": 0.786, "PER": 0.762, "ECU": 0.765, "BRA": 0.760, "UKR": 0.773,
        "MDA": 0.763, "ALB": 0.789, "TUN": 0.732, "LKA": 0.780, "FJI": 0.730,
        "DZA": 0.745, "MNG": 0.741, "DOM": 0.767, "JOR": 0.736, "JAM": 0.709,
        "TKM": 0.744, "LBN": 0.723, "ZAF": 0.717, "PRY": 0.717, "EGY": 0.731,
        "IDN": 0.713, "VNM": 0.726, "PHL": 0.710, "BOL": 0.698, "MAR": 0.698,
        "IRQ": 0.686, "SLV": 0.675, "KGZ": 0.701, "UZB": 0.727, "TJK": 0.679,
        "IND": 0.644, "GHA": 0.602, "KEN": 0.601, "PAK": 0.540, "NGA": 0.539,
        "BGD": 0.670, "MMR": 0.585, "ETH": 0.492, "COD": 0.479, "TZA": 0.549,
        "NER": 0.394, "TCD": 0.394, "CAF": 0.387, "SSD": 0.385, "SOM": 0.380,
        "AFG": 0.462, "MLI": 0.410, "BFA": 0.449, "SLE": 0.477, "MOZ": 0.461,
        "LBR": 0.487, "GIN": 0.465, "BDI": 0.426, "YEM": 0.455, "HTI": 0.535,
        "NPL": 0.601, "CMR": 0.576, "ZWE": 0.593, "AGO": 0.586, "SEN": 0.511,
        "SDN": 0.516, "RWA": 0.548, "UGA": 0.550, "MWI": 0.512, "BEN": 0.504,
        "TGO": 0.539, "GMB": 0.500, "MDG": 0.501, "CIV": 0.534, "ZMB": 0.565,
        "LAO": 0.620, "KHM": 0.600, "BTN": 0.666, "GAB": 0.706, "BWA": 0.708,
        "NAM": 0.610, "CPV": 0.662, "GTM": 0.627, "HND": 0.621, "NIC": 0.667,
        "SWZ": 0.597, "LSO": 0.514, "PNG": 0.568, "VUT": 0.607, "SLB": 0.564,
        "WSM": 0.707, "TON": 0.745, "MHL": 0.639, "FSM": 0.628, "KIR": 0.623,
        "TUV": 0.641, "NRU": 0.740, "TLS": 0.607, "COM": 0.596, "STP": 0.618,
        "GNQ": 0.596, "DJI": 0.509, "ERI": 0.492, "MRT": 0.540, "GNB": 0.483,
        "KWT": 0.831, "OMN": 0.816, "LBY": 0.718, "SYR": 0.577, "PSE": 0.715,
        "VEN": 0.691, "GUY": 0.714, "SUR": 0.738, "TTO": 0.810, "BLZ": 0.700,
        "BRB": 0.809, "ATG": 0.794, "KNA": 0.777, "LCA": 0.725, "VCT": 0.706,
        "GRD": 0.795, "DMA": 0.720, "CUW": 0.810, "ABW": 0.810,
        "IRN": 0.774, "TWN": 0.926, "PRK": 0.574,
    }
    for iso3, hdi_val in hdi_data.items():
        mask = df["iso_a3"] == iso3
        if mask.any():
            df.loc[mask, "hdi"] = hdi_val

    return df


def enrich_cities(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich with most populated city and top cities list using RestCountries capital info."""
    # For now, set most_populated_city same as capital for countries without better data
    # The top_cities JSON array will be populated by a separate enrichment step
    for idx, row in df.iterrows():
        if row["capital"] and not row["most_populated_city"]:
            df.at[idx, "most_populated_city"] = row["capital"]
    return df


# ─── 3. Download flags ──────────────────────────────────────────────────────

FLAG_CDN_URL = "https://flagcdn.com/w640/{code}.png"
FLAG_SVG_URL = "https://flagcdn.com/{code}.svg"


def download_flags():
    """Download flag images for all countries."""
    if not CSV_PATH.exists():
        print("  ⚠ countries.csv not found, run build_dataset first")
        return

    df = pd.read_csv(CSV_PATH, keep_default_na=False)
    existing = set(f.stem.upper() for f in FLAGS_DIR.glob("*.svg"))

    to_download = []
    for _, row in df.iterrows():
        iso2 = row.get("iso_a2", "").strip()
        iso3 = row.get("iso_a3", "").strip()
        if iso3 and iso3 not in existing and iso2:
            to_download.append((iso2.lower(), iso3))

    if not to_download:
        print(f"  ✓ All {len(existing)} flags already downloaded")
        return

    print(f"  ⬇ Downloading {len(to_download)} flags…")
    success = 0
    for iso2_lower, iso3 in to_download:
        # Try SVG from flagcdn
        url = FLAG_SVG_URL.format(code=iso2_lower)
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                path = FLAGS_DIR / f"{iso3}.svg"
                with open(path, "wb") as f:
                    f.write(resp.content)
                success += 1
                continue
        except Exception:
            pass

        # Fallback: PNG
        url = FLAG_CDN_URL.format(code=iso2_lower)
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                path = FLAGS_DIR / f"{iso3}.png"
                with open(path, "wb") as f:
                    f.write(resp.content)
                success += 1
        except Exception as e:
            print(f"    ⚠ Failed to download flag for {iso3}: {e}")

        time.sleep(0.1)  # Rate limiting

    print(f"    ✓ Downloaded {success} flags")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("🌍 GeoFreak Data Downloader")
    print("=" * 50)

    print("\n📦 Step 1: GeoJSON boundaries")
    download_geojson()

    print("\n📊 Step 2: Country dataset")
    build_dataset()

    print("\n🏳️  Step 3: Flag images")
    download_flags()

    print("\n✅ All done!")
    print(f"   Data directory: {DATA_DIR}")


if __name__ == "__main__":
    main()
