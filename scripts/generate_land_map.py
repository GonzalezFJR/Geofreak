"""
Generate a land-only world map by masking out the sea using country GeoJSON
polygons, plus an animated SVG overlay and GIF animation.

Outputs (in static/img/):
  - world_land.jpg         : Physical terrain, sea replaced with white
  - world_land_overlay.svg : Transparent SVG with borders + pulsing animation
  - world_land_animated.gif: Animated GIF compositing both layers

All files use Web Mercator projection, cropped to ±75°N/60°S.

Usage:
    python scripts/generate_land_map.py [--zoom 4] [--gif-fps 8]
"""

import argparse
import csv
import json
import math
import os
import urllib.request
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import shape, MultiPolygon, Polygon, box
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

HIGHLIGHT_COUNTRIES = [
    "USA", "CHN", "DEU", "SAU", "CAN", "MEX", "RUS", "ARG", "AUS", "IRN",
]

# Lower tolerance for better mask accuracy
SIMPLIFY_TOLERANCE_MASK = 0.08
SIMPLIFY_TOLERANCE_SVG = 0.3
MIN_AREA_MASK = 0.01
MIN_AREA_SVG = 0.3

LAT_MAX = 75.0
LAT_MIN = -60.0

SEA_COLOR = (255, 255, 255)
HIGHLIGHT_COLOR = (230, 57, 70)
HIGHLIGHT_ALPHA = 115  # ~45% of 255

CONTINENT_GROUPS = {
    "North America", "South America", "Europe", "Asia", "Africa", "Oceania",
}


# ── Web Mercator helpers ──────────────────────────────────────────

def lat_to_merc_y(lat_deg):
    lat_rad = math.radians(lat_deg)
    return (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2


def merc_project(lon, lat, img_w, img_h, merc_y_top, merc_y_bot):
    x = (lon + 180) / 360 * img_w
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


def lat_to_tile_y(lat, zoom):
    n = 2 ** zoom
    lat_rad = math.radians(lat)
    return int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)


def stitch_tiles(zoom):
    n = 2 ** zoom
    x_start, x_end = 0, n
    y_start = max(0, lat_to_tile_y(LAT_MAX, zoom))
    y_end = min(n, lat_to_tile_y(LAT_MIN, zoom) + 1)
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
            img.paste(tile, ((tx - x_start) * TILE_SIZE,
                             (ty - y_start) * TILE_SIZE))
    print()

    # Precise pixel crop to LAT_MAX..LAT_MIN
    top_lat = tile_y_to_lat(y_start, zoom)
    bot_lat = tile_y_to_lat(y_end, zoom)
    my_full_top = lat_to_merc_y(top_lat)
    my_full_bot = lat_to_merc_y(bot_lat)
    my_crop_top = lat_to_merc_y(LAT_MAX)
    my_crop_bot = lat_to_merc_y(LAT_MIN)
    full_h = num_y * TILE_SIZE
    ct = max(0, int((my_crop_top - my_full_top) / (my_full_bot - my_full_top) * full_h))
    cb = min(full_h, int((my_crop_bot - my_full_top) / (my_full_bot - my_full_top) * full_h))
    img = img.crop((0, ct, num_x * TILE_SIZE, cb))
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


# ── Raster mask from geometries ───────────────────────────────────

def geom_to_pixel_polygons(geom, img_w, img_h, merc_y_top, merc_y_bot):
    """Convert shapely geom to list of PIL-style polygon coordinate lists."""
    polys = []
    if isinstance(geom, Polygon):
        polys = [geom]
    elif isinstance(geom, MultiPolygon):
        polys = list(geom.geoms)

    result = []
    for poly in polys:
        ring = poly.exterior
        coords = list(ring.coords)
        if len(coords) < 3:
            continue
        px_coords = []
        for lon, lat in coords:
            x, y = merc_project(lon, lat, img_w, img_h, merc_y_top, merc_y_bot)
            px_coords.append((x, y))
        result.append(px_coords)
    return result


def build_land_mask(all_geoms, img_w, img_h, merc_y_top, merc_y_bot):
    """Create a binary mask image: white=land, black=sea."""
    mask = Image.new("L", (img_w, img_h), 0)
    draw = ImageDraw.Draw(mask)
    for iso3, geom in all_geoms.items():
        px_polys = geom_to_pixel_polygons(geom, img_w, img_h,
                                          merc_y_top, merc_y_bot)
        for coords in px_polys:
            draw.polygon(coords, fill=255)
    return mask


def apply_sea_mask(img, mask):
    """Replace sea pixels (mask=0) with SEA_COLOR."""
    arr = np.array(img)
    mask_arr = np.array(mask)
    sea = mask_arr == 0
    arr[sea] = SEA_COLOR
    return Image.fromarray(arr)


