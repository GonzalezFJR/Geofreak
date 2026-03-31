"""Dataset Configuration Service — manages dataset visibility and state."""

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "static" / "data"
CONFIG_PATH = DATA_DIR / "datasets_config.json"


class DatasetConfigService:
    def __init__(self):
        self._data: Optional[dict] = None

    def _load(self) -> dict:
        if self._data is None:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            else:
                self._data = {"last_updated": None, "datasets": {}}
        return self._data

    def _save(self, data: dict):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._data = data

    def get_all_datasets(self) -> dict:
        """Return all dataset configurations."""
        return self._load().get("datasets", {})

    def get_dataset(self, dataset_id: str) -> Optional[dict]:
        """Return configuration for a specific dataset."""
        return self.get_all_datasets().get(dataset_id)

    def get_visible_datasets(self) -> list[str]:
        """Return list of dataset IDs that are visible and exist."""
        result = []
        for ds_id, ds_info in self.get_all_datasets().items():
            if ds_info.get("visible", True) and ds_info.get("exists", True):
                result.append(ds_id)
        return result

    def is_visible(self, dataset_id: str) -> bool:
        """Check if a dataset is visible and exists."""
        ds = self.get_dataset(dataset_id)
        if not ds:
            return False
        return ds.get("visible", True) and ds.get("exists", True)

    def toggle_visibility(self, dataset_id: str, visible: bool):
        """Toggle visibility of a dataset."""
        data = self._load()
        if dataset_id in data["datasets"]:
            data["datasets"][dataset_id]["visible"] = visible
            self._save(data)

    def update_existence_state(self) -> dict:
        """Check all datasets for existence and update state. Returns summary."""
        data = self._load()
        summary = {"checked": 0, "exists": 0, "missing": 0, "details": []}

        for ds_id, ds_info in data["datasets"].items():
            summary["checked"] += 1
            exists = True
            entity_count = None
            details = {"id": ds_id, "exists": True, "issues": []}

            # Check CSV file
            csv_file = ds_info.get("csv_file")
            if csv_file:
                csv_path = DATA_DIR / csv_file
                if csv_path.exists():
                    # Count entities
                    try:
                        with open(csv_path, "r", encoding="utf-8") as f:
                            reader = csv.DictReader(f)
                            entity_count = sum(1 for _ in reader)
                    except Exception as e:
                        details["issues"].append(f"Error reading CSV: {e}")
                else:
                    exists = False
                    details["issues"].append(f"CSV file missing: {csv_file}")

            # Check GeoJSON directory
            geojson_dir = ds_info.get("geojson_dir")
            if geojson_dir:
                geojson_path = DATA_DIR / geojson_dir
                if not geojson_path.exists() or not geojson_path.is_dir():
                    exists = False
                    details["issues"].append(f"GeoJSON directory missing: {geojson_dir}")
                else:
                    geojson_count = len([f for f in geojson_path.iterdir() if f.suffix == ".json"])
                    if geojson_count == 0:
                        details["issues"].append(f"GeoJSON directory empty: {geojson_dir}")

            # Update state
            data["datasets"][ds_id]["exists"] = exists
            data["datasets"][ds_id]["entity_count"] = entity_count
            details["exists"] = exists
            details["entity_count"] = entity_count

            if exists:
                summary["exists"] += 1
            else:
                summary["missing"] += 1

            summary["details"].append(details)

        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._save(data)
        return summary

    def get_last_updated(self) -> Optional[str]:
        """Return last update timestamp."""
        return self._load().get("last_updated")


# Singleton instance
_dataset_config_service = None


def get_dataset_config_service() -> DatasetConfigService:
    global _dataset_config_service
    if _dataset_config_service is None:
        _dataset_config_service = DatasetConfigService()
    return _dataset_config_service
