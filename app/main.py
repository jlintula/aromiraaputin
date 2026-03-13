from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .cache import Cache
from .models import Restaurant, RestaurantList, WeekMenu
from .scraper import CITIES, DEFAULT_CITY as _DEFAULT_CITY, AromiScraper, get_city_config, get_week_range

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

RESTAURANT_CACHE_TTL = 86400  # 24h
MENU_CACHE_TTL = 14400  # 4h

DEFAULT_CITY = os.environ.get("AROMIRAAPUTIN_CITY", "").strip() or _DEFAULT_CITY

scraper: AromiScraper
cache: Cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scraper, cache
    scraper = AromiScraper()
    cache = Cache()
    yield
    await scraper.close()


app = FastAPI(title="Aromiraaputin", lifespan=lifespan)

def _parse_favorites() -> list[dict]:
    """Parse favorites from AROMIRAAPUTIN_FAVORITES env var.

    Format: "code:name,code:name,..."
    Example: AROMIRAAPUTIN_FAVORITES="MyllytupaPK:Myllytuvan päiväkoti,KeltinmakiKOU:Keltinmäen koulu"
    """
    env = os.environ.get("AROMIRAAPUTIN_FAVORITES", "")
    if not env.strip():
        return []
    result = []
    for entry in env.split(","):
        entry = entry.strip()
        if ":" in entry:
            code, name = entry.split(":", 1)
            result.append({"code": code.strip(), "name": name.strip()})
    return result


FAVORITES = _parse_favorites()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _validate_city(city: str) -> None:
    """Raise HTTP 400 if city is not in CITIES."""
    if city not in CITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown city '{city}'. Valid cities: {', '.join(CITIES.keys())}",
        )


async def _get_restaurants(city: str = DEFAULT_CITY) -> RestaurantList:
    """Get restaurant list, with caching."""
    key = f"restaurants_{city}"
    cached = cache.get(key)
    if cached:
        return cached

    async with cache.lock(key):
        cached = cache.get(key)
        if cached:
            return cached
        try:
            result = await scraper.get_restaurants(city)
            cache.set(key, result, RESTAURANT_CACHE_TTL)
            return result
        except Exception:
            stale = cache.get_stale(key)
            if stale:
                logger.warning("Using stale restaurant cache")
                return stale
            raise


def _find_restaurant(restaurants: RestaurantList, code: str) -> Restaurant:
    """Find restaurant by code (case-insensitive)."""
    code_lower = code.lower()
    for r in restaurants.restaurants:
        if r.code.lower() == code_lower:
            return r
    raise HTTPException(
        status_code=404,
        detail=f"Restaurant '{code}' not found. Use /api/restaurants to list available restaurants.",
    )


async def _get_menu(restaurant: Restaurant, range_: str, city: str = DEFAULT_CITY) -> WeekMenu:
    """Get menu for a restaurant, with caching."""
    start, end = get_week_range(range_)
    key = f"menu_{city}_{restaurant.code}_{range_}_{start.date()}"
    cached = cache.get(key)
    if cached:
        return cached

    async with cache.lock(key):
        cached = cache.get(key)
        if cached:
            return cached
        try:
            result = await scraper.get_menu(
                restaurant.code, restaurant.id, start, end, city
            )
            result.restaurant = restaurant.name
            cache.set(key, result, MENU_CACHE_TTL)
            return result
        except Exception:
            stale = cache.get_stale(key)
            if stale:
                logger.warning("Using stale menu cache for %s", restaurant.code)
                return stale
            raise


@app.get("/api/restaurants")
async def api_restaurants(
    city: str = Query(DEFAULT_CITY, description="City key (e.g. jyvaskyla, helsinki)"),
):
    """List all restaurants grouped by type."""
    _validate_city(city)
    data = await _get_restaurants(city)
    grouped: dict[str, list[dict]] = {}
    for r in data.restaurants:
        type_name = r.type_name or "Muut"
        if type_name not in grouped:
            grouped[type_name] = []
        grouped[type_name].append({"code": r.code, "name": r.name})
    return {"types": [t.model_dump() for t in data.types], "restaurants": grouped}


@app.get("/api/menu")
async def api_menu(
    restaurant: str = Query(..., description="Restaurant code (e.g. HaapaniemiKOU)"),
    range: Literal["today", "week", "nextweek", "week3", "week4"] = Query(
        "today", description="Time range"
    ),
    city: str = Query(DEFAULT_CITY, description="City key (e.g. jyvaskyla, helsinki)"),
):
    """Get menu as JSON."""
    _validate_city(city)
    restaurants = await _get_restaurants(city)
    rest = _find_restaurant(restaurants, restaurant)
    menu = await _get_menu(rest, range, city)
    return menu.model_dump()


@app.get("/menu", response_class=HTMLResponse)
async def html_menu(
    request: Request,
    restaurant: str | None = Query(None, description="Restaurant code"),
    range: Literal["today", "week", "nextweek", "week3", "week4"] = Query("today"),
    theme: Literal["light", "dark"] = Query("light"),
    city: str = Query(DEFAULT_CITY, description="City key"),
):
    """Get menu as embeddable HTML, or a picker if no restaurant is selected."""
    _validate_city(city)
    restaurants = await _get_restaurants(city)
    city_cfg = get_city_config(city)

    if not restaurant:
        grouped: dict[str, list[dict]] = {}
        for r in restaurants.restaurants:
            type_name = r.type_name or "Muut"
            if type_name not in grouped:
                grouped[type_name] = []
            grouped[type_name].append({"code": r.code, "name": r.name})
        return templates.TemplateResponse(
            "picker.html",
            {
                "request": request,
                "grouped": grouped,
                "favorites": FAVORITES if city == DEFAULT_CITY else [],
                "range": range,
                "theme": theme,
                "city": city,
                "cities": {k: v["name"] for k, v in CITIES.items()},
                "city_name": city_cfg["name"],
            },
        )

    rest = _find_restaurant(restaurants, restaurant)
    menu = await _get_menu(rest, range, city)
    return templates.TemplateResponse(
        "menu.html",
        {
            "request": request,
            "menu": menu,
            "theme": theme,
            "range": range,
            "restaurant_name": rest.name,
            "city": city,
        },
    )


@app.get("/")
async def root():
    return RedirectResponse("/menu")


@app.get("/health")
async def health():
    return {"status": "ok"}
