"""Pre-generate spatial tile JSON files from cities.csv for frontend map.

Splits cities into:
  - base.json: capitals + cities with pop >= 500K (~1,200 cities, loaded at init)
  - {x}_{y}.json: tile files at zoom TILE_ZOOM for remaining cities
  - index.json: lists which tiles exist

Usage:
    python scripts/build_city_tiles.py
"""

import json
import math
import os
import shutil
import sys

import pandas as pd

CITIES_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "static", "data", "cities.csv")
TILES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         "static", "data", "city_tiles")

TILE_ZOOM = 7           # Slippy-map zoom for the tile grid (128×128)
BASE_MIN_POP = 500_000  # Cities above this (+ all capitals) go in base.json


def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lon to slippy-map tile coordinates."""
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    lat_rad = math.radians(max(-85, min(85, lat)))
    y = int((1 - math.asinh(math.tan(lat_rad)) / math.pi) / 2 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def build_record(row: pd.Series) -> dict:
    """Build a slim city record for tile/base JSON."""
    rec: dict = {
        "name": row["name"],
        "lat": round(float(row["lat"]), 5),
        "lon": round(float(row["lon"]), 5),
        "population": int(row["population"]),
        "iso_a3": str(row.get("iso_a3", "")),
        "country": str(row.get("country_name", "")),
        "is_capital": bool(row.get("is_capital", False)),
    }
    for lc in ("en", "es", "fr", "it", "ru"):
        v = row.get(f"name_{lc}", "")
        if v:
            rec[f"name_{lc}"] = str(v)
    for fld in ("elevation", "metro_population", "annual_mean_temp",
                "annual_precipitation", "sunshine_hours_yr"):
        v = row.get(fld, "")
        if v != "" and v is not None:
            try:
                fv = float(v)
                if not math.isnan(fv):
                    rec[fld] = round(fv, 1)
            except (ValueError, TypeError):
                pass
    for fld in ("timezone", "admin1_name"):
        v = row.get(fld, "")
        if v:
            rec[fld] = str(v)
    return rec


def main():
    if not os.path.exists(CITIES_CSV):
        print(f"Error: {CITIES_CSV} not found. Run build_cities.py first.")
        sys.exit(1)

    df = pd.read_csv(CITIES_CSV, keep_default_na=False)
    if "is_capital" in df.columns:
        df["is_capital"] = df["is_capital"] == "national"
    print(f"Total cities: {len(df):,}")

    # Clean output directory
    if os.path.exists(TILES_DIR):
        shutil.rmtree(TILES_DIR)
    os.makedirs(TILES_DIR)

    # ── Base: capitals + pop >= 500K ─────────────────────────────────────────
    is_base = (df["population"] >= BASE_MIN_POP) | (df["is_capital"] == True)  # noqa: E712
    base_df = df[is_base]
    tile_df = df[~is_base]

    base_records = [build_record(row) for _, row in base_df.iterrows()]
    base_path = os.path.join(TILES_DIR, "base.json")
    with open(base_path, "w", encoding="utf-8") as f:
        json.dump(base_records, f, ensure_ascii=False, separators=(",", ":"))
    base_kb = os.path.getsize(base_path) / 1024
    print(f"base.json: {len(base_records):,} cities ({base_kb:.0f} KB)")

    # ── Tiles for remaining cities ───────────────────────────────────────────
    tiles: dict[str, list[dict]] = {}
    for _, row in tile_df.iterrows():
        try:
            x, y = lat_lon_to_tile(float(row["lat"]), float(row["lon"]), TILE_ZOOM)
            key = f"{x}_{y}"
            tiles.setdefault(key, []).append(build_record(row))
        except (ValueError, TypeError):
            continue

    total_size = 0
    max_key, max_count = "", 0
    for key, records in tiles.items():
        fpath = os.path.join(TILES_DIR, f"{key}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, separators=(",", ":"))
        sz = os.path.getsize(fpath)
        total_size += sz
        if len(records) > max_count:
            max_key, max_count = key, len(records)

    # ── Index ────────────────────────────────────────────────────────────────
    index = {"z": TILE_ZOOM, "tiles": sorted(tiles.keys())}
    idx_path = os.path.join(TILES_DIR, "index.json")
    with open(idx_path, "w") as f:
        json.dump(index, f, separators=(",", ":"))

    print(f"Tiles: {len(tiles)} files at z={TILE_ZOOM} "
          f"({total_size / 1024:.0f} KB total)")
    print(f"Avg cities/tile: {len(tile_df) / max(1, len(tiles)):.0f}")
    print(f"Max tile: {max_key} with {max_count} cities")
    print(f"Index: {os.path.getsize(idx_path) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
