"""JSON API endpoints for datasets, quizzes, and match results."""

import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.auth import get_current_user, get_optional_user
from services.dataset import DatasetService
from services.geodata import GeodataService
from services.quiz import (
    generate_ordering_set,
    generate_comparison_set,
    generate_geostats_set,
    get_available_stats,
)
from services.matches import create_match, finish_match, save_match_player
from services.user_stats import record_match_result, get_user_stats, ensure_user_stats
from services.analytics import track
from services.daily_challenge import get_daily_challenge, get_user_daily_result, save_user_daily_result
from services.leaderboards import get_leaderboard, get_user_position, rebuild_all_leaderboards, GAME_TYPES
from services.scoring import (
    process_ranked_attempt,
    get_records,
    get_user_attempts,
    get_user_test_ratings,
    build_test_key,
    ALL_GAME_TYPES as SCORING_GAME_TYPES,
)
from services.rankings import (
    get_game_ranking,
    get_season_ranking,
    get_weekly_ranking,
    get_user_game_ranking,
    get_user_ranking_position,
    rebuild_all_rankings,
)
from services.daily_rankings import (
    save_daily_score,
    get_daily_day_ranking,
    get_daily_monthly_ranking,
    get_daily_absolute_ranking,
    get_user_daily_ranking_position,
    get_user_daily_scores,
    rebuild_all_daily_rankings,
    rebuild_daily_ranking,
)

router = APIRouter(tags=["api"])

dataset_service = DatasetService()
geodata_service = GeodataService()


@router.get("/countries")
async def list_countries(
    search: Optional[str] = Query(None, description="Search by name"),
    region: Optional[str] = Query(None, description="Filter by region"),
):
    """Return list of countries with basic info."""
    df = dataset_service.get_countries()
    if search:
        mask = df["name"].str.contains(search, case=False, na=False)
        df = df[mask]
    if region:
        mask = df["region"].str.contains(region, case=False, na=False)
        df = df[mask]
    # Return all columns for the map viewer
    return df.to_dict(orient="records")


@router.get("/countries/{iso_code}")
async def get_country(iso_code: str):
    """Return full data for a single country."""
    country = dataset_service.get_country(iso_code.upper())
    if country is None:
        raise HTTPException(status_code=404, detail="Country not found")
    return country


@router.get("/geojson/all")
async def get_all_geojson():
    """Return combined GeoJSON FeatureCollection of all countries."""
    data = geodata_service.get_all_geojson()
    return JSONResponse(content=data)


@router.get("/geojson/simple")
async def get_simple_geojson():
    """Return simplified (lightweight) GeoJSON for game maps."""
    data = geodata_service.get_simple_geojson()
    return JSONResponse(content=data)


@router.get("/geojson/{iso_code}")
async def get_country_geojson(iso_code: str):
    """Return GeoJSON for a single country."""
    data = geodata_service.get_country_geojson(iso_code.upper())
    if data is None:
        raise HTTPException(status_code=404, detail="GeoJSON not found")
    return JSONResponse(content=data)


@router.get("/relief-features")
async def get_relief_features(
    feature_type: str = Query("all", description="Filter by type: mountain, volcano, lake, river, etc."),
):
    """Return relief/landform features for the map viewer."""
    return dataset_service.get_relief_features(feature_type=feature_type)


class ReliefFeatureCreate(BaseModel):
    name: str
    type: str
    lat: float
    lon: float
    name_es: str = ""
    name_en: str = ""
    name_fr: str = ""
    name_it: str = ""
    name_ru: str = ""
    country_codes: str = ""
    elevation_m: float | None = None
    length_km: float | None = None
    area_km2: float | None = None
    geojson: dict | None = None


@router.post("/relief-features")
async def create_relief_feature(payload: ReliefFeatureCreate):
    """Create a new relief feature. Appends to CSV and optionally saves GeoJSON."""
    return dataset_service.create_relief_feature(payload.model_dump())


class ReliefFeatureUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    lat: float | None = None
    lon: float | None = None
    name_es: str | None = None
    name_en: str | None = None
    name_fr: str | None = None
    name_it: str | None = None
    name_ru: str | None = None
    country_codes: str | None = None
    elevation_m: float | None = None
    length_km: float | None = None
    area_km2: float | None = None
    geojson: dict | None = None


@router.put("/relief-features/{wikidata_id}")
async def update_relief_feature(wikidata_id: str, payload: ReliefFeatureUpdate):
    """Update an existing relief feature's properties."""
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = dataset_service.update_relief_feature(wikidata_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    return result


class GeojsonAssociate(BaseModel):
    geojson: dict


@router.post("/relief-features/{wikidata_id}/geojson")
async def associate_geojson(wikidata_id: str, payload: GeojsonAssociate):
    """Associate a GeoJSON geometry with an existing relief feature."""
    success = dataset_service.save_relief_geojson(wikidata_id, payload.geojson)
    if not success:
        raise HTTPException(status_code=404, detail="Feature not found")
    return {"status": "ok", "wikidata_id": wikidata_id}


@router.get("/relief-game/data")
async def relief_game_data(
    category: str = Query("all", description="Category: all|relief|water|coast or single type"),
    continent: str = Query("all", description="Continent filter"),
    country_filter: str = Query("", description="Comma-separated ISO3 codes"),
    count_only: bool = Query(False, description="Return only the count"),
):
    """Return relief features filtered for the game."""
    cf = [c.strip().upper() for c in country_filter.split(",") if c.strip()] if country_filter else None
    features = dataset_service.get_relief_for_game(
        category=category, continent=continent, country_filter=cf,
    )
    if count_only:
        return {"count": len(features)}
    return features


@router.get("/cities")
async def get_cities(
    min_population: int = Query(0, description="Minimum population filter"),
    capitals_only: bool = Query(False, description="Only return capitals"),
):
    """Return cities for map markers.

    Supports filtering by minimum population and capitals-only mode.
    Capitals are always included regardless of the population filter.
    """
    cities = dataset_service.get_cities(
        min_population=min_population,
        capitals_only=capitals_only,
    )
    return cities


@router.get("/cities/tier/{tier}")
async def get_cities_tier(tier: int):
    """Return cities for a specific population tier (map display).

    Tiers:
      1 = Capitals + 5M+
      2 = 1M-5M
      3 = 500K-1M
      4 = 100K-500K
      5 = 50K-100K
    """
    if tier < 1 or tier > 5:
        raise HTTPException(status_code=400, detail="Tier must be 1-5")
    return dataset_service.get_cities_for_tier(tier)


@router.get("/cities/{iso_code}")
async def get_country_cities(iso_code: str):
    """Return all cities for a specific country."""
    cities = dataset_service.get_cities_by_country(iso_code.upper())
    if not cities:
        raise HTTPException(status_code=404, detail="No cities found for this country")
    return cities


# ── Map-game endpoints ───────────────────────────────────────────────────────

@router.get("/map-game/data")
async def map_game_data(
    dataset: str = Query("countries", description="Dataset: countries|cities|us-states|spain-provinces|russia-regions"),
    continent: str = Query("all", description="Continent filter (countries/cities only)"),
    entity_type: str = Query("all", description="Entity type filter (countries only): all|country|territory"),
    city_filter: str = Query("capitals", description="City filter: capitals|5m|1m|500k|200k|100k"),
    country_filter: str = Query("", description="Comma-separated iso_a3 codes to filter cities by country"),
    count_only: bool = Query(False, description="Return only the count"),
):
    """Return entity list for the map game based on dataset and filters."""
    if dataset == "countries":
        result = dataset_service.get_countries_for_map(continent=continent, entity_type=entity_type)
    elif dataset == "cities":
        cf_list = [c.strip().upper() for c in country_filter.split(",") if c.strip()] if country_filter else None
        result = dataset_service.get_cities_for_map(city_filter=city_filter, continent=continent, country_filter=cf_list)
    elif dataset == "us-states":
        result = dataset_service.get_us_states()
    elif dataset == "spain-provinces":
        result = dataset_service.get_spain_provinces()
    elif dataset == "russia-regions":
        result = dataset_service.get_russia_regions()
    elif dataset == "france-regions":
        result = dataset_service.get_france_regions()
    elif dataset == "italy-provinces":
        result = dataset_service.get_italy_provinces()
    elif dataset == "germany-states":
        result = dataset_service.get_germany_states()
    elif dataset == "mexico-states":
        result = dataset_service.get_mexico_states()
    elif dataset == "argentina-provinces":
        result = dataset_service.get_argentina_provinces()
    elif dataset == "brazil-states":
        result = dataset_service.get_brazil_states()
    else:
        raise HTTPException(status_code=400, detail="Unknown dataset")
    if count_only:
        return {"count": len(result)}
    return result


@router.get("/map-game/geojson")
async def map_game_geojson(
    dataset: str = Query("countries", description="Dataset: countries|us-states|spain-provinces|russia-regions"),
):
    """Return GeoJSON for the map game (polygon-based datasets only)."""
    if dataset == "countries":
        data = geodata_service.get_simple_geojson()
    elif dataset in ("us-states", "spain-provinces", "russia-regions",
                     "france-regions", "italy-provinces", "germany-states",
                     "mexico-states", "argentina-provinces", "brazil-states"):
        data = geodata_service.get_subnational_geojson(dataset)
    else:
        raise HTTPException(status_code=400, detail="No GeoJSON for dataset: " + dataset)
    return JSONResponse(content=data)


# ── Quiz endpoints ───────────────────────────────────────────────────────────

@router.get("/quiz/stats")
async def quiz_stats():
    """Return available stats for quiz games."""
    return get_available_stats()


@router.get("/quiz/ordering")
async def quiz_ordering(
    num: int = Query(10, ge=1, le=20),
    continent: Optional[str] = Query(None),
    difficulty: str = Query("normal"),
    dataset: str = Query("countries"),
    entity_type: str = Query("all"),
    country_filter: str = Query(""),
):
    """Generate a set of ordering questions."""
    if difficulty not in ("easy", "normal", "hard", "very_hard", "extreme"):
        difficulty = "normal"
    cf = country_filter.strip() or None
    questions = generate_ordering_set(
        num_questions=num, continent=continent, difficulty=difficulty, dataset=dataset, country_filter=cf
    )
    if not questions:
        raise HTTPException(status_code=400, detail="Not enough data for quiz")
    return {"questions": questions}


@router.get("/quiz/comparison")
async def quiz_comparison(
    num: int = Query(10, ge=1, le=30),
    continent: Optional[str] = Query(None),
    difficulty: str = Query("normal"),
    dataset: str = Query("countries"),
    entity_type: str = Query("all"),
    country_filter: str = Query(""),
):
    """Generate a set of comparison questions."""
    if difficulty not in ("easy", "normal", "hard", "very_hard", "extreme"):
        difficulty = "normal"
    cf = country_filter.strip() or None
    questions = generate_comparison_set(
        num_questions=num, continent=continent, difficulty=difficulty, dataset=dataset, country_filter=cf
    )
    if not questions:
        raise HTTPException(status_code=400, detail="Not enough data for quiz")
    return {"questions": questions}


@router.get("/quiz/geostats")
async def quiz_geostats(
    num: int = Query(10, ge=1, le=20),
    continent: Optional[str] = Query(None),
    dataset: str = Query("countries"),
    entity_type: str = Query("all"),
    country_filter: str = Query(""),
):
    """Generate a set of geostats questions (guess entity from stat curve)."""
    cf = country_filter.strip() or None
    data = generate_geostats_set(num_questions=num, continent=continent, dataset=dataset, country_filter=cf)
    if not data or not data.get("questions"):
        raise HTTPException(status_code=400, detail="Not enough data for quiz")
    return data


@router.get("/entity-geojson/{dataset}/{code}")
async def get_entity_geojson(dataset: str, code: str):
    """Return GeoJSON for a single sub-national entity (for outline quiz)."""
    data = geodata_service.get_single_subnational(dataset, code.upper())
    if data is None:
        raise HTTPException(status_code=404, detail="GeoJSON not found")
    return JSONResponse(content=data)


# ── Daily challenge endpoint ─────────────────────────────────────────────────

@router.get("/daily-challenge")
async def api_daily_challenge(user: Optional[dict] = Depends(get_optional_user)):
    """Return today's pre-generated daily challenge.

    If user is logged in and already played today, returns their previous result
    instead of the questions.
    """
    # Check if logged-in user already played
    if user:
        prev = get_user_daily_result(user["user_id"])
        if prev:
            return {"already_played": True, "result": prev}

    challenge = get_daily_challenge()
    if not challenge:
        raise HTTPException(status_code=404, detail="No daily challenge available for today")
    return {"already_played": False, **challenge}


@router.get("/daily-challenge/result")
async def api_daily_challenge_result(user: dict = Depends(get_current_user)):
    """Return the current user's daily challenge result for today, if any."""
    result = get_user_daily_result(user["user_id"])
    if not result:
        return {"played": False}
    return {"played": True, "result": result}


# ── Match result saving ──────────────────────────────────────────────────────

class MatchResultPayload(BaseModel):
    game_type: str
    mode: str = "solo"
    score: int
    total: int
    accuracy: float
    time_ms: int
    config: dict = {}
    ranked: bool = False
    num_questions: int = 0
    per_question_scores: list[float] = []


@router.post("/matches/result")
async def save_match_result(
    payload: MatchResultPayload,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Save a completed match result. Works for logged-in users; anonymous gets a response but nothing persisted."""
    if not user:
        return {"saved": False, "message": "Not logged in"}

    # Create match
    match = create_match(
        mode=payload.mode,
        game_type=payload.game_type,
        config=payload.config,
        total_players=1,
    )

    # Finish it immediately (solo mode)
    won = payload.total > 0 and (payload.score / payload.total) >= 0.5
    finish_match(
        match_id=match["match_id"],
        winner_id=user["user_id"] if won else "",
        duration_ms=payload.time_ms,
    )

    # Save player result
    save_match_player(
        match_id=match["match_id"],
        user_id=user["user_id"],
        score=payload.score,
        rank=1,
        answers_summary=payload.config,
        accuracy=payload.accuracy,
        time_spent_ms=payload.time_ms,
    )

    # Update aggregated stats
    stats = record_match_result(
        user_id=user["user_id"],
        game_type=payload.game_type,
        score=payload.score,
        total=payload.total,
        accuracy=payload.accuracy,
        time_ms=payload.time_ms,
        won=won,
    )

    track("match_finished", {
        "user_id": user["user_id"], "match_id": match["match_id"],
        "game_type": payload.game_type, "mode": payload.mode,
        "score": payload.score, "total": payload.total,
    })

    # Save daily challenge result for one-time enforcement + rankings
    if payload.mode == "daily":
        try:
            save_user_daily_result(user["user_id"], {
                "score": payload.score,
                "total": payload.total,
                "accuracy": int(payload.accuracy),
                "time_ms": payload.time_ms,
                "match_id": match["match_id"],
            })
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            save_daily_score(
                user_id=user["user_id"],
                username=user.get("username", ""),
                date=today,
                game_type=payload.game_type,
                score=payload.score,
                total=payload.total,
                time_ms=payload.time_ms,
                num_questions=payload.num_questions or payload.total,
                config=payload.config,
            )
            rebuild_daily_ranking(today)
        except Exception:
            pass  # daily scoring failure must not break match saving

    # Process ranked attempt (competitive scoring system)
    scoring_result = None
    if payload.ranked and payload.game_type in SCORING_GAME_TYPES:
        try:
            scoring_result = process_ranked_attempt(
                user_id=user["user_id"],
                game_type=payload.game_type,
                score=payload.score,
                total=payload.total,
                num_questions=payload.num_questions or payload.total,
                time_ms=payload.time_ms,
                config=payload.config,
                per_question_scores=payload.per_question_scores or None,
                username=user.get("username", ""),
            )
        except Exception:
            pass  # scoring failure must not break match saving

    result = {
        "saved": True,
        "match_id": match["match_id"],
        "total_matches": int(stats.get("total_matches", 0)),
    }
    if scoring_result:
        result["scoring"] = scoring_result
    return result


@router.get("/user/stats")
async def api_user_stats(user: dict = Depends(get_current_user)):
    """Return the current user's aggregated stats."""
    stats = ensure_user_stats(user["user_id"])
    return stats


# ── Leaderboard endpoints ────────────────────────────────────────────────────

@router.get("/leaderboards/global")
async def api_global_leaderboard(
    metric: str = Query("rating", regex="^(rating|total_matches|best_streak)$"),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Global leaderboard by metric."""
    lb = get_leaderboard("global", "all", metric)
    result = {
        "leaderboard": lb["entries"] if lb else [],
        "metric": metric,
        "updated_at": lb["updated_at"] if lb else None,
    }
    if user:
        pos = get_user_position(user["user_id"], "global", "all", metric)
        result["user_position"] = pos
    return result


@router.get("/leaderboards/game/{game_type}")
async def api_game_leaderboard(
    game_type: str,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Per-game leaderboard (best score)."""
    if game_type not in GAME_TYPES:
        raise HTTPException(status_code=404, detail="Unknown game type")
    lb = get_leaderboard("game", game_type, "best_score")
    result = {
        "leaderboard": lb["entries"] if lb else [],
        "game_type": game_type,
        "updated_at": lb["updated_at"] if lb else None,
    }
    if user:
        pos = get_user_position(user["user_id"], "game", game_type, "best_score")
        result["user_position"] = pos
    return result


@router.get("/leaderboards/top10")
async def api_top10(user: Optional[dict] = Depends(get_optional_user)):
    """Quick top-10 global by rating — for landing page widget."""
    lb = get_leaderboard("global", "all", "rating")
    entries = (lb["entries"] if lb else [])[:10]
    result = {"leaderboard": entries}
    if user:
        result["user_position"] = get_user_position(user["user_id"])
    return result


# ── Ranking endpoints (new scoring system) ───────────────────────────────────

@router.get("/rankings/game/{game_type}")
async def api_game_ranking(
    game_type: str,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Per-game ranking using the new scoring system (R_test → RG)."""
    if game_type not in SCORING_GAME_TYPES:
        raise HTTPException(status_code=404, detail="Unknown game type")
    lb = get_game_ranking(game_type)
    result = {
        "ranking": lb["entries"] if lb else [],
        "game_type": game_type,
        "updated_at": lb.get("updated_at") if lb else None,
    }
    if user:
        pos = get_user_ranking_position(user["user_id"], "game", game_type)
        result["user_position"] = pos
        result["user_detail"] = get_user_game_ranking(user["user_id"], game_type)
    return result


@router.get("/rankings/season")
async def api_season_ranking(user: Optional[dict] = Depends(get_optional_user)):
    """Season ranking (last 12 weeks)."""
    lb = get_season_ranking()
    result = {
        "ranking": lb["entries"] if lb else [],
        "updated_at": lb.get("updated_at") if lb else None,
    }
    if user:
        pos = get_user_ranking_position(user["user_id"], "season")
        result["user_position"] = pos
    return result


@router.get("/rankings/weekly")
async def api_weekly_ranking(
    week: Optional[str] = Query(None, description="ISO week key like 2026-W14"),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Weekly ranking (current or specific week)."""
    lb = get_weekly_ranking(week)
    result = {
        "ranking": lb["entries"] if lb else [],
        "week_key": lb.get("week_key", week) if lb else week,
        "updated_at": lb.get("updated_at") if lb else None,
    }
    if user:
        pos = get_user_ranking_position(user["user_id"], "weekly")
        result["user_position"] = pos
    return result


@router.get("/rankings/rebuild")
async def api_rebuild_rankings(user: dict = Depends(get_current_user)):
    """Manually trigger ranking rebuild (admin-level)."""
    counts = rebuild_all_rankings()
    return {"status": "ok", "rebuilt": counts}


# ── Scoring data endpoints ───────────────────────────────────────────────────

@router.get("/user/scoring")
async def api_user_scoring(user: dict = Depends(get_current_user)):
    """Return the current user's scoring data: test ratings and recent attempts."""
    test_ratings = get_user_test_ratings(user["user_id"])
    recent_attempts = get_user_attempts(user["user_id"], limit=30)

    # Compute game rankings on-the-fly
    from collections import defaultdict
    game_ratings_map: dict[str, list[float]] = defaultdict(list)
    for tr in test_ratings:
        game_ratings_map[tr["game_type"]].append(tr["rating"])

    from services.rankings import compute_game_ranking, compute_game_ranking_final
    game_rankings = {}
    for gt, ratings in game_ratings_map.items():
        rg = compute_game_ranking(ratings)
        rg_final = compute_game_ranking_final(rg, len(ratings))
        game_rankings[gt] = {
            "rg": round(rg, 4),
            "rg_final": round(rg_final, 4),
            "tests_valid": len(ratings),
        }

    return {
        "test_ratings": test_ratings,
        "game_rankings": game_rankings,
        "recent_attempts": recent_attempts,
    }


@router.get("/records/{config_key:path}")
async def api_records(config_key: str):
    """Get records for a specific test configuration."""
    records = get_records(config_key)
    return {"config_key": config_key, "records": records}


# ── Daily challenge ranking endpoints ────────────────────────────────────────

@router.get("/rankings/daily/today")
async def api_daily_today_ranking(
    date: Optional[str] = Query(None, description="Date YYYY-MM-DD, defaults to today"),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Daily challenge ranking for today (or a specific date)."""
    lb = get_daily_day_ranking(date)
    result = {
        "ranking": lb["entries"] if lb else [],
        "date": lb.get("date", date) if lb else date,
        "updated_at": lb.get("updated_at") if lb else None,
    }
    if user:
        pos = get_user_daily_ranking_position(user["user_id"], "daily-day", date)
        result["user_position"] = pos
    return result


@router.get("/rankings/daily/monthly")
async def api_daily_monthly_ranking(
    month: Optional[str] = Query(None, description="Month key like 2026-04"),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Daily challenge monthly ranking (calendar month)."""
    lb = get_daily_monthly_ranking(month)
    result = {
        "ranking": lb["entries"] if lb else [],
        "month_key": lb.get("month_key", month) if lb else month,
        "updated_at": lb.get("updated_at") if lb else None,
    }
    if user:
        pos = get_user_daily_ranking_position(user["user_id"], "daily-monthly", month)
        result["user_position"] = pos
    return result


@router.get("/rankings/daily/absolute")
async def api_daily_absolute_ranking(
    user: Optional[dict] = Depends(get_optional_user),
):
    """Daily challenge all-time ranking."""
    lb = get_daily_absolute_ranking()
    result = {
        "ranking": lb["entries"] if lb else [],
        "updated_at": lb.get("updated_at") if lb else None,
    }
    if user:
        pos = get_user_daily_ranking_position(user["user_id"], "daily-absolute")
        result["user_position"] = pos
    return result


@router.get("/rankings/daily/rebuild")
async def api_rebuild_daily_rankings(user: dict = Depends(get_current_user)):
    """Manually trigger daily challenge ranking rebuild."""
    counts = rebuild_all_daily_rankings()
    return {"status": "ok", "rebuilt": counts}


@router.get("/user/daily-scores")
async def api_user_daily_scores(
    limit: int = Query(30, ge=1, le=90),
    user: dict = Depends(get_current_user),
):
    """Return the current user's recent daily challenge scores."""
    scores = get_user_daily_scores(user["user_id"], limit=limit)
    return {"scores": scores}
