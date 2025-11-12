# core
from backend.api.services.climate_factory import ClimateClientFactory
from backend.api.services.climate_source_manager import ClimateSourceManager
from backend.api.services.climate_source_selector import ClimateSourceSelector
from backend.api.services.climate_validation import ClimateValidationService

# clients
from backend.api.services.nasa_power.nasa_power_client import NASAPowerClient
from backend.api.services.openmeteo_archive.openmeteo_archive_client import (
    OpenMeteoArchiveClient,
)
from backend.api.services.openmeteo_forecast.openmeteo_forecast_client import (
    OpenMeteoForecastClient,
)
from backend.api.services.met_norway.met_norway_client import (
    METNorwayClient,
)
from backend.api.services.nws_forecast.nws_forecast_client import (
    NWSForecastClient,
)
from backend.api.services.nws_stations.nws_stations_client import (
    NWSStationsClient,
)

# adapters
from backend.api.services.nasa_power.nasa_power_sync_adapter import (
    NASAPowerSyncAdapter,
)
from backend.api.services.openmeteo_archive.openmeteo_archive_sync_adapter import (  # noqa: E501
    OpenMeteoArchiveSyncAdapter,
)
from backend.api.services.openmeteo_forecast.openmeteo_forecast_sync_adapter import (  # noqa: E501
    OpenMeteoForecastSyncAdapter,
)
from backend.api.services.nws_forecast.nws_forecast_sync_adapter import (
    NWSDailyForecastSyncAdapter,
)
from backend.api.services.nws_stations.nws_stations_sync_adapter import (
    NWSStationsSyncAdapter,
)


__all__ = [
    # Core
    "ClimateClientFactory",
    "ClimateSourceManager",
    "ClimateSourceSelector",
    "ClimateValidationService",
    # Clients
    "NASAPowerClient",
    "OpenMeteoArchiveClient",
    "OpenMeteoForecastClient",
    "METNorwayClient",
    "NWSForecastClient",
    "NWSStationsClient",
    # Adapters
    "NASAPowerSyncAdapter",
    "OpenMeteoArchiveSyncAdapter",
    "OpenMeteoForecastSyncAdapter",
    "NWSDailyForecastSyncAdapter",
    "NWSStationsSyncAdapter",
]
