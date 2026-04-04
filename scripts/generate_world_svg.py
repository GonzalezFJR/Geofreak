"""
Generate an animated SVG world map from GeoJSON files.
Continents pulse red one by one over a grey background.
The geometry is heavily simplified to keep the SVG small.
"""

import csv
import json
import os
from pathlib import Path
from shapely.geometry import shape, MultiPolygon, Polygon
from shapely.ops import unary_union

BASE_DIR = Path(__file__).resolve().parent.parent
GEOJSON_DIR = BASE_DIR / "static" / "data" / "geojson"
COUNTRIES_CSV = BASE_DIR / "static" / "data" / "countries.csv"
OUTPUT_SVG = BASE_DIR / "static" / "img" / "world_animated.svg"

# Map CSV continents to our desired groups
CONTINENT_GROUPS = {
    "North America": "north_america",
    "South America": "south_america",
    "Europe": "europe",
    "Asia": "asia",
    "Africa": "africa",
    "Oceania": "oceania",
}

SIMPLIFY_TOLERANCE = 0.5  # degrees – aggressive simplification
MIN_AREA = 0.5  # drop polygons smaller than this (sq degrees)

# SVG viewport (Mercator-like equirectangular)
SVG_WIDTH = 900
SVG_HEIGHT = 450
LON_MIN, LON_MAX = -180, 180
LAT_MIN, LAT_MAX = -60, 85  # crop Antarctica


def load_country_continents():
    """Return dict iso_a3 -> continent_group key."""
    mapping = {}
    with open(COUNTRIES_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            iso3 = row["iso_a3"]
            continent = row["continent"]
            group = CONTINENT_GROUPS.get(continent)
            if group:
                mapping[iso3] = group
    return mapping


def load_and_merge_geometries(country_map):
    """Load GeoJSONs, group by continent, simplify and merge."""
    continent_polys = {g: [] for g in CONTINENT_GROUPS.values()}

    for iso3, group in country_map.items():
        path = GEOJSON_DIR / f"{iso3}.geojson"
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for feature in data.get("features", []):
            geom = shape(feature["geometry"])
            if not geom.is_valid:
                geom = geom.buffer(0)
            continent_polys[group].append(geom)

    merged = {}
    for group, polys in continent_polys.items():
        if not polys:
            continue
        union = unary_union(polys)
        simplified = union.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
        # Filter out tiny polygons
        simplified = _filter_small(simplified, MIN_AREA)
        if simplified and not simplified.is_empty:
            merged[group] = simplified
    return merged


def _filter_small(geom, min_area):
    if geom.is_empty:
        return geom
    if isinstance(geom, Polygon):
        return geom if abs(geom.area) >= min_area else Polygon()
    if isinstance(geom, MultiPolygon):
        kept = [p for p in geom.geoms if abs(p.area) >= min_area]
        if not kept:
            return Polygon()
        return MultiPolygon(kept) if len(kept) > 1 else kept[0]
    return geom


def geom_to_svg_path(geom):
    """Convert a Shapely geometry to an SVG path d attribute."""
    parts = []
    polys = []
    if isinstance(geom, Polygon):
        polys = [geom]
    elif isinstance(geom, MultiPolygon):
        polys = list(geom.geoms)

    for poly in polys:
        for ring in [poly.exterior] + list(poly.interiors):
            coords = list(ring.coords)
            if len(coords) < 3:
                continue
            first = _project(coords[0])
            d = f"M{first[0]:.1f},{first[1]:.1f}"
            for c in coords[1:]:
                p = _project(c)
                d += f"L{p[0]:.1f},{p[1]:.1f}"
            d += "Z"
            parts.append(d)
    return " ".join(parts)


def _project(coord):
    """Equirectangular projection: lon,lat -> x,y."""
    lon, lat = coord[0], coord[1]
    x = (lon - LON_MIN) / (LON_MAX - LON_MIN) * SVG_WIDTH
    y = (1 - (lat - LAT_MIN) / (LAT_MAX - LAT_MIN)) * SVG_HEIGHT
    return (x, y)


def _slot_animation(i, n, total_cycle):
    """Return (keyTimes, values) strings for slot i of n in a total_cycle.
    The element is grey except during its 2s slot where it pulses red."""
    slot = total_cycle / n
    t0 = i * slot / total_cycle          # slot start
    t1 = (i * slot + 0.2) / total_cycle  # fade-in done
    t2 = (i * slot + slot - 0.4) / total_cycle  # start fade-out
    t3 = (i * slot + slot) / total_cycle  # slot end
    grey, red = "#cccccc", "#e63946"
    kt = []
    vals = []
    if t0 > 0:
        kt += [0, t0]
        vals += [grey, grey]
    else:
        kt += [0]
        vals += [grey]
    kt += [t1, t2]
    vals += [red, red]
    if t3 < 1:
        kt += [t3, 1]
        vals += [grey, grey]
    else:
        kt += [1]
        vals += [grey]
    kt_str = ";".join(f"{v:.4f}" for v in kt)
    vals_str = ";".join(vals)
    return kt_str, vals_str


def build_svg(merged):
    """Build the animated SVG string."""
    # Animation order
    order = ["north_america", "south_america", "europe", "africa", "asia", "oceania"]
    labels = {
        "north_america": "América del Norte",
        "south_america": "América del Sur",
        "europe": "Europa",
        "africa": "África",
        "asia": "Asia",
        "oceania": "Oceanía",
    }

    n = len(order)
    slot = 2  # seconds per continent
    total_cycle = n * slot

    paths = []
    for i, group in enumerate(order):
        if group not in merged:
            continue
        d = geom_to_svg_path(merged[group])
        path_id = f"continent_{group}"
        # Build keyTimes/values so this element is red only during its slot
        kt, vals = _slot_animation(i, n, total_cycle)
        paths.append(
            f'  <path id="{path_id}" d="{d}" fill="#cccccc" stroke="#999999" stroke-width="0.5">\n'
            f'    <animate attributeName="fill" values="{vals}" '
            f'keyTimes="{kt}" dur="{total_cycle}s" '
            f'repeatCount="indefinite" calcMode="linear"/>\n'
            f'  </path>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" '
        f'width="{SVG_WIDTH}" height="{SVG_HEIGHT}" style="background:#1a1a2e">\n'
        f'  <style>\n'
        f'    path {{ transition: fill 0.3s; }}\n'
        f'  </style>\n'
        + "\n".join(paths)
        + "\n</svg>"
    )
    return svg


def main():
    print("Loading country-continent mapping...")
    country_map = load_country_continents()
    print(f"  {len(country_map)} countries mapped to continents")

    print("Loading and merging geometries...")
    merged = load_and_merge_geometries(country_map)
    for g, geom in merged.items():
        print(f"  {g}: {geom.geom_type}, area={geom.area:.1f}")

    print("Building SVG...")
    svg = build_svg(merged)

    OUTPUT_SVG.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(svg)

    size_kb = os.path.getsize(OUTPUT_SVG) / 1024
    print(f"Written to {OUTPUT_SVG} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
