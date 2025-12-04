"""
Weather conversion and aggregation utilities.

Centralizes all unit conversions and meteorological formulas
to eliminate code duplication between climate clients.

SINGLE SOURCE OF TRUTH for:
- Wind conversion (10m → 2m using FAO-56)
- Temperature conversion (°F → °C)
- Speed conversion (mph → m/s)
- Solar radiation conversion
- Common meteorological validations
- Hourly-to-daily aggregation (e.g., MET Norway)
- Cache handling for APIs
- FAO-56 elevation corrections
- Prometheus metrics for validations
"""

from datetime import datetime, timezone
from typing import Any, Dict, List
from collections import defaultdict

import numpy as np
from email.utils import parsedate_to_datetime
from loguru import logger

try:
    import prometheus_client as prom

    # Counter for validation failures (Prometheus)
    VALIDATION_ERRORS = prom.Counter(
        "weather_validation_errors_total",
        "Total validation errors",
        ["region", "variable"],
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    logger.warning("prometheus_client not available. Metrics disabled.")
    PROMETHEUS_AVAILABLE = False
    VALIDATION_ERRORS = None


class WeatherConversionUtils:
    """
    Meteorological unit conversion utilities.

    All conversions follow international standards:
    - FAO-56 for wind and evapotranspiration
    - SI units (International System)
    """

    @staticmethod
    def convert_wind_10m_to_2m(wind_10m: float | None) -> float | None:
        """
        Convert wind speed from 10m to 2m height using FAO-56.

        FAO-56 formula: u₂ = u₁₀ × 0.748

        This conversion is necessary because:
        - Sensors measure wind at 10m height (standard)
        - FAO-56 ETo requires wind at 2m height
        - Factor 0.748 accounts for logarithmic wind profile

        Args:
            wind_10m: Wind speed at 10m (m/s)

        Returns:
            Wind speed at 2m (m/s) or None

        Reference:
            Allen et al. (1998). FAO Irrigation and Drainage Paper 56
            Chapter 3, Equation 47, page 56
        """
        if wind_10m is None:
            return None
        return wind_10m * 0.748

    @staticmethod
    def fahrenheit_to_celsius(fahrenheit: float | None) -> float | None:
        """
        Convert temperature from Fahrenheit to Celsius.

        Formula: °C = (°F - 32) x 5/9

        Args:
            fahrenheit: Temperature in °F

        Returns:
            Temperature in °C or None
        """
        if fahrenheit is None:
            return None
        return (fahrenheit - 32) * 5.0 / 9.0

    @staticmethod
    def celsius_to_fahrenheit(celsius: float | None) -> float | None:
        """
        Convert temperature from Celsius to Fahrenheit.

        Formula: °F = °C x 9/5 + 32

        Args:
            celsius: Temperature in °C

        Returns:
            Temperature in °F or None
        """
        if celsius is None:
            return None
        return celsius * 9.0 / 5.0 + 32.0

    @staticmethod
    def mph_to_ms(mph: float | None) -> float | None:
        """
        Convert speed from miles per hour to meters per second.

        Formula: 1 mph = 0.44704 m/s

        Args:
            mph: Speed in mph

        Returns:
            Speed in m/s or None
        """
        if mph is None:
            return None
        return mph * 0.44704

    @staticmethod
    def ms_to_mph(ms: float | None) -> float | None:
        """
        Convert speed from meters per second to miles per hour.

        Formula: 1 m/s = 2.23694 mph

        Args:
            ms: Speed in m/s

        Returns:
            Speed in mph or None
        """
        if ms is None:
            return None
        return ms * 2.23694

    @staticmethod
    def wh_per_m2_to_mj_per_m2(wh_per_m2: float | None) -> float | None:
        """
        Convert solar radiation from Wh/m² to MJ/m².

        Formula: 1 Wh = 0.0036 MJ

        Args:
            wh_per_m2: Radiation in Wh/m²

        Returns:
            Radiation in MJ/m² or None
        """
        if wh_per_m2 is None:
            return None
        return wh_per_m2 * 0.0036

    @staticmethod
    def mj_per_m2_to_wh_per_m2(mj_per_m2: float | None) -> float | None:
        """
        Convert solar radiation from MJ/m² to Wh/m².

        Formula: 1 MJ = 277.778 Wh

        Args:
            mj_per_m2: Radiation in MJ/m²

        Returns:
            Radiation in Wh/m² or None
        """
        if mj_per_m2 is None:
            return None
        return mj_per_m2 * 277.778


class WeatherValidationUtils:
    """
    Meteorological data validations.

    Verifies valid ranges for meteorological variables
    based on physical and practical limits.
    """

    # GLOBAL LIMITS (Worldwide)
    # Based on world records and physical limits
    TEMP_MIN = (
        -90.0
    )  # °C (World record: -89.2°C: https://svs.gsfc.nasa.gov/4126/)
    TEMP_MAX = 60.0  # °C (World record: 56.7°C: https://www.ncei.noaa.gov/news/earths-hottest-temperature)
    HUMIDITY_MIN = 0.0  # % (https://www.psu.edu/news/research/story/humans-cant-endure-temperatures-and-humidities-high-previously-thought)
    HUMIDITY_MAX = 100.0  # % (https://www.psu.edu/news/research/story/humans-cant-endure-temperatures-and-humidities-high-previously-thought)
    WIND_MIN = (
        0.0  # m/s (https://mountwashington.org/remembering-the-big-wind/)
    )
    WIND_MAX = 120.0  # m/s (~432 km/h, category 5 hurricane: https://mountwashington.org/remembering-the-big-wind/)
    PRECIP_MIN = 0.0  # mm (https://www.weather.gov/owp/hdsc_world_record)
    PRECIP_MAX = 2000.0  # mm/day (record: ~1825mm: (https://www.weather.gov/owp/hdsc_world_record)
    SOLAR_MIN = 0.0  # MJ/m²/day (https://www.bom.gov.au/climate/austmaps/metadata-daily-solar-exposure.shtml)
    SOLAR_MAX = 35.0  # MJ/m²/day (https://www.bom.gov.au/climate/austmaps/metadata-daily-solar-exposure.shtml)

    # BRAZIL LIMITS (Xavier et al. 2016, 2022)
    # "New improved Brazilian daily weather gridded data (1961–2020)"
    # https://rmets.onlinelibrary.wiley.com/doi/abs/10.1002/joc.7731
    # More rigorous validations for Brazilian data
    BRAZIL_TEMP_MIN = -30.0  # °C (Xavier limits)
    BRAZIL_TEMP_MAX = 50.0  # °C (Xavier limits)
    BRAZIL_HUMIDITY_MIN = 0.0  # %
    BRAZIL_HUMIDITY_MAX = 100.0  # %
    BRAZIL_WIND_MIN = 0.0  # m/s
    BRAZIL_WIND_MAX = 100.0  # m/s (Xavier limits)
    BRAZIL_PRECIP_MIN = 0.0  # mm
    BRAZIL_PRECIP_MAX = 450.0  # mm/day (Xavier limits)
    BRAZIL_SOLAR_MIN = 0.0  # MJ/m²/day
    BRAZIL_SOLAR_MAX = 40.0  # MJ/m²/day (Xavier limits)
    BRAZIL_PRESSURE_MIN = 900.0  # hPa
    BRAZIL_PRESSURE_MAX = 1100.0  # hPa

    # Regional limits dictionary
    REGIONAL_LIMITS = {
        "global": {
            "temperature": (TEMP_MIN, TEMP_MAX),
            "humidity": (HUMIDITY_MIN, HUMIDITY_MAX),
            "wind": (WIND_MIN, WIND_MAX),
            "precipitation": (PRECIP_MIN, PRECIP_MAX),
            "solar": (SOLAR_MIN, SOLAR_MAX),
            "pressure": (800.0, 1150.0),
        },
        "brazil": {
            "temperature": (BRAZIL_TEMP_MIN, BRAZIL_TEMP_MAX),
            "humidity": (BRAZIL_HUMIDITY_MIN, BRAZIL_HUMIDITY_MAX),
            "wind": (BRAZIL_WIND_MIN, BRAZIL_WIND_MAX),
            "precipitation": (BRAZIL_PRECIP_MIN, BRAZIL_PRECIP_MAX),
            "solar": (BRAZIL_SOLAR_MIN, BRAZIL_SOLAR_MAX),
            "pressure": (BRAZIL_PRESSURE_MIN, BRAZIL_PRESSURE_MAX),
        },
    }

    @classmethod
    def get_validation_limits(
        cls,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> dict[str, tuple[float, float]]:
        """
        Returns validation limits by detected region.

        Args:
            lat: Latitude (for automatic region detection)
            lon: Longitude (for automatic region detection)
            region: Explicit region ("global", "brazil", "usa", "nordic")
                   Overrides automatic detection if provided.

        Returns:
            Dict with (min, max) limits for each variable

        Example:
            # Automatic detection
            limits = WeatherValidationUtils.get_validation_limits(
                lat=-23.5505, lon=-46.6333
            )
            # Sao Paulo → Brazil limits

            # Explicit region
            limits = WeatherValidationUtils.get_validation_limits(
                region="brazil"
            )
        """
        # Local import to avoid circular dependency
        from .geographic_utils import GeographicUtils

        # Determine region
        if region is None and lat is not None and lon is not None:
            detected_region = GeographicUtils.get_region(lat, lon)
            region_lower = detected_region.lower()
        elif region is not None:
            region_lower = region.lower()
        else:
            region_lower = "global"

        # Map region to limits
        if region_lower not in cls.REGIONAL_LIMITS:
            logger.warning(
                f"Region '{region_lower}' not recognized. "
                f"Using global limits."
            )
            region_lower = "global"

        return cls.REGIONAL_LIMITS[region_lower]

    @classmethod
    def is_valid_temperature(
        cls,
        temp: float | None,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Validate temperature in °C.

        Args:
            temp: Temperature in °C
            lat: Latitude (for region detection)
            lon: Longitude (for region detection)
            region: Explicit region (overrides detection)
        """
        if temp is None:
            return True
        limits = cls.get_validation_limits(lat, lon, region)
        temp_min, temp_max = limits["temperature"]
        is_valid = temp_min <= temp <= temp_max

        # Register error in Prometheus
        if not is_valid and PROMETHEUS_AVAILABLE:
            from .geographic_utils import GeographicUtils

            detected_region = (
                region
                if region
                else (
                    GeographicUtils.get_region(lat, lon)
                    if lat and lon
                    else "global"
                )
            )
            VALIDATION_ERRORS.labels(
                region=detected_region, variable="temperature"
            ).inc()

        return is_valid

    @classmethod
    def is_valid_humidity(
        cls,
        humidity: float | None,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Validate relative humidity in %.
        """
        if humidity is None:
            return True
        limits = cls.get_validation_limits(lat, lon, region)
        hum_min, hum_max = limits["humidity"]
        return hum_min <= humidity <= hum_max

    @classmethod
    def is_valid_wind_speed(
        cls,
        wind: float | None,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Validate wind speed in m/s.
        """
        if wind is None:
            return True
        limits = cls.get_validation_limits(lat, lon, region)
        wind_min, wind_max = limits["wind"]
        return wind_min <= wind <= wind_max

    @classmethod
    def is_valid_precipitation(
        cls,
        precip: float | None,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Validate precipitation in mm.
        """
        if precip is None:
            return True
        limits = cls.get_validation_limits(lat, lon, region)
        precip_min, precip_max = limits["precipitation"]
        return precip_min <= precip <= precip_max

    @classmethod
    def is_valid_solar_radiation(
        cls,
        solar: float | None,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Validate solar radiation in MJ/m²/day.
        """
        if solar is None:
            return True
        limits = cls.get_validation_limits(lat, lon, region)
        solar_min, solar_max = limits["solar"]
        return solar_min <= solar <= solar_max

    @classmethod
    def validate_daily_data(
        cls,
        data: dict[str, Any],
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Validate complete daily data set with regional limits.

        Args:
            data: Dictionary with daily meteorological data
            lat: Latitude (for region detection)
            lon: Longitude (for region detection)
            region: Explicit region ("global", "brazil", "usa", "nordic")

        Returns:
            True if all valid fields are within limits

        Example:
            >>> data = {
            ...     'temp_max': 35.0,
            ...     'temp_min': 20.0,
            ...     'precipitation_sum': 10.5
            ... }
            >>> valid = WeatherValidationUtils.validate_daily_data(
            ...     data, lat=-23.5505, lon=-46.6333
            ... )
            >>> print(valid)
            True
        """
        validations = [
            cls.is_valid_temperature(data.get("temp_max"), lat, lon, region),
            cls.is_valid_temperature(data.get("temp_min"), lat, lon, region),
            cls.is_valid_temperature(data.get("temp_mean"), lat, lon, region),
            cls.is_valid_humidity(data.get("humidity_mean"), lat, lon, region),
            cls.is_valid_wind_speed(
                data.get("wind_speed_2m_mean"), lat, lon, region
            ),
            cls.is_valid_precipitation(
                data.get("precipitation_sum"), lat, lon, region
            ),
            cls.is_valid_solar_radiation(
                data.get("solar_radiation"), lat, lon, region
            ),
        ]
        return all(validations)


class WeatherAggregationUtils:
    """
    Utilities for meteorological data aggregation.

    Common methods to aggregate hourly data into daily
    following standard meteorological conventions.
    """

    @staticmethod
    def aggregate_temperature(
        values: list[float], method: str = "mean"
    ) -> float | None:
        """
        Aggregate temperature values.

        Args:
            values: List of temperatures
            method: 'mean', 'max', 'min'

        Returns:
            Aggregated temperature or None
        """
        if not values:
            return None

        valid_values = [v for v in values if v is not None]
        if not valid_values:
            return None

        if method == "mean":
            return float(np.mean(valid_values))
        elif method == "max":
            return float(np.max(valid_values))
        elif method == "min":
            return float(np.min(valid_values))
        else:
            logger.warning(f"Unknown method: {method}, using mean")
            return float(np.mean(valid_values))

    @staticmethod
    def aggregate_precipitation(values: list[float]) -> float | None:
        """
        Aggregate precipitation (always sum).

        Args:
            values: List of hourly precipitation

        Returns:
            Total precipitation or None
        """
        if not values:
            return None

        valid_values = [v for v in values if v is not None]
        if not valid_values:
            return None

        return float(np.sum(valid_values))

    @staticmethod
    def safe_division(
        numerator: float | None, denominator: float | None
    ) -> float | None:
        """
        Safe division that returns None if inputs invalid.

        Args:
            numerator: Numerator
            denominator: Denominator

        Returns:
            Division result or None
        """
        if numerator is None or denominator is None:
            return None
        if denominator == 0:
            return None
        return numerator / denominator

    @staticmethod
    def parse_rfc1123_date(date_str: str | None) -> datetime | None:
        """
        Parse RFC 1123 date format from HTTP headers.

        Used by weather API clients to parse Last-Modified and Expires headers.

        Args:
            date_str: Date string in RFC 1123 format
                     (e.g., "Tue, 16 Jun 2020 12:13:49 GMT")

        Returns:
            Parsed datetime (timezone-aware UTC) or None if parsing fails

        Example:
            >>> from weather_utils import WeatherAggregationUtils
            >>> dt = WeatherAggregationUtils.parse_rfc1123_date(
            ...     "Tue, 16 Jun 2020 12:13:49 GMT"
            ... )
            >>> print(dt)
            2020-06-16 12:13:49+00:00
        """
        if not date_str:
            return None
        try:
            dt = parsedate_to_datetime(date_str)
            # Ensure timezone-aware (UTC)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception as e:
            logger.warning(f"Failed to parse RFC1123 date '{date_str}': {e}")
            return None

    @staticmethod
    def calculate_cache_ttl(
        expires: datetime | None, default_ttl: int = 3600
    ) -> int:
        """
        Calculate cache TTL from Expires header.

        Used by weather API clients to determine how long to cache responses.

        Args:
            expires: Expiration datetime from Expires header
            default_ttl: Default TTL in seconds if no Expires header
                        (default: 3600 = 1 hour)

        Returns:
            TTL in seconds (min: 60s, max: 86400s = 24h)

        Example:
            >>> from datetime import datetime, timezone, timedelta
            >>> expires = datetime.now(timezone.utc) + timedelta(hours=2)
            >>> ttl = WeatherAggregationUtils.calculate_cache_ttl(expires)
            >>> print(f"Cache for {ttl} seconds")
            Cache for 7200 seconds
        """
        if not expires:
            return default_ttl

        now = datetime.now(timezone.utc)
        # Ensure expires is timezone-aware (UTC)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)

        ttl_seconds = int((expires - now).total_seconds())

        # Ensure TTL is positive and reasonable
        if ttl_seconds <= 0:
            return 60  # Minimum 1 minute
        if ttl_seconds > 86400:  # Max 24 hours
            return 86400

        return ttl_seconds

    @staticmethod
    def aggregate_hourly_to_daily(
        timeseries: list[dict[str, Any]],
        start_date: datetime,
        end_date: datetime,
        field_mapping: dict[str, str],
        timezone_utils=None,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Aggregate hourly weather data into daily buckets.

        Generic aggregation function used by multiple weather API clients
        (MET Norway, Open-Meteo, NWS) to convert hourly forecasts into
        daily data.

        Args:
            timeseries: List of hourly data points with 'time' and data
                       fields
            start_date: Start date for aggregation (timezone-aware)
            end_date: End date for aggregation (timezone-aware)
            field_mapping: Mapping of API field names to internal names
                          e.g., {'air_temperature': 'temperature_2m'}
            timezone_utils: Optional TimezoneUtils instance for timezone
                           handling (if None, uses datetime.date() for
                           grouping)

        Returns:
            Dictionary mapping dates (YYYY-MM-DD) to lists of hourly data

        Example:
            >>> from datetime import datetime, timezone
            >>> timeseries = [
            ...     {'time': '2024-01-15T12:00:00Z', 'air_temperature': 20.5},
            ...     {'time': '2024-01-15T13:00:00Z', 'air_temperature': 21.0},
            ... ]
            >>> result = WeatherAggregationUtils.aggregate_hourly_to_daily(
            ...     timeseries=timeseries,
            ...     start_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            ...     end_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            ...     field_mapping={'air_temperature': 'temperature_2m'}
            ... )
            >>> print(result.keys())
            dict_keys(['2024-01-15'])
        """
        daily_data: dict[str, list[dict[str, Any]]] = {}

        for entry in timeseries:
            try:
                time_str = entry.get("time")
                if not time_str:
                    continue

                # Parse timestamp
                if isinstance(time_str, str):
                    # Handle ISO 8601 format
                    if "T" in time_str:
                        dt = datetime.fromisoformat(
                            time_str.replace("Z", "+00:00")
                        )
                    else:
                        dt = datetime.fromisoformat(time_str)
                elif isinstance(time_str, datetime):
                    dt = time_str
                else:
                    logger.warning(f"Invalid time format: {time_str}")
                    continue

                # Make timezone-aware if needed
                if timezone_utils and hasattr(timezone_utils, "make_aware"):
                    dt = timezone_utils.make_aware(dt)
                elif dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                # Filter by date range
                if not (start_date <= dt <= end_date):
                    continue

                # Extract date key (YYYY-MM-DD)
                date_key = dt.date().isoformat()

                # Initialize daily bucket
                if date_key not in daily_data:
                    daily_data[date_key] = []

                # Map fields to internal names
                mapped_entry = {"time": dt}
                for api_field, internal_field in field_mapping.items():
                    if api_field in entry:
                        value = entry[api_field]
                        # Handle nested data structures
                        if isinstance(value, dict):
                            mapped_entry[internal_field] = value
                        else:
                            mapped_entry[internal_field] = value

                daily_data[date_key].append(mapped_entry)

            except Exception as e:
                logger.warning(f"Error processing hourly entry: {e}")
                continue

        return daily_data


class CacheUtils:
    """
    Utilities for HTTP response caching from climate APIs.

    Centralizes HTTP header parsing and TTL calculation for caching.
    Used by clients like MET Norway to implement conditional requests.
    """

    @staticmethod
    def parse_rfc1123_date(header: str | None) -> datetime | None:
        """
        Parse RFC1123 date format (used in Expires/Last-Modified headers).

        Args:
            header: Header string (e.g., "Tue, 16 Jun 2020 12:13:49 GMT")

        Returns:
            Timezone-aware UTC datetime or None

        Example:
            >>> expires = CacheUtils.parse_rfc1123_date(
            ...     "Tue, 16 Jun 2020 12:13:49 GMT"
            ... )
            >>> print(expires)
            2020-06-16 12:13:49+00:00
        """
        if not header:
            return None
        try:
            dt = datetime.strptime(header, "%a, %d %b %Y %H:%M:%S GMT")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning(f"Invalid RFC1123 date: {header}")
            return None

    @staticmethod
    def calculate_cache_ttl(
        expires_dt: datetime | None, default_ttl: int = 3600
    ) -> int:
        """
        Calculate TTL in seconds from Expires datetime.

        Args:
            expires_dt: Expiration datetime (timezone-aware)
            default_ttl: Default TTL if expires_dt is None (default: 3600s)

        Returns:
            TTL in seconds (min: 60s, max: 86400s = 24h)

        Example:
            >>> from datetime import datetime, timezone, timedelta
            >>> expires = datetime.now(timezone.utc) + timedelta(hours=2)
            >>> ttl = CacheUtils.calculate_cache_ttl(expires)
            >>> print(f"TTL: {ttl}s")
            TTL: 7200s
        """
        if not expires_dt:
            return default_ttl

        now = datetime.now(timezone.utc)
        # Ensure timezone-aware
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)

        ttl = int((expires_dt - now).total_seconds())
        # Cap between 60s and 86400s (24h)
        return max(60, min(ttl, 86400))


class METNorwayAggregationUtils:
    """
    Specialized utilities for MET Norway data aggregation.

    Moved from met_norway_client.py to centralize aggregation logic
    and avoid code duplication.

    Responsibilities:
    - Aggregate hourly data into daily
    - Calculate statistics (mean, max, min, sum)
    - Validate aggregated data consistency
    """

    @staticmethod
    def aggregate_hourly_to_daily(
        timeseries: List[Dict[str, Any]],
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Aggregate MET Norway hourly data into daily buckets.

        Args:
            timeseries: List of hourly entries from API
            start_date: Start date (timezone-aware)
            end_date: End date (timezone-aware)

        Returns:
            Dict mapping date -> raw aggregated data
        """
        from .geographic_utils import TimezoneUtils

        tz_utils = TimezoneUtils()
        daily_data: Dict[Any, Dict[str, Any]] = defaultdict(
            lambda: {
                "temp_values": [],
                "humidity_values": [],
                "wind_speed_values": [],
                "precipitation_1h": [],
                "precipitation_6h": [],
                "temp_max_6h": [],
                "temp_min_6h": [],
                "count": 0,
            }
        )

        # Ensure timezone-aware dates
        if start_date.tzinfo is None:
            start_date = tz_utils.make_aware(start_date)
        if end_date.tzinfo is None:
            end_date = tz_utils.make_aware(end_date)

        for entry in timeseries:
            try:
                time_str = entry.get("time")
                if not time_str:
                    continue

                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                date_key = dt.date()

                # Filter by period using safe comparison
                if not (start_date <= dt <= end_date):
                    continue

                day_data = daily_data[date_key]

                # Extract instantaneous values
                instant = (
                    entry.get("data", {}).get("instant", {}).get("details", {})
                )

                # Temperature
                if (temp := instant.get("air_temperature")) is not None:
                    day_data["temp_values"].append(temp)

                # Humidity
                if (humidity := instant.get("relative_humidity")) is not None:
                    day_data["humidity_values"].append(humidity)

                # Wind
                if (wind_speed := instant.get("wind_speed")) is not None:
                    day_data["wind_speed_values"].append(wind_speed)

                # Precipitation 1h
                next_1h = (
                    entry.get("data", {})
                    .get("next_1_hours", {})
                    .get("details", {})
                )
                precip_1h = next_1h.get("precipitation_amount")
                if precip_1h is not None:
                    day_data["precipitation_1h"].append(precip_1h)

                # Precipitation 6h
                next_6h = (
                    entry.get("data", {})
                    .get("next_6_hours", {})
                    .get("details", {})
                )
                precip_6h = next_6h.get("precipitation_amount")
                if precip_6h is not None:
                    day_data["precipitation_6h"].append(precip_6h)

                # Extreme temperatures 6h
                temp_max = next_6h.get("air_temperature_max")
                if temp_max is not None:
                    day_data["temp_max_6h"].append(temp_max)
                temp_min = next_6h.get("air_temperature_min")
                if temp_min is not None:
                    day_data["temp_min_6h"].append(temp_min)

                day_data["count"] += 1

            except Exception as e:
                logger.warning(
                    f"Error processing MET Norway hourly entry: {e}"
                )
                continue

        return dict(daily_data)

    @staticmethod
    def calculate_daily_aggregations(
        daily_raw_data: Dict[Any, Dict[str, Any]],
        weather_utils: WeatherConversionUtils,
    ) -> List[Any]:
        """
        Calculate final daily aggregations (mean, max, min, sum).

        Args:
            daily_raw_data: Raw data grouped by date
            weather_utils: WeatherConversionUtils instance

        Returns:
            List of aggregated daily records

        Improvements:
        - Precipitation 6h: weighted sum if multiple values
        - Wind conversion 10m → 2m using FAO-56
        - Detailed logging with logger.bind
        """
        result = []

        for date_key, day_values in daily_raw_data.items():
            try:
                # Mean temperature
                temp_mean = (
                    float(np.nanmean(day_values["temp_values"]))
                    if day_values["temp_values"]
                    else None
                )

                # Extreme temperatures: prefer 6h, fallback instant
                temp_max = (
                    float(np.nanmax(day_values["temp_max_6h"]))
                    if day_values["temp_max_6h"]
                    else (
                        float(np.nanmax(day_values["temp_values"]))
                        if day_values["temp_values"]
                        else None
                    )
                )

                temp_min = (
                    float(np.nanmin(day_values["temp_min_6h"]))
                    if day_values["temp_min_6h"]
                    else (
                        float(np.nanmin(day_values["temp_values"]))
                        if day_values["temp_values"]
                        else None
                    )
                )

                # Mean humidity
                humidity_mean = (
                    float(np.nanmean(day_values["humidity_values"]))
                    if day_values["humidity_values"]
                    else None
                )

                # Wind: convert 10m → 2m using FAO-56
                wind_10m_mean = (
                    float(np.nanmean(day_values["wind_speed_values"]))
                    if day_values["wind_speed_values"]
                    else None
                )
                wind_2m_mean = (
                    weather_utils.convert_wind_10m_to_2m(wind_10m_mean)
                    if wind_10m_mean is not None
                    else None
                )

                # Precipitation: prioritize 1h, fallback weighted 6h
                if day_values["precipitation_1h"]:
                    precipitation_sum = float(
                        np.sum(day_values["precipitation_1h"])
                    )
                elif day_values["precipitation_6h"]:
                    # IMPROVEMENT: Weighted sum if multiple values
                    if len(day_values["precipitation_6h"]) > 1:
                        # Average 6h values (assumes overlap)
                        precipitation_sum = float(
                            np.mean(day_values["precipitation_6h"])
                        )
                    else:
                        # Single value: use directly
                        precipitation_sum = float(
                            day_values["precipitation_6h"][0]
                        )
                    logger.bind(date=date_key).debug(
                        f"Precip 6h: {len(day_values['precipitation_6h'])} "
                        f"values -> {precipitation_sum:.2f}mm"
                    )
                else:
                    precipitation_sum = 0.0

                # Create daily record (generic dict)
                daily_record = {
                    "date": date_key,
                    "temp_max": temp_max,
                    "temp_min": temp_min,
                    "temp_mean": temp_mean,
                    "humidity_mean": humidity_mean,
                    "precipitation_sum": precipitation_sum,
                    "wind_speed_2m_mean": wind_2m_mean,
                }

                result.append(daily_record)

            except Exception as e:
                logger.bind(date=date_key).error(f"Error aggregating day: {e}")
                continue

        # Sort by date
        result.sort(key=lambda x: x["date"])
        return result

    @staticmethod
    def validate_daily_data(daily_data: List[Dict[str, Any]]) -> bool:
        """
        Validate consistency of aggregated daily data.

        Args:
            daily_data: List of daily records (dicts)

        Returns:
            True if data consistent, False otherwise

        Validations:
        - temp_max >= temp_min
        - 0 <= humidity <= 100
        - precipitation >= 0
        """
        if not daily_data:
            logger.warning("Empty daily data")
            return False

        issues = []

        for record in daily_data:
            date = record.get("date")

            # Check temperatures
            temp_max = record.get("temp_max")
            temp_min = record.get("temp_min")
            if (
                temp_max is not None
                and temp_min is not None
                and temp_max < temp_min
            ):
                issues.append(
                    f"Inconsistent temperature on {date}: "
                    f"max={temp_max} < min={temp_min}"
                )

            # Check humidity
            humidity = record.get("humidity_mean")
            if humidity is not None and not (0 <= humidity <= 100):
                issues.append(f"Humidity out of range on {date}: {humidity}%")

            # Check precipitation
            precip = record.get("precipitation_sum")
            if precip is not None and precip < 0:
                issues.append(f"Negative precipitation on {date}: {precip}mm")

        if issues:
            for issue in issues:
                logger.bind(validation="failed").warning(issue)
            return False

        logger.bind(validation="passed").debug(
            f"Daily data validated: {len(daily_data)} records OK"
        )
        return True


# NOTE: TimezoneUtils was moved to geographic_utils.py
# to avoid circular import (weather_utils uses geographic_utils)


class ElevationUtils:
    """
    Utilities for elevation-dependent calculations (FAO-56).

    IMPORTANT: Precise elevation is CRITICAL for ETo accuracy!

    Elevation impact on FAO-56 calculations:

    1. **Atmospheric Pressure (P)**:
       - Varies ~12% per 1000m elevation
       - Example: Sea level (0m) = 101.3 kPa
                  Brasilia (1172m) = 87.8 kPa (-13.3%)
                  La Paz (3640m) = 65.5 kPa (-35.3%)

    2. **Psychrometric Constant (γ)**:
       - Proportional to atmospheric pressure
       - γ = 0.665 × 10^-3 × P
       - Directly affects aerodynamic term of ETo

    3. **Solar Radiation**:
       - Increases ~10% per 1000m (less atmosphere)
       - Affects radiative component of ETo

    **Elevation Precision**:
    - Open-Meteo: ~7-30m (approximate)
    - OpenTopoData: ~1m (SRTM 30m/ASTER 30m)
    - Difference: up to 30m can cause ~0.3% error in ETo

    **Recommended Usage**:
    In eto_services.py:
        1. Get precise elevation: OpenTopoClient.get_elevation()
        2. Calculate factors: ElevationUtils.get_elevation_correction_factor()
        3. Pass factors to calculate_et0()

    References:
        Allen et al. (1998). FAO-56 Irrigation and Drainage Paper 56.
        Chapter 3: Equations 7, 8 (Pressure and Gamma).
    """

    @staticmethod
    def calculate_atmospheric_pressure(elevation: float) -> float:
        """
        Calculate atmospheric pressure from elevation (FAO-56 Eq. 7).

        Formula:
        P = 101.3 × [(293 - 0.0065 × z) / 293]^5.26

        Args:
            elevation: Elevation in meters

        Returns:
            Atmospheric pressure in kPa

        Raises:
            ValueError: If elevation < -1000m (physical limit)

        Reference:
            Allen et al. (1998). FAO-56, Chapter 3, Equation 7, page 31.
        """
        # Validation: physical limit (Dead Sea: -430m)
        if elevation < -1000:
            raise ValueError(
                f"Elevation too low: {elevation}m. Minimum: -1000m"
            )

        return 101.3 * ((293.0 - 0.0065 * elevation) / 293.0) ** 5.26

    @staticmethod
    def calculate_psychrometric_constant(elevation: float) -> float:
        """
        Calculate psychrometric constant from elevation (FAO-56 Eq. 8).

        Formula:
        γ = 0.665 × 10^-3 × P

        where P is atmospheric pressure (kPa) calculated from elevation.

        Args:
            elevation: Elevation in meters

        Returns:
            Psychrometric constant (kPa/°C)
        """
        pressure = ElevationUtils.calculate_atmospheric_pressure(elevation)
        return 0.000665 * pressure

    @staticmethod
    def adjust_solar_radiation_for_elevation(
        radiation_sea_level: float,
        elevation: float,
    ) -> float:
        """
        Adjust solar radiation for elevation.

        Solar radiation increases ~10% per 1000m elevation
        due to lower atmospheric absorption.

        Args:
            radiation_sea_level: Radiation at sea level (MJ/m²/day)
            elevation: Elevation in meters

        Returns:
            Adjusted radiation (MJ/m²/day)

        Note:
            This is an approximation. FAO-56 uses Ra (extraterrestrial)
            which already accounts for elevation via latitude and day of year.
        """
        factor = 1.0 + (elevation / 1000.0) * 0.10
        return radiation_sea_level * factor

    @staticmethod
    def clear_sky_radiation(Ra: np.ndarray, elevation: float) -> np.ndarray:
        """
        Calculate clear sky solar radiation (Rso) - FAO-56 Eq. 37.

        Solar radiation that would be received in absence of clouds.
        Used to calculate cloud cover factor (Rs/Rso).

        Args:
            Ra: Extraterrestrial radiation (MJ/m²/day) - array or scalar
            elevation: Site elevation (m)

        Returns:
            Rso: Clear sky radiation (MJ/m²/day) - array or scalar
        """
        Rso = (0.75 + 2e-5 * elevation) * Ra
        return Rso

    @staticmethod
    def net_longwave_radiation(
        Rs: np.ndarray,
        Ra: np.ndarray,
        Tmax: np.ndarray,
        Tmin: np.ndarray,
        ea: np.ndarray,
        elevation: float,
    ) -> np.ndarray:
        """
        Calculate net longwave radiation (Rnl) - FAO-56 Eq. 39.

        Longwave radiation emitted by surface and absorbed
        by atmosphere. Includes effects of temperature, humidity,
        cloud cover and elevation.

        Args:
            Rs: Measured global solar radiation (MJ/m²/day)
            Ra: Extraterrestrial radiation (MJ/m²/day)
            Tmax: Daily maximum temperature (°C)
            Tmin: Daily minimum temperature (°C)
            ea: Actual vapor pressure (kPa)
            elevation: Site elevation (m)

        Returns:
            Rnl: Net longwave radiation (MJ/m²/day)
        """
        # Stefan-Boltzmann constant [MJ K⁻⁴ m⁻² day⁻¹]
        sigma = 4.903e-9

        # Convert temperatures to Kelvin
        Tmax_K = Tmax + 273.15
        Tmin_K = Tmin + 273.15

        # Clear sky radiation (Rso) - FAO-56 Eq. 37
        Rso = ElevationUtils.clear_sky_radiation(Ra, elevation)

        # Cloud cover factor (fcd) - FAO-56 Eq. 39
        # Rs/Rso ratio with protection against division by zero
        ratio = np.divide(Rs, Rso, out=np.ones_like(Rs), where=Rso > 1e-6)
        fcd = np.clip(1.35 * ratio - 0.35, 0.3, 1.0)

        # Net longwave radiation - FAO-56 Eq. 39
        Rnl = (
            sigma
            * ((Tmax_K**4 + Tmin_K**4) / 2)
            * (0.34 - 0.14 * np.sqrt(np.maximum(ea, 0.01)))
            * fcd
        )

        return Rnl

    @staticmethod
    def get_elevation_correction_factor(elevation: float) -> dict[str, float]:
        """
        Calculate all elevation correction factors for FAO-56 ETo.

        Use precise elevation from OpenTopoData (1m) for maximum
        accuracy. Approximate elevations (Open-Meteo ~7-30m) may cause
        errors in final ETo.

        Args:
            elevation: Elevation in meters (preferably from OpenTopoData)

        Returns:
            Dictionary with FAO-56 correction factors:
            - pressure: Atmospheric pressure (kPa) - FAO-56 Eq. 7
            - gamma: Psychrometric constant (kPa/°C) - FAO-56 Eq. 8
            - solar_factor: Multiplicative factor for solar radiation
            - elevation: Elevation used (m)
        """
        pressure = ElevationUtils.calculate_atmospheric_pressure(elevation)
        gamma = ElevationUtils.calculate_psychrometric_constant(elevation)
        solar_factor = 1.0 + (elevation / 1000.0) * 0.10

        return {
            "pressure": pressure,
            "gamma": gamma,
            "solar_factor": solar_factor,
            "elevation": elevation,
        }

    @staticmethod
    def compare_elevation_impact(
        elevation_precise: float,
        elevation_approx: float,
    ) -> dict[str, Any]:
        """
        Compare impact of different elevation sources on FAO-56 factors.

        Use to quantify improvement when using OpenTopoData (1m) vs
        Open-Meteo (~7-30m).

        Args:
            elevation_precise: Precise elevation (OpenTopoData, 1m)
            elevation_approx: Approximate elevation (Open-Meteo, ~7-30m)

        Returns:
            Dictionary with comparative analysis:
            - elevation_diff_m: Absolute difference (m)
            - pressure_diff_kpa: Pressure difference (kPa)
            - pressure_diff_pct: Pressure difference (%)
            - gamma_diff_pct: Gamma difference (%)
            - eto_impact_pct: Estimated impact on ETo (%)

        Example:
            > # OpenTopoData (precise)
            > precise = 1172.0
            > # Open-Meteo (approximate)
            > approx = 1150.0

            > impact = ElevationUtils.compare_elevation_impact(
                precise, approx
            )
            > print(f"Elevation difference: {impact['elevation_diff_m']:.1f}m")
            > print(f"Impact on ETo: {impact['eto_impact_pct']:.3f}%")
            Elevation difference: 22.0m
            Impact on ETo: 0.245%

        Interpretation:
            - < 10m: Negligible impact (< 0.1% on ETo)
            - 10-30m: Small impact (0.1-0.3% on ETo)
            - > 30m: Significant impact (> 0.3% on ETo)
            - > 100m: Critical impact (> 1% on ETo)
        """
        factors_precise = ElevationUtils.get_elevation_correction_factor(
            elevation_precise
        )
        factors_approx = ElevationUtils.get_elevation_correction_factor(
            elevation_approx
        )

        elevation_diff = abs(elevation_precise - elevation_approx)
        pressure_diff = abs(
            factors_precise["pressure"] - factors_approx["pressure"]
        )
        pressure_diff_pct = (pressure_diff / factors_approx["pressure"]) * 100
        gamma_diff_pct = (
            abs(factors_precise["gamma"] - factors_approx["gamma"])
            / factors_approx["gamma"]
        ) * 100

        # Estimate impact on ETo (approximation based on sensitivity)
        # ETo is ~50% sensitive to pressure in aerodynamic term
        eto_impact_pct = pressure_diff_pct * 0.5

        return {
            "elevation_diff_m": elevation_diff,
            "elevation_precise_m": elevation_precise,
            "elevation_approx_m": elevation_approx,
            "pressure_precise_kpa": factors_precise["pressure"],
            "pressure_approx_kpa": factors_approx["pressure"],
            "pressure_diff_kpa": pressure_diff,
            "pressure_diff_pct": pressure_diff_pct,
            "gamma_diff_pct": gamma_diff_pct,
            "eto_impact_pct": eto_impact_pct,
            "recommendation": (
                "Negligible"
                if elevation_diff < 10
                else (
                    "Small"
                    if elevation_diff < 30
                    else (
                        "Significant" if elevation_diff < 100 else "Critical"
                    )
                )
            ),
        }
