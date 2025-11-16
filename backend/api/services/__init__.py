"""
Climate Data Services Module - EVAonline

Este módulo contém todos os serviços de dados climáticos da aplicação
EVAonline. Suporta 6 fontes de dados climáticos globais e regionais
com cache inteligente.

ARCHITECTURE OVERVIEW:
======================

Core Services (Factory Pattern):
├── ClimateClientFactory          - Factory para criar clients com DI
├── ClimateSourceManager          - Configuração centralizada das APIs
├── ClimateSourceSelector         - Seleção automática de API por localização
└── ClimateValidationService      - Validação centralizada de inputs

API Clients (6 Fontes de Dados):
├── NASA POWER                  - Dados históricos globais (1981+)
├── MET Norway Locationforecast - Previsão global (padronizado 5 dias)
├── NWS/NOAA Forecast           - Previsão USA Continental (padronizado 5 dias)
├── NWS/NOAA Stations           - Observações USA Continental
├── Open-Meteo Archive          - Histórico global (1940+)
└── Open-Meteo Forecast         - Previsão global (padronizado 5 dias)

CACHE STRATEGY:
==============
- Redis-based intelligent caching
- TTL varies by data type (30 days for historical, 6 hours for forecast)
- Automatic cache invalidation
- Compression optional

ERROR HANDLING:
==============
- Comprehensive validation
- Retry logic with exponential backoff
- Proper logging with loguru
- Graceful degradation

PERFORMANCE:
===========
- Async clients for concurrent requests
- Sync adapters for legacy/Celery compatibility
- Connection pooling
- Rate limiting per API requirements

ATTRIBUTIONS REQUIRED:
=====================
All data sources require proper attribution in publications and displays.
See individual client docstrings for specific attribution text.

Author: EVAonline Development Team
Date: November 2025  # Atualizado para data atual (15/11/2025)
Version: 1.0.0
"""

from typing import Any

# Explicit exports para melhor discoverability (mypy, IDEs, __all__)
__all__ = [
    # Core Services
    "ClimateClientFactory",
    "ClimateSourceManager",
    "ClimateSourceSelector",
    "ClimateValidationService",
    # NASA POWER
    "NASAPowerClient",
    "NASAPowerSyncAdapter",
    # Open-Meteo Archive
    "OpenMeteoArchiveClient",
    "OpenMeteoArchiveSyncAdapter",
    # Open-Meteo Forecast
    "OpenMeteoForecastClient",
    "OpenMeteoForecastSyncAdapter",
    # MET Norway
    "METNorwayClient",
    "METNorwaySyncAdapter",
    # NWS Forecast
    "NWSForecastClient",
    "NWSDailyForecastSyncAdapter",
    # NWS Stations
    "NWSStationsClient",
    "NWSStationsSyncAdapter",
    # OpenTopoData
    "OpenTopoClient",
    # Weather Utils
    "WeatherConversionUtils",
    "ElevationUtils",
]


def __getattr__(name: str) -> Any:
    """
    Lazy loading para evitar dependências circulares.
    """
    import importlib

    # Mapeamento centralizado: (submodule_path, class_name)
    lazy_imports: dict[str, tuple[str, str]] = {
        # Core Services
        "ClimateClientFactory": (".climate_factory", "ClimateClientFactory"),
        "ClimateSourceManager": (
            ".climate_source_manager",
            "ClimateSourceManager",
        ),
        "ClimateSourceSelector": (
            ".climate_source_selector",
            "ClimateSourceSelector",
        ),
        "ClimateValidationService": (
            ".climate_validation",
            "ClimateValidationService",
        ),
        # NASA POWER
        "NASAPowerClient": (
            ".nasa_power.nasa_power_client",
            "NASAPowerClient",
        ),
        "NASAPowerSyncAdapter": (
            ".nasa_power.nasa_power_sync_adapter",
            "NASAPowerSyncAdapter",
        ),
        # Open-Meteo Archive
        "OpenMeteoArchiveClient": (
            ".openmeteo_archive.openmeteo_archive_client",
            "OpenMeteoArchiveClient",
        ),
        "OpenMeteoArchiveSyncAdapter": (
            ".openmeteo_archive.openmeteo_archive_sync_adapter",
            "OpenMeteoArchiveSyncAdapter",
        ),
        # Open-Meteo Forecast
        "OpenMeteoForecastClient": (
            ".openmeteo_forecast.openmeteo_forecast_client",
            "OpenMeteoForecastClient",
        ),
        "OpenMeteoForecastSyncAdapter": (
            ".openmeteo_forecast.openmeteo_forecast_sync_adapter",
            "OpenMeteoForecastSyncAdapter",
        ),
        # MET Norway LocationForecast
        "METNorwayClient": (
            ".met_norway.met_norway_client",
            "METNorwayClient",
        ),
        "METNorwaySyncAdapter": (
            ".met_norway.met_norway_sync_adapter",
            "METNorwaySyncAdapter",
        ),
        # NWS Forecast
        "NWSForecastClient": (
            ".nws_forecast.nws_forecast_client",
            "NWSForecastClient",
        ),
        "NWSDailyForecastSyncAdapter": (
            ".nws_forecast.nws_forecast_sync_adapter",
            "NWSDailyForecastSyncAdapter",
        ),
        # NWS Stations
        "NWSStationsClient": (
            ".nws_stations.nws_stations_client",
            "NWSStationsClient",
        ),
        "NWSStationsSyncAdapter": (
            ".nws_stations.nws_stations_sync_adapter",
            "NWSStationsSyncAdapter",
        ),
        # OpenTopoData
        "OpenTopoClient": (".opentopo.opentopo_client", "OpenTopoClient"),
        # Weather Utils
        "WeatherConversionUtils": (".weather_utils", "WeatherConversionUtils"),
        "ElevationUtils": (".weather_utils", "ElevationUtils"),
    }

    if name in lazy_imports:
        module_path, class_name = lazy_imports[name]
        try:
            # Import relativo (__name__ é 'backend.api.services')
            module = importlib.import_module(module_path, package=__name__)
            attr = getattr(module, class_name)
            # Cache evita re-import em chamadas repetidas
            # Nota: __dict__[name] = attr  # Descomente para cache
            return attr
        except (ImportError, AttributeError) as e:
            # Erro mais descritivo com contexto
            raise ImportError(
                f"Falha ao importar '{name}' de '{module_path}': {e}. "
                f"Verifique se o módulo existe e a classe "
                f"'{class_name}' está definida."
            ) from e

    # Fallback para atributos padrão (ex.: __version__)
    if name in {"__version__", "__author__", "__date__"}:
        return globals()[name]

    raise AttributeError(f"Módulo '{__name__}' não possui atributo '{name}'")


# Version info (atualizado para data atual)
__version__ = "1.0.0"
__author__ = "EVAonline Development Team"
__date__ = (
    "November 2025"  # Atualizado para alinhar com data atual (15/11/2025)
)
