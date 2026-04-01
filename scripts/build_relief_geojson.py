#!/usr/bin/env python3
"""
Pipeline to download and process GeoJSON geometries for relief features.

Tier 1: Natural Earth shapefiles (matched by wikidata_id)
Tier 2: Nominatim lookup (for features with P402 OSM relation ID from Wikidata)
Tier 3: Overpass API (for features with wikidata tag in OSM but no P402)

Output: individual simplified GeoJSON files in static/data/relief_geojson/{wikidata_id}.geojson
"""

import csv
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

import geopandas as gpd
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "static" / "data" / "relief_features.csv"
OUT_DIR = BASE_DIR / "static" / "data" / "relief_geojson"
CACHE_DIR = BASE_DIR / "static" / "data" / "_cache" / "relief_geo"

NE_URLS = {
    "rivers": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_rivers_lake_centerlines.zip",
    "lakes": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip",
    "regions": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_geography_regions_polys.zip",
}

# Simplification tolerance in degrees (~1km at equator)
SIMPLIFY_TOLERANCE = 0.01
# Max coordinate count after simplification
MAX_COORDS = 5000

NOMINATIM_URL = "https://nominatim.openstreetmap.org/lookup"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

USER_AGENT = "GeoFreak-Relief-Pipeline/1.0 (educational project)"


def load_csv():
    """Load relief features CSV."""
    features = {}
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            wid = row["wikidata_id"].strip()
            if wid:
                features[wid] = row
    print(f"Loaded {len(features)} features from CSV")
    return features


def count_coords(geojson_geom):
    """Count total coordinate points in a GeoJSON geometry."""
    s = json.dumps(geojson_geom)
    # Rough count: each coordinate pair has two numbers
    return s.count(",") // 2


def simplify_geometry(geojson_geom, tolerance=SIMPLIFY_TOLERANCE):
    """Simplify a GeoJSON geometry using shapely."""
    try:
        geom = shape(geojson_geom)
        if geom.is_empty:
            return None
        simplified = geom.simplify(tolerance, preserve_topology=True)
        if simplified.is_empty:
            return None
        result = mapping(simplified)
        # If still too many coords, increase tolerance
        n_coords = count_coords(result)
        if n_coords > MAX_COORDS:
            simplified = geom.simplify(tolerance * 3, preserve_topology=True)
            result = mapping(simplified)
        if n_coords > MAX_COORDS * 2:
            simplified = geom.simplify(tolerance * 10, preserve_topology=True)
            result = mapping(simplified)
        return result
    except Exception as e:
        print(f"  Simplify error: {e}")
        return None


def save_geojson(wikidata_id, geometry, feature_name=""):
    """Save a single GeoJSON geometry to file."""
    out_path = OUT_DIR / f"{wikidata_id}.geojson"
    geojson = {
        "type": "Feature",
        "properties": {"wikidata_id": wikidata_id, "name": feature_name},
        "geometry": geometry,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, separators=(",", ":"))
    return out_path


def download_file(url, dest_path):
    """Download a file with progress."""
    if dest_path.exists():
        print(f"  Cached: {dest_path.name}")
        return
    print(f"  Downloading {url}...")
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=120) as resp:
        data = resp.read()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(data)
    print(f"  Saved: {dest_path.name} ({len(data) / 1024 / 1024:.1f} MB)")


# ── TIER 1: Natural Earth ─────────────────────────────────────

