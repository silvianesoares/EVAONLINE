"""
Sync Adapter for Open-Meteo Archive API.

Converts asynchronous calls from OpenMeteoArchiveClient to synchronous methods
for compatibility with Celery tasks.

API: https://archive-api.open-meteo.com/v1/archive

Coverage: Global

- Archived Data
- Start: 1990/01/01
- End: Today - 2 days (EVAonline standard)

Variables (10):
- Temperature: max, mean, min (°C)
- Relative Humidity: max, mean, min (%)
- Wind Speed: mean at 10m (m/s)
- Shortwave Radiation: sum (MJ/m²)
- Precipitation: sum (mm)
- ET0 FAO Evapotranspiration (mm)

CACHE STRATEGY (Nov 2025):
- Redis cache via ClimateCache (recommended)
- Fallback: requests_cache local
- TTL: 24h (historical data is stable)
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Union

import pandas as pd
from loguru import logger

from .openmeteo_archive_client import (
    OpenMeteoArchiveClient,
)


class OpenMeteoArchiveSyncAdapter:
    """
    Synchronous adapter for Open-Meteo Archive API.

    Historical data: 1990-01-01 to today-2 days (historical_email mode)
    Models: best_match (best available model)
    Variables: 10 climate variables (T, RH, Wind, Solar, Precip, ET0)
    Wind unit: m/s (meters per second)
    Cache: Shared Redis (TTL 24h)
    """

    def __init__(self, cache: Any | None = None, cache_dir: str = ".cache"):
        """
        Initialize synchronous adapter.

        Args:
            cache: Optional ClimateCache instance (Redis)
            cache_dir: Directory for fallback cache (TTL: 24h)

        Features:
            - Historical data: 1990 to today-2 days (historical_email mode)
            - Best match model: Selects best available model
            - 10 climate variables with standardized units
            - Shared Redis cache between workers
        """
        self.cache = cache  # Redis cache (opcional)
        self.cache_dir = cache_dir

        cache_type = "Redis" if cache else "Local"
        logger.info(
            f"OpenMeteoArchiveSyncAdapter initialized ({cache_type} cache, "
            f"1990 to today-2 days)"
        )

    def get_daily_data_sync(
        self,
        lat: float,
        lon: float,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
    ) -> List[Dict[str, Any]]:
        """
        Download historical data SYNCHRONOUSLY.

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)
            start_date: Start date (str or datetime)
            end_date: End date (str or datetime)

        Returns:
            List of dictionaries with daily data
        """
        # Convert strings to datetime if needed
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date)

        # Execute async safely
        try:
            # Try to get existing loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Loop is already running (async server context)
                # Create new task in existing loop
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._async_get_data(lat, lon, start_date, end_date),
                    )
                    return future.result()
            else:
                # Loop exists but is not running
                return loop.run_until_complete(
                    self._async_get_data(lat, lon, start_date, end_date)
                )
        except RuntimeError:
            # No loop exists, create a new one
            return asyncio.run(
                self._async_get_data(lat, lon, start_date, end_date)
            )

    async def _async_get_data(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
    ) -> List[Dict[str, Any]]:
        """
        Internal async implementation.

        Uses best_match model and wind_speed_unit=ms for consistency.
        """
        try:
            client = OpenMeteoArchiveClient(
                cache=self.cache, cache_dir=self.cache_dir
            )

            response = await client.get_climate_data(
                lat=lat,
                lng=lon,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )

            # Extract data from response
            daily_data = response["climate_data"]
            dates = pd.to_datetime(daily_data["dates"])

            # Convert to list of dictionaries
            records = []
            for i, date in enumerate(dates):
                record = {"date": date.date()}

                # Add all available variables
                for key, values in daily_data.items():
                    if key != "dates" and isinstance(values, list):
                        record[key] = values[i] if i < len(values) else None

                records.append(record)

            logger.info(
                f"Archive: obtained {len(records)} daily records "
                f"for ({lat:.4f}, {lon:.4f}) | "
                f"10 climate variables"
            )
            return records

        except Exception as e:
            logger.error(f"Archive: error downloading data: {str(e)}")
            raise

    def health_check_sync(self) -> bool:
        """
        Check if Archive API is accessible (synchronous).

        Tests with Brasilia coordinates and safe historical date
        (1 year ago).
        Validates response with best_match model.

        Returns:
            True if API is working, False otherwise
        """
        return asyncio.run(self._async_health_check())

    async def _async_health_check(self) -> bool:
        """
        Async implementation of health check.

        Tests: Brasilia, 1990-01-01, best_match model.
        """
        try:
            client = OpenMeteoArchiveClient(
                cache=self.cache, cache_dir=self.cache_dir
            )

            # Test with reference coordinates (Brasilia)
            # Use safe historical date (start of validation period)
            test_date = datetime(1990, 1, 1).date()
            response = await client.get_climate_data(
                lat=-15.7939,
                lng=-47.8828,
                start_date=str(test_date),
                end_date=str(test_date),
            )

            has_data = "climate_data" in response
            has_dates = "dates" in response.get("climate_data", {})
            return has_data and has_dates

        except Exception as e:
            logger.error(f"Archive: health check failed: {str(e)}")
            return False

    @staticmethod
    def get_info() -> Dict[str, Any]:
        """
        Return information about the Archive API data source.

        Includes: coverage, period, variables, license, model, units.

        Returns:
            Dictionary with complete source metadata
        """
        return OpenMeteoArchiveClient.get_info()
