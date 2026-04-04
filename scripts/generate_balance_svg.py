"""
Generate an animated SVG of the balance icon with two countries
hanging from its pans. Each country is extracted from its GeoJSON,
simplified, scaled, and attached at its top-center to the pan string
so it follows the tilt animation.

Usage:
    python scripts/generate_balance_svg.py FRA ITA
    python scripts/generate_balance_svg.py USA BRA
"""

import json
import sys
from pathlib import Path
from shapely.geometry import shape, MultiPolygon, Polygon
from shapely.ops import unary_union

BASE_DIR = Path(__file__).resolve().parent.parent
GEOJSON_DIR = BASE_DIR / "static" / "data" / "geojson"
OUTPUT_DIR = BASE_DIR / "static" / "img"

# Balance geometry constants (from comparison.svg — 200x160 version)
PIVOT = (200, 60)
LEFT_PAN_X = 50
RIGHT_PAN_X = 350
PAN_Y = 120       # bottom of the strings / top of pans
PAN_BOTTOM = 126  # bottom arc of the pan curve

COUNTRY_MAX_W = 140   # max width for a country shape (SVG units)
COUNTRY_MAX_H = 150   # max height

SVG_VIEWBOX_W = 400
SVG_STAND_BOTTOM = 280  # base rect bottom

SIMPLIFY_TOLERANCE = 0.1  # degrees – light simplification
MIN_AREA = 0.05


def load_country_geom(iso3):
    """Load and simplify a country's geometry."""
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
        raise ValueError(f"No geometry found for {iso3}")
    union = unary_union(polys)
    simplified = union.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
    simplified = _filter_small(simplified, MIN_AREA)
    simplified = _keep_mainland(simplified)
    if simplified.is_empty:
        raise ValueError(f"Geometry empty after simplification for {iso3}")
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
    """For MultiPolygons with far-flung overseas territories, keep only
    polygons near the largest one (within 30° of its centroid)."""
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


def geom_to_svg_path(geom, anchor_x, anchor_y):
    """Convert geometry to SVG path, scaled and positioned so that
    the top-center of the bounding box is at (anchor_x, anchor_y)."""
    polys = []
    if isinstance(geom, Polygon):
        polys = [geom]
    elif isinstance(geom, MultiPolygon):
        polys = list(geom.geoms)

    # Get bounding box in geo coordinates
    minx, miny, maxx, maxy = geom.bounds
    geo_w = maxx - minx
    geo_h = maxy - miny
    if geo_w == 0 or geo_h == 0:
        return ""

    # Scale to fit within max dimensions
    scale = min(COUNTRY_MAX_W / geo_w, COUNTRY_MAX_H / geo_h)

    # In geo coords: top = maxy (north), so top-center is ((minx+maxx)/2, maxy)
    # In SVG coords after scaling: width = geo_w*scale, height = geo_h*scale
    svg_w = geo_w * scale
    svg_h = geo_h * scale

    # Offset so that top-center of country maps to (anchor_x, anchor_y)
    # For a point (lon, lat):
    #   svg_x = (lon - minx) * scale  -> ranges [0, svg_w]
    #   svg_y = (maxy - lat) * scale  -> ranges [0, svg_h] (flipped: north=0)
    # Top-center in local SVG = (svg_w/2, 0)
    # We want (svg_w/2, 0) -> (anchor_x, anchor_y)
    off_x = anchor_x - svg_w / 2
    off_y = anchor_y

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
    return " ".join(parts)


def _transform(coord, minx, maxy, scale, off_x, off_y):
    """Transform geo coord to SVG coord."""
    lon, lat = coord[0], coord[1]
    x = (lon - minx) * scale + off_x
    y = (maxy - lat) * scale + off_y
    return (x, y)


