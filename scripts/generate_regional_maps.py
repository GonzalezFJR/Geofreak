"""
Generate regional land-only maps (JPG + animated SVG overlay).

Supports longitude+latitude cropping for vertical (mobile) maps.

Regions:
  euroafrica  — lon -20..60, lat -40..72
  americas    — lon -130..-34, lat -60..72

Usage:
    python scripts/generate_regional_maps.py [--zoom 4]
"""

import csv
import json
import math
import os
import urllib.request
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
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

SIMPLIFY_TOLERANCE_MASK = 0.08
SIMPLIFY_TOLERANCE_SVG = 0.2
MIN_AREA_MASK = 0.01
MIN_AREA_SVG = 0.1

SEA_COLOR = (255, 255, 255)

CONTINENT_GROUPS = {
    "North America", "South America", "Europe", "Asia", "Africa", "Oceania",
}

REGIONS = {
    "euroafrica": {
        "lon_min": -20, "lon_max": 60,
        "lat_min": -40, "lat_max": 72,
        "highlight": ["TUR", "DEU", "COD", "IRN", "DZA",
                       "SAU", "ZAF", "LBY", "FRA", "SWE"],
    },
    "americas": {
        "lon_min": -130, "lon_max": -34,
        "lat_min": -60, "lat_max": 72,
        "highlight": ["USA", "BRA", "PER", "MEX", "ARG",
                       "COL", "CHL", "VEN", "CAN", "ECU"],
    },
}


# ── Web Mercator helpers ──────────────────────────────────────────

def lat_to_merc_y(lat_deg):
    lat_rad = math.radians(lat_deg)
    return (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2


def merc_project(lon, lat, img_w, img_h, lon_min, lon_max, merc_y_top, merc_y_bot):
    x = (lon - lon_min) / (lon_max - lon_min) * img_w
    lat_c = max(min(lat, 84.9), -84.9)
    merc_y = lat_to_merc_y(lat_c)
    y = (merc_y - merc_y_top) / (merc_y_bot - merc_y_top) * img_h
    return x, y


# ── Tile downloading & stitching ──────────────────────────────────

def download_tile(z, x, y):
    url = TILE_URL.format(z=z, x=x, y=y)
    req = urllib.request.Request(url, headers={"User-Agent": "GeoFreak/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return Image.open(BytesIO(resp.read())).convert("RGB")


def tile_y_to_lat(ty, zoom):
    n = 2 ** zoom
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ty / n)))
    return math.degrees(lat_rad)


def lon_to_tile_x(lon, zoom):
    n = 2 ** zoom
    return int((lon + 180) / 360 * n)


def tile_x_to_lon(tx, zoom):
    n = 2 ** zoom
    return tx / n * 360 - 180


def lat_to_tile_y(lat, zoom):
    n = 2 ** zoom
    lat_rad = math.radians(lat)
    return int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)


def stitch_region_tiles(zoom, lon_min, lon_max, lat_min, lat_max):
    n = 2 ** zoom
    x_start = max(0, lon_to_tile_x(lon_min, zoom))
    x_end = min(n, lon_to_tile_x(lon_max, zoom) + 1)
    y_start = max(0, lat_to_tile_y(lat_max, zoom))
    y_end = min(n, lat_to_tile_y(lat_min, zoom) + 1)

    num_x = x_end - x_start
    num_y = y_end - y_start
    total = num_x * num_y
    print(f"  Tiles: {num_x}x{num_y} = {total}")

    img = Image.new("RGB", (num_x * TILE_SIZE, num_y * TILE_SIZE))
    count = 0
    for ty in range(y_start, y_end):
        for tx in range(x_start, x_end):
            count += 1
            if count % 10 == 0 or count == total:
                print(f"    Downloading {count}/{total}...", end="\r")
            tile = download_tile(zoom, tx, ty)
            img.paste(tile, ((tx - x_start) * TILE_SIZE,
                             (ty - y_start) * TILE_SIZE))
    print()

    # Pixel-precise crop to exact lat/lon bounds
    tile_top_lat = tile_y_to_lat(y_start, zoom)
    tile_bot_lat = tile_y_to_lat(y_end, zoom)
    tile_left_lon = tile_x_to_lon(x_start, zoom)
    tile_right_lon = tile_x_to_lon(x_end, zoom)

    full_w = num_x * TILE_SIZE
    full_h = num_y * TILE_SIZE

    # Horizontal crop
    crop_left = int((lon_min - tile_left_lon) / (tile_right_lon - tile_left_lon) * full_w)
    crop_right = int((lon_max - tile_left_lon) / (tile_right_lon - tile_left_lon) * full_w)
    crop_left = max(0, crop_left)
    crop_right = min(full_w, crop_right)

    # Vertical crop (Mercator y)
    my_full_top = lat_to_merc_y(tile_top_lat)
    my_full_bot = lat_to_merc_y(tile_bot_lat)
    my_crop_top = lat_to_merc_y(lat_max)
    my_crop_bot = lat_to_merc_y(lat_min)
    crop_top = max(0, int((my_crop_top - my_full_top) / (my_full_bot - my_full_top) * full_h))
    crop_bot = min(full_h, int((my_crop_bot - my_full_top) / (my_full_bot - my_full_top) * full_h))

    img = img.crop((crop_left, crop_top, crop_right, crop_bot))
    return img


