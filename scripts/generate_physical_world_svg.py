"""
Generate a high-quality world map with physical terrain background (JPG)
and an animated SVG overlay with country outlines and highlight animation.

Both files use Web Mercator projection so they align perfectly when
layered in HTML via CSS.

The JPG is stitched from Esri World Physical Map tiles.
The SVG contains country borders + animation with transparent background.

Usage:
    python scripts/generate_physical_world_svg.py [--zoom 4]
"""

import argparse
import csv
import json
import math
import os
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image
from shapely.geometry import shape, MultiPolygon, Polygon
from shapely.ops import unary_union

BASE_DIR = Path(__file__).resolve().parent.parent
GEOJSON_DIR = BASE_DIR / "static" / "data" / "geojson"
COUNTRIES_CSV = BASE_DIR / "static" / "data" / "countries.csv"
OUTPUT_DIR = BASE_DIR / "static" / "img"

TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Physical_Map/MapServer/tile/{z}/{y}/{x}"
)
TILE_SIZE = 256

# Countries to highlight
HIGHLIGHT_COUNTRIES = [
    "USA", "CHN", "DEU", "SAU", "CAN", "MEX", "RUS", "ARG", "AUS", "IRN",
]

SIMPLIFY_TOLERANCE = 0.3
MIN_AREA = 0.3

# Latitude crop (Web Mercator max is ~±85.05°, we crop bottom)
LAT_MAX = 85.05
LAT_MIN = -60.0


# ── Web Mercator helpers ──────────────────────────────────────────

def lat_to_merc_y(lat_deg):
    """Convert latitude to Mercator normalised y [0,1] (0=top, 1=bottom)."""
    lat_rad = math.radians(lat_deg)
    return (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2


def merc_project(lon, lat, img_w, img_h, lon_min, lon_max, merc_y_top, merc_y_bot):
    """Project lon/lat to pixel coords in the cropped image."""
    x = (lon - lon_min) / (lon_max - lon_min) * img_w
    merc_y = lat_to_merc_y(lat)
    y = (merc_y - merc_y_top) / (merc_y_bot - merc_y_top) * img_h
    return x, y


# ── Tile downloading & stitching ──────────────────────────────────

def download_tile(z, x, y):
    """Download a single tile, return PIL Image."""
    url = TILE_URL.format(z=z, x=x, y=y)
    req = urllib.request.Request(url, headers={"User-Agent": "GeoFreak/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return Image.open(BytesIO(resp.read())).convert("RGB")


def tile_y_to_lat(ty, zoom):
    """Convert tile y index to latitude (top edge of tile)."""
    n = 2 ** zoom
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ty / n)))
    return math.degrees(lat_rad)


def lat_to_tile_y(lat, zoom):
    """Convert latitude to tile y index."""
    n = 2 ** zoom
    lat_rad = math.radians(lat)
    return int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)


def stitch_tiles(zoom):
    """Download and stitch tiles into a cropped world image."""
    n = 2 ** zoom  # number of tiles per axis

    # Full world tiles in x
    x_start, x_end = 0, n

    # Tile y range for our lat crop
    y_start = lat_to_tile_y(LAT_MAX, zoom)
    y_end = lat_to_tile_y(LAT_MIN, zoom) + 1  # +1 to include the tile

    y_start = max(0, y_start)
    y_end = min(n, y_end)

    num_x = x_end - x_start
    num_y = y_end - y_start
    total_tiles = num_x * num_y
    print(f"  Zoom {zoom}: {num_x}x{num_y} = {total_tiles} tiles")

    img = Image.new("RGB", (num_x * TILE_SIZE, num_y * TILE_SIZE))

    count = 0
    for ty in range(y_start, y_end):
        for tx in range(x_start, x_end):
            count += 1
            if count % 20 == 0 or count == total_tiles:
                print(f"    Downloading tile {count}/{total_tiles}...", end="\r")
            tile = download_tile(zoom, tx, ty)
            px = (tx - x_start) * TILE_SIZE
            py = (ty - y_start) * TILE_SIZE
            img.paste(tile, (px, py))

    print()

    # Now crop precisely to LAT_MIN..LAT_MAX within the stitched image
    # Tile y_start corresponds to the top edge of tile row y_start
    top_lat = tile_y_to_lat(y_start, zoom)
    bot_lat = tile_y_to_lat(y_end, zoom)

    merc_y_full_top = lat_to_merc_y(top_lat)
    merc_y_full_bot = lat_to_merc_y(bot_lat)

    merc_y_crop_top = lat_to_merc_y(LAT_MAX)
    merc_y_crop_bot = lat_to_merc_y(LAT_MIN)

    full_h = num_y * TILE_SIZE
    crop_top_px = int((merc_y_crop_top - merc_y_full_top) /
                      (merc_y_full_bot - merc_y_full_top) * full_h)
    crop_bot_px = int((merc_y_crop_bot - merc_y_full_top) /
                      (merc_y_full_bot - merc_y_full_top) * full_h)

    crop_top_px = max(0, crop_top_px)
    crop_bot_px = min(full_h, crop_bot_px)

    img = img.crop((0, crop_top_px, num_x * TILE_SIZE, crop_bot_px))

    return img


