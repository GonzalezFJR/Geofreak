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
    city_filter: str = Query("capitals", description="City filter: capitals|5m|1m|100k"),
):
    """Return entity list for the map game based on dataset and filters."""
    if dataset == "countries":
        return dataset_service.get_countries_for_map(continent=continent, entity_type=entity_type)
    elif dataset == "cities":
        return dataset_service.get_cities_for_map(city_filter=city_filter, continent=continent)
    elif dataset == "us-states":
        return dataset_service.get_us_states()
    elif dataset == "spain-provinces":
        return dataset_service.get_spain_provinces()
    elif dataset == "russia-regions":
        return dataset_service.get_russia_regions()
    elif dataset == "france-regions":
        return dataset_service.get_france_regions()
    elif dataset == "italy-regions":
        return dataset_service.get_italy_regions()
    elif dataset == "germany-states":
        return dataset_service.get_germany_states()
    else:
        raise HTTPException(status_code=400, detail="Unknown dataset")


@router.get("/map-game/geojson")
async def map_game_geojson(
    dataset: str = Query("countries", description="Dataset: countries|us-states|spain-provinces|russia-regions"),
):
    """Return GeoJSON for the map game (polygon-based datasets only)."""
    if dataset == "countries":
        data = geodata_service.get_simple_geojson()
    elif dataset in ("us-states", "spain-provinces", "russia-regions",
                     "france-regions", "italy-regions", "germany-states"):
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
):
    """Generate a set of ordering questions."""
    if difficulty not in ("easy", "normal", "hard", "very_hard", "extreme"):
        difficulty = "normal"
    questions = generate_ordering_set(
        num_questions=num, continent=continent, difficulty=difficulty, dataset=dataset
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
):
    """Generate a set of comparison questions."""
    if difficulty not in ("easy", "normal", "hard", "very_hard", "extreme"):
        difficulty = "normal"
    questions = generate_comparison_set(
        num_questions=num, continent=continent, difficulty=difficulty, dataset=dataset
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
):
    """Generate a set of geostats questions (guess entity from stat curve)."""
    data = generate_geostats_set(num_questions=num, continent=continent, dataset=dataset)
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

    # Save daily challenge result for one-time enforcement
    if payload.mode == "daily":
        save_user_daily_result(user["user_id"], {
            "score": payload.score,
            "total": payload.total,
            "accuracy": payload.accuracy,
            "time_ms": payload.time_ms,
            "match_id": match["match_id"],
        })

    return {
        "saved": True,
        "match_id": match["match_id"],
        "total_matches": int(stats.get("total_matches", 0)),
    }


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
