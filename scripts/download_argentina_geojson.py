#!/usr/bin/env python3
"""Download GeoJSON files for Argentine provinces from GADM."""

import json
import os
import urllib.request
import ssl

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_ARG_1.json"

CODE_MAPPING = {
    'buenos aires': 'AR-B', 'buenosaires': 'AR-B',
    'ciudad autónoma de buenos aires': 'AR-C',
    'ciudad de buenos aires': 'AR-C', 'capital federal': 'AR-C',
    'ciudaddebuenosaires': 'AR-C',
    'catamarca': 'AR-K', 'chaco': 'AR-H', 'chubut': 'AR-U',
    'córdoba': 'AR-X', 'cordoba': 'AR-X', 'corrientes': 'AR-W',
    'entre ríos': 'AR-E', 'entre rios': 'AR-E', 'entreríos': 'AR-E',
    'formosa': 'AR-P',
    'jujuy': 'AR-Y', 'la pampa': 'AR-L', 'lapampa': 'AR-L',
    'la rioja': 'AR-F', 'larioja': 'AR-F',
    'mendoza': 'AR-M', 'misiones': 'AR-N', 'neuquén': 'AR-Q',
    'neuquen': 'AR-Q', 'río negro': 'AR-R', 'rio negro': 'AR-R',
    'ríonegro': 'AR-R',
    'salta': 'AR-A', 'san juan': 'AR-J', 'sanjuan': 'AR-J',
    'san luis': 'AR-D', 'sanluis': 'AR-D',
    'santa cruz': 'AR-Z', 'santacruz': 'AR-Z',
    'santa fe': 'AR-S', 'santafe': 'AR-S',
    'santiago del estero': 'AR-G', 'santiagodelestero': 'AR-G',
    'tierra del fuego': 'AR-V', 'tierradelfuego': 'AR-V',
    'tierra del fuego, antártida e islas del atlántico sur': 'AR-V',
    'tucumán': 'AR-T', 'tucuman': 'AR-T',
}

ALL_CODES = {
    'AR-B','AR-C','AR-K','AR-H','AR-U','AR-X','AR-W','AR-E',
    'AR-P','AR-Y','AR-L','AR-F','AR-M','AR-N','AR-Q','AR-R',
    'AR-A','AR-J','AR-D','AR-Z','AR-S','AR-G','AR-V','AR-T'
}


def main():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "static", "data", "geojson_argentina")
    os.makedirs(output_dir, exist_ok=True)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    print("Downloading Argentine provinces GeoJSON from GADM...")
    req = urllib.request.Request(GADM_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ctx, timeout=120) as response:
        data = json.loads(response.read().decode('utf-8'))

    found = set()
    for feature in data.get('features', []):
        props = feature.get('properties', {})
        name = props.get('NAME_1', '')
        code = CODE_MAPPING.get(name.lower())

        if code and code in ALL_CODES:
            geojson = {"type": "FeatureCollection", "features": [feature]}
            filepath = os.path.join(output_dir, f"{code}.geojson")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(geojson, f, ensure_ascii=False)
            found.add(code)
            print(f"  Saved {code}: {name}")
        else:
            print(f"  WARNING: Could not map '{name}'")

    missing = ALL_CODES - found
    if missing:
        print(f"\nMissing: {missing}")
    else:
        print(f"\nAll {len(found)} provinces saved successfully!")


if __name__ == '__main__':
    main()
