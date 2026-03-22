"""JSON API endpoints for datasets."""

import json
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from services.dataset import DatasetService
from services.geodata import GeodataService

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
