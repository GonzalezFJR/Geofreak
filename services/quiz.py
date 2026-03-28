"""Quiz engine — generates question sets for ordering & comparison games."""

import json
import os
import random
from typing import Optional

import pandas as pd

from services.dataset import DatasetService

_ds = DatasetService()

# ── Variable config loader ───────────────────────────────────────────────

_VAR_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "static", "data", "variable_config.json"
)
_var_config_cache: dict | None = None


def _load_var_config() -> dict:
    global _var_config_cache
    if _var_config_cache is None:
        with open(_VAR_CONFIG_PATH, "r", encoding="utf-8") as f:
            _var_config_cache = json.load(f)
    return _var_config_cache


def reload_var_config():
    """Force-reload the config (called after admin edits)."""
    global _var_config_cache
    _var_config_cache = None


def _build_quiz_stats(dataset_id: str = "countries") -> dict[str, dict]:
    """Build QUIZ_STATS dict from enabled variables in variable_config.json."""
    cfg = _load_var_config()
    ds = cfg.get("datasets", {}).get(dataset_id, {})
    stats: dict[str, dict] = {}
    for v in ds.get("variables", []):
        if v.get("enabled"):
            stats[v["key"]] = {
                "label_es": v["label_es"],
                "label_en": v["label_en"],
                "label_fr": v.get("label_fr", v["label_en"]),
                "label_it": v.get("label_it", v["label_en"]),
                "label_ru": v.get("label_ru", v["label_en"]),
                "description_es": v.get("description_es", ""),
                "description_en": v.get("description_en", ""),
                "unit": v["unit"],
                "format": v["format"],
            }
    return stats


def get_quiz_stats() -> dict[str, dict]:
    return _build_quiz_stats()


STAT_KEYS_FUNC = lambda: list(_build_quiz_stats().keys())


def _get_valid_countries(stat: str, continent: Optional[str] = None) -> list[dict]:
    """Return countries that have a valid numeric value for the given stat.
    Excludes territories (entity_type != 'country')."""
    df = _ds.get_countries()
    if df.empty:
        return []

    # Filter only sovereign countries
    if "entity_type" in df.columns:
        df = df[df["entity_type"] == "country"]

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
            "name_es": row.get("name_es", row["name"]),
            "name_fr": row.get("name_fr", ""),
            "name_it": row.get("name_it", ""),
            "name_ru": row.get("name_ru", ""),
            "flag_emoji": row.get("flag_emoji", ""),
            "continent": row.get("continent", ""),
            "stat_value": val,
        })
    return records


def _pick_by_difficulty(
    reference_value: float,
    candidates: list[dict],
    difficulty: str,
) -> Optional[dict]:
    """Pick a country from *candidates* relative to *reference_value* using difficulty rules.

    Difficulty percentile bands (by distance to reference):
        easy       → farthest 75 %
        normal     → any (random)
        hard       → closest 50 %
        very_hard  → closest 25 %
        extreme    → closest 10 %
    """
    if not candidates:
        return None
    if difficulty == "normal":
        return random.choice(candidates)

    ranked = sorted(candidates, key=lambda c: abs(c["stat_value"] - reference_value))
    n = len(ranked)

    if difficulty == "easy":
        start = max(1, int(n * 0.25))
        pool = ranked[start:]
    elif difficulty == "hard":
        pool = ranked[: max(1, int(n * 0.50))]
    elif difficulty == "very_hard":
        pool = ranked[: max(1, int(n * 0.25))]
    elif difficulty == "extreme":
        pool = ranked[: max(1, int(n * 0.10))]
    else:
        pool = ranked

    return random.choice(pool) if pool else random.choice(candidates)


