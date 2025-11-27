"""
Adapter síncrono para MET Norway 2.0.

GLOBAL com dados DIÁRIOS e ESTRATÉGIA REGIONAL.

Este adapter permite usar o cliente assíncrono MET Norway
em código síncrono, facilitando a integração com data_download.py.

Características:
GLOBAL (qualquer coordenada do mundo)
Dados DIÁRIOS agregados de dados horários
ESTRATÉGIA REGIONAL para qualidade otimizada:
   - Nordic (NO/SE/FI/DK/Baltics): Temp + Humidity + Precipitation
     (1km MET Nordic, radar + crowdsourced bias correction)
   - Rest of World: Temp + Humidity only
     (9km ECMWF, skip precipitation - use Open-Meteo instead)
Variáveis otimizadas para ETo FAO-56
Sem limite de cobertura

Licença: CC-BY 4.0 - Exibir em todas as visualizações com dados MET Norway
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from validation_logic_eto.api.services.geographic_utils import GeographicUtils

from .met_norway_client import (
    METNorwayDailyData,
    METNorwayClient,
    METNorwayConfig,
)


class METNorwaySyncAdapter:
    """
    Adapter síncrono para MET Norway.
    Usar somente "MET Norway" para MET Norway.
    """

    def __init__(
        self,
        config: METNorwayConfig | None = None,
        cache: Any | None = None,
    ):
        """
        Inicializa adapter GLOBAL do MET Norway.
        """
        self.config = config or METNorwayConfig()
        self.cache = cache
        self._client: METNorwayClient | None = (
            None  # Pool simples para reutilização
        )
        logger.info("🌍 METNorwaySyncAdapter initialized (GLOBAL)")

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
        Busca dados DIÁRIOS de forma SÍNCRONA (compatível com Celery/sync code).

        Args:
            lat: Latitude (-90 a 90)
            lon: Longitude (-180 a 180)
            start_date: Data inicial
            end_date: Data final
            altitude: Elevação em metros (opcional)
            timezone: Fuso horário (opcional)

        Returns:
            Lista de dados diários

        Example:
            >>> adapter = METNorwaySyncAdapter()
            >>> data = adapter.get_daily_data_sync(
            ...     lat=60.0, lon=10.0,
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
        Busca dados DIÁRIOS de forma ASSÍNCRONA (para FastAPI/Celery async tasks).

        Use este método em contextos assíncronos.
        Para código síncrono, use get_daily_data_sync().
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
        Busca dados DIÁRIOS de forma assíncrona.

        USO:
            # Em Celery task (async def)
            adapter = METNorwaySyncAdapter()
            data = await adapter.get_daily_data(...)

            # Em código síncrono (se necessário)
            data = asyncio.run(adapter.get_daily_data(...))
        """
        client = await self._get_client()  # Reutiliza client do pool

        try:
            # Validações básicas - GeographicUtils (SINGLE SOURCE OF TRUTH)
            if not GeographicUtils.is_valid_coordinate(lat, lon):
                msg = f"Coordenadas inválidas: ({lat}, {lon})"
                raise ValueError(msg)

            # Enforcement de 5 dias de previsão
            delta_days = (end_date - start_date).days
            if delta_days > 5:
                end_date = start_date + timedelta(days=5)
                logger.bind(lat=lat, lon=lon).warning(
                    f"Horizonte ajustado para 5 dias: {delta_days} -> 5"
                )

            # Log região detectada com get_region
            # (4 tiers: usa/nordic/brazil/global)
            region = GeographicUtils.get_region(lat, lon)

            # Labels regionais para logging
            region_labels = {
                "nordic": "NORDIC (1km + radar)",
                "usa": "USA (NOAA/NWS)",
                "brazil": "BRAZIL (Xavier et al. validation)",
                "global": "GLOBAL (9km ECMWF)",
            }
            region_label = region_labels.get(region, "UNKNOWN")

            # Log específico para Brasil
            if region == "brazil":
                logger.bind(lat=lat, lon=lon).debug(
                    "Região BR: Usando validações Xavier et al. "
                    "(Open-Meteo fallback para precip histórica)"
                )

            logger.bind(lat=lat, lon=lon, region=region_label).info(
                f"📡 Consultando MET Norway API: "
                f"({lat}, {lon}, {altitude}m) - {region_label}"
            )

            # Buscar dados DIÁRIOS (agregados de horários)
            # Cliente automaticamente filtra variáveis por região
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
                    "⚠️  MET Norway retornou dados vazios"
                )
                return []

            logger.bind(lat=lat, lon=lon).info(
                f"✅ MET Norway: {len(daily_data)} dias "
                f"obtidos (de {start_date.date()} a {end_date.date()})"
            )

            return daily_data

        except Exception as e:
            logger.bind(lat=lat, lon=lon).error(
                f"❌ Erro ao buscar dados MET Norway: {e}"
            )
            raise

    def health_check_sync(self) -> bool:
        """
        Health check síncrono (testa com coordenada GLOBAL).

        Returns:
            bool: True se API está acessível
        """
        return asyncio.run(self._async_health_check())

    async def _async_health_check(self) -> bool:
        """
        Health check assíncrono interno.

        Testa com coordenadas de Brasília (Brasil) para validar
        que é realmente GLOBAL.
        """
        client = await self._get_client()

        try:
            # Teste com Brasília (fora da Europa, prova que é GLOBAL!)
            is_healthy = await client.health_check()

            if is_healthy:
                logger.info("🏥 MET Norway health check: ✅ OK (GLOBAL)")
            else:
                logger.error("🏥 MET Norway health check: ❌ FAIL")

            return is_healthy

        except Exception as e:
            logger.error(f"🏥 MET Norway health check failed: {e}")
            return False

    def get_attribution(self) -> str:
        """
        Retorna string de atribuição para visualizações (CC-BY 4.0).

        Use em plots Dash:
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
        Retorna informações sobre cobertura GLOBAL com qualidade regional.

        Returns:
            dict: Informações de cobertura com quality tiers
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
                    # Usa constant de geographic_utils
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