def build_svg(iso_left, iso_right, geom_left, geom_right):
    """Build the composite SVG with balance + hanging countries."""
    # Countries hang from just below the pan curve
    hang_y = PAN_BOTTOM + 0.5

    path_left = geom_to_svg_path(geom_left, LEFT_PAN_X, hang_y)
    path_right = geom_to_svg_path(geom_right, RIGHT_PAN_X, hang_y)

    # Compute new viewBox to accommodate countries hanging below
    # Get actual extents by checking bounding boxes
    left_bounds = geom_left.bounds
    right_bounds = geom_right.bounds

    def country_svg_bottom(geom, anchor_x, anchor_y):
        minx, miny, maxx, maxy = geom.bounds
        geo_w = maxx - minx
        geo_h = maxy - miny
        scale = min(COUNTRY_MAX_W / geo_w, COUNTRY_MAX_H / geo_h)
        return anchor_y + geo_h * scale

    max_bottom = max(
        country_svg_bottom(geom_left, LEFT_PAN_X, hang_y),
        country_svg_bottom(geom_right, RIGHT_PAN_X, hang_y),
    )
    # Add some padding
    vb_height = max(280, max_bottom + 15)
    # Horizontal margin so tilted content doesn't clip
    margin_x = 80
    vb_x = -margin_x
    vb_w = SVG_VIEWBOX_W + 2 * margin_x

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb_x} 0 {vb_w} {vb_height:.1f}" width="{vb_w}" height="{vb_height:.0f}" fill="none">
  <style>
    .balance {{
      transform-origin: {PIVOT[0]}px {PIVOT[1]}px;
      animation: tilt 3s ease-in-out infinite;
    }}
    @keyframes tilt {{
      0%, 100% {{ transform: rotate(0deg); }}
      25%  {{ transform: rotate(-12deg); }}
      75%  {{ transform: rotate(12deg); }}
    }}
  </style>

  <!-- Stand pole -->
  <line x1="{PIVOT[0]}" y1="{PIVOT[1]}" x2="{PIVOT[0]}" y2="265" stroke="#2b2b2b" stroke-width="5" stroke-linecap="round"/>
  <!-- Stand base -->
  <rect x="155" y="261" width="90" height="12" rx="6" fill="#2b2b2b" opacity="0.55"/>

  <!-- Rotating balance (beam + strings + pans + countries) -->
  <g class="balance">
    <!-- Beam -->
    <line x1="{LEFT_PAN_X}" y1="{PIVOT[1]}" x2="{RIGHT_PAN_X}" y2="{PIVOT[1]}" stroke="#2b2b2b" stroke-width="5" stroke-linecap="round"/>
    <!-- Pivot cap -->
    <circle cx="{PIVOT[0]}" cy="{PIVOT[1]}" r="9" fill="#2b2b2b"/>

    <!-- Left string -->
    <line x1="{LEFT_PAN_X}" y1="{PIVOT[1]}" x2="{LEFT_PAN_X}" y2="{PAN_Y}" stroke="#2b2b2b" stroke-width="2.5"/>
    <!-- Left pan -->
    <path d="M{LEFT_PAN_X - 30},{PAN_BOTTOM} Q{LEFT_PAN_X},{PAN_BOTTOM - 8} {LEFT_PAN_X + 30},{PAN_BOTTOM}" stroke="#2b2b2b" stroke-width="3.5"
          fill="#2b2b2b" fill-opacity="0.2" stroke-linecap="round"/>
    <!-- Left country: {iso_left} -->
    <path d="{path_left}" fill="#c4a882" fill-opacity="0.9" stroke="#8b7355" stroke-width="0.6"/>

    <!-- Right string -->
    <line x1="{RIGHT_PAN_X}" y1="{PIVOT[1]}" x2="{RIGHT_PAN_X}" y2="{PAN_Y}" stroke="#2b2b2b" stroke-width="2.5"/>
    <!-- Right pan -->
    <path d="M{RIGHT_PAN_X - 30},{PAN_BOTTOM} Q{RIGHT_PAN_X},{PAN_BOTTOM - 8} {RIGHT_PAN_X + 30},{PAN_BOTTOM}" stroke="#2b2b2b" stroke-width="3.5"
          fill="#2b2b2b" fill-opacity="0.2" stroke-linecap="round"/>
    <!-- Right country: {iso_right} -->
    <path d="{path_right}" fill="#c4a882" fill-opacity="0.9" stroke="#8b7355" stroke-width="0.5"/>
  </g>
</svg>"""
    return svg


def main():
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} ISO3_LEFT ISO3_RIGHT")
        print(f"Example: python {sys.argv[0]} FRA ITA")
        sys.exit(1)

    iso_left = sys.argv[1].upper()
    iso_right = sys.argv[2].upper()

    print(f"Loading {iso_left}...")
    geom_left = load_country_geom(iso_left)
    print(f"  {geom_left.geom_type}, bounds={geom_left.bounds}")

    print(f"Loading {iso_right}...")
    geom_right = load_country_geom(iso_right)
    print(f"  {geom_right.geom_type}, bounds={geom_right.bounds}")

    print("Building SVG...")
    svg = build_svg(iso_left, iso_right, geom_left, geom_right)

    output = OUTPUT_DIR / f"balance_{iso_left}_{iso_right}.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(svg)

    import os
    size_kb = os.path.getsize(output) / 1024
    print(f"Written to {output} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
