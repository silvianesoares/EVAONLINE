"""
Synchronous Adapter for NWS Stations Client (National Weather Service).

This adapter allows using the asynchronous NWS Stations client in
synchronous code, facilitating integration with data_download.py which
uses Celery (synchronous).

Pattern followed: NASAPowerSyncAdapter

Features:
- Conversion of hourly NWS data to daily aggregations (pandas)
- Monitoring of known issues (delays, nulls, rounding)
- Filtering of delayed observations (optional)
- Detailed data quality logging
- Integrated Redis cache (optional)

Known Issues Handled:
- Delayed observations (>20min MADIS delay) - optionally filtered
- Null values in temperatures (max/min outside CST) - skipped
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

from .nws_stations_client import NWSStationsClient, NWSStationsConfig


class _FallbackGeographicUtils:
    """Fallback GeographicUtils when the real one is not available."""

    @staticmethod
    def is_in_usa(lat: float, lon: float) -> bool:
        """Fallback: simple bounding box for USA."""
        return -125 <= lon <= -66 and 24 <= lat <= 50


# Import GeographicUtils for coverage validation
GeographicUtils: type = _FallbackGeographicUtils
try:
    from scripts.api.services.geographic_utils import (
        GeographicUtils,  # type: ignore[no-redef]
    )
except ImportError:
    try:
        from ..geographic_utils import (
            GeographicUtils,
        )  # type: ignore[no-redef]
    except ImportError:
        logger.warning(
            "GeographicUtils not found - using fallback for USA coverage"
        )


class DailyNWSData:
    """Aggregated daily NWS data (converted from hourly data)."""

    def __init__(
        self,
        date: datetime,
        temp_min: float | None = None,
        temp_max: float | None = None,
        temp_mean: float | None = None,
        humidity: float | None = None,
        wind_speed: float | None = None,
    ):
        self.date = date
        self.temp_min = temp_min
        self.temp_max = temp_max
        self.temp_mean = temp_mean
        self.humidity = humidity
        self.wind_speed = wind_speed


class NWSStationsSyncAdapter:
    """
    Synchronous adapter for asynchronous NWSStationsClient.

    Converts synchronous calls to asynchronous using asyncio.run(),
    maintaining compatibility with legacy code (Celery tasks).

    Responsibilities:
    - Simple synchronous interface
    - Conversion of hourly NWS data to daily aggregations (pandas)
    - Mapping of NWS fields → EVAonline standard
    - Filtering of delayed observations (optional)
    - Detailed data quality logging
    - Graceful error handling

    NWS API Details:
    - Returns HOURLY data from weather stations
    - We need to aggregate to DAILY using pandas
    - Coverage: USA Extended (including Alaska, Hawaii)
    - No authentication required
    - Known issues: delays (MADIS), nulls (CST), rounding (<0.4")

    Args:
        config: NWS Stations configuration (optional)
        cache: Cache service (optional)
        filter_delayed: Filter delayed observations >20min (default: False)
    """

    def __init__(
        self,
        config: NWSStationsConfig | None = None,
        cache: Any | None = None,
        filter_delayed: bool = False,
    ):
        """
        Initialize adapter.

        Args:
            config: NWS Stations configuration (optional)
            cache: Cache service (optional)
            filter_delayed: If True, remove observations with delay >20min
        """
        self.config = config or NWSStationsConfig()
        self.cache = cache
        self.filter_delayed = filter_delayed
        logger.info(
            f"NWSStationsSyncAdapter initialized "
            f"(filter_delayed={filter_delayed})"
        )

    def get_daily_data_sync(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
    ) -> list[DailyNWSData]:
        """
        Fetch daily data synchronously.

        Internally:
        1. Call NWS API (returns hourly data)
        2. Group by day
        3. Calculate min, max, mean
        4. Return as DailyNWSData

        Args:
            lat: Latitude (-90 to 90, must be in USA coverage)
            lon: Longitude (-180 to 180, must be in USA coverage)
            start_date: Start date
            end_date: End date

        Returns:
            List[DailyNWSData]: Daily data

        Raises:
            ValueError: If coordinates outside USA
            Exception: If request fails
        """
        logger.debug(
            f"NWS Sync request: lat={lat}, lon={lon}, "
            f"dates={start_date.date()} to {end_date.date()}"
        )

        # Execute async function synchronously
        return asyncio.run(
            self._async_get_daily_data(
                lat=lat,
                lon=lon,
                start_date=start_date,
                end_date=end_date,
            )
        )

    async def _async_get_daily_data(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
    ) -> list[DailyNWSData]:
        """
        Internal asynchronous method.

        Flow:
        1. Create NWS Stations client
        2. Validate coverage
        3. Find nearest station
        4. Fetch station observations
        5. Group by day
        6. Calculate aggregations (min, max, mean)
        7. Return as DailyNWSData
        """
        client = NWSStationsClient(config=self.config, cache=self.cache)

        try:
            # 1. Validate USA coverage
            if not GeographicUtils.is_in_usa(lat=lat, lon=lon):
                logger.warning(
                    f"Coordinates ({lat}, {lon}) outside NWS coverage (USA)"
                )
                msg = f"NWS: Coordinates ({lat}, {lon}) outside USA coverage"
                raise ValueError(msg)

            # 2. Find nearest active station
            logger.info(
                f"Searching for nearest active NWS station: " f"({lat}, {lon})"
            )
            station = await client.find_nearest_active_station(
                lat=lat, lon=lon, max_candidates=5
            )

            if not station:
                logger.warning("No NWS station found")
                return []
            logger.info(
                f"Using station: {station.station_id} ({station.name}) - "
                f"{station.distance_km:.1f} km away - "
                f"elev: {station.elevation_m or 'N/A'} m - "
                f"active: {'YES' if station.is_active else 'NO (fallback)'}"
            )

            # 3. Calculate and validate date range (NWS 7-day limit)
            today_utc = datetime.utcnow().date()
            max_start = today_utc - timedelta(days=6)  # 7 days including today

            requested_start = start_date.date()
            if requested_start < max_start:
                logger.warning(
                    f"NWS only has 7 days of history - adjusting "
                    f"start_date from {requested_start} to {max_start}"
                )
                start_date = datetime.combine(
                    max_start, datetime.min.time(), tzinfo=timezone.utc
                )
            else:
                if start_date.tzinfo is None:
                    start_date = start_date.replace(tzinfo=timezone.utc)

            days_back = (end_date.date() - start_date.date()).days + 1
            days_back = min(days_back, 7)  # Enforce API limit

            # 4. Fetch station observations
            observations = await client.get_observations(
                station_id=station.station_id,
                days_back=days_back,
            )

            if not observations:
                logger.warning("NWS returned empty data")
                return []

            logger.info(
                f"NWS: {len(observations)} hourly observations retrieved"
            )

            # Filter delayed observations (if configured)
            if self.filter_delayed:
                original_count = len(observations)
                observations = [
                    obs for obs in observations if not obs.is_delayed
                ]
                filtered_count = original_count - len(observations)
                if filtered_count > 0:
                    threshold = self.config.observation_delay_threshold
                    logger.warning(
                        f"Filtered {filtered_count} delayed observations "
                        f"(>{threshold}min)"
                    )

            # Log data quality
            temps = [
                o.temp_celsius
                for o in observations
                if o.temp_celsius is not None
            ]
            if len(observations) > 0:
                completeness = len(temps) / len(observations) * 100
                logger.info(
                    f"Quality: {len(temps)}/{len(observations)} "
                    f"({completeness:.1f}%) "
                    f"valid temperatures"
                )
            else:
                logger.warning("No observations available after filtering")
                return []

            # 5. Aggregate observations to daily using client's built-in method
            daily_data = client.aggregate_to_daily(observations, station)

            # Convert DailyEToData to DailyNWSData format
            daily_nws_data = [
                DailyNWSData(
                    date=d.date,
                    temp_min=d.T_min,
                    temp_max=d.T_max,
                    temp_mean=d.T_mean,
                    humidity=d.RH_mean,
                    wind_speed=d.wind_2m_mean_ms,
                )
                for d in daily_data
            ]

            logger.info(
                f"NWS sync: {len(daily_nws_data)} days aggregated "
                f"(from {len(observations)} observations)"
            )

            return daily_nws_data

        except Exception as e:
            logger.error(f"Error fetching NWS data: {e}")
            raise

        finally:
            await client.close()

    def health_check_sync(self) -> bool:
        """
        Synchronous health check.

        Tests connectivity with NWS API.

        Returns:
            bool: True if API is accessible
        """
        return asyncio.run(self._async_health_check())

    async def _async_health_check(self) -> bool:
        """
        Internal asynchronous health check.

        Tests with default coordinates (NYC).
        """
        client = NWSStationsClient(config=self.config, cache=self.cache)

        try:
            # Test with NYC (always in coverage)
            station = await client.find_nearest_active_station(
                lat=40.7128, lon=-74.0060, max_candidates=1
            )

            is_healthy = station is not None
            status_icon = "OK" if is_healthy else "FAIL"
            logger.info(f"NWS health check: {status_icon}")
            return is_healthy

        except Exception as e:
            logger.error(f"NWS health check failed: {e}")
            return False

        finally:
            await client.close()
