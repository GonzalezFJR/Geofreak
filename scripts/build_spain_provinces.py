"""Download Spain province GeoJSON boundaries.

Creates individual GeoJSON files in static/data/geojson_spain/ for each province.
Uses a public GeoJSON of Spanish provinces.
"""

import json
import os
import urllib.request

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "data")
GEOJSON_DIR = os.path.join(DATA_DIR, "geojson_spain")

# Public source: Spanish provinces
SOURCE_URL = (
    "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/spain-provinces.geojson"
)

# Province name → code mapping (INE codes)
NAME_TO_CODE = {
    "Álava": "01", "Albacete": "02", "Alicante": "03", "Almería": "04",
    "Ávila": "05", "Badajoz": "06", "Islas Baleares": "07", "Barcelona": "08",
    "Burgos": "09", "Cáceres": "10", "Cádiz": "11", "Castellón": "12",
    "Ciudad Real": "13", "Córdoba": "14", "A Coruña": "15", "Cuenca": "16",
    "Girona": "17", "Granada": "18", "Guadalajara": "19", "Guipúzcoa": "20",
    "Huelva": "21", "Huesca": "22", "Jaén": "23", "León": "24",
    "Lleida": "25", "La Rioja": "26", "Lugo": "27", "Madrid": "28",
    "Málaga": "29", "Murcia": "30", "Navarra": "31", "Ourense": "32",
    "Asturias": "33", "Palencia": "34", "Las Palmas": "35", "Pontevedra": "36",
    "Salamanca": "37", "Santa Cruz de Tenerife": "38", "Cantabria": "39",
    "Segovia": "40", "Sevilla": "41", "Soria": "42", "Tarragona": "43",
    "Teruel": "44", "Toledo": "45", "Valencia": "46", "Valladolid": "47",
    "Vizcaya": "48", "Zamora": "49", "Zaragoza": "50", "Ceuta": "51", "Melilla": "52",
    # Alternative names
    "Araba/Álava": "01", "Araba": "01", "Alacant": "03", "Illes Balears": "07",
    "Bizkaia": "48", "Gipuzkoa": "20", "Castelló": "12", "València": "46",
    "Coruña (A)": "15", "Palmas (Las)": "35", "Rioja (La)": "26",
    "Balears (Illes)": "07", "Alicante/Alacant": "03", "Valencia/València": "46",
    "Castellón/Castelló": "12",
}


def download_and_split():
    """Download combined Spain provinces GeoJSON and split into files."""
    os.makedirs(GEOJSON_DIR, exist_ok=True)

    print(f"Downloading Spain provinces GeoJSON from {SOURCE_URL}...")
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "GeoFreak/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    features = data.get("features", [])
    print(f"Found {len(features)} features.")

    count = 0
    for feature in features:
        props = feature.get("properties", {})
        name = props.get("name", "")

        code = NAME_TO_CODE.get(name)
        if not code:
            # Try partial match
            for k, v in NAME_TO_CODE.items():
                if k.lower() in name.lower() or name.lower() in k.lower():
                    code = v
                    break

        if not code:
            print(f"  ⚠ Skipping unknown: {name}")
            continue

        out_path = os.path.join(GEOJSON_DIR, f"{code}.geojson")
        geojson = {"type": "FeatureCollection", "features": [feature]}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False)
        count += 1
        print(f"  ✓ {code} — {name}")

    print(f"\nDone! Created {count} province GeoJSON files in {GEOJSON_DIR}")


if __name__ == "__main__":
    download_and_split()