# ── SVG generation ────────────────────────────────────────────────

def geom_to_svg_path(geom, img_w, img_h, merc_y_top, merc_y_bot):
    parts = []
    polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms) if isinstance(geom, MultiPolygon) else []
    for poly in polys:
        for ring in [poly.exterior] + list(poly.interiors):
            coords = list(ring.coords)
            if len(coords) < 3:
                continue
            fx, fy = merc_project(coords[0][0], coords[0][1],
                                  img_w, img_h, merc_y_top, merc_y_bot)
            d = f"M{fx:.1f},{fy:.1f}"
            for lon, lat in coords[1:]:
                px, py = merc_project(lon, lat, img_w, img_h,
                                      merc_y_top, merc_y_bot)
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


def build_overlay_svg(all_geoms, highlight_geoms, img_w, img_h,
                      merc_y_top, merc_y_bot):
    n = len(HIGHLIGHT_COUNTRIES)
    total_cycle = n * 2

    border_paths = []
    for iso3, geom in all_geoms.items():
        if iso3 in HIGHLIGHT_COUNTRIES:
            continue
        d = geom_to_svg_path(geom, img_w, img_h, merc_y_top, merc_y_bot)
        border_paths.append(
            f'  <path d="{d}" fill="none" stroke="rgba(0,0,0,0.2)" stroke-width="0.5"/>'
        )

    hl_paths = []
    for i, iso3 in enumerate(HIGHLIGHT_COUNTRIES):
        if iso3 not in highlight_geoms:
            continue
        d = geom_to_svg_path(highlight_geoms[iso3], img_w, img_h,
                             merc_y_top, merc_y_bot)
        kt_str, slot_vals = _slot_animation(i, n, total_cycle)
        fill_vals = ";".join(
            v.replace("OFF", "rgba(0,0,0,0)").replace("ON", "rgba(230,57,70,0.45)")
            for v in slot_vals
        )
        stroke_vals = ";".join(
            v.replace("OFF", "rgba(0,0,0,0.2)").replace("ON", "rgba(193,18,31,0.8)")
            for v in slot_vals
        )
        sw_vals = ";".join(
            v.replace("OFF", "0.5").replace("ON", "1.5") for v in slot_vals
        )
        hl_paths.append(
            f'  <path id="hl_{iso3}" d="{d}" fill="none"'
            f' stroke="rgba(0,0,0,0.2)" stroke-width="0.5">\n'
            f'    <animate attributeName="fill" values="{fill_vals}" '
            f'keyTimes="{kt_str}" dur="{total_cycle}s" repeatCount="indefinite"/>\n'
            f'    <animate attributeName="stroke" values="{stroke_vals}" '
            f'keyTimes="{kt_str}" dur="{total_cycle}s" repeatCount="indefinite"/>\n'
            f'    <animate attributeName="stroke-width" values="{sw_vals}" '
            f'keyTimes="{kt_str}" dur="{total_cycle}s" repeatCount="indefinite"/>\n'
            f'  </path>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="0 0 {img_w} {img_h}"'
        f' width="{img_w}" height="{img_h}">\n'
        + "\n".join(border_paths) + "\n"
        + "\n".join(hl_paths) + "\n"
        + "</svg>"
    )


# ── GIF generation ────────────────────────────────────────────────

def render_highlight_frame(base_img, geom, img_w, img_h,
                           merc_y_top, merc_y_bot):
    """Render a single frame with one country highlighted."""
    frame = base_img.copy().convert("RGBA")
    overlay = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    px_polys = geom_to_pixel_polygons(geom, img_w, img_h,
                                      merc_y_top, merc_y_bot)
    color = HIGHLIGHT_COLOR + (HIGHLIGHT_ALPHA,)
    for coords in px_polys:
        draw.polygon(coords, fill=color, outline=(193, 18, 31, 200))

    frame = Image.alpha_over(frame, overlay) if hasattr(Image, 'alpha_over') else Image.alpha_composite(frame, overlay)
    return frame.convert("RGB")


def generate_gif(base_img, highlight_geoms, img_w, img_h,
                 merc_y_top, merc_y_bot, fps=8, hold_frames=10):
    """Generate animated GIF cycling through highlighted countries."""
    frames = []
    # Add a couple of neutral frames at start
    base_rgb = base_img.copy().convert("RGB")
    for _ in range(3):
        frames.append(base_rgb.copy())

    for iso3 in HIGHLIGHT_COUNTRIES:
        if iso3 not in highlight_geoms:
            continue
        hl_frame = render_highlight_frame(
            base_img, highlight_geoms[iso3],
            img_w, img_h, merc_y_top, merc_y_bot
        )
        # Hold each highlighted country for several frames
        for _ in range(hold_frames):
            frames.append(hl_frame)
        # Brief neutral transition (2 frames)
        for _ in range(2):
            frames.append(base_rgb.copy())

    return frames


