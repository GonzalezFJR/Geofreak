"""
Generate an animated SVG of Europe from GeoJSON files.
Five countries (España, Polonia, Reino Unido, Rumanía, Rusia)
pulse red one by one over a grey background.
"""

import csv
import json
import os
from pathlib import Path
from shapely.geometry import shape, MultiPolygon, Polygon, box
from shapely.ops import unary_union

BASE_DIR = Path(__file__).resolve().parent.parent
GEOJSON_DIR = BASE_DIR / "static" / "data" / "geojson"
COUNTRIES_CSV = BASE_DIR / "static" / "data" / "countries.csv"
OUTPUT_SVG = BASE_DIR / "static" / "img" / "europe_animated.svg"

# Countries to highlight (in order)
HIGHLIGHT_COUNTRIES = ["ESP", "POL", "GBR", "ROU", "RUS"]
HIGHLIGHT_LABELS = {
    "ESP": "España",
    "POL": "Polonia",
    "GBR": "Reino Unido",
    "ROU": "Rumanía",
    "RUS": "Rusia",
}

# Europe bounding box (lon_min, lat_min, lon_max, lat_max)
EUROPE_BBOX = (-25, 34, 60, 72)
SIMPLIFY_TOLERANCE = 0.15  # less aggressive for Europe
MIN_AREA = 0.05

SVG_WIDTH = 800
SVG_HEIGHT = 600


def get_european_countries():
    """Return set of ISO3 codes for European countries."""
    codes = set()
    with open(COUNTRIES_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["continent"] == "Europe":
                codes.add(row["iso_a3"])
    # Also add Turkey (transcontinental, often shown on Europe maps)
    codes.add("TUR")
    return codes


def load_country_geom(iso3):
    """Load and return simplified geometry for a country, clipped to Europe bbox."""
    path = GEOJSON_DIR / f"{iso3}.geojson"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    polys = []
    for feature in data.get("features", []):
        geom = shape(feature["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        polys.append(geom)
    if not polys:
        return None
    union = unary_union(polys)
    # Clip to Europe bounding box
    clip_box = box(*EUROPE_BBOX)
    clipped = union.intersection(clip_box)
    if clipped.is_empty:
        return None
    simplified = clipped.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
    simplified = _filter_small(simplified, MIN_AREA)
    if simplified.is_empty:
        return None
    return simplified


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


def _project(coord):
    """Equirectangular projection for Europe viewport."""
    lon, lat = coord[0], coord[1]
    lon_min, lat_min, lon_max, lat_max = EUROPE_BBOX
    x = (lon - lon_min) / (lon_max - lon_min) * SVG_WIDTH
    y = (1 - (lat - lat_min) / (lat_max - lat_min)) * SVG_HEIGHT
    return (x, y)


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


def _slot_animation(i, n, total_cycle):
    """Return (keyTimes, values) strings for slot i of n in a total_cycle.
    The element is grey except during its 2s slot where it pulses red."""
    slot = total_cycle / n
    t0 = i * slot / total_cycle
    t1 = (i * slot + 0.2) / total_cycle
    t2 = (i * slot + slot - 0.4) / total_cycle
    t3 = (i * slot + slot) / total_cycle
    kt = []
    vals = []
    if t0 > 0:
        kt += [0, t0]
        vals += ["GREY", "GREY"]
    else:
        kt += [0]
        vals += ["GREY"]
    kt += [t1, t2]
    vals += ["RED", "RED"]
    if t3 < 1:
        kt += [t3, 1]
        vals += ["GREY", "GREY"]
    else:
        kt += [1]
        vals += ["GREY"]
    kt_str = ";".join(f"{v:.4f}" for v in kt)
    return kt_str, vals


def build_svg(background_geoms, highlight_geoms):
    """Build the animated SVG for Europe."""
    n = len(HIGHLIGHT_COUNTRIES)
    slot = 2
    total_cycle = n * slot

    bg_paths = []
    for iso3, geom in background_geoms.items():
        if iso3 in HIGHLIGHT_COUNTRIES:
            continue  # drawn separately
        d = geom_to_svg_path(geom)
        bg_paths.append(f'  <path d="{d}" fill="#cccccc" stroke="#888888" stroke-width="0.3"/>')

    hl_paths = []
    for i, iso3 in enumerate(HIGHLIGHT_COUNTRIES):
        if iso3 not in highlight_geoms:
            continue
        d = geom_to_svg_path(highlight_geoms[iso3])
        kt_str, slot_vals = _slot_animation(i, n, total_cycle)
        fill_vals = ";".join(v.replace("GREY", "#cccccc").replace("RED", "#e63946") for v in slot_vals)
        stroke_vals = ";".join(v.replace("GREY", "#888888").replace("RED", "#c1121f") for v in slot_vals)
        hl_paths.append(
            f'  <path id="country_{iso3}" d="{d}" fill="#cccccc" stroke="#888888" stroke-width="0.3">\n'
            f'    <animate attributeName="fill" values="{fill_vals}" '
            f'keyTimes="{kt_str}" dur="{total_cycle}s" '
            f'repeatCount="indefinite" calcMode="linear"/>\n'
            f'    <animate attributeName="stroke" values="{stroke_vals}" '
            f'keyTimes="{kt_str}" dur="{total_cycle}s" '
            f'repeatCount="indefinite" calcMode="linear"/>\n'
            f'  </path>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" '
        f'width="{SVG_WIDTH}" height="{SVG_HEIGHT}" style="background:#1a1a2e">\n'
        + "\n".join(bg_paths) + "\n"
        + "\n".join(hl_paths) + "\n"
        + "</svg>"
    )
    return svg


def main():
    print("Loading European country codes...")
    eu_codes = get_european_countries()
    print(f"  {len(eu_codes)} European countries")

    print("Loading geometries...")
    all_geoms = {}
    for iso3 in eu_codes:
        geom = load_country_geom(iso3)
        if geom:
            all_geoms[iso3] = geom
            print(f"  {iso3}: {geom.geom_type}")

    # Also load highlight countries in case they're not in Europe set
    highlight_geoms = {}
    for iso3 in HIGHLIGHT_COUNTRIES:
        if iso3 in all_geoms:
            highlight_geoms[iso3] = all_geoms[iso3]
        else:
            geom = load_country_geom(iso3)
            if geom:
                highlight_geoms[iso3] = geom
                all_geoms[iso3] = geom

    print(f"\nHighlight countries loaded: {list(highlight_geoms.keys())}")

    print("Building SVG...")
    svg = build_svg(all_geoms, highlight_geoms)

    OUTPUT_SVG.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(svg)

    size_kb = os.path.getsize(OUTPUT_SVG) / 1024
    print(f"Written to {OUTPUT_SVG} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
