"""
NASA POWER Sync Adapter - Synchronous wrapper for async client.

Este adapter permite usar o cliente assíncrono NASA POWER em código síncrono
(Celery tasks, sync endpoints).
"""

import asyncio
from datetime import datetime
from typing import Any

from loguru import logger

from .nasa_power_client import NASAPowerClient, NASAPowerConfig, NASAPowerData


class NASAPowerSyncAdapter:
    """
    Adapter síncrono para NASAPowerClient assíncrono.
    """

    def __init__(
        self, config: NASAPowerConfig | None = None, cache: Any | None = None
    ):
        """
        Inicializa adapter.

        Args:
            config: Configuração NASA POWER (opcional)
            cache: Cache service (opcional)
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
        Baixa dados NASA POWER de forma SÍNCRONA.

        Args:
            lat: Latitude (-90 a 90)
            lon: Longitude (-180 a 180)
            start_date: Data inicial
            end_date: Data final
            community: Comunidade NASA ('AG' para Agronomia)

        Returns:
            Lista de dados diários

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
        Método assíncrono interno.

        Cria cliente, faz requisição, fecha conexão.
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

            logger.info(f"✅ NASA POWER sync: {len(data)} registros obtidos")
            return data

        finally:
            await client.close()

    def health_check_sync(self) -> bool:
        """
        Health check síncrono.

        Returns:
            bool: True se API está acessível
        """
        try:
            # Verificar se já há event loop rodando
            asyncio.get_running_loop()
            import nest_asyncio

            nest_asyncio.apply()
            return asyncio.run(self._async_health_check())
        except RuntimeError:
            # Não há loop rodando
            return asyncio.run(self._async_health_check())

    async def _async_health_check(self) -> bool:
        """Health check assíncrono interno."""
        client = NASAPowerClient(config=self.config, cache=self.cache)

        try:
            return await client.health_check()
        finally:
            await client.close()

    @staticmethod
    def get_info() -> dict[str, Any]:
        """
        Retorna metadados da fonte NASA POWER.

        Returns:
            Dicionário com metadados completos da fonte
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
