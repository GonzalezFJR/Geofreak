#!/usr/bin/env python3
"""
Build a comprehensive world cities dataset for GeoFreak.

Sources (automated):
  1. GeoNames cities15000  — base city list (filter to 100k+, deduplicate)
  2. GeoNames alternateNamesV2  — multilingual names in es/en/fr/it/ru
  3. GeoNames admin1CodesASCII  — province/state names
  4. Open-Meteo Elevation API  — elevation at 90 m resolution (batch)
  5. Open-Meteo Historical API  — 1991-2020 climate normals (parallel)
  6. World Bank WDI API  — country-level economic / demographic indicators

Sources (optional, require manual download or known URL):
  7. WHO Air Quality DB v6.1  — PM2.5, PM10, NO2 per city
  8. UN WUP 2024  — metro (agglomeration) population + 10-yr growth

Target: ~5,500 cities with ≥100k population + all national capitals
Columns: ~38 (identity, admin, multilingual names, climate, economic, air quality)

Usage:
    python scripts/build_cities.py
    python scripts/build_cities.py --skip-climate   # skip Open-Meteo calls
    python scripts/build_cities.py --skip-altnames  # skip 200 MB download
    python scripts/build_cities.py --force          # ignore all caches
"""

from __future__ import annotations

import argparse
import csv
import difflib
import io
import json
import math
import sys
import time
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "static" / "data"
CACHE    = DATA_DIR / "_cache"
CACHE.mkdir(parents=True, exist_ok=True)

CITIES_CSV    = DATA_DIR / "cities.csv"
COUNTRIES_CSV = DATA_DIR / "countries.csv"
VAR_CONFIG    = DATA_DIR / "variable_config.json"

# ── GeoNames URLs ─────────────────────────────────────────────────────────────
CITIES_URL   = "https://download.geonames.org/export/dump/cities15000.zip"
ALTNAMES_URL = "https://download.geonames.org/export/dump/alternateNamesV2.zip"
ADMIN1_URL   = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"

# ── External optional URLs ────────────────────────────────────────────────────
# UN WUP 2024 — cities over 300k population time series
UN_WUP_URL = (
    "https://population.un.org/wup/assets/xls/WUP2024-F21-Cities_Over_300K.xlsx"
)
# WHO air quality: download manually from
# https://www.who.int/data/gho/data/themes/air-pollution/who-air-quality-database
# and save to CACHE/who_air_quality.xlsx
WHO_AQ_PATH = CACHE / "who_air_quality.xlsx"

# ── GeoNames column schema ────────────────────────────────────────────────────
GEONAMES_COLS = [
    "geonameid", "name", "asciiname", "alternatenames",
    "latitude", "longitude", "feature_class", "feature_code",
    "country_code", "cc2", "admin1_code", "admin2_code",
    "admin3_code", "admin4_code", "population", "elevation",
    "dem", "timezone", "modification_date",
]

# Feature-code taxonomy (populated places only)
FEATURE_PRIORITY = {
    "PPLC": 0, "PPLG": 1, "PPLA": 2,
    "PPLA2": 3, "PPLA3": 4, "PPL": 5,
}
INCLUDE_FEATURE_CODES = set(FEATURE_PRIORITY)
CAPITAL_CODES         = {"PPLC", "PPLG"}
ADMIN1_CODES          = {"PPLA"}

TARGET_LANGS    = {"es", "en", "fr", "it", "ru"}
MIN_POPULATION  = 100_000
DEDUP_RADIUS_KM = 15.0

