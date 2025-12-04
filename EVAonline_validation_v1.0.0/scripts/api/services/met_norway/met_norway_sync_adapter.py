"""
Synchronous adapter for MET Norway 2.0.
GLOBAL with DAILY data and REGIONAL STRATEGY.

- Forecast API with GLOBAL coverage
- Start: Today
- End: Today + 5 days (EVAonline standard)
- Total: 6 days of forecast

This adapter allows using the asynchronous MET Norway client
in synchronous code, facilitating integration with data_download.py.

Features:
GLOBAL (any coordinates worldwide)
DAILY data aggregated from hourly data
REGIONAL STRATEGY for optimized quality:
   - Nordic (NO/SE/FI/DK/Baltics): Temp + Humidity + Precipitation
     (1km MET Nordic, radar + crowdsourced bias correction)
   - Rest of World: Temp + Humidity only
     (9km ECMWF, skip precipitation - use Open-Meteo instead)
Variables optimized for ETo FAO-56
No coverage limits

License: CC-BY 4.0 - Display in all visualizations with MET Norway data
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from scripts.api.services.geographic_utils import GeographicUtils

from .met_norway_client import (
    METNorwayDailyData,
    METNorwayClient,
    METNorwayConfig,
)


class METNorwaySyncAdapter:
    """
    Synchronous adapter for MET Norway.
    Use only "MET Norway" when referring to MET Norway.
    """

    def __init__(
        self,
        config: METNorwayConfig | None = None,
        cache: Any | None = None,
    ):
        """
        Initialize GLOBAL MET Norway adapter.
        """
        self.config = config or METNorwayConfig()
        self.cache = cache
        self._client: METNorwayClient | None = None  # Simple pool for reuse
        logger.info("METNorwaySyncAdapter initialized (GLOBAL)")

    async def _get_client(self) -> METNorwayClient:
        """Get or create client from pool."""
        if self._client is None:
            self._client = METNorwayClient(
                config=self.config, cache=self.cache
            )
        return self._client

    def get_daily_data_sync(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
        altitude: float | None = None,
        timezone: str | None = None,
    ) -> list[METNorwayDailyData]:
        """
        Fetch DAILY data SYNCHRONOUSLY (compatible with Celery/sync code).

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)
            start_date: Start date
            end_date: End date
            altitude: Elevation in meters (optional)
            timezone: Timezone (optional)

        Returns:
            List of daily data

        """
        return asyncio.run(
            self._async_get_daily_data(
                lat=lat,
                lon=lon,
                start_date=start_date,
                end_date=end_date,
                altitude=altitude,
                timezone=timezone,
            )
        )

    async def get_daily_data(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
        altitude: float | None = None,
        timezone: str | None = None,
    ) -> list[METNorwayDailyData]:
        """
        Fetch DAILY data ASYNCHRONOUSLY (for FastAPI/Celery async tasks).

        Use this method in asynchronous contexts.
        For synchronous code, use get_daily_data_sync().
        """
        return await self._async_get_daily_data(
            lat=lat,
            lon=lon,
            start_date=start_date,
            end_date=end_date,
            altitude=altitude,
            timezone=timezone,
        )

    async def _async_get_daily_data(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
        altitude: float | None = None,
        timezone: str | None = None,
    ) -> list[METNorwayDailyData]:
        """
        Fetch DAILY data asynchronously.

        USAGE:
            # In Celery task (async def)
            adapter = METNorwaySyncAdapter()
            data = await adapter.get_daily_data(...)

            # In synchronous code (if necessary)
            data = asyncio.run(adapter.get_daily_data(...))
        """
        client = await self._get_client()  # Reuse client from pool

        try:
            # Basic validations - GeographicUtils (SINGLE SOURCE OF TRUTH)
            if not GeographicUtils.is_valid_coordinate(lat, lon):
                msg = f"Coordenadas inválidas: ({lat}, {lon})"
                raise ValueError(msg)

            # Enforce 5-day forecast limit
            delta_days = (end_date - start_date).days
            if delta_days > 5:
                end_date = start_date + timedelta(days=5)
                logger.bind(lat=lat, lon=lon).warning(
                    f"Forecast horizon adjusted to 5 days: {delta_days} -> 5"
                )

            # Log detected region with get_region
            # (4 tiers: usa/nordic/brazil/global)
            region = GeographicUtils.get_region(lat, lon)

            # Regional labels for logging
            region_labels = {
                "nordic": "NORDIC (1km + radar)",
                "usa": "USA (NOAA/NWS)",
                "brazil": "BRAZIL (Xavier et al. validation)",
                "global": "GLOBAL (9km ECMWF)",
            }
            region_label = region_labels.get(region, "UNKNOWN")

            # Specific log for Brazil
            if region == "brazil":
                logger.bind(lat=lat, lon=lon).debug(
                    "Brazil region: Using Xavier et al. validations "
                    "(Open-Meteo fallback for historical precipitation)"
                )

            logger.bind(lat=lat, lon=lon, region=region_label).info(
                f"Querying MET Norway API: "
                f"({lat}, {lon}, {altitude}m) - {region_label}"
            )

            # Fetch DAILY data (aggregated from hourly)
            # Client automatically filters variables by region
            daily_data = await client.get_daily_forecast(
                lat=lat,
                lon=lon,
                start_date=start_date,
                end_date=end_date,
                altitude=altitude,
                timezone=timezone,
                variables=None,
            )

            if not daily_data:
                logger.bind(lat=lat, lon=lon).warning(
                    "MET Norway returned empty data"
                )
                return []

            logger.bind(lat=lat, lon=lon).info(
                f"MET Norway: {len(daily_data)} days "
                f"retrieved (from {start_date.date()} to {end_date.date()})"
            )

            return daily_data

        except Exception as e:
            logger.bind(lat=lat, lon=lon).error(
                f"Error fetching MET Norway data: {e}"
            )
            raise

    def health_check_sync(self) -> bool:
        """
        Synchronous health check (tests with GLOBAL coordinates).

        Returns:
            bool: True if API is accessible
        """
        return asyncio.run(self._async_health_check())

    async def _async_health_check(self) -> bool:
        """
        Internal asynchronous health check.

        Tests with Brasilia (Brazil) coordinates to validate
        that it is truly GLOBAL.
        """
        client = await self._get_client()

        try:
            # Teste com Brasília (fora da Europa, prova que é GLOBAL!)
            is_healthy = await client.health_check()

            if is_healthy:
                logger.info("MET Norway health check: OK (GLOBAL)")
            else:
                logger.error("MET Norway health check: FAIL")

            return is_healthy

        except Exception as e:
            logger.error(f"MET Norway health check failed: {e}")
            return False

    def get_attribution(self) -> str:
        """
        Return attribution string for visualizations (CC-BY 4.0).

        Use in Dash plots:
            fig.add_annotation(
                text=adapter.get_attribution(),
                xref="paper", yref="paper",
                x=1.0, y=-0.1,
                showarrow=False,
                font=dict(size=10, color="gray"),
            )

        Returns:
            str: Attribution text
        """
        return "Weather data from MET Norway (CC-BY 4.0)"

    def get_coverage_info(self) -> dict:
        """
        Return information about GLOBAL coverage with regional quality.

        Returns:
            dict: Coverage information with quality tiers
        """
        return {
            "adapter": "METNorwaySyncAdapter",
            "coverage": "GLOBAL with regional quality optimization",
            "bbox": {
                "lon_min": -180,
                "lat_min": -90,
                "lon_max": 180,
                "lat_max": 90,
            },
            "quality_tiers": {
                "nordic": {
                    "region": "Norway, Denmark, Sweden, Finland, Baltics",
                    "bbox": GeographicUtils.NORDIC_BBOX,
                    # Uses constant from geographic_utils
                    "resolution": "1 km",
                    "model": "MEPS 2.5km + MET Nordic downscaling",
                    "updates": "Hourly",
                    "post_processing": (
                        "Extensive (radar + Netatmo crowdsourced)"
                    ),
                    "variables": [
                        "air_temperature_max",
                        "air_temperature_min",
                        "air_temperature_mean",
                        "relative_humidity_mean",
                        "wind_speed_10m_mean",
                        "precipitation_sum",
                    ],
                    "precipitation_quality": (
                        "Very High (radar + bias correction)"
                    ),
                },
                "brazil": {
                    "region": "Brazil",
                    "bbox": GeographicUtils.BRAZIL_BBOX,
                    "resolution": "11 km (Open-Meteo fallback recommended)",
                    "model": "ECMWF IFS",
                    "updates": "4x per day",
                    "variables": [
                        "air_temperature_max",
                        "air_temperature_min",
                        "air_temperature_mean",
                        "relative_humidity_mean",
                    ],
                    "precipitation_quality": (
                        "Lower (excluded - use Open-Meteo instead)"
                    ),
                    "note": (
                        "Use NASA POWER for historical data; "
                        "MET Norway for forecast only (no precipitation). "
                        "Xavier et al. validation thresholds applied."
                    ),
                },
                "global": {
                    "region": "Rest of World",
                    "resolution": "9 km",
                    "model": "ECMWF IFS",
                    "updates": "4x per day",
                    "post_processing": "Minimal",
                    "variables": [
                        "air_temperature_max",
                        "air_temperature_min",
                        "air_temperature_mean",
                        "relative_humidity_mean",
                    ],
                    "precipitation_quality": (
                        "Lower (use Open-Meteo instead)"
                    ),
                    "note": (
                        "Precipitation excluded - "
                        "use Open-Meteo for better global quality"
                    ),
                },
            },
            "data_type": "Forecast only (no historical data)",
            "forecast_horizon": "Up to 5 days ahead (standardized)",
            "update_frequency": "Every 6 hours",
            "license": "CC-BY 4.0 (attribution required)",
            "attribution": "Weather data from MET Norway",
        }
