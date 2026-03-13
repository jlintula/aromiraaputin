from __future__ import annotations

import asyncio
import time
from typing import Any


class Cache:
    """Simple in-memory cache with TTL and per-key locking."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, key: str) -> Any | None:
        """Return cached value if not expired, else None."""
        if key in self._data:
            expiry, value = self._data[key]
            if time.time() < expiry:
                return value
        return None

    def get_stale(self, key: str) -> Any | None:
        """Return cached value even if expired."""
        if key in self._data:
            return self._data[key][1]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._data[key] = (time.time() + ttl_seconds, value)

    def lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]
