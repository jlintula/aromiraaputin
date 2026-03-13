from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from .models import (
    DayMenu,
    Dish,
    Meal,
    Restaurant,
    RestaurantList,
    RestaurantType,
    WeekMenu,
)

logger = logging.getLogger(__name__)

CITIES: dict[str, dict[str, str]] = {
    "jyvaskyla": {
        "name": "Jyväskylä",
        "base_url": "https://aromimenu.cgisaas.fi/JyvaskylaAromieMenus/FI/Default/Ravintola",
        "currentpage": "/JyvaskylaAromieMenus/FI/Default/Ravintola/_/Page/home",
    },
    "helsinki": {
        "name": "Helsinki",
        "base_url": "https://aromi.hel.fi/aromiemenus/FI/Default/PALKE",
        "currentpage": "/aromiemenus/FI/Default/PALKE/_/Page/home",
    },
    "tampere": {
        "name": "Tampere",
        "base_url": "https://aromimenu.cgisaas.fi/TampereAromieMenus/FI/Default/Tampere",
        "currentpage": "/TampereAromieMenus/FI/Default/Tampere/_/Page/home",
    },
}

DEFAULT_CITY = "jyvaskyla"


def get_city_config(city: str) -> dict[str, str]:
    """Get city configuration by key. Raises KeyError for unknown cities."""
    if city not in CITIES:
        raise KeyError(f"Unknown city: {city}")
    return CITIES[city]


class AromiScraper:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(follow_redirects=True, timeout=30)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_restaurants(self, city: str = DEFAULT_CITY) -> RestaurantList:
        """Fetch all restaurant types and restaurants from GetPageInfo."""
        cfg = get_city_config(city)
        r = await self._client.get(
            f"{cfg['base_url']}/_/api/Common/Page/GetPageInfo",
            params={"currentpage": cfg["currentpage"]},
        )
        r.raise_for_status()
        data = r.json()

        types = []
        type_map: dict[str, str] = {}  # id -> name
        for rt in data.get("RestaurantTypes", []):
            types.append(
                RestaurantType(code=rt["UniqueCode"], name=rt["NameOrCode"])
            )
            type_map[rt["Id"]] = rt["NameOrCode"]
            # Also map UniqueCode for lookup
            type_map[rt["UniqueCode"]] = rt["NameOrCode"]

        # Build a map from type ID to type code
        type_id_to_code: dict[str, str] = {}
        for rt in data.get("RestaurantTypes", []):
            type_id_to_code[rt["Id"]] = rt["UniqueCode"]

        restaurants = []
        for rest in data.get("Restaurants", []):
            type_id = rest.get("BcRestaurantTypeId", "")
            type_code = type_id_to_code.get(type_id, "")
            type_name = type_map.get(type_id, "")
            restaurants.append(
                Restaurant(
                    name=rest["NameOrUniqueCode"],
                    code=rest["UniqueCode"],
                    id=rest["Id"],
                    type_code=type_code,
                    type_name=type_name,
                )
            )

        return RestaurantList(types=types, restaurants=restaurants)

    async def _get_diner_group(
        self, base_url: str, restaurant_code: str, restaurant_id: str
    ) -> dict | None:
        """Get the first diner group for a restaurant."""
        now = datetime.now(timezone.utc).isoformat()
        r = await self._client.get(
            f"{base_url}/{restaurant_code}/api/GetRestaurantPublicDinerGroups",
            params={"id": restaurant_id, "startDate": now, "endDate": now},
        )
        r.raise_for_status()
        groups = r.json()
        if not groups:
            return None
        dg = groups[0]
        # Ensure SuitabilityDietIds is an array, not null
        dg["SuitabilityDietIds"] = dg.get("SuitabilityDietIds") or []
        return dg

    async def get_menu(
        self,
        restaurant_code: str,
        restaurant_id: str,
        start_date: datetime,
        end_date: datetime,
        city: str = DEFAULT_CITY,
    ) -> WeekMenu:
        """Fetch menu for a restaurant within a date range."""
        cfg = get_city_config(city)
        base_url = cfg["base_url"]
        dg = await self._get_diner_group(base_url, restaurant_code, restaurant_id)
        if not dg:
            return WeekMenu(
                restaurant="", restaurant_code=restaurant_code, days=[]
            )

        r = await self._client.post(
            f"{base_url}/{restaurant_code}/api/Common/Restaurant/RestaurantMeals",
            params={
                "Id": restaurant_id,
                "StartDate": start_date.isoformat(),
                "EndDate": end_date.isoformat(),
            },
            json=dg,
        )
        r.raise_for_status()
        raw_days = r.json()

        days = []
        for raw_day in raw_days:
            meals = []
            for raw_meal in raw_day.get("Meals", []):
                dishes = []
                for raw_dish in raw_meal.get("Dishes", []):
                    dishes.append(
                        Dish(
                            name=raw_dish["DishName"],
                            diets=raw_dish.get("DietDetails") or "",
                        )
                    )
                meals.append(Meal(name=raw_meal["MealName"], dishes=dishes))
            days.append(
                DayMenu(
                    date=raw_day["Date"][:10],
                    weekday=raw_day.get("MenuDate", ""),
                    meals=meals,
                )
            )

        return WeekMenu(
            restaurant=dg.get("Name", ""),
            restaurant_code=restaurant_code,
            days=days,
        )


WEEK_OFFSETS = {
    "today": None,
    "week": 0,
    "nextweek": 1,
    "week3": 2,
    "week4": 3,
}


def get_week_range(week: str) -> tuple[datetime, datetime]:
    """Return (start, end) datetime for a given range key."""
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if week == "today":
        return today, today

    offset = WEEK_OFFSETS.get(week, 0)
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    friday = monday + timedelta(days=4, hours=23, minutes=59)

    return monday, friday