# ── Country geometry ──────────────────────────────────────────────

CONTINENT_GROUPS = {
    "North America", "South America", "Europe", "Asia", "Africa", "Oceania",
}


def load_all_country_codes():
    codes = set()
    with open(COUNTRIES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["continent"] in CONTINENT_GROUPS:
                codes.add(row["iso_a3"])
    return codes


def load_country_geom(iso3):
    path = GEOJSON_DIR / f"{iso3}.geojson"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    polys = []
    for feat in data.get("features", []):
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        polys.append(geom)
    if not polys:
        return None
    union = unary_union(polys)
    simplified = union.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
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


# ── SVG generation ────────────────────────────────────────────────

def geom_to_svg_path(geom, img_w, img_h, merc_y_top, merc_y_bot):
    """Convert geometry to SVG path in Web Mercator pixel coords."""
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
            first = merc_project(coords[0][0], coords[0][1],
                                 img_w, img_h, -180, 180,
                                 merc_y_top, merc_y_bot)
            d = f"M{first[0]:.1f},{first[1]:.1f}"
            for c in coords[1:]:
                # Clamp latitude to avoid math errors near poles
                lat = max(min(c[1], 85.0), -85.0)
                p = merc_project(c[0], lat, img_w, img_h,
                                 -180, 180, merc_y_top, merc_y_bot)
                d += f"L{p[0]:.1f},{p[1]:.1f}"
            d += "Z"
            parts.append(d)
    return " ".join(parts)


def _slot_animation(i, n, total_cycle):
    slot = total_cycle / n
    t0 = i * slot / total_cycle
    t1 = (i * slot + 0.2) / total_cycle
    t2 = (i * slot + slot - 0.4) / total_cycle
    t3 = (i * slot + slot) / total_cycle
    kt, vals = [], []
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


def build_overlay_svg(all_geoms, highlight_geoms, img_w, img_h,
                      merc_y_top, merc_y_bot):
    """Build the transparent SVG overlay with borders and animation."""
    n = len(HIGHLIGHT_COUNTRIES)
    total_cycle = n * 2

    # Border-only paths for all countries
    border_paths = []
    for iso3, geom in all_geoms.items():
        if iso3 in HIGHLIGHT_COUNTRIES:
            continue
        d = geom_to_svg_path(geom, img_w, img_h, merc_y_top, merc_y_bot)
        border_paths.append(
            f'  <path d="{d}" fill="none" stroke="rgba(0,0,0,0.15)" stroke-width="0.5"/>'
        )

    # Highlighted countries
    hl_paths = []
    for i, iso3 in enumerate(HIGHLIGHT_COUNTRIES):
        if iso3 not in highlight_geoms:
            continue
        d = geom_to_svg_path(highlight_geoms[iso3], img_w, img_h,
                             merc_y_top, merc_y_bot)
        kt_str, slot_vals = _slot_animation(i, n, total_cycle)
        fill_vals = ";".join(
            v.replace("GREY", "rgba(0,0,0,0)").replace("RED", "rgba(230,57,70,0.45)")
            for v in slot_vals
        )
        stroke_vals = ";".join(
            v.replace("GREY", "rgba(0,0,0,0.15)").replace("RED", "rgba(193,18,31,0.7)")
            for v in slot_vals
        )
        hl_paths.append(
            f'  <path id="hl_{iso3}" d="{d}" fill="none"'
            f' stroke="rgba(0,0,0,0.15)" stroke-width="0.5">\n'
            f'    <animate attributeName="fill" values="{fill_vals}" '
            f'keyTimes="{kt_str}" dur="{total_cycle}s" '
            f'repeatCount="indefinite" calcMode="linear"/>\n'
            f'    <animate attributeName="stroke" values="{stroke_vals}" '
            f'keyTimes="{kt_str}" dur="{total_cycle}s" '
            f'repeatCount="indefinite" calcMode="linear"/>\n'
            f'    <animate attributeName="stroke-width" '
            f'values="{";".join(v.replace("GREY","0.5").replace("RED","1.5") for v in slot_vals)}" '
            f'keyTimes="{kt_str}" dur="{total_cycle}s" '
            f'repeatCount="indefinite" calcMode="linear"/>\n'
            f'  </path>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="0 0 {img_w} {img_h}"'
        f' width="{img_w}" height="{img_h}"'
        f' style="position:absolute;top:0;left:0">\n'
        + "\n".join(border_paths) + "\n"
        + "\n".join(hl_paths) + "\n"
        + "</svg>"
    )
    return svg


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zoom", type=int, default=4,
                        help="Tile zoom level (3-5, default 4)")
    args = parser.parse_args()
    zoom = max(3, min(5, args.zoom))

    print(f"Downloading Esri Physical tiles at zoom {zoom}...")
    img = stitch_tiles(zoom)
    img_w, img_h = img.size
    print(f"  Image size: {img_w} x {img_h}")

    # Mercator y bounds for the cropped image
    merc_y_top = lat_to_merc_y(LAT_MAX)
    merc_y_bot = lat_to_merc_y(LAT_MIN)

    # Save JPG
    jpg_path = OUTPUT_DIR / "world_physical.jpg"
    img.save(jpg_path, "JPEG", quality=90)
    jpg_kb = os.path.getsize(jpg_path) / 1024
    print(f"  Saved {jpg_path} ({jpg_kb:.0f} KB)")

    print("Loading country geometries...")
    all_codes = load_all_country_codes()
    all_geoms = {}
    for iso3 in all_codes:
        geom = load_country_geom(iso3)
        if geom:
            all_geoms[iso3] = geom
    print(f"  {len(all_geoms)} countries loaded")

    highlight_geoms = {iso3: all_geoms[iso3]
                       for iso3 in HIGHLIGHT_COUNTRIES
                       if iso3 in all_geoms}
    print(f"  Highlight: {list(highlight_geoms.keys())}")

    print("Building SVG overlay...")
    svg = build_overlay_svg(all_geoms, highlight_geoms,
                            img_w, img_h, merc_y_top, merc_y_bot)

    svg_path = OUTPUT_DIR / "world_physical_overlay.svg"
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    svg_kb = os.path.getsize(svg_path) / 1024
    print(f"  Saved {svg_path} ({svg_kb:.0f} KB)")

    # Also generate a demo HTML that layers them
    html_path = OUTPUT_DIR / "world_physical_demo.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Physical World Map</title>
<style>
body {{ margin: 0; background: #1a1a2e; display: flex;
       justify-content: center; align-items: center; min-height: 100vh; }}
.map-wrap {{ position: relative; max-width: 100%; }}
.map-wrap img {{ width: 100%; display: block; border-radius: 8px; }}
.map-wrap svg {{ position: absolute; top: 0; left: 0;
                 width: 100%; height: 100%; }}
</style></head>
<body>
<div class="map-wrap">
  <img src="world_physical.jpg" alt="Physical world map"/>
  <object data="world_physical_overlay.svg" type="image/svg+xml"
          style="position:absolute;top:0;left:0;width:100%;height:100%"></object>
</div>
<p style="color:#666;text-align:center;font-size:0.8em;margin-top:8px">
  Tiles © Esri — World Physical Map
</p>
</body></html>""")
    print(f"  Demo: {html_path}")
    print("Done!")


if __name__ == "__main__":
    main()
