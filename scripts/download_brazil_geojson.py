#!/usr/bin/env python3
"""Download GeoJSON files for Brazilian states from GADM."""

import json
import os
import urllib.request
import ssl

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_BRA_1.json"

CODE_MAPPING = {
    'acre': 'AC', 'alagoas': 'AL', 'amapá': 'AP', 'amapa': 'AP',
    'amazonas': 'AM', 'bahia': 'BA', 'ceará': 'CE', 'ceara': 'CE',
    'distrito federal': 'DF', 'distritofederal': 'DF',
    'espírito santo': 'ES', 'espirito santo': 'ES', 'espíritosanto': 'ES',
    'goiás': 'GO', 'goias': 'GO', 'maranhão': 'MA', 'maranhao': 'MA',
    'mato grosso': 'MT', 'matogrosso': 'MT',
    'mato grosso do sul': 'MS', 'matogrossodosul': 'MS',
    'minas gerais': 'MG', 'minasgerais': 'MG',
    'pará': 'PA', 'para': 'PA',
    'paraíba': 'PB', 'paraiba': 'PB', 'paraná': 'PR', 'parana': 'PR',
    'pernambuco': 'PE', 'piauí': 'PI', 'piaui': 'PI',
    'rio de janeiro': 'RJ', 'riodejaneiro': 'RJ',
    'rio grande do norte': 'RN', 'riograndedonorte': 'RN',
    'rio grande do sul': 'RS', 'riograndedosul': 'RS',
    'rondônia': 'RO', 'rondonia': 'RO',
    'roraima': 'RR', 'santa catarina': 'SC', 'santacatarina': 'SC',
    'são paulo': 'SP', 'sao paulo': 'SP', 'sãopaulo': 'SP',
    'sergipe': 'SE', 'tocantins': 'TO',
}

ALL_CODES = {
    'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA',
    'MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN',
    'RS','RO','RR','SC','SP','SE','TO'
}


def main():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "static", "data", "geojson_brazil")
    os.makedirs(output_dir, exist_ok=True)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    print("Downloading Brazilian states GeoJSON from GADM...")
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
        print(f"\nAll {len(found)} states saved successfully!")


if __name__ == '__main__':
    main()
