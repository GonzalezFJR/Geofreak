"""Download Russia regions GeoJSON boundaries.

Creates individual GeoJSON files in static/data/geojson_russia/ for each
federal subject.
Uses a simplified public GeoJSON of Russian regions.
"""

import json
import os
import urllib.request

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "data")
GEOJSON_DIR = os.path.join(DATA_DIR, "geojson_russia")

# Public source: Russia administrative regions
SOURCE_URL = (
    "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/russia.geojson"
)

# Region name → our CSV code mapping (Cyrillic names from source)
NAME_TO_CODE = {
    # Cyrillic names (as they appear in the GeoJSON)
    "Адыгея": "AD", "Алтай": "AL", "Алтайский край": "ALT",
    "Амурская область": "AMU", "Архангельская область": "ARK",
    "Астраханская область": "AST", "Башкортостан": "BA",
    "Белгородская область": "BEL", "Брянская область": "BRY",
    "Бурятия": "BU", "Чеченская республика": "CE",
    "Челябинская область": "CHE", "Чукотский автономный округ": "CHU",
    "Чувашия": "CU", "Дагестан": "DA", "Ингушетия": "IN",
    "Иркутская область": "IRK", "Ивановская область": "IVA",
    "Еврейская автономная область": "Jewish",
    "Кабардино-Балкарская республика": "KB",
    "Калининградская область": "KGD", "Калужская область": "KLU",
    "Камчатский край": "KAM", "Карачаево-Черкесская республика": "KC",
    "Республика Карелия": "KR", "Кемеровская область": "KEM",
    "Хабаровский край": "KHA",
    "Ханты-Мансийский автономный округ - Югра": "KHM",
    "Кировская область": "KIR", "Республика Коми": "KO",
    "Костромская область": "KOS", "Краснодарский край": "KDA",
    "Красноярский край": "KYA", "Курганская область": "KGN",
    "Курская область": "KRS", "Ленинградская область": "LEN",
    "Липецкая область": "LIP", "Магаданская область": "MAG",
    "Марий Эл": "ME", "Республика Мордовия": "MO",
    "Москва": "MOW", "Московская область": "MOS",
    "Мурманская область": "MUR", "Нижегородская область": "NIZ",
    "Новгородская область": "NGR", "Новосибирская область": "NVS",
    "Омская область": "OMS", "Оренбургская область": "ORE",
    "Орловская область": "ORL", "Пензенская область": "PNZ",
    "Пермский край": "PER", "Приморский край": "PRI",
    "Псковская область": "PSK", "Ростовская область": "ROS",
    "Рязанская область": "RYA", "Санкт-Петербург": "SPE",
    "Сахалинская область": "SAK", "Самарская область": "SAM",
    "Саратовская область": "SAR",
    "Республика Саха (Якутия)": "SA",
    "Северная Осетия - Алания": "SE",
    "Смоленская область": "SMO", "Ставропольский край": "STA",
    "Свердловская область": "SVE", "Тамбовская область": "TAM",
    "Татарстан": "TA", "Томская область": "TOM",
    "Тульская область": "TUL", "Тыва": "TY",
    "Тверская область": "TVE", "Тюменская область": "TYU",
    "Удмуртская республика": "UD", "Ульяновская область": "ULY",
    "Владимирская область": "VLA", "Волгоградская область": "VGG",
    "Вологодская область": "VLG", "Воронежская область": "VOR",
    "Ямало-Ненецкий автономный округ": "YAN",
    "Ярославская область": "YAR", "Забайкальский край": "ZAB",
}


def download_and_split():
    """Download combined Russia GeoJSON and split into individual files."""
    os.makedirs(GEOJSON_DIR, exist_ok=True)

    print(f"Downloading Russia regions GeoJSON from {SOURCE_URL}...")
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "GeoFreak/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    features = data.get("features", [])
    print(f"Found {len(features)} features.")

    count = 0
    matched_codes = set()
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

        if code in matched_codes:
            continue
        matched_codes.add(code)

        out_path = os.path.join(GEOJSON_DIR, f"{code}.geojson")
        geojson = {"type": "FeatureCollection", "features": [feature]}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False)
        count += 1
        print(f"  ✓ {code} — {name}")

    print(f"\nDone! Created {count} region GeoJSON files in {GEOJSON_DIR}")


if __name__ == "__main__":
    download_and_split()
