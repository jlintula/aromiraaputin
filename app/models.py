from __future__ import annotations

from pydantic import BaseModel


class Dish(BaseModel):
    name: str
    diets: str  # e.g. "L, M, G"


class Meal(BaseModel):
    name: str  # e.g. "Lounas", "Kasvislounas"
    dishes: list[Dish]


class DayMenu(BaseModel):
    date: str  # ISO date, e.g. "2026-03-12"
    weekday: str  # e.g. "to 12.3.2026"
    meals: list[Meal]


class WeekMenu(BaseModel):
    restaurant: str
    restaurant_code: str
    days: list[DayMenu]


class Restaurant(BaseModel):
    name: str
    code: str  # UniqueCode, e.g. "HaapaniemiKOU"
    id: str  # GUID
    type_code: str  # e.g. "Koulu", "Paivakoti"
    type_name: str  # e.g. "Koulut", "Päiväkodit"


class RestaurantType(BaseModel):
    code: str  # UniqueCode
    name: str  # Display name


class RestaurantList(BaseModel):
    types: list[RestaurantType]
    restaurants: list[Restaurant]