def tier1_natural_earth(features, covered):
    """Download Natural Earth shapefiles and match by wikidata_id."""
    print("\n" + "=" * 60)
    print("TIER 1: Natural Earth")
    print("=" * 60)

    matched = 0
    for layer_name, url in NE_URLS.items():
        zip_path = CACHE_DIR / f"ne_{layer_name}.zip"
        download_file(url, zip_path)

        # Extract shapefile from zip
        extract_dir = CACHE_DIR / f"ne_{layer_name}"
        if not extract_dir.exists():
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)
            print(f"  Extracted {layer_name}")

        # Find the .shp file
        shp_files = list(extract_dir.rglob("*.shp"))
        if not shp_files:
            print(f"  ERROR: No .shp found in {layer_name}")
            continue

        gdf = gpd.read_file(shp_files[0])
        print(f"  {layer_name}: {len(gdf)} features, columns: {list(gdf.columns)[:8]}...")

        # Find wikidataid column (case varies)
        wid_col = None
        for col in gdf.columns:
            if col.lower() in ("wikidataid", "wikidata_id", "wikidata"):
                wid_col = col
                break

        if not wid_col:
            print(f"  WARNING: No wikidata column in {layer_name}")
            continue

        layer_matched = 0
        for _, row in gdf.iterrows():
            wid = str(row[wid_col]).strip()
            if not wid or wid == "None" or wid == "nan":
                continue
            if wid not in features:
                continue
            if wid in covered:
                continue

            geom = row.geometry
            if geom is None or geom.is_empty:
                continue

            geojson_geom = simplify_geometry(mapping(geom))
            if geojson_geom is None:
                continue

            name = features[wid].get("name", "")
            save_geojson(wid, geojson_geom, name)
            covered.add(wid)
            layer_matched += 1

        matched += layer_matched
        print(f"  → {layer_matched} matched from {layer_name}")

    print(f"\nTier 1 total: {matched} features with geometry")
    return matched


# ── TIER 2: Wikidata P402 + Nominatim ────────────────────────

