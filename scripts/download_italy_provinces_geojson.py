#!/usr/bin/env python3
"""
Script to download and process GeoJSON files for Italian provinces.
Source: ISTAT (Istituto Nazionale di Statistica) administrative boundaries
"""

import json
import os
import urllib.request
import ssl

# Province codes mapping to their ISTAT codes (for reference)
PROVINCE_CODES = [
    "AG", "AL", "AN", "AO", "AP", "AQ", "AR", "AT", "AV", "BA",
    "BG", "BI", "BL", "BN", "BO", "BR", "BS", "BT", "BZ", "CA",
    "CB", "CE", "CH", "CI", "CL", "CN", "CO", "CR", "CS", "CT",
    "CZ", "EN", "FC", "FE", "FG", "FI", "FM", "FR", "GE", "GO",
    "GR", "IM", "IS", "KR", "LC", "LE", "LI", "LO", "LT", "LU",
    "MB", "MC", "ME", "MI", "MN", "MO", "MS", "MT", "NA", "NO",
    "NU", "OG", "OR", "OT", "PA", "PC", "PD", "PE", "PG", "PI",
    "PN", "PO", "PR", "PT", "PU", "PV", "PZ", "RA", "RC", "RE",
    "RG", "RI", "RM", "RN", "RO", "SA", "SI", "SO", "SP", "SR",
    "SS", "SU", "SV", "TA", "TE", "TN", "TO", "TP", "TR", "TS",
    "TV", "UD", "VA", "VB", "VC", "VE", "VI", "VR", "VS", "VT", "VV"
]

# GADM URL for Italy administrative level 2 (provinces)
GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_ITA_2.json"

# Alternative: OpenDataSoft ISTAT data
OPENDATASOFT_URL = "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/georef-italy-provincia/exports/geojson"

def download_geojson():
    """Download the GeoJSON file containing all Italian provinces."""
    output_dir = os.path.join(os.path.dirname(__file__), "..", "static", "data", "geojson_italy_provinces")
    os.makedirs(output_dir, exist_ok=True)

    # Try GADM first
    print("Downloading Italian provinces GeoJSON from GADM...")

    # Create SSL context that doesn't verify (for some servers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(GADM_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=60) as response:
            data = json.loads(response.read().decode('utf-8'))
            process_gadm_data(data, output_dir)
            return True
    except Exception as e:
        print(f"GADM download failed: {e}")

    # Try OpenDataSoft as backup
    print("Trying OpenDataSoft...")
    try:
        req = urllib.request.Request(OPENDATASOFT_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=60) as response:
            data = json.loads(response.read().decode('utf-8'))
            process_opendatasoft_data(data, output_dir)
            return True
    except Exception as e:
        print(f"OpenDataSoft download failed: {e}")

    return False


def process_gadm_data(data, output_dir):
    """Process GADM format GeoJSON and split by province."""
    # GADM uses different property names
    # NAME_2 is the province name, HASC_2 includes the province code

    code_mapping = create_province_code_mapping()

    for feature in data.get('features', []):
        props = feature.get('properties', {})
        name = props.get('NAME_2', '')
        hasc = props.get('HASC_2', '')  # Format: IT.XX.YY

        # Extract province code from HASC or map from name
        code = None
        if hasc:
            parts = hasc.split('.')
            if len(parts) >= 3:
                code = parts[2]

        if not code:
            code = code_mapping.get(name.lower())

        if code and code in PROVINCE_CODES:
            save_province_geojson(feature, code, output_dir)
            print(f"Saved {code}: {name}")
        else:
            print(f"Warning: Could not map province '{name}' (HASC: {hasc})")


def process_opendatasoft_data(data, output_dir):
    """Process OpenDataSoft format GeoJSON and split by province."""
    code_mapping = create_province_code_mapping()

    for feature in data.get('features', []):
        props = feature.get('properties', {})
        name = props.get('prov_name', props.get('name', ''))
        code = props.get('prov_sigla', props.get('prov_acr', ''))

        if not code:
            code = code_mapping.get(name.lower())

        if code and code in PROVINCE_CODES:
            save_province_geojson(feature, code, output_dir)
            print(f"Saved {code}: {name}")
        else:
            print(f"Warning: Could not map province '{name}'")