# ── Climate constants ─────────────────────────────────────────────────────────
CLIMATE_START    = "1991-01-01"
CLIMATE_END      = "2020-12-31"
CLIMATE_WORKERS  = 24        # concurrent Open-Meteo requests
CLIMATE_CACHE    = CACHE / "climate_normals.json"
ELEVATION_CACHE  = CACHE / "elevations.json"


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi   = math.radians(lat2 - lat1)
    dlam   = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def normalize_name(s: str) -> str:
    """Lowercase, strip diacritics, remove punctuation, normalize whitespace."""
    if not s:
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = "".join(c if c.isalnum() or c == " " else " " for c in s)
    for suffix in (" city", " municipality", " metropolitan", " metro", " urban"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return " ".join(s.split())


def fuzzy_score(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def download_file(url: str, dest: Path, desc: str, force: bool = False) -> bool:
    if dest.exists() and not force:
        print(f"    ✓ Cached: {dest.name}")
        return True
    print(f"    ⬇ Downloading {desc}…")
    try:
        r = requests.get(url, timeout=120, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        print(f"      ✓ {dest.stat().st_size / 1e6:.1f} MB")
        return True
    except Exception as e:
        print(f"      ✗ Failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — GeoNames base data
# ══════════════════════════════════════════════════════════════════════════════

def download_geonames(force: bool = False) -> pd.DataFrame:
    zip_path  = CACHE / "cities15000.zip"
    txt_path  = CACHE / "cities15000.txt"

    if not txt_path.exists() or force:
        if download_file(CITIES_URL, zip_path, "GeoNames cities15000", force):
            with zipfile.ZipFile(zip_path) as zf:
                zf.extract("cities15000.txt", CACHE)
        else:
            raise RuntimeError("Cannot download GeoNames cities15000")

    df = pd.read_csv(
        txt_path,
        sep="\t", header=None, names=GEONAMES_COLS,
        dtype={"geonameid": int, "population": int,
               "latitude": float, "longitude": float},
        keep_default_na=False,
        quoting=csv.QUOTE_NONE,
        on_bad_lines="skip",
    )
    print(f"    Raw GeoNames entries: {len(df):,}")
    return df


def filter_and_deduplicate(df: pd.DataFrame, countries_df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter to the target city list and remove duplicates.

    Rules:
    - Keep only feature_class == 'P' (populated places)
    - Keep only codes in INCLUDE_FEATURE_CODES
    - Keep if population >= MIN_POPULATION OR feature_code in CAPITAL_CODES
    - Build ISO3 from countries_df
    - Spatial dedup per country: within DEDUP_RADIUS_KM, keep highest-priority entry
    """
    iso2_to_iso3 = dict(zip(countries_df["iso_a2"].str.strip(),
                            countries_df["iso_a3"].str.strip()))

    df = df[df["feature_class"] == "P"].copy()
    df = df[df["feature_code"].isin(INCLUDE_FEATURE_CODES)].copy()
    df["iso_a3"] = df["country_code"].map(iso2_to_iso3)
    df = df[df["iso_a3"].notna() & (df["iso_a3"] != "")].copy()

    # Apply population floor (always include capitals)
    df = df[
        (df["population"] >= MIN_POPULATION) |
        (df["feature_code"].isin(CAPITAL_CODES))
    ].copy()

    print(f"    After filters: {len(df):,}")

    # ── Spatial deduplication per country ─────────────────────────────────────
    # Within each country, if two entries are within DEDUP_RADIUS_KM, keep the
    # one with the higher feature-code priority; break ties by population.
    df["_priority"] = df["feature_code"].map(FEATURE_PRIORITY)
    df = df.sort_values(["iso_a3", "_priority", "population"],
                        ascending=[True, True, False]).copy()

    kept: list[int] = []
    removed: set[int] = set()

    for iso3, grp in df.groupby("iso_a3"):
        rows = grp.to_dict("records")
        for i, r in enumerate(rows):
            if r["geonameid"] in removed:
                continue
            kept.append(r["geonameid"])
            for j in range(i + 1, len(rows)):
                s = rows[j]
                if s["geonameid"] in removed:
                    continue
                dist = haversine_km(r["latitude"], r["longitude"],
                                    s["latitude"], s["longitude"])
                if dist <= DEDUP_RADIUS_KM:
                    removed.add(s["geonameid"])

    df = df[df["geonameid"].isin(kept)].copy()
    print(f"    After dedup ({len(removed)} removed): {len(df):,}")

    # ── is_capital ─────────────────────────────────────────────────────────────
    def capital_level(fc: str) -> str:
        if fc in CAPITAL_CODES:
            return "national"
        if fc in ADMIN1_CODES:
            return "admin1"
        return "no"

    df["is_capital"] = df["feature_code"].apply(capital_level)
    return df.drop(columns=["_priority"])


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — Admin1 names
# ══════════════════════════════════════════════════════════════════════════════

def download_admin1_codes(force: bool = False) -> dict[str, str]:
    """Returns {(country_code, admin1_code): name}."""
    path = CACHE / "admin1CodesASCII.txt"
    if not path.exists() or force:
        if not download_file(ADMIN1_URL, path, "GeoNames admin1 codes", force):
            return {}
    mapping: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 2:
                continue
            key = parts[0]   # e.g. "US.CA"
            name = parts[1]  # e.g. "California"
            mapping[key] = name
    print(f"    Admin1 codes loaded: {len(mapping):,}")
    return mapping


def apply_admin1_names(df: pd.DataFrame, admin1_map: dict[str, str]) -> pd.DataFrame:
    def resolve(row: pd.Series) -> str:
        key = f"{row['country_code']}.{row['admin1_code']}"
        return admin1_map.get(key, "")
    df["admin1_name"] = df.apply(resolve, axis=1)
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — Multilingual names (alternateNamesV2, streamed)
# ══════════════════════════════════════════════════════════════════════════════

def download_altnames(force: bool = False) -> Path:
    zip_path = CACHE / "alternateNamesV2.zip"
    download_file(ALTNAMES_URL, zip_path, "GeoNames alternateNamesV2 (~200 MB)", force)
    return zip_path


def build_multilingual_names(
    cities_df: pd.DataFrame,
    altnames_zip: Path,
) -> dict[int, dict[str, str]]:
    """
    Stream through alternateNamesV2.zip (2 GB uncompressed) and collect
    the best name in each target language for every city in cities_df.

    Selection priority per (geonameid, language):
      1. isPreferredName=1, not historic, not colloquial
      2. isPreferredName=1 (even if colloquial)
      3. Any non-historic, non-colloquial entry
      4. Any entry (fall back)
    """
    target_ids: set[str] = set(cities_df["geonameid"].astype(str))

    # {geonameid: {lang: [(priority, name)]}}
    # priority: lower = better
    #   0 = preferred, not historic, not colloquial
    #   1 = preferred, possibly colloquial
    #   2 = not preferred, not historic, not colloquial
    #   3 = anything else
    collected: dict[int, dict[str, list]] = {}

    print(f"    Streaming alternateNamesV2 (target IDs: {len(target_ids):,})…")
    t0 = time.time()
    line_count = 0

    try:
        with zipfile.ZipFile(altnames_zip) as zf:
            inner = "alternateNamesV2.txt"
            if inner not in zf.namelist():
                inner = zf.namelist()[0]
            with zf.open(inner) as raw:
                import io as _io
                reader = _io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
                for line in reader:
                    line_count += 1
                    if line_count % 10_000_000 == 0:
                        elapsed = time.time() - t0
                        print(f"      … {line_count/1e6:.0f}M lines, {elapsed:.0f}s")

                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 4:
                        continue
                    geonameid_s = parts[1]
                    if geonameid_s not in target_ids:
                        continue
                    isolang = parts[2]
                    if isolang not in TARGET_LANGS:
                        continue

                    name         = parts[3]
                    is_preferred = (parts[4] == "1") if len(parts) > 4 else False
                    is_short     = (parts[5] == "1") if len(parts) > 5 else False
                    is_colloquial= (parts[6] == "1") if len(parts) > 6 else False
                    is_historic  = (parts[7] == "1") if len(parts) > 7 else False

                    if is_historic:
                        continue  # never use obsolete names as primary

                    if is_preferred and not is_colloquial:
                        prio = 0
                    elif is_preferred:
                        prio = 1
                    elif not is_colloquial:
                        prio = 2
                    else:
                        prio = 3

                    gid = int(geonameid_s)
                    if gid not in collected:
                        collected[gid] = {}
                    if isolang not in collected[gid]:
                        collected[gid][isolang] = []
                    collected[gid][isolang].append((prio, name))
    except Exception as e:
        print(f"    ⚠ Error streaming alternateNames: {e}")

    # Reduce to best name per language
    result: dict[int, dict[str, str]] = {}
    for gid, langs in collected.items():
        result[gid] = {}
        for lang, entries in langs.items():
            best = sorted(entries, key=lambda x: x[0])[0][1]
            result[gid][lang] = best

    elapsed = time.time() - t0
    print(f"    Streamed {line_count/1e6:.1f}M lines in {elapsed:.0f}s → "
          f"{len(result):,} cities with alt names")
    return result


def apply_multilingual_names(
    df: pd.DataFrame,
    altnames: dict[int, dict[str, str]],
) -> pd.DataFrame:
    """
    Add name_en, name_es, name_fr, name_it, name_ru columns.
    Fallback chain per language:
      altnames[geonameid][lang] → altnames[geonameid]['en'] → df['name'] → df['asciiname']
    """
    for lang in TARGET_LANGS:
        col = f"name_{lang}"
        df[col] = ""

    for idx, row in df.iterrows():
        gid   = row["geonameid"]
        entry = altnames.get(gid, {})
        fallback_en  = entry.get("en", "") or row["name"]
        fallback_any = row["name"] or row["asciiname"]

        for lang in TARGET_LANGS:
            name = entry.get(lang, "") or fallback_en or fallback_any
            df.at[idx, f"name_{lang}"] = name

    # Coverage report
    for lang in TARGET_LANGS:
        col = f"name_{lang}"
        n_filled = (df[col] != "").sum()
        print(f"    name_{lang}: {n_filled}/{len(df)} ({100*n_filled/len(df):.1f}%)")

    return df


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 4 — Elevation (Open-Meteo Elevation API, batch 100 coords/call)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_elevations(
    cities_df: pd.DataFrame,
    force: bool = False,
) -> dict[int, float]:
    if ELEVATION_CACHE.exists() and not force:
        with open(ELEVATION_CACHE) as f:
            cached = json.load(f)
        print(f"    ✓ Elevation cache: {len(cached):,} entries")
        return {int(k): v for k, v in cached.items()}

    # Only fetch cities with missing/zero DEM
    needs = cities_df[
        (cities_df["dem"].isna()) | (cities_df["dem"] == "") | (cities_df["dem"] == 0)
    ]
    if needs.empty:
        return {}

    results: dict[int, float] = {}
    rows = needs[["geonameid", "latitude", "longitude"]].to_dict("records")
    BATCH = 100
    print(f"    Fetching elevations for {len(rows):,} cities…")

    for i in range(0, len(rows), BATCH):
        batch = rows[i : i + BATCH]
        lats = ",".join(str(r["latitude"]) for r in batch)
        lons = ",".join(str(r["longitude"]) for r in batch)
        try:
            resp = requests.get(
                "https://api.open-meteo.com/v1/elevation",
                params={"latitude": lats, "longitude": lons},
                timeout=30,
            )
            resp.raise_for_status()
            elevs = resp.json().get("elevation", [])
            for r, elev in zip(batch, elevs):
                if elev is not None:
                    results[r["geonameid"]] = round(elev, 1)
        except Exception as e:
            print(f"      ⚠ Elevation batch {i//BATCH}: {e}")
        time.sleep(0.1)

    with open(ELEVATION_CACHE, "w") as f:
        json.dump({str(k): v for k, v in results.items()}, f)
    print(f"    ✓ Elevation fetched: {len(results):,}")
    return results


def apply_elevations(
    df: pd.DataFrame,
    elevations: dict[int, float],
) -> pd.DataFrame:
    """Use GeoNames DEM where available; fill gaps with Open-Meteo."""
    # Coerce DEM to numeric
    df["dem"] = pd.to_numeric(df["dem"], errors="coerce")
    df["elevation"] = pd.to_numeric(df["elevation"], errors="coerce")

    def best_elev(row: pd.Series) -> float:
        gid  = row["geonameid"]
        dem  = row["dem"]
        elev = row["elevation"]
        base = dem if (dem is not None and not pd.isna(dem)) else elev
        if base is None or pd.isna(base):
            base = elevations.get(gid, None)
        return round(float(base), 1) if (base is not None and not pd.isna(base)) else ""

    df["elevation"] = df.apply(best_elev, axis=1)
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 5 — Climate normals via Open-Meteo Historical API (parallel)
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_climate_one(
    geonameid: int,
    lat: float,
    lon: float,
) -> tuple[int, dict]:
    """Fetch 1991-2020 monthly climate normals for one city."""
    try:
        resp = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude":  lat,
                "longitude": lon,
                "start_date": CLIMATE_START,
                "end_date":   CLIMATE_END,
                "monthly": (
                    "temperature_2m_mean,"
                    "precipitation_sum,"
                    "sunshine_duration,"
                    "wind_speed_10m_mean"
                ),
                "timezone": "UTC",
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        monthly = data.get("monthly", {})

        def annual_mean(vals: list) -> float | None:
            v = [x for x in (vals or []) if x is not None]
            return round(sum(v) / len(v), 2) if v else None

        def annual_sum(vals: list) -> float | None:
            """Average yearly total: mean of monthly values × 12."""
            v = [x for x in (vals or []) if x is not None]
            if not v:
                return None
            # Monthly means → annual total
            return round(sum(v) / len(v) * 12, 1)

        temps  = monthly.get("temperature_2m_mean", [])
        precip = monthly.get("precipitation_sum", [])
        sun    = monthly.get("sunshine_duration", [])
        wind   = monthly.get("wind_speed_10m_mean", [])

        # Compute per-year max/min temp from monthly series
        temp_v = [x for x in temps if x is not None]
        max_t  = round(max(temp_v), 1) if temp_v else None
        min_t  = round(min(temp_v), 1) if temp_v else None

        # Sunshine: Open-Meteo returns seconds/day; convert to hours/year
        sun_v = [x for x in sun if x is not None]
        sun_h_yr = round(sum(sun_v) / len(sun_v) * 365 / 3600, 0) if sun_v else None

        result = {
            "annual_mean_temp":        annual_mean(temps),
            "max_temp_warmest_month":  max_t,
            "min_temp_coldest_month":  min_t,
            "temp_annual_range":       (
                round(max_t - min_t, 1)
                if max_t is not None and min_t is not None else None
            ),
            "annual_precipitation":    annual_sum(precip),
            "sunshine_hours_yr":       sun_h_yr,
            "mean_wind_speed":         annual_mean(wind),
        }
        return geonameid, result
    except Exception:
        return geonameid, {}


def fetch_climate_normals(
    cities_df: pd.DataFrame,
    force: bool = False,
) -> dict[int, dict]:
    if CLIMATE_CACHE.exists() and not force:
        with open(CLIMATE_CACHE) as f:
            cached = json.load(f)
        print(f"    ✓ Climate cache: {len(cached):,} entries")
        return {int(k): v for k, v in cached.items()}

    rows = cities_df[["geonameid", "latitude", "longitude"]].to_dict("records")
    print(f"    Fetching climate normals for {len(rows):,} cities "
          f"({CLIMATE_WORKERS} workers)…")

    results: dict[int, dict] = {}
    done = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=CLIMATE_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_climate_one, r["geonameid"],
                        r["latitude"], r["longitude"]): r["geonameid"]
            for r in rows
        }
        for fut in as_completed(futures):
            gid, data = fut.result()
            if data:
                results[gid] = data
            done += 1
            if done % 500 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                remaining = (len(rows) - done) / rate
                print(f"      {done}/{len(rows)} — "
                      f"{elapsed:.0f}s elapsed, ~{remaining:.0f}s remaining")

    elapsed = time.time() - t0
    print(f"    ✓ Climate fetched: {len(results):,} cities in {elapsed:.0f}s")

    with open(CLIMATE_CACHE, "w") as f:
        json.dump({str(k): v for k, v in results.items()}, f)
    return results


def apply_climate(
    df: pd.DataFrame,
    climate: dict[int, dict],
) -> pd.DataFrame:
    climate_cols = [
        "annual_mean_temp", "max_temp_warmest_month", "min_temp_coldest_month",
        "temp_annual_range", "annual_precipitation", "sunshine_hours_yr",
        "mean_wind_speed",
    ]
    for col in climate_cols:
        df[col] = None

    for idx, row in df.iterrows():
        data = climate.get(row["geonameid"], {})
        for col in climate_cols:
            df.at[idx, col] = data.get(col, None)

    return df


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 6 — World Bank WDI (country-level, assigned to all cities in country)
# ══════════════════════════════════════════════════════════════════════════════

WB_INDICATORS: dict[str, str] = {
    "NY.GDP.PCAP.PP.CD": "gdp_per_capita_ppp",   # GDP per capita PPP
    "IT.NET.USER.ZS":    "internet_pct",           # Internet users %
    "SP.URB.TOTL.IN.ZS": "urban_pct",             # Urban population %
    "NV.AGR.TOTL.ZS":    "agri_pct_gdp",          # Agriculture % GDP
    "NV.IND.TOTL.ZS":    "industry_pct_gdp",      # Industry % GDP
    "NV.SRV.TOTL.ZS":    "services_pct_gdp",      # Services % GDP
    "SP.DYN.LE00.IN":    "life_expectancy",        # Life expectancy
    "SP.POP.DPND":       "age_dependency_ratio",   # Age dependency ratio
    "SI.POV.GINI":       "gini",                   # Gini index
    "EN.ATM.CO2E.PC":    "co2_per_capita",         # CO2 per capita
    "SE.ADT.LITR.ZS":    "literacy_rate",          # Adult literacy rate
    "SH.MED.BEDS.ZS":    "hospital_beds_per_1k",   # Hospital beds per 1k
}

WB_API = "https://api.worldbank.org/v2/country/all/indicator/{code}?date=2019:2024&format=json&per_page=20000"


def fetch_worldbank() -> dict[str, dict[str, float]]:
    """Returns {indicator_short_name: {iso3: value}}."""
    cache_path = CACHE / "worldbank.json"
    if cache_path.exists():
        with open(cache_path) as f:
            data = json.load(f)
        print(f"    ✓ World Bank cache: {len(data)} indicators")
        return data

    results: dict[str, dict[str, float]] = {}
    for code, name in WB_INDICATORS.items():
        try:
            resp = requests.get(WB_API.format(code=code), timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            if len(raw) < 2 or not raw[1]:
                continue
            values: dict[str, tuple] = {}
            for entry in raw[1]:
                iso3 = entry.get("countryiso3code", "")
                val  = entry.get("value")
                year = entry.get("date", "0")
                if val is not None and iso3 and len(iso3) == 3:
                    if iso3 not in values or year > values[iso3][1]:
                        values[iso3] = (val, year)
            results[name] = {
                iso3: round(v, 4) for iso3, (v, _) in values.items()
            }
            print(f"    ✓ {name}: {len(results[name])} countries")
            time.sleep(0.25)
        except Exception as e:
            print(f"    ⚠ {name} ({code}): {e}")

    with open(cache_path, "w") as f:
        json.dump(results, f)
    return results


def apply_worldbank(
    df: pd.DataFrame,
    wb_data: dict[str, dict[str, float]],
) -> pd.DataFrame:
    """Assign country-level WB indicators to every city in that country."""
    for col, iso3_map in wb_data.items():
        df[col] = df["iso_a3"].map(iso3_map)
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 7 (optional) — WHO Air Quality DB
# ══════════════════════════════════════════════════════════════════════════════

def match_who_air_quality(df: pd.DataFrame) -> pd.DataFrame:
    """
    If WHO_AQ_PATH exists, load and match PM2.5 / PM10 / NO2 to cities.

    Matching strategy:
      1. Exact match on (name_normalized, iso3)
      2. Fuzzy match (score ≥ 0.85) within the same country
      3. Spatial match (nearest city within 50 km) — only if city has coordinates
    """
    if not WHO_AQ_PATH.exists():
        print("    ⓘ WHO Air Quality file not found — skipping "
              f"(expected: {WHO_AQ_PATH})")
        df["pm25"] = None
        df["pm10"] = None
        df["no2"]  = None
        return df

    print(f"    Loading WHO Air Quality data from {WHO_AQ_PATH.name}…")
    try:
        who = pd.read_excel(WHO_AQ_PATH, keep_default_na=False)
    except Exception as e:
        print(f"    ⚠ Could not read WHO file: {e}")
        df["pm25"] = df["pm10"] = df["no2"] = None
        return df

    # Normalise column names (WHO changes them between versions)
    who.columns = [c.strip().lower().replace(" ", "_") for c in who.columns]
    name_col    = next((c for c in who.columns if "city" in c), None)
    iso3_col    = next((c for c in who.columns if "iso3" in c or "iso_3" in c), None)
    pm25_col    = next((c for c in who.columns if "pm2" in c and "5" in c), None)
    pm10_col    = next((c for c in who.columns if "pm10" in c), None)
    no2_col     = next((c for c in who.columns if "no2" in c), None)

    if not name_col or not iso3_col:
        print("    ⚠ Could not identify city/iso3 columns in WHO file — skipping")
        df["pm25"] = df["pm10"] = df["no2"] = None
        return df

    # Take most recent measurement per city
    year_col = next((c for c in who.columns if "year" in c), None)
    if year_col:
        who = (who.sort_values(year_col, ascending=False)
                  .groupby([iso3_col, name_col], as_index=False)
                  .first())

    # Build lookup: (norm_name, iso3) → (pm25, pm10, no2)
    who_lookup: dict[tuple, dict] = {}
    who_by_country: dict[str, list] = {}

    for _, row in who.iterrows():
        iso3 = str(row.get(iso3_col, "")).strip().upper()
        name = str(row.get(name_col, "")).strip()
        norm = normalize_name(name)
        pm25 = row.get(pm25_col) if pm25_col else None
        pm10 = row.get(pm10_col) if pm10_col else None
        no2  = row.get(no2_col) if no2_col else None
        entry = {"pm25": pm25, "pm10": pm10, "no2": no2, "name_norm": norm}
        who_lookup[(norm, iso3)] = entry
        who_by_country.setdefault(iso3, []).append(entry)

    df["pm25"] = None
    df["pm10"] = None
    df["no2"]  = None
    matched = 0

    for idx, row in df.iterrows():
        iso3      = str(row["iso_a3"]).upper()
        city_norm = normalize_name(str(row["name"]))

        # 1. Exact match
        entry = who_lookup.get((city_norm, iso3))

        # 2. Fuzzy match within same country
        if entry is None and iso3 in who_by_country:
            best_score = 0.0
            best_entry = None
            for candidate in who_by_country[iso3]:
                score = fuzzy_score(city_norm, candidate["name_norm"])
                if score > best_score:
                    best_score = score
                    best_entry = candidate
            if best_score >= 0.85:
                entry = best_entry

        if entry:
            df.at[idx, "pm25"] = entry["pm25"]
            df.at[idx, "pm10"] = entry["pm10"]
            df.at[idx, "no2"]  = entry["no2"]
            matched += 1

    print(f"    ✓ WHO match: {matched}/{len(df)} cities ({100*matched/len(df):.1f}%)")
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 8 (optional) — UN WUP metro populations + 10-year growth
# ══════════════════════════════════════════════════════════════════════════════

def fetch_un_wup(force: bool = False) -> pd.DataFrame | None:
    path = CACHE / "un_wup.xlsx"
    if not path.exists() or force:
        ok = download_file(UN_WUP_URL, path, "UN WUP 2024 city populations", force)
        if not ok:
            return None
    try:
        # The WUP file has a complex header — try to find the data rows
        xl = pd.read_excel(path, header=None, keep_default_na=False)
        # Find row where first column is 'Index' or 'Country code'
        header_row = None
        for i, row in xl.iterrows():
            first = str(row.iloc[0]).lower().strip()
            if first in ("index", "country code", "country_code"):
                header_row = i
                break
        if header_row is None:
            # Try generic parse
            xl = pd.read_excel(path, keep_default_na=False)
        else:
            xl = pd.read_excel(path, header=header_row, keep_default_na=False)
        print(f"    UN WUP loaded: {len(xl):,} rows, cols={list(xl.columns[:8])}")
        return xl
    except Exception as e:
        print(f"    ⚠ Could not parse UN WUP: {e}")
        return None


def apply_un_wup(
    df: pd.DataFrame,
    wup: pd.DataFrame | None,
) -> pd.DataFrame:
    df["metro_population"]  = None
    df["pop_growth_10yr"]   = None

    if wup is None:
        print("    ⓘ UN WUP not available — metro_population / pop_growth_10yr empty")
        return df

    # Identify relevant columns dynamically
    cols = [str(c).lower().strip() for c in wup.columns]
    wup.columns = cols

    iso3_col  = next((c for c in cols if "iso" in c or "country code" in c), None)
    name_col  = next((c for c in cols if "agglom" in c or "city" in c
                      or "urban" in c), None)

    # Population columns: years are column names (e.g., '2010', '2020', '2030')
    year_cols = [c for c in cols if c.isdigit() and 1950 <= int(c) <= 2030]

    if not iso3_col or not name_col or len(year_cols) < 2:
        print("    ⚠ Could not identify columns in WUP file — skipping")
        return df

    # Sort year columns chronologically
    year_cols_sorted = sorted(year_cols, key=int)
    recent_year  = year_cols_sorted[-1]
    decade_ago   = str(int(recent_year) - 10)
    if decade_ago not in year_cols_sorted:
        decade_ago = year_cols_sorted[max(0, len(year_cols_sorted) - 3)]

    # Build lookup: (norm_name, iso3) → (metro_pop, growth_10yr)
    wup_lookup: dict[tuple, dict] = {}
    wup_by_country: dict[str, list] = {}

    for _, row in wup.iterrows():
        iso3 = str(row.get(iso3_col, "")).strip().upper()
        if len(iso3) != 3:
            continue
        city_name = str(row.get(name_col, "")).strip()
        norm = normalize_name(city_name)

        pop_recent = row.get(recent_year)
        pop_decade = row.get(decade_ago)
        try:
            pop_recent = float(pop_recent) * 1000  # WUP stores in thousands
            pop_decade = float(pop_decade) * 1000
            # CAGR over 10 years
            if pop_decade > 0:
                growth = round((pop_recent / pop_decade) ** (1 / 10) - 1, 4)
            else:
                growth = None
        except (TypeError, ValueError, ZeroDivisionError):
            pop_recent = None
            growth     = None

        entry = {"metro_pop": pop_recent, "growth": growth, "norm": norm}
        wup_lookup[(norm, iso3)] = entry
        wup_by_country.setdefault(iso3, []).append(entry)

    matched = 0
    for idx, row in df.iterrows():
        iso3 = str(row["iso_a3"]).upper()
        city_norm = normalize_name(str(row["name"]))

        entry = wup_lookup.get((city_norm, iso3))
        if entry is None and iso3 in wup_by_country:
            best, best_entry = 0.0, None
            for cand in wup_by_country[iso3]:
                s = fuzzy_score(city_norm, cand["norm"])
                if s > best:
                    best, best_entry = s, cand
            if best >= 0.82:
                entry = best_entry

        if entry:
            if entry["metro_pop"] is not None:
                df.at[idx, "metro_population"] = int(entry["metro_pop"])
            df.at[idx, "pop_growth_10yr"] = entry["growth"]
            matched += 1

    print(f"    ✓ UN WUP match: {matched}/{len(df)} cities ({100*matched/len(df):.1f}%)")
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 9 — HDI (embedded table, same as countries download_data.py)
# ══════════════════════════════════════════════════════════════════════════════

HDI_TABLE: dict[str, float] = {
    "NOR": 0.966, "IRL": 0.945, "CHE": 0.962, "ISL": 0.959, "HKG": 0.952,
    "DNK": 0.952, "SWE": 0.947, "DEU": 0.942, "NLD": 0.941, "FIN": 0.940,
    "AUS": 0.946, "SGP": 0.939, "GBR": 0.929, "BEL": 0.937, "NZL": 0.936,
    "CAN": 0.935, "USA": 0.921, "AUT": 0.926, "ISR": 0.919, "JPN": 0.920,
    "LIE": 0.935, "SVN": 0.918, "KOR": 0.929, "LUX": 0.927, "ESP": 0.911,
    "FRA": 0.903, "CZE": 0.900, "MLT": 0.918, "EST": 0.899, "ITA": 0.895,
    "ARE": 0.911, "GRC": 0.893, "CYP": 0.907, "LTU": 0.879, "POL": 0.881,
    "AND": 0.884, "LVA": 0.879, "PRT": 0.874, "SVK": 0.855, "HUN": 0.851,
    "SAU": 0.875, "BHR": 0.888, "CHL": 0.860, "HRV": 0.858, "QAT": 0.855,
    "ARG": 0.849, "BRN": 0.829, "MNE": 0.844, "ROU": 0.827, "KAZ": 0.811,
    "RUS": 0.822, "BLR": 0.808, "TUR": 0.838, "URY": 0.830, "BGR": 0.795,
    "PAN": 0.805, "MYS": 0.803, "MUS": 0.796, "THA": 0.800, "SRB": 0.805,
    "GEO": 0.802, "CHN": 0.788, "MKD": 0.770, "CRI": 0.806, "MEX": 0.781,
    "CUB": 0.764, "COL": 0.758, "BIH": 0.768, "AZE": 0.745, "ARM": 0.786,
    "PER": 0.762, "ECU": 0.765, "BRA": 0.760, "UKR": 0.773, "MDA": 0.763,
    "ALB": 0.789, "TUN": 0.732, "LKA": 0.780, "DZA": 0.745, "MNG": 0.741,
    "DOM": 0.767, "JOR": 0.736, "JAM": 0.709, "TKM": 0.744, "LBN": 0.723,
    "ZAF": 0.717, "PRY": 0.717, "EGY": 0.731, "IDN": 0.713, "VNM": 0.726,
    "PHL": 0.710, "BOL": 0.698, "MAR": 0.698, "IRQ": 0.686, "SLV": 0.675,
    "KGZ": 0.701, "UZB": 0.727, "TJK": 0.679, "IND": 0.644, "GHA": 0.602,
    "KEN": 0.601, "PAK": 0.540, "NGA": 0.539, "BGD": 0.670, "MMR": 0.585,
    "ETH": 0.492, "COD": 0.479, "TZA": 0.549, "NER": 0.394, "TCD": 0.394,
    "CAF": 0.387, "SSD": 0.385, "SOM": 0.380, "AFG": 0.462, "MLI": 0.410,
    "BFA": 0.449, "SLE": 0.477, "MOZ": 0.461, "LBR": 0.487, "GIN": 0.465,
    "BDI": 0.426, "YEM": 0.455, "HTI": 0.535, "NPL": 0.601, "CMR": 0.576,
    "ZWE": 0.593, "AGO": 0.586, "SEN": 0.511, "SDN": 0.516, "RWA": 0.548,
    "UGA": 0.550, "MWI": 0.512, "BEN": 0.504, "TGO": 0.539, "GMB": 0.500,
    "MDG": 0.501, "CIV": 0.534, "ZMB": 0.565, "LAO": 0.620, "KHM": 0.600,
    "BTN": 0.666, "GAB": 0.706, "BWA": 0.708, "NAM": 0.610, "CPV": 0.662,
    "GTM": 0.627, "HND": 0.621, "NIC": 0.667, "SWZ": 0.597, "LSO": 0.514,
    "PNG": 0.568, "VUT": 0.607, "SLB": 0.564, "WSM": 0.707, "TON": 0.745,
    "IRN": 0.774, "TWN": 0.926, "PRK": 0.574, "KWT": 0.831, "OMN": 0.816,
    "LBY": 0.718, "SYR": 0.577, "PSE": 0.715, "VEN": 0.691, "GUY": 0.714,
    "SUR": 0.738, "TTO": 0.810, "BLZ": 0.700, "BRB": 0.809,
}


def apply_hdi(df: pd.DataFrame) -> pd.DataFrame:
    df["hdi"] = df["iso_a3"].map(HDI_TABLE)
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 10 — Update countries.csv (top_cities, capital_population, etc.)
# ══════════════════════════════════════════════════════════════════════════════

def update_countries_csv(cities_df: pd.DataFrame, countries_df: pd.DataFrame) -> pd.DataFrame:
    """Update top_cities, most_populated_city, and capital_population in countries.csv."""
    top_cities_map: dict[str, str]  = {}
    most_pop_map:   dict[str, str]  = {}
    cap_pop_map:    dict[str, int]  = {}

    for iso3, grp in cities_df.groupby("iso_a3"):
        srt = grp.sort_values("population", ascending=False)
        cities_list = []
        for _, row in srt.head(10).iterrows():
            cities_list.append({
                "name":       row["name"],
                "population": int(row["population"]),
                "lat":        round(float(row["latitude"]), 4),
                "lon":        round(float(row["longitude"]), 4),
                "is_capital": row["is_capital"] in ("national", "admin1"),
            })
        top_cities_map[iso3] = json.dumps(cities_list, ensure_ascii=False)
        if len(srt) > 0:
            most_pop_map[iso3] = srt.iloc[0]["name"]
        caps = srt[srt["is_capital"] == "national"]
        if len(caps) > 0:
            cap_pop_map[iso3] = int(caps.iloc[0]["population"])

    for idx, row in countries_df.iterrows():
        iso3 = row["iso_a3"]
        if iso3 in top_cities_map:
            countries_df.at[idx, "top_cities"]          = top_cities_map[iso3]
        if iso3 in most_pop_map:
            countries_df.at[idx, "most_populated_city"] = most_pop_map[iso3]
        if iso3 in cap_pop_map:
            countries_df.at[idx, "capital_population"]  = cap_pop_map[iso3]
    return countries_df


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 11 — Update variable_config.json (cities dataset)
# ══════════════════════════════════════════════════════════════════════════════

CITIES_VARIABLES = [
    # ── Demographic ───────────────────────────────────────────────────────────
    {"key": "population",          "label_es": "Población",          "label_en": "Population",
     "label_fr": "Population",     "label_it": "Popolazione",        "label_ru": "Население",
     "unit": "", "format": "integer", "enabled": True, "description_es": "Población del municipio (GeoNames)"},
    {"key": "metro_population",    "label_es": "Área metropolitana", "label_en": "Metro population",
     "label_fr": "Population métropolitaine", "label_it": "Area metropolitana", "label_ru": "Метрополия",
     "unit": "", "format": "integer", "enabled": True, "description_es": "Población del área metropolitana (UN WUP)"},
    {"key": "pop_growth_10yr",     "label_es": "Crecimiento 10 años","label_en": "10-yr growth rate",
     "label_fr": "Croissance sur 10 ans", "label_it": "Crescita 10 anni", "label_ru": "Рост за 10 лет",
     "unit": "%", "format": "percent", "enabled": True, "description_es": "Tasa de crecimiento anual compuesto (CAGR) en 10 años"},

    # ── Geographic ────────────────────────────────────────────────────────────
    {"key": "elevation",           "label_es": "Altitud",            "label_en": "Elevation",
     "label_fr": "Altitude",       "label_it": "Altitudine",         "label_ru": "Высота",
     "unit": "m", "format": "integer", "enabled": True},

    # ── Climate ───────────────────────────────────────────────────────────────
    {"key": "annual_mean_temp",    "label_es": "Temperatura media anual", "label_en": "Annual mean temperature",
     "label_fr": "Température annuelle moyenne", "label_it": "Temperatura media annua", "label_ru": "Среднегодовая температура",
     "unit": "°C", "format": "decimal", "enabled": True},
    {"key": "max_temp_warmest_month", "label_es": "Temperatura máx. (mes más cálido)", "label_en": "Max temp (warmest month)",
     "label_fr": "Température max (mois le plus chaud)", "label_it": "Temp. massima (mese più caldo)", "label_ru": "Макс. температура (самый тёплый месяц)",
     "unit": "°C", "format": "decimal", "enabled": True},
    {"key": "min_temp_coldest_month", "label_es": "Temperatura mín. (mes más frío)", "label_en": "Min temp (coldest month)",
     "label_fr": "Température min (mois le plus froid)", "label_it": "Temp. minima (mese più freddo)", "label_ru": "Мин. температура (самый холодный месяц)",
     "unit": "°C", "format": "decimal", "enabled": True},
    {"key": "temp_annual_range",   "label_es": "Amplitud térmica anual", "label_en": "Annual temperature range",
     "label_fr": "Amplitude thermique annuelle", "label_it": "Escursione termica annua", "label_ru": "Годовая амплитуда температур",
     "unit": "°C", "format": "decimal", "enabled": True},
    {"key": "annual_precipitation","label_es": "Precipitación anual","label_en": "Annual precipitation",
     "label_fr": "Précipitations annuelles","label_it": "Precipitazioni annuali","label_ru": "Годовые осадки",
     "unit": "mm", "format": "integer", "enabled": True},
    {"key": "sunshine_hours_yr",   "label_es": "Horas de sol al año","label_en": "Annual sunshine hours",
     "label_fr": "Heures d'ensoleillement par an", "label_it": "Ore di sole annue", "label_ru": "Часы солнечного сияния в год",
     "unit": "h", "format": "integer", "enabled": True},
    {"key": "mean_wind_speed",     "label_es": "Velocidad media del viento", "label_en": "Mean wind speed",
     "label_fr": "Vitesse moyenne du vent", "label_it": "Velocità media del vento", "label_ru": "Средняя скорость ветра",
     "unit": "m/s", "format": "decimal", "enabled": True},

    # ── Air quality ───────────────────────────────────────────────────────────
    {"key": "pm25",                "label_es": "PM2.5",              "label_en": "PM2.5",
     "label_fr": "PM2.5",          "label_it": "PM2.5",              "label_ru": "PM2.5",
     "unit": "µg/m³", "format": "decimal", "enabled": True, "description_es": "Concentración media anual de partículas PM2.5 (WHO)"},
    {"key": "pm10",                "label_es": "PM10",               "label_en": "PM10",
     "label_fr": "PM10",           "label_it": "PM10",               "label_ru": "PM10",
     "unit": "µg/m³", "format": "decimal", "enabled": True},

    # ── Economic / country-level ──────────────────────────────────────────────
    {"key": "gdp_per_capita_ppp",  "label_es": "PIB per cápita (PPA)", "label_en": "GDP per capita (PPP)",
     "label_fr": "PIB par habitant (PPA)", "label_it": "PIL pro capite (PPA)", "label_ru": "ВВП на душу (ППС)",
     "unit": "$", "format": "integer", "enabled": True, "description_es": "PIB per cápita en paridad de poder adquisitivo (Banco Mundial)"},
    {"key": "hdi",                 "label_es": "IDH",                "label_en": "HDI",
     "label_fr": "IDH",            "label_it": "ISU",                "label_ru": "ИРЧП",
     "unit": "", "format": "decimal", "enabled": True, "description_es": "Índice de Desarrollo Humano (PNUD)"},
    {"key": "internet_pct",        "label_es": "Usuarios de internet","label_en": "Internet users",
     "label_fr": "Utilisateurs d'internet","label_it": "Utenti internet","label_ru": "Пользователи интернета",
     "unit": "%", "format": "decimal", "enabled": True},
    {"key": "life_expectancy",     "label_es": "Esperanza de vida",  "label_en": "Life expectancy",
     "label_fr": "Espérance de vie","label_it": "Aspettativa di vita","label_ru": "Продолжительность жизни",
     "unit": "años", "format": "decimal", "enabled": True},
    {"key": "urban_pct",           "label_es": "Urbanización",       "label_en": "Urban population",
     "label_fr": "Population urbaine","label_it": "Popolazione urbana","label_ru": "Городское население",
     "unit": "%", "format": "decimal", "enabled": True},
    {"key": "agri_pct_gdp",        "label_es": "Agricultura (% PIB)","label_en": "Agriculture (% GDP)",
     "label_fr": "Agriculture (% PIB)","label_it": "Agricoltura (% PIL)","label_ru": "Сельское хозяйство (% ВВП)",
     "unit": "%", "format": "decimal", "enabled": True},
    {"key": "industry_pct_gdp",    "label_es": "Industria (% PIB)", "label_en": "Industry (% GDP)",
     "label_fr": "Industrie (% PIB)","label_it": "Industria (% PIL)","label_ru": "Промышленность (% ВВП)",
     "unit": "%", "format": "decimal", "enabled": True},
    {"key": "services_pct_gdp",    "label_es": "Servicios (% PIB)", "label_en": "Services (% GDP)",
     "label_fr": "Services (% PIB)","label_it": "Servizi (% PIL)","label_ru": "Сфера услуг (% ВВП)",
     "unit": "%", "format": "decimal", "enabled": True},
    {"key": "literacy_rate",       "label_es": "Tasa de alfabetización","label_en": "Literacy rate",
     "label_fr": "Taux d'alphabétisation","label_it": "Tasso di alfabetizzazione","label_ru": "Уровень грамотности",
     "unit": "%", "format": "decimal", "enabled": True},
    {"key": "gini",                "label_es": "Índice de Gini",    "label_en": "Gini index",
     "label_fr": "Indice de Gini","label_it": "Indice di Gini","label_ru": "Индекс Джини",
     "unit": "", "format": "decimal", "enabled": True},
    {"key": "co2_per_capita",      "label_es": "CO₂ per cápita",   "label_en": "CO₂ per capita",
     "label_fr": "CO₂ par habitant","label_it": "CO₂ pro capite","label_ru": "CO₂ на душу",
     "unit": "t", "format": "decimal", "enabled": True},
    {"key": "hospital_beds_per_1k","label_es": "Camas hospitalarias (por 1.000)", "label_en": "Hospital beds (per 1,000)",
     "label_fr": "Lits d'hôpital (pour 1 000)","label_it": "Posti letto ospedalieri (per 1.000)","label_ru": "Больничные койки (на 1 000)",
     "unit": "", "format": "decimal", "enabled": True},
]


def update_variable_config(var_config_path: Path) -> None:
    try:
        with open(var_config_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {"datasets": {}}

    cfg.setdefault("datasets", {})
    cfg["datasets"]["cities"] = {
        "label": "Cities",
        "variables": CITIES_VARIABLES,
    }
    with open(var_config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"    ✓ variable_config.json updated ({len(CITIES_VARIABLES)} variables)")


# ══════════════════════════════════════════════════════════════════════════════
#  FINAL — Assemble and save
# ══════════════════════════════════════════════════════════════════════════════

FINAL_COLUMNS = [
    # Identity / location
    "geonameid", "name", "asciiname",
    "name_en", "name_es", "name_fr", "name_it", "name_ru",
    "lat", "lon", "elevation", "timezone", "feature_code", "is_capital",
    # Administrative
    "iso_a2", "iso_a3", "country_name", "admin1_code", "admin1_name",
    # Demographic
    "population", "metro_population", "pop_growth_10yr",
    # Climate
    "annual_mean_temp", "max_temp_warmest_month", "min_temp_coldest_month",
    "temp_annual_range", "annual_precipitation",
    "sunshine_hours_yr", "mean_wind_speed",
    # Air quality
    "pm25", "pm10",
    # Economic (country-level)
    "gdp_per_capita_ppp", "hdi", "internet_pct", "life_expectancy",
    "urban_pct", "agri_pct_gdp", "industry_pct_gdp", "services_pct_gdp",
    "literacy_rate", "gini", "co2_per_capita", "hospital_beds_per_1k",
]


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Build GeoFreak cities dataset")
    parser.add_argument("--skip-climate",  action="store_true",
                        help="Skip Open-Meteo climate API calls")
    parser.add_argument("--skip-altnames", action="store_true",
                        help="Skip alternateNamesV2 download (multilingual names)")
    parser.add_argument("--force",         action="store_true",
                        help="Ignore all caches and re-download everything")
    args = parser.parse_args()

    print("🏙️  GeoFreak Cities Dataset Builder — v2")
    print("=" * 60)

    # ── Load countries reference ──────────────────────────────────────────────
    print("\n📂 Loading countries reference…")
    if not COUNTRIES_CSV.exists():
        print("  ✗ countries.csv not found — run download_data.py first")
        sys.exit(1)
    countries_df = pd.read_csv(COUNTRIES_CSV, keep_default_na=False)
    print(f"   {len(countries_df)} countries loaded")

    country_names = dict(zip(countries_df["iso_a3"], countries_df["name"]))

    # ── Step 1: GeoNames base ─────────────────────────────────────────────────
    print("\n📦 Step 1 — GeoNames city list")
    geonames_df = download_geonames(args.force)
    cities_df   = filter_and_deduplicate(geonames_df, countries_df)

    # Rename and add country name
    cities_df = cities_df.rename(columns={
        "latitude": "lat", "longitude": "lon",
        "country_code": "iso_a2",
    })
    cities_df["country_name"] = cities_df["iso_a3"].map(country_names).fillna("")
    cities_df["asciiname"]    = cities_df["asciiname"].fillna(cities_df["name"])

    # ── Step 2: Admin1 names ──────────────────────────────────────────────────
    print("\n📍 Step 2 — Admin1 (province/state) names")
    admin1_map = download_admin1_codes(args.force)
    # Restore country_code for the lookup key (we renamed to iso_a2)
    cities_df["country_code"] = cities_df["iso_a2"]
    cities_df = apply_admin1_names(cities_df, admin1_map)

    # ── Step 3: Multilingual names ────────────────────────────────────────────
    if args.skip_altnames:
        print("\n🌐 Step 3 — Multilingual names [SKIPPED]")
        for lang in TARGET_LANGS:
            cities_df[f"name_{lang}"] = cities_df["name"]
    else:
        print("\n🌐 Step 3 — Multilingual names (streaming ~200 MB download)")
        altnames_zip = download_altnames(args.force)
        altnames     = build_multilingual_names(cities_df, altnames_zip)
        cities_df    = apply_multilingual_names(cities_df, altnames)

    # ── Step 4: Elevation ─────────────────────────────────────────────────────
    print("\n⛰️  Step 4 — Elevation")
    elevations = fetch_elevations(cities_df, args.force)
    cities_df  = apply_elevations(cities_df, elevations)

    # ── Step 5: Climate normals ───────────────────────────────────────────────
    if args.skip_climate:
        print("\n🌡️  Step 5 — Climate normals [SKIPPED]")
        for col in ["annual_mean_temp", "max_temp_warmest_month",
                    "min_temp_coldest_month", "temp_annual_range",
                    "annual_precipitation", "sunshine_hours_yr", "mean_wind_speed"]:
            cities_df[col] = None
    else:
        print(f"\n🌡️  Step 5 — Climate normals ({CLIMATE_START} → {CLIMATE_END})")
        climate = fetch_climate_normals(cities_df, args.force)
        cities_df = apply_climate(cities_df, climate)

    # ── Step 6: World Bank ────────────────────────────────────────────────────
    print("\n💰 Step 6 — World Bank economic indicators")
    wb_data   = fetch_worldbank()
    cities_df = apply_worldbank(cities_df, wb_data)

    # ── Step 7: HDI ───────────────────────────────────────────────────────────
    print("\n📊 Step 7 — HDI")
    cities_df = apply_hdi(cities_df)
    print(f"    HDI filled: {cities_df['hdi'].notna().sum()} cities")

    # ── Step 8: WHO Air Quality ───────────────────────────────────────────────
    print("\n🌫️  Step 8 — WHO Air Quality")
    cities_df = match_who_air_quality(cities_df)

    # ── Step 9: UN WUP ────────────────────────────────────────────────────────
    print("\n🏙️  Step 9 — UN WUP metro populations")
    wup_df    = fetch_un_wup(args.force)
    cities_df = apply_un_wup(cities_df, wup_df)

    # ── Assemble final columns ────────────────────────────────────────────────
    print("\n🔧 Assembling final dataset…")
    for col in FINAL_COLUMNS:
        if col not in cities_df.columns:
            cities_df[col] = None

    final = (
        cities_df[FINAL_COLUMNS]
        .sort_values(["iso_a3", "population"], ascending=[True, False])
        .reset_index(drop=True)
    )

    # ── Stats ─────────────────────────────────────────────────────────────────
    n_total    = len(final)
    n_capitals = (final["is_capital"] == "national").sum()
    n_1m       = (final["population"] >= 1_000_000).sum()
    n_countries= final["iso_a3"].nunique()
    n_climate  = final["annual_mean_temp"].notna().sum()
    n_aq       = final["pm25"].notna().sum()

    print(f"\n📈 Dataset summary:")
    print(f"   Total cities:      {n_total:,}")
    print(f"   National capitals: {n_capitals:,}")
    print(f"   1M+ cities:        {n_1m:,}")
    print(f"   Countries covered: {n_countries:,}")
    print(f"   Climate data:      {n_climate:,} ({100*n_climate/n_total:.1f}%)")
    print(f"   Air quality:       {n_aq:,} ({100*n_aq/n_total:.1f}%)")
    print(f"   Columns:           {len(final.columns)}")

    # ── Save cities.csv ───────────────────────────────────────────────────────
    print(f"\n💾 Saving {CITIES_CSV}…")
    final.to_csv(CITIES_CSV, index=False)
    print(f"   ✓ {CITIES_CSV.stat().st_size / 1e6:.1f} MB")

    # ── Update countries.csv ──────────────────────────────────────────────────
    print(f"\n🔄 Updating countries.csv…")
    countries_df = update_countries_csv(cities_df, countries_df)
    countries_df.to_csv(COUNTRIES_CSV, index=False)
    print(f"   ✓ Updated")

    # ── Update variable_config.json ───────────────────────────────────────────
    print(f"\n⚙️  Updating variable_config.json…")
    update_variable_config(VAR_CONFIG)

    print("\n✅ Done!")
    print(f"   Output: {CITIES_CSV}")
    print(f"\n💡 Optional enrichments (manual download required):")
    print(f"   WHO air quality: download from https://www.who.int/data/gho/data/themes/air-pollution/who-air-quality-database")
    print(f"   → save as: {WHO_AQ_PATH}")


if __name__ == "__main__":
    main()
