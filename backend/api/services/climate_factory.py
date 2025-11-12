"""
Factory para criar clientes climáticos com cache injetado (Redis).

Fornece método centralizado para instanciar clientes de APIs climáticas
com todas as dependências (cache Redis) corretamente injetadas.
"""

from loguru import logger

try:
    from .met_norway.met_norway_client import (
        METNorwayClient,
    )
    from .nasa_power.nasa_power_client import NASAPowerClient
    from .nws_forecast.nws_forecast_client import NWSForecastClient
    from .openmeteo_archive.openmeteo_archive_client import (
        OpenMeteoArchiveClient,
    )
    from .openmeteo_forecast.openmeteo_forecast_client import (
        OpenMeteoForecastClient,
    )
    from backend.infrastructure.cache.climate_cache import ClimateCacheService
except ImportError:
    from .met_norway.met_norway_client import (
        METNorwayClient,
    )
    from .nasa_power.nasa_power_client import NASAPowerClient
    from .nws_forecast.nws_forecast_client import NWSForecastClient
    from .openmeteo_archive.openmeteo_archive_client import (
        OpenMeteoArchiveClient,
    )
    from .openmeteo_forecast.openmeteo_forecast_client import (
        OpenMeteoForecastClient,
    )
    from backend.infrastructure.cache.climate_cache import ClimateCacheService


class ClimateClientFactory:
    """
    Factory para criar clientes climáticos com dependências injetadas.

    Features:
    - Singleton do serviço de cache (reutiliza conexão Redis)
    - Injeção automática de cache em todos os clientes
    - Método centralizado de cleanup
    """

    _cache_service: ClimateCacheService | None = None

    @classmethod
    def get_cache_service(cls) -> ClimateCacheService:
        """
        Retorna instância singleton do serviço de cache.

        Garante que todos os clientes compartilhem a mesma
        conexão Redis, evitando overhead de múltiplas conexões.

        Returns:
            ClimateCacheService: Serviço de cache compartilhado
        """
        if cls._cache_service is None:
            cls._cache_service = ClimateCacheService(prefix="climate")
            logger.info("ClimateCacheService singleton criado")
        return cls._cache_service

    @classmethod
    def create_nasa_power(cls) -> NASAPowerClient:
        """
        Cria cliente NASA POWER com cache injetado.
        """
        cache = cls.get_cache_service()
        client = NASAPowerClient(cache=cache)
        logger.debug("NASAPowerClient criado com cache injetado")
        return client

    @classmethod
    def create_met_norway(cls) -> METNorwayClient:
        """
        Cria cliente MET Norway com cache injetado.
        """
        cache = cls.get_cache_service()
        client = METNorwayClient(cache=cache)
        logger.debug("🇳🇴 METNorwayClient criado com cache injetado")
        return client

    @classmethod
    def create_nws(cls) -> NWSForecastClient:
        """
        Cria cliente NWS (National Weather Service).

        Nota: NWS usa cache interno, não precisa de injeção.
        """
        client = NWSForecastClient()
        logger.debug("🇺🇸 NWSForecastClient criado")
        return client

    @classmethod
    def create_nws_stations(cls):
        """
        Cria cliente NWS Stations com cache injetado.
        """
        from .nws_stations.nws_stations_client import NWSStationsClient

        cache = cls.get_cache_service()
        client = NWSStationsClient(cache=cache)
        logger.debug("🇺🇸 NWSStationsClient criado com cache injetado")
        return client

    @classmethod
    def create_openmeteo(cls):
        """
        Cria cliente Open-Meteo Forecast (padrão para compatibilidade).
        """
        return cls.create_openmeteo_forecast()

    @classmethod
    def create_openmeteo_archive(
        cls,
        cache_dir: str = ".cache",
    ):
        """
        Cria cliente Open-Meteo Archive.
        """
        client = OpenMeteoArchiveClient(cache_dir=cache_dir)
        logger.debug("OpenMeteoArchiveClient criado (1940-2025)")
        return client

    @classmethod
    def create_openmeteo_forecast(
        cls,
        cache_dir: str = ".cache",
    ):
        """
        Cria cliente Open-Meteo Forecast.
        """
        client = OpenMeteoForecastClient(cache_dir=cache_dir)
        logger.debug("OpenMeteoForecastClient criado (-30d a +5d)")
        return client

    @classmethod
    async def close_all(cls):
        """
        Fecha todas as conexões abertas (Redis, HTTP clients).
        """
        if cls._cache_service and cls._cache_service.redis:
            await cls._cache_service.redis.close()
            logger.info("ClimateCacheService Redis connection closed")
            cls._cache_service = None
