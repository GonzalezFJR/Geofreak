"""Quiz engine — generates question sets for ordering & comparison games."""

import random
from typing import Optional

import pandas as pd

from services.dataset import DatasetService

_ds = DatasetService()

# Stats available for quiz games, with display info
QUIZ_STATS: dict[str, dict] = {
    "population":         {"label_es": "Población",            "label_en": "Population",          "unit": "",       "format": "int"},
    "area_km2":           {"label_es": "Superficie (km²)",     "label_en": "Area (km²)",          "unit": "km²",    "format": "int"},
    "density_per_km2":    {"label_es": "Densidad (hab/km²)",   "label_en": "Density (pop/km²)",   "unit": "hab/km²","format": "float1"},
    "gdp_usd":            {"label_es": "PIB (USD)",            "label_en": "GDP (USD)",           "unit": "USD",    "format": "money"},
    "gdp_per_capita_usd": {"label_es": "PIB per cápita (USD)", "label_en": "GDP per capita (USD)","unit": "USD",    "format": "money"},
    "life_expectancy":    {"label_es": "Esperanza de vida",    "label_en": "Life expectancy",     "unit": "años",   "format": "float1"},
    "hdi":                {"label_es": "IDH",                  "label_en": "HDI",                 "unit": "",       "format": "float3"},
    "gini":               {"label_es": "Índice Gini",          "label_en": "Gini index",          "unit": "",       "format": "float1"},
    "co2_per_capita":     {"label_es": "CO₂ per cápita",      "label_en": "CO₂ per capita",      "unit": "t",      "format": "float1"},
    "birth_rate":         {"label_es": "Natalidad (‰)",        "label_en": "Birth rate (‰)",      "unit": "‰",      "format": "float1"},
    "urban_population_pct":{"label_es": "Población urbana (%)", "label_en": "Urban population (%)", "unit": "%",     "format": "float1"},
}

STAT_KEYS = list(QUIZ_STATS.keys())


def _get_valid_countries(stat: str, continent: Optional[str] = None) -> list[dict]:
    """Return countries that have a valid numeric value for the given stat."""
    df = _ds.get_countries()
    if df.empty:
        return []

    # Filter continent
    if continent and continent != "all":
        continent_map = {
            "europe": ["Europe"],
            "asia": ["Asia"],
            "africa": ["Africa"],
            "america": ["North America", "South America"],
            "oceania": ["Oceania"],
        }
        allowed = continent_map.get(continent, [])
        if allowed:
            df = df[df["continent"].isin(allowed)]

    # Keep rows with valid stat
    if stat not in df.columns:
        return []

    df = df[df[stat].notna()]
    df = df[df[stat] != ""]

    records = []
    for _, row in df.iterrows():
        try:
            val = float(row[stat])
        except (ValueError, TypeError):
            continue
        records.append({
            "iso_a3": row["iso_a3"],
            "name": row["name"],
            "flag_emoji": row.get("flag_emoji", ""),
            "continent": row.get("continent", ""),
            "stat_value": val,
        })
    return records


def generate_ordering_question(
    stat: Optional[str] = None,
    continent: Optional[str] = None,
    count: int = 5,
    ascending: Optional[bool] = None,
) -> Optional[dict]:
    """Generate one ordering question: sort N countries by a stat.

    Returns:
        {
            "stat": "population",
            "stat_info": { "label_es": ..., "unit": ... },
            "ascending": False,
            "countries": [ { "iso_a3", "name", "flag_emoji" }, ... ],  # shuffled
            "correct_order": [ "CHN", "IND", "USA", "IDN", "BRA" ],   # iso_a3 in correct order
        }
    """
    if stat is None:
        stat = random.choice(STAT_KEYS)
    if ascending is None:
        ascending = random.choice([True, False])

    countries = _get_valid_countries(stat, continent)
    if len(countries) < count:
        return None

    sample = random.sample(countries, count)
    sorted_sample = sorted(sample, key=lambda c: c["stat_value"], reverse=not ascending)
    correct_order = [c["iso_a3"] for c in sorted_sample]

    # Shuffle for the player
    display = [{"iso_a3": c["iso_a3"], "name": c["name"], "flag_emoji": c["flag_emoji"]} for c in sample]
    random.shuffle(display)

    return {
        "stat": stat,
        "stat_info": QUIZ_STATS[stat],
        "ascending": ascending,
        "countries": display,
        "correct_order": correct_order,
        "correct_values": {c["iso_a3"]: c["stat_value"] for c in sorted_sample},
    }


def generate_comparison_question(
    stat: Optional[str] = None,
    continent: Optional[str] = None,
) -> Optional[dict]:
    """Generate one comparison question: which of 2 countries has a higher stat?

    Returns:
        {
            "stat": "population",
            "stat_info": { ... },
            "countries": [ { iso_a3, name, flag_emoji }, { ... } ],
            "correct_iso": "CHN",
            "values": { "CHN": 1400000000, "IND": 1380000000 },
        }
    """
    if stat is None:
        stat = random.choice(STAT_KEYS)

    countries = _get_valid_countries(stat, continent)
    if len(countries) < 2:
        return None

    pair = random.sample(countries, 2)
    pair.sort(key=lambda c: c["stat_value"], reverse=True)

    return {
        "stat": stat,
        "stat_info": QUIZ_STATS[stat],
        "countries": [
            {"iso_a3": c["iso_a3"], "name": c["name"], "flag_emoji": c["flag_emoji"]}
            for c in pair
        ],
        "correct_iso": pair[0]["iso_a3"],
        "values": {c["iso_a3"]: c["stat_value"] for c in pair},
    }


def generate_ordering_set(
    num_questions: int = 10,
    continent: Optional[str] = None,
) -> list[dict]:
    """Generate a full set of ordering questions with varied stats."""
    questions = []
    used_stats = []
    for _ in range(num_questions):
        if not used_stats:
            used_stats = STAT_KEYS.copy()
            random.shuffle(used_stats)
        q = None
        attempts = 0
        while q is None and attempts < len(STAT_KEYS):
            stat = used_stats.pop() if used_stats else random.choice(STAT_KEYS)
            q = generate_ordering_question(stat=stat, continent=continent)
            attempts += 1
        if q:
            questions.append(q)
    return questions


def generate_comparison_set(
    num_questions: int = 10,
    continent: Optional[str] = None,
) -> list[dict]:
    """Generate a full set of comparison questions with varied stats."""
    questions = []
    used_stats = []
    for _ in range(num_questions):
        if not used_stats:
            used_stats = STAT_KEYS.copy()
            random.shuffle(used_stats)
        q = None
        attempts = 0
        while q is None and attempts < len(STAT_KEYS):
            stat = used_stats.pop() if used_stats else random.choice(STAT_KEYS)
            q = generate_comparison_question(stat=stat, continent=continent)
            attempts += 1
        if q:
            questions.append(q)
    return questions


def get_available_stats() -> dict:
    """Return stats metadata for the frontend."""
    return QUIZ_STATS
