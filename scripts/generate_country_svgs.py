"""
Generate small individual SVG files for country outlines.
Each SVG contains a single <path> element with the country shape
normalised to a 100x100 viewBox (top-center anchored at 50,0).

Usage:
    python scripts/generate_country_svgs.py
"""

import json
from pathlib import Path
from shapely.geometry import shape, MultiPolygon, Polygon
from shapely.ops import unary_union

BASE_DIR = Path(__file__).resolve().parent.parent
GEOJSON_DIR = BASE_DIR / "static" / "data" / "geojson"
OUTPUT_DIR = BASE_DIR / "static" / "img" / "icons" / "countries_small"

# Countries to export
COUNTRY_LIST = [
    "ESP", "ITA", "FRA", "BRA", "ARG", "MEX", "USA", "CHN", "IND", "AUS",
    "GBR", "UKR", "IRN", "SYR", "EGY", "ZAF", "CHE", "URY", "COL",
    "CZE", "POL", "JPN", "KAZ", "MNG", "DZA", "ETH", "DEU", "VEN",
]

SIMPLIFY_TOLERANCE = 0.1
MIN_AREA = 0.05
VIEWBOX_SIZE = 100  # normalised SVG coordinate space


def load_country_geom(iso3):
    path = GEOJSON_DIR / f"{iso3}.geojson"
    if not path.exists():
        raise FileNotFoundError(f"GeoJSON not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    polys = []
    for feature in data.get("features", []):
        geom = shape(feature["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        polys.append(geom)
    if not polys:
        raise ValueError(f"No geometry for {iso3}")
    union = unary_union(polys)
    simplified = union.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
    simplified = _filter_small(simplified, MIN_AREA)
    simplified = _keep_mainland(simplified)
    if simplified.is_empty:
        raise ValueError(f"Empty geometry for {iso3}")
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


def _keep_mainland(geom):
    if not isinstance(geom, MultiPolygon):
        return geom
    polys = sorted(geom.geoms, key=lambda p: p.area, reverse=True)
    if len(polys) <= 1:
        return geom
    main = polys[0]
    cx, cy = main.centroid.x, main.centroid.y
    kept = [main]
    for p in polys[1:]:
        px, py = p.centroid.x, p.centroid.y
        if abs(px - cx) < 10 and abs(py - cy) < 10:
            kept.append(p)
    return MultiPolygon(kept) if len(kept) > 1 else kept[0]


def geom_to_normalised_path(geom):
    """Convert geometry to SVG path normalised in a VIEWBOX_SIZE square.
    The shape is fit inside (0,0)-(w,h) preserving aspect ratio,
    centered horizontally, with the top at y=0."""
    polys = []
    if isinstance(geom, Polygon):
        polys = [geom]
    elif isinstance(geom, MultiPolygon):
        polys = list(geom.geoms)

    minx, miny, maxx, maxy = geom.bounds
    geo_w = maxx - minx
    geo_h = maxy - miny
    if geo_w == 0 or geo_h == 0:
        return "", 0, 0

    scale = min(VIEWBOX_SIZE / geo_w, VIEWBOX_SIZE / geo_h)
    svg_w = geo_w * scale
    svg_h = geo_h * scale
    # Center horizontally within VIEWBOX_SIZE, top at y=0
    off_x = (VIEWBOX_SIZE - svg_w) / 2
    off_y = 0

    parts = []
    for poly in polys:
        for ring in [poly.exterior] + list(poly.interiors):
            coords = list(ring.coords)
            if len(coords) < 3:
                continue
            first = _transform(coords[0], minx, maxy, scale, off_x, off_y)
            d = f"M{first[0]:.2f},{first[1]:.2f}"
            for c in coords[1:]:
                p = _transform(c, minx, maxy, scale, off_x, off_y)
                d += f"L{p[0]:.2f},{p[1]:.2f}"
            d += "Z"
            parts.append(d)
    return " ".join(parts), svg_w, svg_h


def _transform(coord, minx, maxy, scale, off_x, off_y):
    lon, lat = coord[0], coord[1]
    x = (lon - minx) * scale + off_x
    y = (maxy - lat) * scale + off_y
    return (x, y)


def build_country_svg(path_d, svg_w, svg_h):
    """Wrap the path in a minimal SVG."""
    # viewBox is VIEWBOX_SIZE wide but only as tall as needed
    vb_h = svg_h
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX_SIZE} {vb_h:.1f}"'
        f' width="{VIEWBOX_SIZE}" height="{vb_h:.0f}" fill="none">\n'
        f'  <path d="{path_d}" fill="#c4a882" fill-opacity="0.9"'
        f' stroke="#8b7355" stroke-width="0.5"/>\n'
        f'</svg>'
    )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for iso3 in COUNTRY_LIST:
        print(f"Processing {iso3}...", end=" ")
        try:
            geom = load_country_geom(iso3)
            path_d, svg_w, svg_h = geom_to_normalised_path(geom)
            svg = build_country_svg(path_d, svg_w, svg_h)
            out = OUTPUT_DIR / f"{iso3}.svg"
            with open(out, "w", encoding="utf-8") as f:
                f.write(svg)
            print(f"OK ({len(path_d)} chars)")
        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\nDone. Files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
