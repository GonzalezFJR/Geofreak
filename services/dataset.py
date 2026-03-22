"""Dataset loading and querying service."""

import json
import os
from typing import Optional

import pandas as pd


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "data")
COUNTRIES_CSV = os.path.join(DATA_DIR, "countries.csv")
CITIES_CSV = os.path.join(DATA_DIR, "cities.csv")


class DatasetService:
    """Loads and serves country and city datasets."""

    def __init__(self):
        self._countries_df: Optional[pd.DataFrame] = None
        self._cities_df: Optional[pd.DataFrame] = None

    # ── Countries ────────────────────────────────────────────

    def _load_countries(self) -> pd.DataFrame:
        if self._countries_df is None:
            if not os.path.exists(COUNTRIES_CSV):
                self._countries_df = pd.DataFrame()
            else:
                self._countries_df = pd.read_csv(COUNTRIES_CSV, keep_default_na=False)
        return self._countries_df

    def get_countries(self) -> pd.DataFrame:
        return self._load_countries()

    def get_country(self, iso_code: str) -> Optional[dict]:
        df = self._load_countries()
        if df.empty:
            return None
        match = df[(df["iso_a3"] == iso_code) | (df["iso_a2"] == iso_code)]
        if match.empty:
            return None
        row = match.iloc[0].to_dict()
        for field in ["top_cities", "official_languages"]:
            if field in row and isinstance(row[field], str) and row[field]:
                try:
                    row[field] = json.loads(row[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return row

    # ── Cities ───────────────────────────────────────────────

    def _load_cities(self) -> pd.DataFrame:
        if self._cities_df is None:
            if not os.path.exists(CITIES_CSV):
                self._cities_df = pd.DataFrame()
            else:
                self._cities_df = pd.read_csv(CITIES_CSV, keep_default_na=False)
        return self._cities_df

    def get_cities(
        self, min_population: int = 0, capitals_only: bool = False
    ) -> list[dict]:
        """Return cities from the cities dataset.

        Args:
            min_population: Filter cities with at least this population.
            capitals_only: If True, only return capital cities.
        """
        df = self._load_cities()
        if df.empty:
            return []

        if capitals_only:
            df = df[df["is_capital"] == True]  # noqa: E712
        elif min_population > 0:
            # Always include capitals regardless of population filter
            df = df[(df["population"] >= min_population) | (df["is_capital"] == True)]  # noqa: E712

        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "name": row["name"],
                    "country": row.get("country_name", ""),
                    "iso_a3": row.get("iso_a3", ""),
                    "iso_a2": row.get("iso_a2", ""),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "population": int(row["population"]),
                    "is_capital": bool(row["is_capital"]),
                })
            except (ValueError, TypeError):
                continue
        return records

    def get_cities_by_country(self, iso_code: str) -> list[dict]:
        """Return all cities for a specific country."""
        df = self._load_cities()
        if df.empty:
            return []
        mask = (df["iso_a3"] == iso_code) | (df["iso_a2"] == iso_code)
        filtered = df[mask].sort_values("population", ascending=False)
        records = []
        for _, row in filtered.iterrows():
            try:
                records.append({
                    "name": row["name"],
                    "country": row.get("country_name", ""),
                    "iso_a3": row.get("iso_a3", ""),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "population": int(row["population"]),
                    "is_capital": bool(row["is_capital"]),
                })
            except (ValueError, TypeError):
                continue
        return records
