"""Dataset loading and querying service."""

import json
import os
from typing import Any, Optional

import pandas as pd


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "data")
COUNTRIES_CSV = os.path.join(DATA_DIR, "countries.csv")
CITIES_CSV = os.path.join(DATA_DIR, "cities.csv")
US_STATES_CSV = os.path.join(DATA_DIR, "usastates.csv")
SPAIN_PROVINCES_CSV = os.path.join(DATA_DIR, "spain_provinces.csv")
RUSSIA_REGIONS_CSV = os.path.join(DATA_DIR, "russia_regions.csv")
FRANCE_REGIONS_CSV = os.path.join(DATA_DIR, "france_regions.csv")
ITALY_PROVINCES_CSV = os.path.join(DATA_DIR, "italy_provinces.csv")
GERMANY_STATES_CSV = os.path.join(DATA_DIR, "germany_states.csv")
MEXICO_STATES_CSV = os.path.join(DATA_DIR, "mexico_states.csv")
ARGENTINA_PROVINCES_CSV = os.path.join(DATA_DIR, "argentina_provinces.csv")
BRAZIL_STATES_CSV = os.path.join(DATA_DIR, "brazil_states.csv")
RELIEF_CSV = os.path.join(DATA_DIR, "relief_features.csv")
RELIEF_GEOJSON_DIR = os.path.join(DATA_DIR, "relief_geojson")

# Maps filter key → continent values in the countries CSV
CONTINENT_MAP: dict[str, list[str]] = {
    "europe":   ["Europe"],
    "asia":     ["Asia"],
    "africa":   ["Africa"],
    "americas": ["North America", "South America"],
    "oceania":  ["Oceania"],
}


