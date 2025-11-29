"""
NASA POWER Sync Adapter - Synchronous wrapper for async client.

This adapter allows using the asynchronous NASA POWER client in synchronous code
(Celery tasks, sync endpoints).
"""

import asyncio
from datetime import datetime
from typing import Any

from loguru import logger

from .nasa_power_client import NASAPowerClient, NASAPowerConfig, NASAPowerData


class NASAPowerSyncAdapter:
    """
    Synchronous adapter for asynchronous NASAPowerClient.
    """

    def __init__(
        self, config: NASAPowerConfig | None = None, cache: Any | None = None
    ):
        """
        Initialize adapter.

        Args:
            config: NASA POWER configuration (optional)
            cache: Cache service (optional)
        """
        self.config = config or NASAPowerConfig()
        self.cache = cache
        logger.info("NASAPowerSyncAdapter initialized")

    def get_daily_data_sync(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
        community: str = "AG",
    ) -> list[NASAPowerData]:
        """
        Download NASA POWER data SYNCHRONOUSLY.

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)
            start_date: Start date
            end_date: End date
            community: NASA community ('AG' for Agronomy)

        Returns:
            List of daily data

        Example:
            >>> adapter = NASAPowerSyncAdapter()
            >>> data = adapter.get_daily_data_sync(
            ...     lat=-15.7939, lon=-47.8828,
            ...     start_date=datetime(2024, 1, 1),
            ...     end_date=datetime(2024, 1, 7)
            ... )
        """
        return asyncio.run(
            self._async_get_daily_data(
                lat=lat,
                lon=lon,
                start_date=start_date,
                end_date=end_date,
                community=community,
            )
        )

    async def _async_get_daily_data(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
        community: str,
    ) -> list[NASAPowerData]:
        """
        Internal asynchronous method.

        Creates client, makes request, closes connection.
        """
        client = NASAPowerClient(config=self.config, cache=self.cache)

        try:
            data = await client.get_daily_data(
                lat=lat,
                lon=lon,
                start_date=start_date,
                end_date=end_date,
                community=community,
            )

            logger.info(f"NASA POWER sync: {len(data)} records retrieved")
            return data

        finally:
            await client.close()

    def health_check_sync(self) -> bool:
        """
        Synchronous health check.

        Returns:
            bool: True if API is accessible
        """
        try:
            # Check if event loop is already running
            asyncio.get_running_loop()
            import nest_asyncio

            nest_asyncio.apply()
            return asyncio.run(self._async_health_check())
        except RuntimeError:
            # No loop running
            return asyncio.run(self._async_health_check())

    async def _async_health_check(self) -> bool:
        """Internal asynchronous health check."""
        client = NASAPowerClient(config=self.config, cache=self.cache)

        try:
            return await client.health_check()
        finally:
            await client.close()

    @staticmethod
    def get_info() -> dict[str, Any]:
        """
        Return NASA POWER source metadata.

        Returns:
            Dictionary with complete source metadata
        """
        return {
            "api": "NASA POWER",
            "url": "https://power.larc.nasa.gov/",
            "coverage": "Global",
            "period": "1981-present (daily delay: 2-7 days)",
            "resolution": "Daily (0.5° x 0.625° grid)",
            "range_limits": "7-30 days per request",
            "community": "AG (Agronomy) - UPPERCASE required",
            "variables": 7,
            "license": "Public Domain",
            "attribution": (
                "NASA Langley Research Center POWER Project "
                "funded through the NASA Earth Science Directorate "
                "Applied Science Program"
            ),
        }
