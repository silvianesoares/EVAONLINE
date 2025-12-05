"""
Sync Adapter for Open-Meteo Forecast API.

Converts asynchronous calls from OpenMeteoForecastClient to synchronous methods
for compatibility with Celery tasks and legacy scripts.

API: https://api.open-meteo.com/v1/forecast

Coverage: Global

- Forecast Data
- Start: Today - 29 days
- End: Today + 5 days (EVAonline standard)
- Total: 35 days

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
- Dynamic TTL: 1h (forecast), 6h (recent)
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Union

import pandas as pd
from loguru import logger

from backend.api.services.openmeteo_forecast.openmeteo_forecast_client import (
    OpenMeteoForecastClient,
)


class OpenMeteoForecastSyncAdapter:
    """
    Synchronous adapter for Open-Meteo Forecast API.

    Supports Redis cache (via ClimateCache) with fallback to local cache.
    """

    def __init__(self, cache: Any | None = None, cache_dir: str = ".cache"):
        """
        Initialize synchronous adapter.

        Args:
            cache: Optional ClimateCache instance (Redis)
            cache_dir: Directory for fallback cache (TTL: 6 hours)

        Features:
            - Recent data: today - 29 days
            - Forecast data: today + 5 days (standardized)
            - Best match model: Selects best available model
            - 10 climate variables with standardized units
            - Shared Redis cache between workers
        """
        self.cache = cache  # Redis cache (opcional)
        self.cache_dir = cache_dir

        cache_type = "Redis" if cache else "Local"
        logger.info(
            f"OpenMeteoForecastSyncAdapter initialized ({cache_type} cache, "
            f"-29d to +5d = 35d total)"
        )

    def get_daily_data_sync(
        self,
        lat: float,
        lon: float,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
    ) -> List[Dict[str, Any]]:
        """
        Download recent/future data SYNCHRONOUSLY.

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

        # Validation - Forecast API: -29d to +5d (35 days total)
        today = datetime.now().date()
        min_date = today - timedelta(days=29)
        max_date = today + timedelta(days=5)

        if start_date.date() < min_date:
            logger.warning(
                f"Forecast: adjusting start_date to {min_date} "
                f"(limit: today - 29 days)"
            )
            start_date = datetime.combine(min_date, datetime.min.time())

        if end_date.date() > max_date:
            logger.warning(
                f"Forecast: adjusting end_date to {max_date} "
                f"(limit: today + 5 days standardized)"
            )
            end_date = datetime.combine(max_date, datetime.min.time())

        # Execute async safely (same as Archive adapter)
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

        Uses best_match model, past_days=29, and wind_speed_unit=ms.
        """
        try:
            client = OpenMeteoForecastClient(
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
                f"Forecast: {len(records)} daily records "
                f"for ({lat:.4f}, {lon:.4f}) | "
                f"10 climate variables"
            )
            return records

        except Exception as e:
            logger.error(f"Forecast: error downloading data: {str(e)}")
            raise

    def get_forecast_sync(
        self,
        lat: float,
        lon: float,
        days: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Download future forecasts SYNCHRONOUSLY.
        """
        if not 1 <= days <= 5:
            msg = "Forecast: days must be between 1 and 5"
            logger.error(msg)
            raise ValueError(msg)

        # Calculate period
        start_date = datetime.now()
        end_date = start_date + timedelta(days=days - 1)

        return self.get_daily_data_sync(lat, lon, start_date, end_date)

    def health_check_sync(self) -> bool:
        """
        Check if Forecast API is accessible (synchronous).
        """
        try:
            # Tentar obter loop existente
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Loop já está rodando
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, self._async_health_check()
                    )
                    return future.result()
            else:
                # Loop exists but is not running
                return loop.run_until_complete(self._async_health_check())
        except RuntimeError:
            # No loop exists, create a new one
            return asyncio.run(self._async_health_check())

    async def _async_health_check(self) -> bool:
        """
        Async implementation of health check.

        Tests: Brasilia, current date, best_match model.
        """
        try:
            client = OpenMeteoForecastClient(
                cache=self.cache, cache_dir=self.cache_dir
            )

            # Test with reference coordinates (Brasilia)
            # Use current date (Forecast API always has it)
            today = datetime.now().date()
            response = await client.get_climate_data(
                lat=-15.7939,
                lng=-47.8828,
                start_date=str(today),
                end_date=str(today),
            )

            has_data = "climate_data" in response
            has_dates = "dates" in response.get("climate_data", {})
            return has_data and has_dates

        except Exception as e:
            logger.error(f"Forecast: health check failed: {str(e)}")
            return False

    @staticmethod
    def get_info() -> Dict[str, Any]:
        """
        Return information about the Forecast API data source.

        Includes: coverage, period, variables, license, model, units.

        Returns:
            Dictionary with complete source metadata
        """
        return OpenMeteoForecastClient.get_info()