def fetch_p402_from_wikidata(wikidata_ids):
    """Query Wikidata SPARQL for P402 (OSM relation ID) values."""
    print("  Querying Wikidata for P402 (OSM relation IDs)...")
    results = {}
    batch_size = 200
    ids_list = list(wikidata_ids)

    for i in range(0, len(ids_list), batch_size):
        batch = ids_list[i : i + batch_size]
        values = " ".join(f"wd:{wid}" for wid in batch)
        query = f"""
        SELECT ?item ?osmRelation WHERE {{
          VALUES ?item {{ {values} }}
          ?item wdt:P402 ?osmRelation .
        }}
        """
        try:
            req = Request(
                f"{WIKIDATA_SPARQL}?query={__import__('urllib.parse', fromlist=['quote']).quote(query)}&format=json",
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            for binding in data["results"]["bindings"]:
                wid = binding["item"]["value"].split("/")[-1]
                osm_id = binding["osmRelation"]["value"]
                results[wid] = osm_id
        except Exception as e:
            print(f"  SPARQL batch error: {e}")
        if i + batch_size < len(ids_list):
            time.sleep(1)

    print(f"  Found {len(results)} P402 values")
    return results


def fetch_nominatim_batch(osm_ids_map, features, covered):
    """Fetch GeoJSON from Nominatim in batches of 50."""
    print("  Fetching geometry from Nominatim...")
    matched = 0
    items = [(wid, osm_id) for wid, osm_id in osm_ids_map.items() if wid not in covered]
    print(f"  {len(items)} features to fetch")

    batch_size = 50
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        osm_ids_str = ",".join(f"R{osm_id}" for _, osm_id in batch)
        url = f"{NOMINATIM_URL}?osm_ids={osm_ids_str}&format=geojson&polygon_geojson=1&polygon_threshold=0.005"

        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())

            if data.get("type") == "FeatureCollection":
                # Map OSM IDs back to wikidata IDs
                osm_to_wid = {osm_id: wid for wid, osm_id in batch}

                for feat in data.get("features", []):
                    osm_type = feat.get("properties", {}).get("osm_type", "")
                    osm_id = str(feat.get("properties", {}).get("osm_id", ""))

                    # Find corresponding wikidata ID
                    wid = osm_to_wid.get(osm_id)
                    if not wid:
                        # Try matching by extratags.wikidata
                        extra = feat.get("properties", {}).get("extratags", {})
                        if extra and "wikidata" in extra:
                            wid = extra["wikidata"]
                    if not wid or wid in covered:
                        continue

                    geom = feat.get("geometry")
                    if not geom or geom.get("type") == "Point":
                        continue

                    geojson_geom = simplify_geometry(geom)
                    if geojson_geom is None:
                        continue

                    name = features.get(wid, {}).get("name", "")
                    save_geojson(wid, geojson_geom, name)
                    covered.add(wid)
                    matched += 1

        except Exception as e:
            print(f"  Nominatim batch error at {i}: {e}")

        time.sleep(1.1)  # Rate limit
        if (i // batch_size + 1) % 5 == 0:
            print(f"    {i + batch_size}/{len(items)} processed, {matched} matched")

    print(f"  → {matched} matched from Nominatim")
    return matched


def tier2_nominatim(features, covered):
    """Fetch geometries via Wikidata P402 → Nominatim."""
    print("\n" + "=" * 60)
    print("TIER 2: Wikidata P402 + Nominatim")
    print("=" * 60)

    uncovered = {wid for wid in features if wid not in covered}
    print(f"  {len(uncovered)} features still need geometry")

    # Cache P402 results
    p402_cache = CACHE_DIR / "p402_map.json"
    if p402_cache.exists():
        with open(p402_cache) as f:
            p402_map = json.load(f)
        print(f"  Loaded {len(p402_map)} cached P402 values")
        # Fetch any new ones
        new_ids = uncovered - set(p402_map.keys()) - {wid for wid, v in p402_map.items() if v is None}
        if new_ids:
            new_p402 = fetch_p402_from_wikidata(new_ids)
            # Mark missing ones as None
            for wid in new_ids:
                if wid not in new_p402:
                    p402_map[wid] = None
                else:
                    p402_map[wid] = new_p402[wid]
            with open(p402_cache, "w") as f:
                json.dump(p402_map, f)
    else:
        p402_map_raw = fetch_p402_from_wikidata(uncovered)
        p402_map = {}
        for wid in uncovered:
            p402_map[wid] = p402_map_raw.get(wid)
        with open(p402_cache, "w") as f:
            json.dump(p402_map, f)

    # Filter to valid P402 entries
    valid_p402 = {wid: osm_id for wid, osm_id in p402_map.items()
                  if osm_id is not None and wid not in covered}
    print(f"  {len(valid_p402)} features with valid P402")

    if valid_p402:
        matched = fetch_nominatim_batch(valid_p402, features, covered)
        return matched
    return 0


# ── TIER 3: Overpass API ──────────────────────────────────────

def tier3_overpass(features, covered):
    """Fetch geometries from Overpass API by wikidata tag."""
    print("\n" + "=" * 60)
    print("TIER 3: Overpass API")
    print("=" * 60)

    # Only try types that are likely to have polygon/line geometry in OSM
    USEFUL_TYPES = {"river", "lake", "island", "mountain_range", "glacier",
                    "peninsula", "desert", "plateau", "strait", "plain",
                    "cape", "valley", "canyon"}

    uncovered = [wid for wid in features
                 if wid not in covered and features[wid]["type"] in USEFUL_TYPES]
    print(f"  {len(uncovered)} features to try via Overpass")

    matched = 0
    errors = 0

    for idx, wid in enumerate(uncovered):
        if errors > 10:
            print("  Too many errors, stopping Overpass tier")
            break

        query = f"""
[out:json][timeout:30];
(relation["wikidata"="{wid}"];way["wikidata"="{wid}"];);
out geom;
"""
        try:
            import urllib.parse
            req = Request(
                OVERPASS_URL,
                data=f"data={urllib.parse.quote(query)}".encode(),
                headers={"User-Agent": USER_AGENT},
                method="POST",
            )
            with urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())

            elements = data.get("elements", [])
            if not elements:
                time.sleep(1.5)
                continue

            # Convert OSM elements to geometry
            geom = osm_elements_to_geojson(elements)
            if geom is None:
                time.sleep(1.5)
                continue

            geojson_geom = simplify_geometry(geom)
            if geojson_geom is None:
                time.sleep(1.5)
                continue

            name = features[wid].get("name", "")
            save_geojson(wid, geojson_geom, name)
            covered.add(wid)
            matched += 1
            errors = 0  # Reset on success

        except (HTTPError, URLError, TimeoutError) as e:
            errors += 1
            print(f"  Overpass error for {wid}: {e}")
        except Exception as e:
            print(f"  Overpass parse error for {wid}: {e}")

        time.sleep(2)  # Be nice to Overpass
        if (idx + 1) % 20 == 0:
            print(f"    {idx + 1}/{len(uncovered)} processed, {matched} matched")

    print(f"  → {matched} matched from Overpass")
    return matched