def generate_ordering_question(
    stat: Optional[str] = None,
    continent: Optional[str] = None,
    count: int = 5,
    ascending: Optional[bool] = None,
    difficulty: str = "normal",
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
    quiz_stats = get_quiz_stats()
    stat_keys = list(quiz_stats.keys())
    if stat is None:
        stat = random.choice(stat_keys)
    if ascending is None:
        ascending = random.choice([True, False])

    countries = _get_valid_countries(stat, continent)
    if len(countries) < count:
        return None

    # Difficulty-aware sequential selection
    chosen_isos: set[str] = set()
    sample: list[dict] = []

    first = random.choice(countries)
    sample.append(first)
    chosen_isos.add(first["iso_a3"])

    for _ in range(count - 1):
        prev = sample[-1]
        pool = [c for c in countries if c["iso_a3"] not in chosen_isos]
        if not pool:
            break
        pick = _pick_by_difficulty(prev["stat_value"], pool, difficulty)
        if pick is None:
            break
        sample.append(pick)
        chosen_isos.add(pick["iso_a3"])

    if len(sample) < count:
        return None

    sorted_sample = sorted(sample, key=lambda c: c["stat_value"], reverse=not ascending)
    correct_order = [c["iso_a3"] for c in sorted_sample]

    # Shuffle for the player
    display = [{"iso_a3": c["iso_a3"], "name": c["name"], "name_es": c["name_es"], "name_fr": c["name_fr"], "name_it": c["name_it"], "name_ru": c["name_ru"], "flag_emoji": c["flag_emoji"]} for c in sample]
    random.shuffle(display)

    return {
        "stat": stat,
        "stat_info": quiz_stats[stat],
        "ascending": ascending,
        "countries": display,
        "correct_order": correct_order,
        "correct_values": {c["iso_a3"]: c["stat_value"] for c in sorted_sample},
    }


def generate_comparison_question(
    stat: Optional[str] = None,
    continent: Optional[str] = None,
    difficulty: str = "normal",
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
    quiz_stats = get_quiz_stats()
    stat_keys = list(quiz_stats.keys())
    if stat is None:
        stat = random.choice(stat_keys)

    countries = _get_valid_countries(stat, continent)
    if len(countries) < 2:
        return None

    first = random.choice(countries)
    pool = [c for c in countries if c["iso_a3"] != first["iso_a3"]]
    if not pool:
        return None

    second = _pick_by_difficulty(first["stat_value"], pool, difficulty)
    if second is None:
        return None

    pair = [first, second]
    pair.sort(key=lambda c: c["stat_value"], reverse=True)

    return {
        "stat": stat,
        "stat_info": quiz_stats[stat],
        "countries": [
            {"iso_a3": c["iso_a3"], "name": c["name"], "name_es": c["name_es"], "name_fr": c["name_fr"], "name_it": c["name_it"], "name_ru": c["name_ru"], "flag_emoji": c["flag_emoji"]}
            for c in pair
        ],
        "correct_iso": pair[0]["iso_a3"],
        "values": {c["iso_a3"]: c["stat_value"] for c in pair},
    }


def generate_ordering_set(
    num_questions: int = 10,
    continent: Optional[str] = None,
    difficulty: str = "normal",
) -> list[dict]:
    """Generate a full set of ordering questions with varied stats."""
    stat_keys = STAT_KEYS_FUNC()
    questions = []
    used_stats = []
    for _ in range(num_questions):
        if not used_stats:
            used_stats = stat_keys.copy()
            random.shuffle(used_stats)
        q = None
        attempts = 0
        while q is None and attempts < len(stat_keys):
            stat = used_stats.pop() if used_stats else random.choice(stat_keys)
            q = generate_ordering_question(stat=stat, continent=continent, difficulty=difficulty)
            attempts += 1
        if q:
            questions.append(q)
    return questions


def generate_comparison_set(
    num_questions: int = 10,
    continent: Optional[str] = None,
    difficulty: str = "normal",
) -> list[dict]:
    """Generate a full set of comparison questions with varied stats."""
    stat_keys = STAT_KEYS_FUNC()
    questions = []
    used_stats = []
    for _ in range(num_questions):
        if not used_stats:
            used_stats = stat_keys.copy()
            random.shuffle(used_stats)
        q = None
        attempts = 0
        while q is None and attempts < len(stat_keys):
            stat = used_stats.pop() if used_stats else random.choice(stat_keys)
            q = generate_comparison_question(stat=stat, continent=continent, difficulty=difficulty)
            attempts += 1
        if q:
            questions.append(q)
    return questions


# ── GeoStats game ────────────────────────────────────────────────────────────

def generate_geostats_question(
    stat: Optional[str] = None,
    continent: Optional[str] = None,
) -> Optional[dict]:
    """Generate one geostats question: guess a country from its position on a stat curve.

    Returns:
        {
            "stat": "population",
            "stat_info": { ... },
            "curve": [val0, val1, ...],          # sorted ascending
            "positions": { "ESP": 45, ... },      # iso -> index in curve
            "target_iso": "ESP",
            "target_index": 45,
        }
    """
    quiz_stats = get_quiz_stats()
    stat_keys = list(quiz_stats.keys())
    if stat is None:
        stat = random.choice(stat_keys)

    countries = _get_valid_countries(stat, continent)
    if len(countries) < 20:
        return None

    countries.sort(key=lambda c: c["stat_value"])
    target = random.choice(countries)
    target_index = countries.index(target)

    curve = [c["stat_value"] for c in countries]
    positions = {c["iso_a3"]: i for i, c in enumerate(countries)}

    return {
        "stat": stat,
        "stat_info": quiz_stats[stat],
        "curve": curve,
        "positions": positions,
        "target_iso": target["iso_a3"],
        "target_index": target_index,
    }


def generate_geostats_set(
    num_questions: int = 10,
    continent: Optional[str] = None,
    max_attempts: int = 5,
) -> dict:
    """Generate a full geostats game with a countries lookup and N questions."""
    # Build countries lookup once (all sovereign countries)
    df = _ds.get_countries()
    if df.empty:
        return {"countries_lookup": {}, "max_attempts": max_attempts, "questions": []}
    if "entity_type" in df.columns:
        df = df[df["entity_type"] == "country"]

    countries_lookup: dict[str, dict] = {}
    for _, row in df.iterrows():
        countries_lookup[row["iso_a3"]] = {
            "name": row.get("name", ""),
            "name_es": row.get("name_es", row.get("name", "")),
            "name_fr": row.get("name_fr", ""),
            "name_it": row.get("name_it", ""),
            "name_ru": row.get("name_ru", ""),
            "flag_emoji": row.get("flag_emoji", ""),
        }

    # Generate questions with varied stats
    stat_keys = STAT_KEYS_FUNC()
    questions: list[dict] = []
    used_stats: list[str] = []
    for _ in range(num_questions):
        if not used_stats:
            used_stats = stat_keys.copy()
            random.shuffle(used_stats)
        q = None
        attempts = 0
        while q is None and attempts < len(stat_keys):
            stat = used_stats.pop() if used_stats else random.choice(stat_keys)
            q = generate_geostats_question(stat=stat, continent=continent)
            attempts += 1
        if q:
            questions.append(q)

    return {
        "countries_lookup": countries_lookup,
        "max_attempts": max_attempts,
        "questions": questions,
    }


def get_available_stats() -> dict:
    """Return stats metadata for the frontend."""
    return get_quiz_stats()


def get_all_variables(dataset_id: str | None = None) -> list[dict]:
    """Return all variable definitions (enabled and disabled).
    If dataset_id is None, return variables for all datasets as a flat list.
    """
    cfg = _load_var_config()
    if dataset_id:
        ds = cfg.get("datasets", {}).get(dataset_id, {})
        return ds.get("variables", [])
    # Flatten all datasets
    all_vars = []
    for ds in cfg.get("datasets", {}).values():
        all_vars.extend(ds.get("variables", []))
    return all_vars


def get_datasets() -> dict:
    """Return datasets metadata (without full variable details)."""
    cfg = _load_var_config()
    return cfg.get("datasets", {})


def get_sources() -> list[dict]:
    """Return all data sources."""
    cfg = _load_var_config()
    return cfg.get("sources", [])


def toggle_variable(key: str, enabled: bool, dataset_id: str = "countries"):
    """Enable or disable a variable and save to config."""
    cfg = _load_var_config()
    ds = cfg.get("datasets", {}).get(dataset_id, {})
    for v in ds.get("variables", []):
        if v["key"] == key:
            v["enabled"] = enabled
            break
    with open(_VAR_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    reload_var_config()
