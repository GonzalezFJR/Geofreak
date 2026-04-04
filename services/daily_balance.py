"""
Daily balance SVG generator.
Picks two countries from a rotating list based on the current date,
reads their pre-generated SVG path data, and assembles an animated
balance SVG. The result is cached to disk with the date stamp.
"""

import re
import os
import random
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
COUNTRIES_SVG_DIR = BASE_DIR / "static" / "img" / "icons" / "countries_small"
CACHE_DIR = BASE_DIR / "static" / "img" / "icons" / "_cache"

# Pool of countries for random daily pairs
COUNTRY_POOL = [
    "ESP", "ITA", "FRA", "BRA", "ARG", "MEX", "USA", "CHN", "IND", "AUS",
    "GBR", "UKR", "IRN", "SYR", "EGY", "ZAF", "CHE", "URY", "COL",
    "CZE", "POL", "JPN", "KAZ", "MNG", "DZA", "ETH", "DEU", "VEN",
]

# Balance geometry constants
PIVOT = (200, 60)
LEFT_PAN_X = 50
RIGHT_PAN_X = 350
PAN_Y = 120
PAN_BOTTOM = 126
SVG_VIEWBOX_W = 400
COUNTRY_MAX_W = 140
COUNTRY_MAX_H = 150
VIEWBOX_SIZE = 100  # normalised country SVG size


def get_daily_pair(today: date | None = None) -> tuple[str, str]:
    """Return two ISO3 codes for today's balance pair.
    Uses the date as a random seed so the same day always gives
    the same pair, but different days give different combinations."""
    if today is None:
        today = date.today()
    rng = random.Random(today.toordinal())
    left, right = rng.sample(COUNTRY_POOL, 2)
    return left, right


def _extract_path_d(svg_path: Path) -> tuple[str, float]:
    """Extract the d attribute and viewBox height from a country SVG."""
    content = svg_path.read_text(encoding="utf-8")
    # Extract path d
    m = re.search(r'd="([^"]+)"', content)
    if not m:
        raise ValueError(f"No path d found in {svg_path}")
    d = m.group(1)
    # Extract viewBox height
    m2 = re.search(r'viewBox="0 0 [\d.]+ ([\d.]+)"', content)
    vb_h = float(m2.group(1)) if m2 else VIEWBOX_SIZE
    return d, vb_h


def _reposition_path(path_d: str, src_vb_h: float,
                     anchor_x: float, anchor_y: float) -> str:
    """Reposition a normalised path (in 100x100 space) to hang from
    (anchor_x, anchor_y) as top-center, scaled to COUNTRY_MAX_W/H."""
    scale = min(COUNTRY_MAX_W / VIEWBOX_SIZE, COUNTRY_MAX_H / src_vb_h)

    # After scaling, the path occupies scale*VIEWBOX_SIZE wide, scale*src_vb_h tall
    scaled_w = VIEWBOX_SIZE * scale
    # Top-center of source is at (50, 0) in normalised space
    # We want that to map to (anchor_x, anchor_y)
    off_x = anchor_x - scaled_w / 2
    off_y = anchor_y

    # Parse and transform all coordinates in the path
    result = []
    i = 0
    while i < len(path_d):
        c = path_d[i]
        if c in "MLZ":
            result.append(c)
            i += 1
        elif c == ',' or c == ' ':
            i += 1
        elif c == '-' or c == '.' or c.isdigit():
            # Read x
            x_str, i = _read_number(path_d, i)
            # Skip separator
            while i < len(path_d) and path_d[i] in ', ':
                i += 1
            # Read y
            y_str, i = _read_number(path_d, i)
            x = float(x_str) * scale + off_x
            y = float(y_str) * scale + off_y
            result.append(f"{x:.2f},{y:.2f}")
        else:
            i += 1
    return "".join(result)