# ── Country geometry ──────────────────────────────────────────────

def load_all_country_codes():
    codes = set()
    with open(COUNTRIES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["continent"] in CONTINENT_GROUPS:
                codes.add(row["iso_a3"])
    return codes


def load_country_geom(iso3, simplify_tol, min_area):
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
    simplified = union.simplify(simplify_tol, preserve_topology=True)
    simplified = _filter_small(simplified, min_area)
    return simplified if not simplified.is_empty else None


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


def clip_geom_to_bbox(geom, lon_min, lon_max, lat_min, lat_max):
    """Clip geometry to a bounding box."""
    from shapely.geometry import box as shp_box
    bbox = shp_box(lon_min, lat_min, lon_max, lat_max)
    try:
        clipped = geom.intersection(bbox)
        if clipped.is_empty:
            return None
        return clipped
    except Exception:
        return None


# ── Raster mask ───────────────────────────────────────────────────

def geom_to_pixel_polygons(geom, img_w, img_h, lon_min, lon_max,
                           merc_y_top, merc_y_bot):
    polys = []
    if isinstance(geom, Polygon):
        polys = [geom]
    elif isinstance(geom, MultiPolygon):
        polys = list(geom.geoms)

    result = []
    for poly in polys:
        coords = list(poly.exterior.coords)
        if len(coords) < 3:
            continue
        px = []
        for lon, lat in coords:
            x, y = merc_project(lon, lat, img_w, img_h, lon_min, lon_max,
                                merc_y_top, merc_y_bot)
            px.append((x, y))
        result.append(px)
    return result


def build_land_mask(all_geoms, img_w, img_h, lon_min, lon_max,
                    merc_y_top, merc_y_bot):
    mask = Image.new("L", (img_w, img_h), 0)
    draw = ImageDraw.Draw(mask)
    for iso3, geom in all_geoms.items():
        px_polys = geom_to_pixel_polygons(geom, img_w, img_h, lon_min,
                                          lon_max, merc_y_top, merc_y_bot)
        for coords in px_polys:
            draw.polygon(coords, fill=255)
    return mask


def apply_sea_mask(img, mask):
    arr = np.array(img)
    mask_arr = np.array(mask)
    arr[mask_arr == 0] = SEA_COLOR
    return Image.fromarray(arr)


# ── SVG generation ────────────────────────────────────────────────

def geom_to_svg_path(geom, img_w, img_h, lon_min, lon_max,
                     merc_y_top, merc_y_bot):
    parts = []
    polys = ([geom] if isinstance(geom, Polygon)
             else list(geom.geoms) if isinstance(geom, MultiPolygon) else [])
    for poly in polys:
        for ring in [poly.exterior] + list(poly.interiors):
            coords = list(ring.coords)
            if len(coords) < 3:
                continue
            fx, fy = merc_project(coords[0][0], coords[0][1],
                                  img_w, img_h, lon_min, lon_max,
                                  merc_y_top, merc_y_bot)
            d = f"M{fx:.1f},{fy:.1f}"
            for lon, lat in coords[1:]:
                px, py = merc_project(lon, lat, img_w, img_h,
                                      lon_min, lon_max, merc_y_top, merc_y_bot)
                d += f"L{px:.1f},{py:.1f}"
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
        kt += [0, t0]; vals += ["OFF", "OFF"]
    else:
        kt += [0]; vals += ["OFF"]
    kt += [t1, t2]; vals += ["ON", "ON"]
    if t3 < 1:
        kt += [t3, 1]; vals += ["OFF", "OFF"]
    else:
        kt += [1]; vals += ["OFF"]
    return ";".join(f"{v:.4f}" for v in kt), vals


def build_overlay_svg(all_geoms, highlight_list, highlight_geoms,
                      img_w, img_h, lon_min, lon_max,
                      merc_y_top, merc_y_bot):
    n = len(highlight_list)
    total_cycle = n * 2
    hl_set = set(highlight_list)

    border_paths = []
    for iso3, geom in all_geoms.items():
        if iso3 in hl_set:
            continue
        d = geom_to_svg_path(geom, img_w, img_h, lon_min, lon_max,
                             merc_y_top, merc_y_bot)
        border_paths.append(
            f'  <path d="{d}" fill="none" stroke="rgba(0,0,0,0.2)" '
            f'stroke-width="0.5"/>'
        )

    hl_paths = []
    for i, iso3 in enumerate(highlight_list):
        if iso3 not in highlight_geoms:
            continue
        d = geom_to_svg_path(highlight_geoms[iso3], img_w, img_h,
                             lon_min, lon_max, merc_y_top, merc_y_bot)
        kt_str, slot_vals = _slot_animation(i, n, total_cycle)
        fill_vals = ";".join(
            v.replace("OFF", "rgba(0,0,0,0)")
             .replace("ON", "rgba(26,115,232,0.45)")
            for v in slot_vals
        )
        stroke_vals = ";".join(
            v.replace("OFF", "rgba(0,0,0,0.2)")
             .replace("ON", "rgba(13,71,161,0.8)")
            for v in slot_vals
        )
        sw_vals = ";".join(
            v.replace("OFF", "0.5").replace("ON", "1.5") for v in slot_vals
        )
        hl_paths.append(
            f'  <path id="hl_{iso3}" d="{d}" fill="none"'
            f' stroke="rgba(0,0,0,0.2)" stroke-width="0.5">\n'
            f'    <animate attributeName="fill" values="{fill_vals}" '
            f'keyTimes="{kt_str}" dur="{total_cycle}s" '
            f'repeatCount="indefinite"/>\n'
            f'    <animate attributeName="stroke" values="{stroke_vals}" '
            f'keyTimes="{kt_str}" dur="{total_cycle}s" '
            f'repeatCount="indefinite"/>\n'
            f'    <animate attributeName="stroke-width" values="{sw_vals}" '
            f'keyTimes="{kt_str}" dur="{total_cycle}s" '
            f'repeatCount="indefinite"/>\n'
            f'  </path>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="0 0 {img_w} {img_h}"'
        f' preserveAspectRatio="xMidYMid slice">\n'
        + "\n".join(border_paths) + "\n"
        + "\n".join(hl_paths) + "\n"
        + "</svg>"
    )


# ── Main ──────────────────────────────────────────────────────────

def generate_region(name, cfg, zoom):
    lon_min = cfg["lon_min"]
    lon_max = cfg["lon_max"]
    lat_min = cfg["lat_min"]
    lat_max = cfg["lat_max"]
    highlight_list = cfg["highlight"]

    print(f"\n{'='*60}")
    print(f"Region: {name}  lon [{lon_min},{lon_max}]  lat [{lat_min},{lat_max}]")
    print(f"{'='*60}")

    # 1) Download & stitch tiles
    print("Downloading tiles...")
    img = stitch_region_tiles(zoom, lon_min, lon_max, lat_min, lat_max)
    img_w, img_h = img.size
    merc_y_top = lat_to_merc_y(lat_max)
    merc_y_bot = lat_to_merc_y(lat_min)
    print(f"  Image: {img_w} x {img_h}")

    # 2) Load geometries
    print("Loading countries...")
    all_codes = load_all_country_codes()
    mask_geoms = {}
    svg_geoms = {}
    for iso3 in all_codes:
        gm = load_country_geom(iso3, SIMPLIFY_TOLERANCE_MASK, MIN_AREA_MASK)
        if gm:
            clipped = clip_geom_to_bbox(gm, lon_min, lon_max, lat_min, lat_max)
            if clipped and not clipped.is_empty:
                mask_geoms[iso3] = clipped
        gs = load_country_geom(iso3, SIMPLIFY_TOLERANCE_SVG, MIN_AREA_SVG)
        if gs:
            clipped = clip_geom_to_bbox(gs, lon_min, lon_max, lat_min, lat_max)
            if clipped and not clipped.is_empty:
                svg_geoms[iso3] = clipped
    print(f"  {len(mask_geoms)} mask, {len(svg_geoms)} SVG countries")

    # 3) Build land mask
    print("Building land mask...")
    mask = build_land_mask(mask_geoms, img_w, img_h, lon_min, lon_max,
                           merc_y_top, merc_y_bot)
    land_img = apply_sea_mask(img, mask)

    jpg_path = OUTPUT_DIR / f"{name}_land.jpg"
    land_img.save(jpg_path, "JPEG", quality=92)
    print(f"  Saved {jpg_path} ({os.path.getsize(jpg_path) // 1024} KB)")

    # 4) Build SVG overlay
    print("Building SVG overlay...")
    highlight_geoms = {iso3: svg_geoms[iso3]
                       for iso3 in highlight_list if iso3 in svg_geoms}
    missing = [c for c in highlight_list if c not in highlight_geoms]
    if missing:
        print(f"  WARNING: missing highlight countries: {missing}")

    svg = build_overlay_svg(svg_geoms, highlight_list, highlight_geoms,
                            img_w, img_h, lon_min, lon_max,
                            merc_y_top, merc_y_bot)
    svg_path = OUTPUT_DIR / f"{name}_land_overlay.svg"
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"  Saved {svg_path} ({os.path.getsize(svg_path) // 1024} KB)")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--zoom", type=int, default=4)
    parser.add_argument("--region", choices=list(REGIONS.keys()),
                        help="Generate only this region")
    args = parser.parse_args()
    zoom = max(3, min(5, args.zoom))

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    regions = {args.region: REGIONS[args.region]} if args.region else REGIONS
    for name, cfg in regions.items():
        generate_region(name, cfg, zoom)

    print("\nDone!")


if __name__ == "__main__":
    main()
