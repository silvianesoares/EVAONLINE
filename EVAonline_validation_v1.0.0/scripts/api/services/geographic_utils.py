"""
Centralized geographic utilities for region detection.

This module centralizes ALL geolocation operations,
eliminating code duplication across multiple modules.

SINGLE SOURCE OF TRUTH for:
- USA coordinate detection
- Nordic coordinate detection (MET Norway 1km)
- Brazil coordinate detection (rigorous validations)
- Global coordinate detection

Bounding Boxes:
- USA Continental: -125°W to -66°W, 24°N to 49°N (NWS coverage)
- Nordic Region: 4°E to 31°E, 54°N to 71.5°N (MET Norway 1km)
- Brazil: -74°W to -34°W, -34°S to 5°N (Xavier et al. 2016)
- Global: Any coordinate within (-180, -90) to (180, 90)

Usage:
    from validation_logic_eto.api.services.geographic_utils import GeographicUtils

    if GeographicUtils.is_in_usa(lat, lon):
        # Use NWS
        pass
    elif GeographicUtils.is_in_nordic(lat, lon):
        # Use MET Norway with high quality precipitation
        pass
    elif GeographicUtils.is_in_brazil(lat, lon):
        # Use Brazil-specific validations
        pass
    else:
        # Use Open-Meteo or NASA POWER (global)
        pass
"""

from datetime import datetime, date, timezone
from loguru import logger
from typing import Literal
from functools import wraps
import inspect