# ── Draw thin borders on the base image ───────────────────────────

def draw_borders_on_image(img, all_geoms, img_w, img_h,
                          merc_y_top, merc_y_bot):
    """Draw country borders onto the image for the GIF base."""
    draw = ImageDraw.Draw(img)
    for iso3, geom in all_geoms.items():
        px_polys = geom_to_pixel_polygons(geom, img_w, img_h,
                                          merc_y_top, merc_y_bot)
        for coords in px_polys:
            if len(coords) >= 3:
                draw.polygon(coords, outline=(0, 0, 0, 40))


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zoom", type=int, default=4)
    parser.add_argument("--gif-fps", type=int, default=8)
    args = parser.parse_args()
    zoom = max(3, min(5, args.zoom))

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1) Download tiles
    print("Downloading Esri Physical tiles...")
    img = stitch_tiles(zoom)
    img_w, img_h = img.size
    merc_y_top = lat_to_merc_y(LAT_MAX)
    merc_y_bot = lat_to_merc_y(LAT_MIN)
    print(f"  Image size: {img_w} x {img_h}")

    # 2) Load country geometries (high detail for mask, lower for SVG)
    print("Loading country geometries...")
    all_codes = load_all_country_codes()

    mask_geoms = {}
    svg_geoms = {}
    for iso3 in all_codes:
        gm = load_country_geom(iso3, SIMPLIFY_TOLERANCE_MASK, MIN_AREA_MASK)
        if gm:
            mask_geoms[iso3] = gm
        gs = load_country_geom(iso3, SIMPLIFY_TOLERANCE_SVG, MIN_AREA_SVG)
        if gs:
            svg_geoms[iso3] = gs
    print(f"  {len(mask_geoms)} countries (mask), {len(svg_geoms)} countries (SVG)")

    # 3) Build land mask & apply
    print("Building land mask...")
    mask = build_land_mask(mask_geoms, img_w, img_h, merc_y_top, merc_y_bot)
    land_img = apply_sea_mask(img, mask)

    jpg_path = OUTPUT_DIR / "world_land.jpg"
    land_img.save(jpg_path, "JPEG", quality=92)
    print(f"  Saved {jpg_path} ({os.path.getsize(jpg_path) // 1024} KB)")

    # 4) Build SVG overlay
    print("Building SVG overlay...")
    highlight_geoms_svg = {iso3: svg_geoms[iso3]
                           for iso3 in HIGHLIGHT_COUNTRIES
                           if iso3 in svg_geoms}
    svg = build_overlay_svg(svg_geoms, highlight_geoms_svg,
                            img_w, img_h, merc_y_top, merc_y_bot)
    svg_path = OUTPUT_DIR / "world_land_overlay.svg"
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"  Saved {svg_path} ({os.path.getsize(svg_path) // 1024} KB)")

    # 5) Generate GIF
    print("Generating animated GIF...")
    # Use mask geoms for precise highlight on the raster
    highlight_geoms_mask = {iso3: mask_geoms[iso3]
                            for iso3 in HIGHLIGHT_COUNTRIES
                            if iso3 in mask_geoms}

    # Draw borders on land image for GIF base
    gif_base = land_img.copy()
    draw_borders_on_image(gif_base, mask_geoms, img_w, img_h,
                          merc_y_top, merc_y_bot)

    # Scale down for GIF size (full res would be huge)
    gif_w = min(img_w, 1200)
    scale = gif_w / img_w
    gif_h = int(img_h * scale)
    gif_base_small = gif_base.resize((gif_w, gif_h), Image.LANCZOS)

    # Scale merc boundaries stay the same, just use smaller image dims
    # Re-gen highlight geoms at mask tolerance for crisp edges
    frames = generate_gif(gif_base_small, highlight_geoms_mask,
                          gif_w, gif_h, merc_y_top, merc_y_bot,
                          fps=args.gif_fps, hold_frames=10)

    gif_path = OUTPUT_DIR / "world_land_animated.gif"
    duration_ms = 1000 // args.gif_fps
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )
    print(f"  Saved {gif_path} ({os.path.getsize(gif_path) // 1024} KB)"
          f" — {len(frames)} frames @ {args.gif_fps} fps")

    print("Done!")


if __name__ == "__main__":
    main()
