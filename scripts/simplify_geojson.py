"""Generate a simplified (lightweight) GeoJSON for game maps.

Reads all_countries.geojson, simplifies geometries using Douglas-Peucker,
rounds coordinates to 2 decimal places, strips unnecessary properties,
and writes all_countries_simple.geojson.

Usage:
    python scripts/simplify_geojson.py [tolerance]
    Default tolerance: 0.05 degrees (~5 km at equator)
"""

import json
import os
import sys

from shapely.geometry import shape, mapping
from shapely.validation import make_valid

GEOJSON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "static", "data", "geojson"
)
INPUT = os.path.join(GEOJSON_DIR, "all_countries.geojson")
OUTPUT = os.path.join(GEOJSON_DIR, "all_countries_simple.geojson")

# Properties to keep (minimal set for games)
KEEP_PROPS = {"ISO_A3", "name", "NAME"}


def simplify_feature(feature: dict, tolerance: float) -> dict | None:
    """Simplify a single GeoJSON feature."""
    geom = feature.get("geometry")
    if not geom:
        return None

    try:
        shp = shape(geom)
        if not shp.is_valid:
            shp = make_valid(shp)
        simplified = shp.simplify(tolerance, preserve_topology=True)
        if simplified.is_empty:
            return None
    except Exception:
        return None

    # Round coordinates to 2 decimal places (~1.1 km precision)
    simple_geom = mapping(simplified)
    simple_geom = round_coords(simple_geom)

    # Strip properties to minimal set
    props = feature.get("properties", {})
    minimal_props = {k: v for k, v in props.items() if k in KEEP_PROPS}

    return {
        "type": "Feature",
        "properties": minimal_props,
        "geometry": simple_geom,
    }


def round_coords(geom: dict, precision: int = 2) -> dict:
    """Round all coordinates in a GeoJSON geometry dict."""
    def _round(coords):
        if isinstance(coords[0], (list, tuple)):
            return [_round(c) for c in coords]
        return [round(c, precision) for c in coords]

    return {
        "type": geom["type"],
        "coordinates": _round(geom["coordinates"]),
    }


def count_points(geom: dict) -> int:
    """Count total coordinate points in a geometry."""
    total = 0
    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])
    if gtype == "Polygon":
        for ring in coords:
            total += len(ring)
    elif gtype == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                total += len(ring)
    return total


def main():
    tolerance = float(sys.argv[1]) if len(sys.argv) > 1 else 0.05

    print(f"Reading {INPUT}...")
    with open(INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    features_in = data["features"]
    total_pts_in = sum(count_points(f.get("geometry", {})) for f in features_in)

    features_out = []
    for feat in features_in:
        simplified = simplify_feature(feat, tolerance)
        if simplified:
            features_out.append(simplified)

    total_pts_out = sum(count_points(f.get("geometry", {})) for f in features_out)

    result = {"type": "FeatureCollection", "features": features_out}
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, separators=(",", ":"))

    size_in = os.path.getsize(INPUT)
    size_out = os.path.getsize(OUTPUT)

    print(f"Features: {len(features_in)} → {len(features_out)}")
    print(f"Points:   {total_pts_in:,} → {total_pts_out:,} ({100*total_pts_out/total_pts_in:.1f}%)")
    print(f"Size:     {size_in/1024/1024:.1f} MB → {size_out/1024/1024:.1f} MB ({100*size_out/size_in:.1f}%)")
    print(f"Written to {OUTPUT}")


if __name__ == "__main__":
    main()