class GeographicUtils:
    """Centralizes geographic detection with standardized bounding boxes."""

    # Bounding boxes: (lon_min, lat_min, lon_max, lat_max) = (W, S, E, N)

    USA_BBOX = (-125.0, 24.0, -66.0, 49.0)
    """
    USA Continental bounding box (NWS coverage).

    Coverage:
        Longitude: -125°W (West Coast) to -66°W (East Coast)
        Latitude: 24°N (South Florida) to 49°N (Canada Border)

    Included states:
        All 48 contiguous states

    Excluded:
        Alaska, Hawaii, Puerto Rico, territories
    """

    NORDIC_BBOX = (4.0, 54.0, 31.0, 71.5)
    """
    Nordic Region bounding box (MET Norway 1km high quality).

    Coverage:
        Longitude: 4°E (West Denmark) to 31°E (Finland/Baltics)
        Latitude: 54°N (South Denmark) to 71.5°N (North Norway)

    Included countries:
        Norway, Denmark, Sweden, Finland, Estonia, Latvia, Lithuania

    Special quality:
        - Resolution: 1 km (vs 9km global)
        - Updates: Every hour (vs 4x/day global)
        - Precipitation: Radar + crowdsourced (Netatmo)
        - Post-processing: Extensive with bias correction
    """

    BRAZIL_BBOX = (-74.0, -34.0, -34.0, 5.0)
    """
    Brazil bounding box (Xavier et al. 2016).

    Coverage:
        Longitude: -74°W (West Border) to -34°W (East Coast)
        Latitude: -34°S (South) to 5°N (North)

    Description:
        Continental Brazil boundaries, including all regions.
        Used for specific validations and source optimization.
    """

    GLOBAL_BBOX = (-180.0, -90.0, 180.0, 90.0)
    """Global bounding box (any valid coordinate)."""

    @staticmethod
    def is_in_usa(lat: float, lon: float) -> bool:
        """
        Check if coordinates are in continental USA.

        Uses bounding box: (-125.0, 24.0, -66.0, 49.0)
        Coverage: NWS API (National Weather Service)

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)

        Returns:
            bool: True if inside USA bbox, False otherwise

        Example:
            if GeographicUtils.is_in_usa(39.7392, -104.9903):
                # Denver, CO - inside USA
                pass
        """
        lon_min, lat_min, lon_max, lat_max = GeographicUtils.USA_BBOX
        in_usa = (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max)

        if not in_usa:
            logger.debug(
                f"Coordinates ({lat:.4f}, {lon:.4f}) "
                f"OUTSIDE USA Continental coverage"
            )

        return in_usa

    @staticmethod
    def is_in_nordic(lat: float, lon: float) -> bool:
        """
        Check if coordinates are in Nordic region.

        Uses bounding box: (4.0, 54.0, 31.0, 71.5)
        Coverage: MET Norway 1km high quality with radar

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)

        Returns:
            bool: True if inside Nordic bbox, False otherwise

        Example:
            if GeographicUtils.is_in_nordic(60.1699, 24.9384):
                # Helsinki, Finland - inside Nordic region
                pass
        """
        lon_min, lat_min, lon_max, lat_max = GeographicUtils.NORDIC_BBOX
        in_nordic = (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max)

        if in_nordic:
            logger.debug(
                f"Coordinates ({lat:.4f}, {lon:.4f}) "
                f"in NORDIC region (MET Norway 1km)"
            )

        return in_nordic

    @staticmethod
    def is_in_brazil(lat: float, lon: float) -> bool:
        """
        Check if coordinates are in Brazil.

        Uses bounding box: (-74.0, -34.0, -34.0, 5.0)
        Coverage: Brazilian continental territory

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)

        Returns:
            bool: True if inside Brazil bbox, False otherwise

        Example:
            if GeographicUtils.is_in_brazil(-23.5505, -46.6333):
                # Sao Paulo, Brazil - inside territory
                pass
        """
        lon_min, lat_min, lon_max, lat_max = GeographicUtils.BRAZIL_BBOX
        in_brazil = (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max)

        if in_brazil:
            logger.debug(
                f"Coordinates ({lat:.4f}, {lon:.4f}) " f"in BRAZIL region"
            )

        return in_brazil

    @staticmethod
    def is_valid_coordinate(lat: float, lon: float) -> bool:
        """
        Check if coordinates are valid (within (-180, -90) to (180, 90)).

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            bool: True if valid, False otherwise
        """
        lon_min, lat_min, lon_max, lat_max = GeographicUtils.GLOBAL_BBOX
        return (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max)

    @staticmethod
    def is_in_bbox(lat: float, lon: float, bbox: tuple) -> bool:
        """
        Check if coordinates are inside a bounding box.

        Args:
            lat: Latitude
            lon: Longitude
            bbox: Tuple (west, south, east, north)

        Returns:
            bool: True if inside bbox

        Example:
            # Check if inside USA region
            if GeographicUtils.is_in_bbox(40.7, -74.0,
                                          GeographicUtils.USA_BBOX):
                # Inside USA region
                pass
        """
        if not GeographicUtils.is_valid_coordinate(lat, lon):
            return False

        west, south, east, north = bbox
        return (west <= lon <= east) and (south <= lat <= north)

    @staticmethod
    def get_region(
        lat: float, lon: float
    ) -> Literal["usa", "nordic", "brazil", "global"]:
        """
        Detect geographic region with priority:
        USA > Nordic > Brazil > Global.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            str: One of "usa", "nordic", "brazil", "global"

        Example:
            region = GeographicUtils.get_region(39.7392, -104.9903)
            # Returns: "usa"

            region = GeographicUtils.get_region(60.1699, 24.9384)
            # Returns: "nordic"

            region = GeographicUtils.get_region(-23.5505, -46.6333)
            # Returns: "brazil"
        """
        if GeographicUtils.is_in_usa(lat, lon):
            return "usa"
        elif GeographicUtils.is_in_nordic(lat, lon):
            return "nordic"
        elif GeographicUtils.is_in_brazil(lat, lon):
            return "brazil"
        else:
            return "global"

    @staticmethod
    def get_recommended_sources(lat: float, lon: float) -> list[str]:
        """
        Return list of recommended climate sources by region,
        in priority order. Standardized for forecast (5 days).

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            list[str]: Ordered list of source names (API priority)

        Regions:
            USA:
                1. nws_forecast (high quality forecast)
                2. nws_stations (real-time observations)
                3. openmeteo_forecast (global fallback)
                4. openmeteo_archive (historical)
                5. nasa_power (universal fallback)

            Nordic:
                1. met_norway (1km forecast with radar)
                2. openmeteo_forecast (global fallback)
                3. openmeteo_archive (historical)
                4. nasa_power (universal fallback)

            Brazil:
                1. openmeteo_forecast (best global for BR)
                2. nasa_power (validated historical)
                3. openmeteo_archive (historical)

            Global:
                1. openmeteo_forecast (best global)
                2. openmeteo_archive (historical)
                3. nasa_power (universal fallback)

        Example:
            sources = GeographicUtils.get_recommended_sources(
                39.7392, -104.9903
            )
            # Returns: ["nws_forecast", "nws_stations",
            #           "openmeteo_forecast", ...]
        """
        region = GeographicUtils.get_region(lat, lon)

        # Common base sources (avoid repetition)
        base_sources = [
            "openmeteo_forecast",  # Global forecast (5 days)
            "openmeteo_archive",  # Historical fallback
            "nasa_power",  # Universal
        ]

        # Region mapping -> priority sources
        region_sources = {
            "usa": [
                "nws_forecast",  # Best for forecast
                "nws_stations",  # Real-time observations
            ]
            + base_sources,
            "nordic": [
                "met_norway",  # Best: 1km + radar
            ]
            + base_sources,
            "brazil": [
                # Optimized for Brazil: skip MET (low quality precip)
                "openmeteo_forecast",  # Best global
                "nasa_power",  # Validated historical
                "openmeteo_archive",  # Historical
            ],
        }

        return region_sources.get(region, base_sources)


