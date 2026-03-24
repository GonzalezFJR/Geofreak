"""GeoJSON loading and serving service."""

import json
import os
from typing import Optional


GEOJSON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "static", "data", "geojson"
)


class GeodataService:
    """Loads and serves GeoJSON data."""

    def __init__(self):
        self._all_cache: Optional[dict] = None
        self._simple_cache: Optional[dict] = None

    def get_all_geojson(self) -> dict:
        """Return a combined FeatureCollection from all individual country files."""
        if self._all_cache is not None:
            return self._all_cache

        combined_path = os.path.join(GEOJSON_DIR, "all_countries.geojson")
        if os.path.exists(combined_path):
            with open(combined_path, "r", encoding="utf-8") as f:
                self._all_cache = json.load(f)
            return self._all_cache

        # Fallback: combine individual files
        features = []
        if os.path.isdir(GEOJSON_DIR):
            for fname in sorted(os.listdir(GEOJSON_DIR)):
                if fname.endswith(".geojson") and fname not in (
                    "all_countries.geojson",
                    "all_countries_simple.geojson",
                ):
                    fpath = os.path.join(GEOJSON_DIR, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if data.get("type") == "FeatureCollection":
                            features.extend(data.get("features", []))
                        elif data.get("type") == "Feature":
                            features.append(data)
                    except (json.JSONDecodeError, OSError):
                        continue

        self._all_cache = {"type": "FeatureCollection", "features": features}
        return self._all_cache

    def get_simple_geojson(self) -> dict:
        """Return simplified (lightweight) GeoJSON for game maps."""
        if self._simple_cache is not None:
            return self._simple_cache

        simple_path = os.path.join(GEOJSON_DIR, "all_countries_simple.geojson")
        if os.path.exists(simple_path):
            with open(simple_path, "r", encoding="utf-8") as f:
                self._simple_cache = json.load(f)
            return self._simple_cache

        # Fallback to full version
        return self.get_all_geojson()

    def get_country_geojson(self, iso_code: str) -> Optional[dict]:
        """Return GeoJSON for a single country by ISO code."""
        # Try individual file first
        for ext in [".geojson", ".geo.json"]:
            fpath = os.path.join(GEOJSON_DIR, f"{iso_code}{ext}")
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    return json.load(f)

        # Fallback: search in combined file
        all_data = self.get_all_geojson()
        for feature in all_data.get("features", []):
            props = feature.get("properties", {})
            if props.get("ISO_A3") == iso_code or props.get("iso_a3") == iso_code:
                return {
                    "type": "FeatureCollection",
                    "features": [feature],
                }
        return None
