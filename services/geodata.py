"""GeoJSON loading and serving service."""

import json
import os
from typing import Optional


_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "data")
GEOJSON_DIR = os.path.join(_DATA_DIR, "geojson")

SUBNATIONAL_DIRS: dict[str, str] = {
    "us-states":        os.path.join(_DATA_DIR, "geojson_us"),
    "spain-provinces":  os.path.join(_DATA_DIR, "geojson_spain"),
    "russia-regions":   os.path.join(_DATA_DIR, "geojson_russia"),
    "france-regions":   os.path.join(_DATA_DIR, "geojson_france"),
    "italy-provinces":    os.path.join(_DATA_DIR, "geojson_italy_provinces"),
    "germany-states":   os.path.join(_DATA_DIR, "geojson_germany"),
    "mexico-states":    os.path.join(_DATA_DIR, "geojson_mexico"),
    "argentina-provinces": os.path.join(_DATA_DIR, "geojson_argentina"),
    "brazil-states":    os.path.join(_DATA_DIR, "geojson_brazil"),
}


class GeodataService:
    """Loads and serves GeoJSON data."""

    def __init__(self):
        self._all_cache: Optional[dict] = None
        self._simple_cache: Optional[dict] = None
        self._subnational_cache: dict[str, dict] = {}

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

    def get_subnational_geojson(self, dataset: str) -> dict:
        """Return a FeatureCollection combining all .geojson files for a sub-national dataset.

        Adds ``_game_id`` (filename without extension) to each feature's properties
        so the JS engine can match features to CSV entity IDs.
        """
        if dataset in self._subnational_cache:
            return self._subnational_cache[dataset]

        directory = SUBNATIONAL_DIRS.get(dataset)
        if not directory or not os.path.isdir(directory):
            return {"type": "FeatureCollection", "features": []}

        features: list = []
        for fname in sorted(os.listdir(directory)):
            if not fname.endswith(".geojson"):
                continue
            game_id = fname[:-8]  # strip ".geojson"
            fpath = os.path.join(directory, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("type") == "FeatureCollection":
                    for feat in data.get("features", []):
                        feat.setdefault("properties", {})["_game_id"] = game_id
                        features.append(feat)
                elif data.get("type") == "Feature":
                    data.setdefault("properties", {})["_game_id"] = game_id
                    features.append(data)
            except (json.JSONDecodeError, OSError):
                continue

        result = {"type": "FeatureCollection", "features": features}
        self._subnational_cache[dataset] = result
        return result

    def get_single_subnational(self, dataset: str, code: str) -> Optional[dict]:
        """Return GeoJSON for a single sub-national entity by dataset and code."""
        directory = SUBNATIONAL_DIRS.get(dataset)
        if not directory:
            return None
        fpath = os.path.join(directory, f"{code}.geojson")
        if not os.path.exists(fpath):
            return None
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)

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