def osm_elements_to_geojson(elements):
    """Convert Overpass JSON elements to a GeoJSON geometry."""
    from shapely.geometry import LineString, Polygon, MultiLineString, MultiPolygon

    lines = []
    polygons = []

    for el in elements:
        if el["type"] == "way" and "geometry" in el:
            coords = [(pt["lon"], pt["lat"]) for pt in el["geometry"]]
            if len(coords) < 2:
                continue
            if coords[0] == coords[-1] and len(coords) >= 4:
                polygons.append(Polygon(coords))
            else:
                lines.append(LineString(coords))

        elif el["type"] == "relation" and "members" in el:
            for member in el["members"]:
                if member["type"] == "way" and "geometry" in member:
                    coords = [(pt["lon"], pt["lat"]) for pt in member["geometry"]]
                    if len(coords) < 2:
                        continue
                    role = member.get("role", "")
                    if role in ("outer", "inner", "") and coords[0] == coords[-1] and len(coords) >= 4:
                        polygons.append(Polygon(coords))
                    else:
                        lines.append(LineString(coords))

    # Prefer polygons over lines
    if polygons:
        try:
            merged = unary_union(polygons)
            return mapping(merged)
        except Exception:
            if len(polygons) == 1:
                return mapping(polygons[0])
            return mapping(MultiPolygon(polygons))

    if lines:
        if len(lines) == 1:
            return mapping(lines[0])
        try:
            from shapely.ops import linemerge
            merged = linemerge(lines)
            return mapping(merged)
        except Exception:
            return mapping(MultiLineString(lines))

    return None


# ── MAIN ──────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    features = load_csv()
    covered = set()

    # Check already-existing GeoJSON files
    existing = 0
    for f in OUT_DIR.glob("Q*.geojson"):
        wid = f.stem
        if wid in features:
            covered.add(wid)
            existing += 1
    if existing:
        print(f"Already have {existing} GeoJSON files")

    # Run tiers
    t1 = tier1_natural_earth(features, covered)
    t2 = tier2_nominatim(features, covered)
    t3 = tier3_overpass(features, covered)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Tier 1 (Natural Earth): {t1}")
    print(f"  Tier 2 (Nominatim):     {t2}")
    print(f"  Tier 3 (Overpass):      {t3}")
    print(f"  Already existing:       {existing}")
    print(f"  Total with geometry:    {len(covered)} / {len(features)}")
    print(f"  Missing:                {len(features) - len(covered)}")

    # Per-type breakdown
    type_counts = {}
    type_covered = {}
    for wid, row in features.items():
        t = row["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
        if wid in covered:
            type_covered[t] = type_covered.get(t, 0) + 1

    print("\n  Type breakdown:")
    for t in sorted(type_counts.keys(), key=lambda x: -type_counts[x]):
        total = type_counts[t]
        got = type_covered.get(t, 0)
        pct = got * 100 // total if total else 0
        print(f"    {t:20s}: {got:4d}/{total:4d} ({pct}%)")


if __name__ == "__main__":
    main()