class DatasetService:
    """Loads and serves country and city datasets."""

    def __init__(self):
        self._countries_df: Optional[pd.DataFrame] = None
        self._cities_df: Optional[pd.DataFrame] = None
        self._us_df: Optional[pd.DataFrame] = None
        self._spain_df: Optional[pd.DataFrame] = None
        self._russia_df: Optional[pd.DataFrame] = None
        self._france_df: Optional[pd.DataFrame] = None
        self._italy_df: Optional[pd.DataFrame] = None
        self._germany_df: Optional[pd.DataFrame] = None
        self._mexico_df: Optional[pd.DataFrame] = None
        self._argentina_df: Optional[pd.DataFrame] = None
        self._brazil_df: Optional[pd.DataFrame] = None
        self._relief_df: Optional[pd.DataFrame] = None
        self._map_game_counts: Optional[dict] = None
        self._city_tiers: Optional[dict[int, list[dict]]] = None

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
                # Convert is_capital from string ("national"/"admin1"/"no") to bool
                if "is_capital" in self._cities_df.columns:
                    self._cities_df["is_capital"] = self._cities_df["is_capital"] == "national"
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
                rec = {
                    "name": row["name"],
                    "country": row.get("country_name", ""),
                    "iso_a3": row.get("iso_a3", ""),
                    "iso_a2": row.get("iso_a2", ""),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "population": int(row["population"]),
                    "is_capital": bool(row["is_capital"]),
                }
                # Localized names
                for lc in ("en", "es", "fr", "it", "ru"):
                    v = row.get(f"name_{lc}", "")
                    if v:
                        rec[f"name_{lc}"] = v
                # Optional numeric fields
                for fld in ("elevation", "metro_population", "annual_mean_temp",
                            "annual_precipitation", "sunshine_hours_yr"):
                    v = row.get(fld, "")
                    if v != "" and v is not None:
                        try:
                            rec[fld] = float(v)
                        except (ValueError, TypeError):
                            pass
                # Optional string fields
                for fld in ("timezone", "admin1_name"):
                    v = row.get(fld, "")
                    if v:
                        rec[fld] = v
                records.append(rec)
            except (ValueError, TypeError):
                continue
        return records

    # ── City tiers (for lazy map loading) ─────────────────────

    def _build_city_tiers(self) -> dict[int, list[dict]]:
        """Precompute city records grouped by population tier for lazy map loading."""
        if self._city_tiers is not None:
            return self._city_tiers

        df = self._load_cities()
        if df.empty:
            self._city_tiers = {i: [] for i in range(1, 6)}
            return self._city_tiers

        tiers: dict[int, list[dict]] = {i: [] for i in range(1, 6)}

        for _, row in df.iterrows():
            try:
                pop = int(row["population"])
                is_capital = bool(row["is_capital"])

                rec: dict[str, Any] = {
                    "name": row["name"],
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "population": pop,
                    "iso_a3": row.get("iso_a3", ""),
                    "iso_a2": row.get("iso_a2", ""),
                    "country": row.get("country_name", ""),
                    "is_capital": is_capital,
                }
                # Localized names
                for lc in ("en", "es", "fr", "it", "ru"):
                    v = row.get(f"name_{lc}", "")
                    if v:
                        rec[f"name_{lc}"] = v
                # Popup-ready fields
                for fld in ("elevation", "metro_population", "annual_mean_temp",
                            "annual_precipitation", "sunshine_hours_yr"):
                    v = row.get(fld, "")
                    if v != "" and v is not None:
                        try:
                            rec[fld] = float(v)
                        except (ValueError, TypeError):
                            pass
                for fld in ("timezone", "admin1_name"):
                    v = row.get(fld, "")
                    if v:
                        rec[fld] = v

                # Assign to tier
                if is_capital or pop >= 5_000_000:
                    tiers[1].append(rec)
                elif pop >= 1_000_000:
                    tiers[2].append(rec)
                elif pop >= 500_000:
                    tiers[3].append(rec)
                elif pop >= 100_000:
                    tiers[4].append(rec)
                else:  # 50k-100k
                    tiers[5].append(rec)
            except (ValueError, TypeError):
                continue

        self._city_tiers = tiers
        return tiers

    def get_cities_for_tier(self, tier: int) -> list[dict]:
        """Return city records for a specific population tier (1-5)."""
        tiers = self._build_city_tiers()
        return tiers.get(tier, [])

    def get_countries_for_map(self, continent: str = "all", entity_type: str = "all") -> list[dict]:
        """Return countries with essential fields for the map game, with optional filtering."""
        df = self._load_countries()
        if df.empty:
            return []
        if continent and continent != "all":
            continent_values = CONTINENT_MAP.get(continent, [])
            if continent_values:
                df = df[df["continent"].isin(continent_values)]
        if entity_type and entity_type != "all":
            df = df[df["entity_type"] == entity_type]
        df = df[df["iso_a3"].notna() & (df["iso_a3"] != "")]
        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "id": str(row["iso_a3"]),
                    "iso_a3": str(row["iso_a3"]),
                    "name": str(row.get("name", "")),
                    "name_es": str(row.get("name_es", "")),
                    "name_fr": str(row.get("name_fr", "")),
                    "name_it": str(row.get("name_it", "")),
                    "name_ru": str(row.get("name_ru", "")),
                    "name_official": str(row.get("name_official", "")),
                    "capital": str(row.get("capital", "")),
                    "capital_es": str(row.get("capital_es", "")),
                    "capital_fr": str(row.get("capital_fr", "")),
                    "capital_it": str(row.get("capital_it", "")),
                    "capital_ru": str(row.get("capital_ru", "")),
                    "lat": float(row.get("lat", 0) or 0),
                    "lon": float(row.get("lon", 0) or 0),
                    "continent": str(row.get("continent", "")),
                    "entity_type": str(row.get("entity_type", "country")),
                })
            except (ValueError, TypeError):
                continue
        return records

    def get_cities_for_map(self, city_filter: str = "capitals", continent: str = "all", country_filter: list[str] | None = None) -> list[dict]:
        """Return cities for the map game with optional filter and continent.

        city_filter: 'capitals' | '5m' | '1m' | '500k' | '200k' | '100k'
        continent: 'all' | 'europe' | 'asia' | 'africa' | 'americas' | 'oceania'
        country_filter: list of iso_a3 codes (OR logic) or None
        """
        df = self._load_cities()
        if df.empty:
            return []

        if city_filter == "capitals":
            df = df[df["is_capital"] == True]  # noqa: E712
        elif city_filter in ("capitals_country", "capitals_territory"):
            df = df[df["is_capital"] == True]  # noqa: E712
            countries_df = self._load_countries()
            if not countries_df.empty:
                et = "country" if city_filter == "capitals_country" else "territory"
                iso_set = set(countries_df[countries_df["entity_type"] == et]["iso_a3"].tolist())
                df = df[df["iso_a3"].isin(iso_set)]
        elif city_filter == "5m":
            df = df[df["population"] >= 5_000_000]
        elif city_filter == "1m":
            df = df[df["population"] >= 1_000_000]
        elif city_filter == "500k":
            df = df[df["population"] >= 500_000]
        elif city_filter == "200k":
            df = df[df["population"] >= 200_000]
        elif city_filter == "100k":
            df = df[df["population"] >= 100_000]
        elif city_filter == "50k":
            df = df[df["population"] >= 50_000]

        if continent and continent != "all":
            continent_values = CONTINENT_MAP.get(continent, [])
            if continent_values:
                countries_df = self._load_countries()
                if not countries_df.empty:
                    iso_set = set(
                        countries_df[countries_df["continent"].isin(continent_values)]["iso_a3"].tolist()
                    )
                    df = df[df["iso_a3"].isin(iso_set)]

        if country_filter:
            df = df[df["iso_a3"].isin(country_filter)]

        records = []
        for _, row in df.iterrows():
            try:
                city_id = str(int(row["geonameid"])) if row.get("geonameid") else (
                    str(row["name"]) + "_" + str(row.get("iso_a3", ""))
                )
                records.append({
                    "id": city_id,
                    "name": str(row["name"]),
                    "asciiname": str(row.get("asciiname", row["name"])),
                    "iso_a3": str(row.get("iso_a3", "")),
                    "country_name": str(row.get("country_name", "")),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "population": int(row.get("population", 0) or 0),
                    "is_capital": bool(row.get("is_capital", False)),
                })
            except (ValueError, TypeError):
                continue
        return records

    # ── Sub-national datasets ─────────────────────────────────

    def _load_us(self) -> pd.DataFrame:
        if self._us_df is None:
            if not os.path.exists(US_STATES_CSV):
                self._us_df = pd.DataFrame()
            else:
                self._us_df = pd.read_csv(US_STATES_CSV, keep_default_na=False)
        return self._us_df

    def _load_spain(self) -> pd.DataFrame:
        if self._spain_df is None:
            if not os.path.exists(SPAIN_PROVINCES_CSV):
                self._spain_df = pd.DataFrame()
            else:
                self._spain_df = pd.read_csv(SPAIN_PROVINCES_CSV, keep_default_na=False, dtype={"code": str})
        return self._spain_df

    def _load_russia(self) -> pd.DataFrame:
        if self._russia_df is None:
            if not os.path.exists(RUSSIA_REGIONS_CSV):
                self._russia_df = pd.DataFrame()
            else:
                self._russia_df = pd.read_csv(RUSSIA_REGIONS_CSV, keep_default_na=False)
        return self._russia_df

    def _load_france(self) -> pd.DataFrame:
        if self._france_df is None:
            if not os.path.exists(FRANCE_REGIONS_CSV):
                self._france_df = pd.DataFrame()
            else:
                self._france_df = pd.read_csv(FRANCE_REGIONS_CSV, keep_default_na=False)
        return self._france_df

    def _load_italy(self) -> pd.DataFrame:
        if self._italy_df is None:
            if not os.path.exists(ITALY_PROVINCES_CSV):
                self._italy_df = pd.DataFrame()
            else:
                self._italy_df = pd.read_csv(ITALY_PROVINCES_CSV, keep_default_na=False)
        return self._italy_df

    def _load_germany(self) -> pd.DataFrame:
        if self._germany_df is None:
            if not os.path.exists(GERMANY_STATES_CSV):
                self._germany_df = pd.DataFrame()
            else:
                self._germany_df = pd.read_csv(GERMANY_STATES_CSV, keep_default_na=False)
        return self._germany_df

    def _load_mexico(self) -> pd.DataFrame:
        if self._mexico_df is None:
            if not os.path.exists(MEXICO_STATES_CSV):
                self._mexico_df = pd.DataFrame()
            else:
                self._mexico_df = pd.read_csv(MEXICO_STATES_CSV, keep_default_na=False)
        return self._mexico_df

    def _load_argentina(self) -> pd.DataFrame:
        if self._argentina_df is None:
            if not os.path.exists(ARGENTINA_PROVINCES_CSV):
                self._argentina_df = pd.DataFrame()
            else:
                self._argentina_df = pd.read_csv(ARGENTINA_PROVINCES_CSV, keep_default_na=False)
        return self._argentina_df

    def _load_brazil(self) -> pd.DataFrame:
        if self._brazil_df is None:
            if not os.path.exists(BRAZIL_STATES_CSV):
                self._brazil_df = pd.DataFrame()
            else:
                self._brazil_df = pd.read_csv(BRAZIL_STATES_CSV, keep_default_na=False)
        return self._brazil_df

    def get_us_states(self) -> list[dict]:
        df = self._load_us()
        if df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "id": str(row["code"]),
                    "name": str(row["name"]),
                    "name_es": str(row.get("name_es", row["name"])),
                    "capital": str(row.get("capital", "")),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                })
            except (ValueError, TypeError):
                continue
        return records

    def get_spain_provinces(self) -> list[dict]:
        df = self._load_spain()
        if df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "id": str(row["code"]),
                    "name": str(row["name"]),
                    "name_es": str(row.get("name_es", row["name"])),
                    "capital": str(row.get("capital", "")),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                })
            except (ValueError, TypeError):
                continue
        return records

    def get_russia_regions(self) -> list[dict]:
        df = self._load_russia()
        if df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "id": str(row["code"]),
                    "name": str(row["name"]),
                    "name_es": str(row.get("name_es", row["name"])),
                    "name_ru": str(row.get("name_ru", "")),
                    "capital": str(row.get("capital", "")),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                })
            except (ValueError, TypeError):
                continue
        return records

    def get_france_regions(self) -> list[dict]:
        df = self._load_france()
        if df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "id": str(row["code"]),
                    "name": str(row["name"]),
                    "name_es": str(row.get("name_es", row["name"])),
                    "name_en": str(row.get("name_en", row["name"])),
                    "name_fr": str(row.get("name_fr", row["name"])),
                    "name_it": str(row.get("name_it", row["name"])),
                    "name_ru": str(row.get("name_ru", "")),
                    "capital": str(row.get("capital", "")),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                })
            except (ValueError, TypeError):
                continue
        return records

    def get_italy_provinces(self) -> list[dict]:
        df = self._load_italy()
        if df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "id": str(row["code"]),
                    "name": str(row["name"]),
                    "name_es": str(row.get("name_es", row["name"])),
                    "name_en": str(row.get("name_en", row["name"])),
                    "name_fr": str(row.get("name_fr", row["name"])),
                    "name_it": str(row.get("name_it", row["name"])),
                    "name_ru": str(row.get("name_ru", "")),
                    "capital": str(row.get("capital", "")),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                })
            except (ValueError, TypeError):
                continue
        return records

    def get_germany_states(self) -> list[dict]:
        df = self._load_germany()
        if df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "id": str(row["code"]),
                    "name": str(row["name"]),
                    "name_es": str(row.get("name_es", row["name"])),
                    "name_en": str(row.get("name_en", row["name"])),
                    "name_fr": str(row.get("name_fr", row["name"])),
                    "name_it": str(row.get("name_it", row["name"])),
                    "name_ru": str(row.get("name_ru", "")),
                    "capital": str(row.get("capital", "")),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                })
            except (ValueError, TypeError):
                continue
        return records

    def get_mexico_states(self) -> list[dict]:
        df = self._load_mexico()
        if df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "id": str(row["code"]),
                    "name": str(row["name"]),
                    "name_es": str(row.get("name_es", row["name"])),
                    "name_en": str(row.get("name_en", row["name"])),
                    "capital": str(row.get("capital", "")),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                })
            except (ValueError, TypeError):
                continue
        return records

    def get_argentina_provinces(self) -> list[dict]:
        df = self._load_argentina()
        if df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "id": str(row["code"]),
                    "name": str(row["name"]),
                    "name_es": str(row.get("name_es", row["name"])),
                    "name_en": str(row.get("name_en", row["name"])),
                    "capital": str(row.get("capital", "")),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                })
            except (ValueError, TypeError):
                continue
        return records

    def get_brazil_states(self) -> list[dict]:
        df = self._load_brazil()
        if df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "id": str(row["code"]),
                    "name": str(row["name"]),
                    "name_es": str(row.get("name_es", row["name"])),
                    "name_en": str(row.get("name_en", row["name"])),
                    "name_pt": str(row.get("name_pt", row["name"])),
                    "capital": str(row.get("capital", "")),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                })
            except (ValueError, TypeError):
                continue
        return records

    # ── Relief features ────────────────────────────────────────

    def _load_relief(self) -> pd.DataFrame:
        if self._relief_df is None:
            if not os.path.exists(RELIEF_CSV):
                self._relief_df = pd.DataFrame()
            else:
                self._relief_df = pd.read_csv(RELIEF_CSV, keep_default_na=False)
                # Precompute which features have GeoJSON geometry files
                geo_ids: set[str] = set()
                if os.path.isdir(RELIEF_GEOJSON_DIR):
                    geo_ids = {
                        f[:-8]  # strip ".geojson"
                        for f in os.listdir(RELIEF_GEOJSON_DIR)
                        if f.endswith(".geojson")
                    }
                self._relief_df["has_geojson"] = self._relief_df["wikidata_id"].isin(geo_ids)
        return self._relief_df

    def get_relief_features(self, feature_type: str = "all") -> list[dict]:
        df = self._load_relief()
        if df.empty:
            return []
        if feature_type and feature_type != "all":
            df = df[df["type"] == feature_type]
        records = []
        for _, row in df.iterrows():
            try:
                rec: dict[str, Any] = {
                    "id": int(row["id"]),
                    "wikidata_id": str(row["wikidata_id"]),
                    "name": str(row["name"]),
                    "name_es": str(row.get("name_es", row["name"])),
                    "name_en": str(row.get("name_en", row["name"])),
                    "name_fr": str(row.get("name_fr", row["name"])),
                    "name_it": str(row.get("name_it", row["name"])),
                    "name_ru": str(row.get("name_ru", row["name"])),
                    "type": str(row["type"]),
                    "country_codes": str(row.get("country_codes", "")),
                    "country_names_en": str(row.get("country_names_en", "")),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "continent": str(row.get("continent", "")),
                    "subcontinent": str(row.get("subcontinent", "")),
                    "has_geojson": bool(row.get("has_geojson", False)),
                    "min_zoom": int(row.get("min_zoom", 11)),
                }
                for col in ("elevation_m", "length_km", "area_km2"):
                    v = row.get(col, "")
                    rec[col] = round(float(v), 2) if v != "" else None
                records.append(rec)
            except (ValueError, TypeError):
                continue
        return records

    def get_relief_for_game(
        self,
        category: str = "all",
        continent: str = "all",
        country_filter: list[str] | None = None,
    ) -> list[dict]:
        """Return relief features filtered for the game."""
        # Category → type groups
        CATEGORY_TYPES: dict[str, list[str]] = {
            "all": [],
            "relief": ["mountain", "volcano", "mountain_range", "valley",
                        "canyon", "desert", "plateau", "plain"],
            "water": ["river", "lake", "waterfall", "glacier"],
            "coast": ["strait", "cape", "peninsula", "island"],
        }

        df = self._load_relief()
        if df.empty:
            return []

        # Filter by category
        if "," in category:
            # Multi-type custom selection (e.g. "mountain,volcano")
            types = [t.strip() for t in category.split(",") if t.strip()]
            df = df[df["type"].isin(types)]
        else:
            type_list = CATEGORY_TYPES.get(category)
            if type_list is None:
                # Single-type category (e.g. "mountain")
                df = df[df["type"] == category]
            elif type_list:
                df = df[df["type"].isin(type_list)]

        # Filter by continent
        if continent and continent != "all":
            df = df[df["subcontinent"] == continent]

        # Filter by country
        if country_filter:
            iso_set = set(country_filter)
            mask = df["country_codes"].apply(
                lambda codes: bool(set(c.strip() for c in codes.split(",") if c.strip()) & iso_set)
            )
            df = df[mask]

        records = []
        for _, row in df.iterrows():
            try:
                records.append({
                    "id": int(row["id"]),
                    "wikidata_id": str(row["wikidata_id"]),
                    "name": str(row["name"]),
                    "name_es": str(row.get("name_es", row["name"])),
                    "name_en": str(row.get("name_en", row["name"])),
                    "name_fr": str(row.get("name_fr", row["name"])),
                    "name_it": str(row.get("name_it", row["name"])),
                    "name_ru": str(row.get("name_ru", row["name"])),
                    "type": str(row["type"]),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "has_geojson": bool(row.get("has_geojson", False)),
                    "min_zoom": int(row.get("min_zoom", 11)),
                })
            except (ValueError, TypeError):
                continue
        return records

    def get_relief_game_counts(self) -> dict[str, dict[str, int]]:
        """Precompute entity counts for all relief category/continent combos."""
        df = self._load_relief()
        if df.empty:
            return {}

        CATEGORIES = {
            "all": [],
            "relief": ["mountain", "volcano", "mountain_range", "valley",
                        "canyon", "desert", "plateau", "plain"],
            "water": ["river", "lake", "waterfall", "glacier"],
            "coast": ["strait", "cape", "peninsula", "island"],
            "mountain": ["mountain"], "volcano": ["volcano"],
            "mountain_range": ["mountain_range"], "lake": ["lake"],
            "river": ["river"], "desert": ["desert"], "valley": ["valley"],
            "canyon": ["canyon"], "plateau": ["plateau"], "glacier": ["glacier"],
            "waterfall": ["waterfall"], "peninsula": ["peninsula"],
            "cape": ["cape"], "island": ["island"], "plain": ["plain"],
            "strait": ["strait"],
        }
        CONTINENTS = ["all", "europe", "asia", "africa", "north_america",
                       "central_america", "south_america", "oceania"]

        result: dict[str, dict[str, int]] = {}
        for cat, type_list in CATEGORIES.items():
            sub = df[df["type"].isin(type_list)] if type_list else df
            counts: dict[str, int] = {}
            for cont in CONTINENTS:
                if cont == "all":
                    counts[cont] = len(sub)
                else:
                    counts[cont] = int((sub["subcontinent"] == cont).sum())
            result[cat] = counts
        return result

    def get_dataset_df(self, dataset_id: str) -> pd.DataFrame:
        """Return the full DataFrame for any dataset by ID."""
        if dataset_id == "cities":
            df = self._load_cities().copy()
            if not df.empty and "geonameid" in df.columns:
                df["code"] = df["geonameid"].astype(str)
            return df
        loaders: dict[str, Any] = {
            "countries":       self._load_countries,
            "us-states":       self._load_us,
            "spain-provinces": self._load_spain,
            "russia-regions":  self._load_russia,
            "france-regions":  self._load_france,
            "italy-provinces":   self._load_italy,
            "germany-states":  self._load_germany,
            "mexico-states":   self._load_mexico,
            "argentina-provinces": self._load_argentina,
            "brazil-states":   self._load_brazil,
        }
        loader = loaders.get(dataset_id)
        return loader() if loader else pd.DataFrame()

    # ── Map game counts ───────────────────────────────────────

    def get_map_game_counts(self) -> dict:
        """Precompute entity counts for all dataset/filter combinations."""
        if self._map_game_counts is not None:
            return self._map_game_counts

        result: dict = {}

        # ── Countries ──
        df_c = self._load_countries()
        counts_c: dict[str, int] = {}
        continents_keys = ["all"] + list(CONTINENT_MAP.keys())
        entity_types = ["all", "country", "territory"]

        for cont_key in continents_keys:
            cont_values = CONTINENT_MAP.get(cont_key)
            df_cont = df_c[df_c["continent"].isin(cont_values)] if cont_values else df_c
            for et in entity_types:
                df_et = df_cont if et == "all" else df_cont[df_cont["entity_type"] == et]
                counts_c[cont_key + "_" + et] = int(len(df_et))
        result["countries"] = counts_c

        # ── Cities ──
        df_cities = self._load_cities()
        df_countries_for_join = self._load_countries()
        iso3_continent: dict[str, str] = {}
        if not df_countries_for_join.empty:
            for _, row in df_countries_for_join[["iso_a3", "continent"]].iterrows():
                iso3_continent[str(row["iso_a3"])] = str(row["continent"])

        if not df_countries_for_join.empty:
            _country_iso = set(df_countries_for_join[df_countries_for_join["entity_type"] == "country"]["iso_a3"].tolist())
            _territory_iso = set(df_countries_for_join[df_countries_for_join["entity_type"] == "territory"]["iso_a3"].tolist())
        else:
            _country_iso, _territory_iso = set(), set()

        city_filters_fns: dict = {
            "capitals":           lambda df: df[df["is_capital"] == True],   # noqa: E712
            "capitals_country":   lambda df, _c=_country_iso: df[(df["is_capital"] == True) & (df["iso_a3"].isin(_c))],   # noqa: E712
            "capitals_territory": lambda df, _t=_territory_iso: df[(df["is_capital"] == True) & (df["iso_a3"].isin(_t))],  # noqa: E712
            "5m":                 lambda df: df[df["population"] >= 5_000_000],
            "1m":                 lambda df: df[df["population"] >= 1_000_000],
            "500k":               lambda df: df[df["population"] >= 500_000],
            "200k":               lambda df: df[df["population"] >= 200_000],
            "100k":               lambda df: df[df["population"] >= 100_000],
            "50k":                lambda df: df[df["population"] >= 50_000],
        }
        counts_cities: dict[str, int] = {}
        for cf_key, cf_fn in city_filters_fns.items():
            df_cf = cf_fn(df_cities)
            for cont_key in continents_keys:
                cont_values = CONTINENT_MAP.get(cont_key)
                if cont_values:
                    iso_set = {iso for iso, cont in iso3_continent.items() if cont in cont_values}
                    df_cont = df_cf[df_cf["iso_a3"].isin(iso_set)]
                else:
                    df_cont = df_cf
                counts_cities[cf_key + "_" + cont_key] = int(len(df_cont))
        result["cities"] = counts_cities

        # ── Sub-nationals ──
        df_us = self._load_us()
        result["us-states"] = {"all": int(len(df_us)) if not df_us.empty else 0}
        df_spain = self._load_spain()
        result["spain-provinces"] = {"all": int(len(df_spain)) if not df_spain.empty else 0}
        df_russia = self._load_russia()
        result["russia-regions"] = {"all": int(len(df_russia)) if not df_russia.empty else 0}
        df_france = self._load_france()
        result["france-regions"] = {"all": int(len(df_france)) if not df_france.empty else 0}
        df_italy = self._load_italy()
        result["italy-provinces"] = {"all": int(len(df_italy)) if not df_italy.empty else 0}
        df_germany = self._load_germany()
        result["germany-states"] = {"all": int(len(df_germany)) if not df_germany.empty else 0}
        df_mexico = self._load_mexico()
        result["mexico-states"] = {"all": int(len(df_mexico)) if not df_mexico.empty else 0}
        df_argentina = self._load_argentina()
        result["argentina-provinces"] = {"all": int(len(df_argentina)) if not df_argentina.empty else 0}
        df_brazil = self._load_brazil()
        result["brazil-states"] = {"all": int(len(df_brazil)) if not df_brazil.empty else 0}

        self._map_game_counts = result
        return result

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

    # ── Relief editing ──────────────────────────────────────────

    def create_relief_feature(self, data: dict) -> dict:
        """Create a new relief feature, append to CSV, optionally save GeoJSON."""
        import csv as csv_mod

        df = self._load_relief()
        next_id = int(df["id"].max()) + 1 if not df.empty else 1
        wikidata_id = f"U{next_id}"

        new_row = {
            "id": next_id,
            "wikidata_id": wikidata_id,
            "name": data["name"],
            "name_es": data.get("name_es", ""),
            "name_en": data.get("name_en", ""),
            "name_fr": data.get("name_fr", ""),
            "name_it": data.get("name_it", ""),
            "name_ru": data.get("name_ru", ""),
            "type": data["type"],
            "country_codes": data.get("country_codes", ""),
            "country_names_en": "",
            "lat": data["lat"],
            "lon": data["lon"],
            "elevation_m": data.get("elevation_m") or "",
            "length_km": data.get("length_km") or "",
            "area_km2": data.get("area_km2") or "",
            "sitelinks": 0,
            "continent": "",
            "subcontinent": "",
            "min_zoom": 11,
        }

        with open(RELIEF_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv_mod.DictWriter(f, fieldnames=list(new_row.keys()))
            writer.writerow(new_row)

        has_geojson = False
        if data.get("geojson"):
            self.save_relief_geojson(wikidata_id, data["geojson"])
            has_geojson = True

        self._relief_df = None  # invalidate cache

        result = dict(new_row)
        result["has_geojson"] = has_geojson
        return result

    def save_relief_geojson(self, wikidata_id: str, geojson: dict) -> bool:
        """Save GeoJSON geometry to a file for the given wikidata_id."""
        import json as json_mod

        df = self._load_relief()
        if df[df["wikidata_id"] == wikidata_id].empty:
            return False

        if geojson.get("type") in ("Point", "LineString", "Polygon",
                                    "MultiPoint", "MultiLineString", "MultiPolygon"):
            feature = {
                "type": "Feature",
                "geometry": geojson,
                "properties": {"wikidata_id": wikidata_id},
            }
        else:
            feature = geojson

        os.makedirs(RELIEF_GEOJSON_DIR, exist_ok=True)
        filepath = os.path.join(RELIEF_GEOJSON_DIR, f"{wikidata_id}.geojson")
        with open(filepath, "w", encoding="utf-8") as f:
            json_mod.dump(feature, f, ensure_ascii=False)

        self._relief_df = None  # invalidate cache
        return True

    def update_relief_feature(self, wikidata_id: str, updates: dict) -> dict | None:
        """Update an existing relief feature in the CSV. Returns updated record or None."""
        import csv as csv_mod

        df = self._load_relief()
        mask = df["wikidata_id"] == wikidata_id
        if not mask.any():
            return None

        # Handle geojson separately
        geojson = updates.pop("geojson", None)
        if geojson:
            self.save_relief_geojson(wikidata_id, geojson)

        # Update CSV columns
        csv_cols = [
            "name", "type", "lat", "lon",
            "name_es", "name_en", "name_fr", "name_it", "name_ru",
            "country_codes", "elevation_m", "length_km", "area_km2",
        ]
        for col in csv_cols:
            if col in updates:
                df.loc[mask, col] = updates[col]

        # Rewrite CSV (without has_geojson which is computed)
        write_df = df.drop(columns=["has_geojson"], errors="ignore")
        write_df.to_csv(RELIEF_CSV, index=False)

        self._relief_df = None  # invalidate cache

        # Return updated record in API format
        row = self._load_relief()[mask].iloc[0]
        rec: dict[str, Any] = {
            "id": int(row["id"]),
            "wikidata_id": str(row["wikidata_id"]),
            "name": str(row["name"]),
            "name_es": str(row.get("name_es", row["name"])),
            "name_en": str(row.get("name_en", row["name"])),
            "name_fr": str(row.get("name_fr", row["name"])),
            "name_it": str(row.get("name_it", row["name"])),
            "name_ru": str(row.get("name_ru", row["name"])),
            "type": str(row["type"]),
            "country_codes": str(row.get("country_codes", "")),
            "country_names_en": str(row.get("country_names_en", "")),
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "continent": str(row.get("continent", "")),
            "subcontinent": str(row.get("subcontinent", "")),
            "has_geojson": bool(row.get("has_geojson", False)),
            "min_zoom": int(row.get("min_zoom", 11)),
        }
        for col in ("elevation_m", "length_km", "area_km2"):
            v = row.get(col, "")
            rec[col] = round(float(v), 2) if v != "" else None
        return rec
