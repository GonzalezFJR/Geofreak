#!/usr/bin/env python3
"""Download GeoJSON files for Mexican states from GADM."""

import json
import os
import urllib.request
import ssl

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_MEX_1.json"

# Mexican state codes used in our CSV (ISO 3166-2:MX style)
CODE_MAPPING = {
    'aguascalientes': 'AGU', 'baja california': 'BCN',
    'bajacalifornia': 'BCN',
    'baja california sur': 'BCS', 'bajacaliforniasur': 'BCS',
    'campeche': 'CAM',
    'chiapas': 'CHP', 'chihuahua': 'CHH',
    'ciudad de méxico': 'CMX', 'coahuila': 'COA',
    'coahuila de zaragoza': 'COA', 'colima': 'COL',
    'durango': 'DUR', 'guanajuato': 'GUA',
    'guerrero': 'GRO', 'hidalgo': 'HID',
    'jalisco': 'JAL', 'méxico': 'MEX', 'mexico': 'MEX',
    'michoacán': 'MIC', 'michoacán de ocampo': 'MIC',
    'morelos': 'MOR', 'nayarit': 'NAY',
    'nuevo león': 'NLE', 'nuevoleón': 'NLE', 'oaxaca': 'OAX',
    'puebla': 'PUE', 'querétaro': 'QUE',
    'quintana roo': 'ROO', 'quintanaroo': 'ROO',
    'san luis potosí': 'SLP', 'sanluispotosí': 'SLP',
    'sinaloa': 'SIN', 'sonora': 'SON',
    'tabasco': 'TAB', 'tamaulipas': 'TAM',
    'tlaxcala': 'TLA', 'veracruz': 'VER',
    'veracruz de ignacio de la llave': 'VER',
    'yucatán': 'YUC', 'zacatecas': 'ZAC',
    'distrito federal': 'CMX', 'distritofederal': 'CMX',
}

ALL_CODES = {
    'AGU','BCN','BCS','CAM','CHP','CHH','CMX','COA','COL','DUR',
    'GRO','GUA','HID','JAL','MEX','MIC','MOR','NAY','NLE','OAX',
    'PUE','QUE','ROO','SIN','SLP','SON','TAB','TAM','TLA','VER',
    'YUC','ZAC'
}


def main():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "static", "data", "geojson_mexico")
    os.makedirs(output_dir, exist_ok=True)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    print("Downloading Mexican states GeoJSON from GADM...")
    req = urllib.request.Request(GADM_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ctx, timeout=120) as response:
        data = json.loads(response.read().decode('utf-8'))

    found = set()
    for feature in data.get('features', []):
        props = feature.get('properties', {})
        name = props.get('NAME_1', '')
        hasc = props.get('HASC_1', '')  # e.g. MX.AG

        code = CODE_MAPPING.get(name.lower())
        if not code and hasc:
            parts = hasc.split('.')
            if len(parts) >= 2:
                short = parts[1]
                # try direct match
                for c in ALL_CODES:
                    if c.startswith(short) or short.startswith(c[:2]):
                        code = c
                        break

        if code and code in ALL_CODES:
            geojson = {"type": "FeatureCollection", "features": [feature]}
            filepath = os.path.join(output_dir, f"{code}.geojson")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(geojson, f, ensure_ascii=False)
            found.add(code)
            print(f"  Saved {code}: {name}")
        else:
            print(f"  WARNING: Could not map '{name}' (HASC: {hasc})")

    missing = ALL_CODES - found
    if missing:
        print(f"\nMissing: {missing}")
    else:
        print(f"\nAll {len(found)} states saved successfully!")


if __name__ == '__main__':
    main()