def create_province_code_mapping():
    """Create a mapping from province names to codes."""
    return {
        'agrigento': 'AG', 'alessandria': 'AL', 'ancona': 'AN', 'aosta': 'AO',
        "valle d'aosta": 'AO', "valle d'aosta/vallée d'aoste": 'AO',
        'ascoli piceno': 'AP', 'ascolipiceno': 'AP', "l'aquila": 'AQ', 'aquila': 'AQ',
        'arezzo': 'AR', 'asti': 'AT', 'avellino': 'AV', 'bari': 'BA',
        'bergamo': 'BG', 'biella': 'BI', 'belluno': 'BL', 'benevento': 'BN',
        'bologna': 'BO', 'brindisi': 'BR', 'brescia': 'BS',
        'barletta-andria-trani': 'BT', 'bolzano': 'BZ', 'bozen': 'BZ',
        'bolzano/bozen': 'BZ', 'cagliari': 'CA', 'campobasso': 'CB',
        'caserta': 'CE', 'chieti': 'CH', 'carbonia-iglesias': 'CI',
        'caltanissetta': 'CL', 'cuneo': 'CN', 'como': 'CO', 'cremona': 'CR',
        'cosenza': 'CS', 'catania': 'CT', 'catanzaro': 'CZ', 'enna': 'EN',
        'forlì-cesena': 'FC', 'forli-cesena': 'FC', "forli'-cesena": 'FC', 'ferrara': 'FE',
        'foggia': 'FG', 'firenze': 'FI', 'florence': 'FI', 'fermo': 'FM',
        'frosinone': 'FR', 'genova': 'GE', 'gorizia': 'GO', 'grosseto': 'GR',
        'imperia': 'IM', 'isernia': 'IS', 'crotone': 'KR', 'lecco': 'LC',
        'lecce': 'LE', 'livorno': 'LI', 'lodi': 'LO', 'latina': 'LT',
        'lucca': 'LU', 'monza e brianza': 'MB', 'monza e della brianza': 'MB',
        'monzaandbrianza': 'MB', 'macerata': 'MC', 'messina': 'ME',
        'milano': 'MI', 'milan': 'MI', 'mantova': 'MN', 'mantua': 'MN',
        'modena': 'MO', 'massa-carrara': 'MS', 'massa carrara': 'MS',
        'massacarrara': 'MS', 'matera': 'MT', 'napoli': 'NA', 'naples': 'NA',
        'novara': 'NO', 'nuoro': 'NU', 'ogliastra': 'OG', 'oristano': 'OR',
        'olbia-tempio': 'OT', 'palermo': 'PA', 'piacenza': 'PC', 'padova': 'PD',
        'padua': 'PD', 'pescara': 'PE', 'perugia': 'PG', 'pisa': 'PI',
        'pordenone': 'PN', 'prato': 'PO', 'parma': 'PR', 'pistoia': 'PT',
        'pesaro e urbino': 'PU', 'pesaro-urbino': 'PU', 'pesaroeurbino': 'PU',
        'pavia': 'PV', 'potenza': 'PZ', 'ravenna': 'RA',
        'reggio calabria': 'RC', 'reggio di calabria': 'RC', 'reggiodicalabria': 'RC',
        'reggio emilia': 'RE', "reggio nell'emilia": 'RE', "reggionell'emilia": 'RE',
        'ragusa': 'RG', 'rieti': 'RI', 'roma': 'RM', 'rome': 'RM', 'rimini': 'RN',
        'rovigo': 'RO', 'salerno': 'SA', 'siena': 'SI', 'sondrio': 'SO',
        'la spezia': 'SP', 'laspezia': 'SP', 'siracusa': 'SR', 'syracuse': 'SR',
        'sassari': 'SS', 'sud sardegna': 'SU', 'savona': 'SV', 'taranto': 'TA',
        'teramo': 'TE', 'trento': 'TN', 'torino': 'TO', 'turin': 'TO',
        'trapani': 'TP', 'terni': 'TR', 'trieste': 'TS', 'treviso': 'TV',
        'udine': 'UD', 'varese': 'VA', 'verbano-cusio-ossola': 'VB',
        'vercelli': 'VC', 'venezia': 'VE', 'venice': 'VE', 'vicenza': 'VI',
        'verona': 'VR', 'medio campidano': 'VS', 'mediocampidano': 'VS',
        'viterbo': 'VT', 'vibo valentia': 'VV', 'vibovalentia': 'VV'
    }


def save_province_geojson(feature, code, output_dir):
    """Save a single province as a GeoJSON file."""
    geojson = {
        "type": "FeatureCollection",
        "features": [feature]
    }

    filepath = os.path.join(output_dir, f"{code}.geojson")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)


def simplify_geometry(geometry, tolerance=0.001):
    """Simplify geometry to reduce file size (basic implementation)."""
    # This is a basic point reduction - for production use shapely or similar
    if geometry['type'] == 'Polygon':
        geometry['coordinates'] = [simplify_ring(ring, tolerance) for ring in geometry['coordinates']]
    elif geometry['type'] == 'MultiPolygon':
        geometry['coordinates'] = [
            [simplify_ring(ring, tolerance) for ring in polygon]
            for polygon in geometry['coordinates']
        ]
    return geometry


def simplify_ring(ring, tolerance):
    """Reduce points in a ring while maintaining shape (basic)."""
    if len(ring) <= 10:
        return ring
    # Keep every nth point based on tolerance
    step = max(1, int(len(ring) * tolerance * 10))
    simplified = ring[::step]
    # Ensure ring is closed
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified


if __name__ == '__main__':
    if download_geojson():
        print("\nGeoJSON files downloaded successfully!")
    else:
        print("\nFailed to download GeoJSON files.")
        print("Please download manually from ISTAT or GADM.")
