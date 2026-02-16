"""Coordinate parsing helpers.

This module provides a small parser for latitude/longitude values and acts
as a fallback when the third-party ``lat_lon_parser`` package is not
available.
"""

from __future__ import annotations

import re
from typing import Iterable


_DMS_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _numbers(value: str) -> list[float]:
    return [float(num) for num in _DMS_RE.findall(value)]


def _direction_multiplier(value: str) -> int:
    value = value.strip().upper()
    for direction, multiplier in (("S", -1), ("W", -1), ("N", 1), ("E", 1)):
        if direction in value:
            return multiplier
    return 1


def _dms_to_decimal(parts: Iterable[float]) -> float:
    values = list(parts)
    if not values:
        raise ValueError("No numeric values found in coordinate string.")
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        degrees, minutes = values
        return degrees + minutes / 60
    degrees, minutes, seconds = values[:3]
    return degrees + minutes / 60 + seconds / 3600


def parse_coordinate(value: str) -> float:
    """Parse a latitude/longitude string into decimal degrees."""
    if value is None:
        raise ValueError("Coordinate value is required.")

    value = str(value).strip()
    if not value:
        raise ValueError("Coordinate value is required.")

    parts = _numbers(value)
    decimal = _dms_to_decimal(parts)
    multiplier = _direction_multiplier(value)

    if decimal < 0:
        multiplier = -1

    return abs(decimal) * multiplier