class TimezoneUtils:
    """
    Utilities for consistent timezone handling.

    Ensures correct comparisons between datetimes with/without timezone.
    Centralized here to avoid circular import with weather_utils.
    """

    @staticmethod
    def ensure_naive(dt) -> datetime:
        """
        Convert datetime to naive (no timezone).

        Args:
            dt: Possibly timezone-aware datetime

        Returns:
            Naive datetime (no timezone)
        """
        if not isinstance(dt, datetime):
            raise TypeError("dt must be a datetime instance")
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    @staticmethod
    def ensure_utc(dt) -> datetime:
        """
        Convert datetime to UTC timezone-aware.

        Args:
            dt: Possibly naive datetime

        Returns:
            UTC timezone-aware datetime
        """
        if not isinstance(dt, datetime):
            raise TypeError("dt must be a datetime instance")
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def make_aware(dt, tz=None) -> datetime:
        """
        Convert naive datetime to timezone-aware.

        Args:
            dt: Possibly naive datetime
            tz: Timezone (default: UTC)

        Returns:
            Timezone-aware datetime
        """
        if not isinstance(dt, datetime):
            raise TypeError("dt must be a datetime instance")
        if dt.tzinfo is None:
            target_tz = tz or timezone.utc
            return dt.replace(tzinfo=target_tz)
        return dt

    @staticmethod
    def compare_dates_safe(dt1, dt2, comparison: str = "lt") -> bool:
        """
        Compare two dates safely (ignoring timezone).

        Args:
            dt1: First date
            dt2: Second date
            comparison: 'lt', 'le', 'gt', 'ge', 'eq'

        Returns:
            Comparison result
        """
        if not isinstance(dt1, (datetime, date)) or not isinstance(
            dt2, (datetime, date)
        ):
            raise TypeError("dt1 and dt2 must be datetime or date instances")

        date1 = dt1.date() if isinstance(dt1, datetime) else dt1
        date2 = dt2.date() if isinstance(dt2, datetime) else dt2

        if comparison == "lt":
            return date1 < date2
        elif comparison == "le":
            return date1 <= date2
        elif comparison == "gt":
            return date1 > date2
        elif comparison == "ge":
            return date1 >= date2
        elif comparison == "eq":
            return date1 == date2
        else:
            raise ValueError(f"Invalid comparison: {comparison}")


def validate_coordinates(func):
    """
    Decorator to validate coordinates before executing function.

    Validates that lat/lon are valid floats within (-180, -90) to (180, 90).
    Raises ValueError if invalid. Uses inspect for robust parsing.

    Usage:
        @validate_coordinates
        def get_weather(lat: float, lon: float):
            # lat/lon already validated here
            pass
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Robust parsing using inspect.signature
        sig = inspect.signature(func)
        try:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
        except TypeError:
            # Fallback to positional args if bind fails
            if len(args) >= 2:
                lat, lon = args[-2], args[-1]
            elif "lat" in kwargs and "lon" in kwargs:
                lat = kwargs["lat"]
                lon = kwargs["lon"]
            else:
                raise ValueError("Function must provide 'lat' and 'lon'")
        else:
            # Extract lat/lon robustly (prioritize named kwargs)
            lat = bound.arguments.get("lat")
            lon = bound.arguments.get("lon")
            if lat is None or lon is None:
                # Fallback to positional args
                if len(args) >= 2:
                    lat, lon = args[-2], args[-1]
                else:
                    raise ValueError("Function must provide 'lat' and 'lon'")

        # Convert to float if necessary
        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            raise ValueError("lat and lon must be numeric")

        # Validate coordinates
        if not GeographicUtils.is_valid_coordinate(lat, lon):
            raise ValueError(
                f"Invalid coordinates: lat={lat}, lon={lon}. "
                "Must be within lon (-180 to 180), lat (-90 to 90)"
            )

        return func(*args, **kwargs)

    return wrapper