def _read_number(s, i):
    """Read a number (possibly negative, with decimal) from string."""
    start = i
    if i < len(s) and s[i] == '-':
        i += 1
    while i < len(s) and (s[i].isdigit() or s[i] == '.'):
        i += 1
    return s[start:i], i


def _compute_country_bottom(src_vb_h: float, anchor_y: float) -> float:
    """Compute the bottom y of a repositioned country."""
    scale = min(COUNTRY_MAX_W / VIEWBOX_SIZE, COUNTRY_MAX_H / src_vb_h)
    return anchor_y + src_vb_h * scale


def build_balance_svg(iso_left: str, iso_right: str) -> str:
    """Build the animated balance SVG from pre-generated country paths."""
    left_svg = COUNTRIES_SVG_DIR / f"{iso_left}.svg"
    right_svg = COUNTRIES_SVG_DIR / f"{iso_right}.svg"

    path_d_left, vb_h_left = _extract_path_d(left_svg)
    path_d_right, vb_h_right = _extract_path_d(right_svg)

    hang_y = PAN_BOTTOM + 0.5

    repo_left = _reposition_path(path_d_left, vb_h_left, LEFT_PAN_X, hang_y)
    repo_right = _reposition_path(path_d_right, vb_h_right, RIGHT_PAN_X, hang_y)

    bottom_left = _compute_country_bottom(vb_h_left, hang_y)
    bottom_right = _compute_country_bottom(vb_h_right, hang_y)
    max_bottom = max(bottom_left, bottom_right)

    vb_height = max(280, max_bottom + 15)
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

  <!-- Rotating balance -->
  <g class="balance">
    <line x1="{LEFT_PAN_X}" y1="{PIVOT[1]}" x2="{RIGHT_PAN_X}" y2="{PIVOT[1]}" stroke="#2b2b2b" stroke-width="5" stroke-linecap="round"/>
    <circle cx="{PIVOT[0]}" cy="{PIVOT[1]}" r="9" fill="#2b2b2b"/>

    <line x1="{LEFT_PAN_X}" y1="{PIVOT[1]}" x2="{LEFT_PAN_X}" y2="{PAN_Y}" stroke="#2b2b2b" stroke-width="2.5"/>
    <path d="M{LEFT_PAN_X - 30},{PAN_BOTTOM} Q{LEFT_PAN_X},{PAN_BOTTOM - 8} {LEFT_PAN_X + 30},{PAN_BOTTOM}" stroke="#2b2b2b" stroke-width="3.5"
          fill="#2b2b2b" fill-opacity="0.2" stroke-linecap="round"/>
    <path d="{repo_left}" fill="#c4a882" fill-opacity="0.9" stroke="#8b7355" stroke-width="0.6"/>

    <line x1="{RIGHT_PAN_X}" y1="{PIVOT[1]}" x2="{RIGHT_PAN_X}" y2="{PAN_Y}" stroke="#2b2b2b" stroke-width="2.5"/>
    <path d="M{RIGHT_PAN_X - 30},{PAN_BOTTOM} Q{RIGHT_PAN_X},{PAN_BOTTOM - 8} {RIGHT_PAN_X + 30},{PAN_BOTTOM}" stroke="#2b2b2b" stroke-width="3.5"
          fill="#2b2b2b" fill-opacity="0.2" stroke-linecap="round"/>
    <path d="{repo_right}" fill="#c4a882" fill-opacity="0.9" stroke="#8b7355" stroke-width="0.5"/>
  </g>
</svg>"""
    return svg


def get_daily_balance_svg() -> str:
    """Get today's balance SVG, generating if needed."""
    today = date.today()
    cache_file = CACHE_DIR / f"comparison_{today.isoformat()}.svg"

    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Clean old cached files
    for old in CACHE_DIR.glob("comparison_*.svg"):
        if old != cache_file:
            old.unlink(missing_ok=True)

    iso_left, iso_right = get_daily_pair(today)
    svg = build_balance_svg(iso_left, iso_right)
    cache_file.write_text(svg, encoding="utf-8")
    return svg
