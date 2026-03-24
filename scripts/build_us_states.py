"""Download US state GeoJSON boundaries from public sources.

Creates individual GeoJSON files in static/data/geojson_us/ for each state.
Uses the public US Census Bureau cartographic boundary files (500k scale).
"""

import json
import os
import sys
import urllib.request

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "data")
GEOJSON_US_DIR = os.path.join(DATA_DIR, "geojson_us")

# US Census Bureau 500k cartographic boundaries (2023)
STATES_GEOJSON_URL = (
    "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"
)

# State FIPS → postal code mapping
FIPS_TO_CODE = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY",
}


def download_and_split():
    """Download combined US states GeoJSON and split into individual files."""
    os.makedirs(GEOJSON_US_DIR, exist_ok=True)

    print(f"Downloading US states GeoJSON from {STATES_GEOJSON_URL}...")
    req = urllib.request.Request(STATES_GEOJSON_URL, headers={"User-Agent": "GeoFreak/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    features = data.get("features", [])
    print(f"Found {len(features)} features.")

    count = 0
    for feature in features:
        props = feature.get("properties", {})
        name = props.get("name", "")

        # Try to get state code from various properties
        code = None
        if "id" in feature:
            fips = str(feature["id"]).zfill(2)
            code = FIPS_TO_CODE.get(fips)

        if not code:
            # Fallback: match by name
            for fips, c in FIPS_TO_CODE.items():
                pass  # would need name mapping

        if not code:
            print(f"  Skipping unknown feature: {name}")
            continue

        # Skip DC (not a state)
        if code == "DC":
            continue

        # Write individual GeoJSON
        out_path = os.path.join(GEOJSON_US_DIR, f"{code}.geojson")
        geojson = {
            "type": "FeatureCollection",
            "features": [feature],
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False)
        count += 1
        print(f"  ✓ {code} — {name}")

    print(f"\nDone! Created {count} state GeoJSON files in {GEOJSON_US_DIR}")


if __name__ == "__main__":
    download_and_split()
