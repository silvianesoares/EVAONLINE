"""
Sync Adapter para OpenTopoData Elevation API.

Converte chamadas assíncronas do OpenTopoClient em métodos síncronos
para compatibilidade com Celery tasks, scripts offline e código síncrono
legado.

API: https://www.opentopodata.org/
Cobertura: Global (múltiplos datasets com fallback nativo)
Resolução: ~30m (SRTM/ASTER) a ~1.8km (ETOPO1)
Licença: Pública (dados SRTM/ASTER domínio público)

Multi-Dataset Fallback:
- /v1/srtm30m,aster30m (padrão)
- API tenta SRTM30m primeiro, automaticamente ASTER30m se necessário
- Cada ponto usa o melhor dataset disponível

Rate Limits (2025):
- Máximo 1 request por segundo
- Máximo 1000 requests por dia
- Máximo 100 localizações por request

Cache Strategy:
- TTL: 30 dias (elevação não muda)
- Key: f"opentopo:{lat:.6f}:{lon:.6f}"

Uso no Cálculo de ETo FAO-56:
1. **Pressão Atmosférica** (P):
   P = 101.3 x [(293 - 0.0065 x z) / 293]^5.26

2. **Psychrometric Constant** (Y):
   Y = 0.665 x 10^-3 x P

3. **Radiação Solar Extraterrestre** (Ra):
   Aumenta ~10% por 1000m de altitude
"""

import asyncio
import concurrent.futures
from typing import Any

from loguru import logger

from scripts.api.services.geographic_utils import GeographicUtils
from scripts.api.services.opentopo.opentopo_client import (
    OpenTopoClient,
    OpenTopoConfig,
    OpenTopoLocation,
)


class OpenTopoSyncAdapter:
    """
    Adapter síncrono para OpenTopoData Elevation API.

    Suporta Redis cache (via ClimateCache) com fallback para cache local.
    Fornece métodos síncronos para elevação (ponto único ou batch).
    """

    def __init__(
        self,
        config: OpenTopoConfig | None = None,
        cache: Any | None = None,
    ):
        """
        Inicializa adapter síncrono.

        Args:
            config: Optional OpenTopoConfig
            cache: Optional ClimateCache instance (Redis)

        Features:
            - Global coverage with native multi-dataset fallback
            - Batch processing up to 100 locations per request
            - Redis cache (30 days TTL for elevation)
            - Rate limit compliant (1 req/s, 1000 req/day)
        """
        self.config = config or OpenTopoConfig()
        self.cache = cache

        cache_type = "Redis" if cache else "No cache"
        logger.info(
            f"OpenTopoSyncAdapter initialized | {cache_type} | "
            f"dataset={self.config.default_dataset}"
        )

    def get_elevation_sync(
        self,
        lat: float,
        lon: float,
        dataset: str | None = None,
    ) -> OpenTopoLocation | None:
        """
        Busca elevação para um ponto único (SÍNCRONO).

        Usa multi-dataset fallback nativo da API.

        Args:
            lat: Latitude
            lon: Longitude
            dataset: Optional dataset override (default: srtm30m,aster30m)

        Returns:
            OpenTopoLocation with elevation, or None if error

        Example:
            > adapter = OpenTopoSyncAdapter()
            > location = adapter.get_elevation_sync(-15.7801, -47.9292)
            > if location:
                print(f"Elevation: {location.elevation}m")
            Elevation: 1172m
        """
        try:
            # Tentar obter loop existente
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Loop já está rodando (contexto async)
                # Usar executor para evitar "RuntimeError: This event loop
                # is already running"
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._async_get_elevation(lat, lon, dataset),
                    )
                    return future.result()
            else:
                # Loop existe mas não está rodando
                return loop.run_until_complete(
                    self._async_get_elevation(lat, lon, dataset)
                )
        except RuntimeError:
            # Nenhum loop, criar um novo
            return asyncio.run(self._async_get_elevation(lat, lon, dataset))

    async def _async_get_elevation(
        self,
        lat: float,
        lon: float,
        dataset: str | None = None,
    ) -> OpenTopoLocation | None:
        """
        Implementação async interna (ponto único).
        """
        client = OpenTopoClient(config=self.config, cache=self.cache)

        try:
            return await client.get_elevation(lat, lon, dataset)
        finally:
            await client.close()

    def get_elevations_batch_sync(
        self,
        locations: list[tuple[float, float]],
        dataset: str | None = None,
    ) -> list[OpenTopoLocation]:
        """
        Busca múltiplos pontos de forma SÍNCRONA (máx 100 por request).

        Auto-switches to ASTER30m if batch contains lat > 60°.
        For > 100 locations, splits recursively and respects rate limits.

        Args:
            locations: List of (lat, lon) tuples
            dataset: Optional dataset override (default: srtm30m)

        Returns:
            List of OpenTopoLocation objects

        Example:
            > locations = [
                (-15.7801, -47.9292),  # Brasília
                (-23.5505, -46.6333),  # São Paulo
            ]
            > results = adapter.get_elevations_batch_sync(locations)
            > for loc in results:
                print(f"{loc.lat}, {loc.lon}: {loc.elevation}m")
        """
        try:
            # Tentar obter loop existente
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Loop já está rodando
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._async_get_elevations_batch(locations, dataset),
                    )
                    return future.result()
            else:
                # Loop existe mas não está rodando
                return loop.run_until_complete(
                    self._async_get_elevations_batch(locations, dataset)
                )
        except RuntimeError:
            # Nenhum loop, criar um novo
            return asyncio.run(
                self._async_get_elevations_batch(locations, dataset)
            )

    async def _async_get_elevations_batch(
        self,
        locations: list[tuple[float, float]],
        dataset: str | None = None,
    ) -> list[OpenTopoLocation]:
        """
        Implementação async interna (batch).
        """
        client = OpenTopoClient(config=self.config, cache=self.cache)

        try:
            return await client.get_elevations_batch(locations, dataset)
        finally:
            await client.close()

    async def _async_is_in_coverage(self, lat: float, lon: float) -> bool:
        """
        Implementação async interna (coverage check).

        Sempre retorna True com fallback nativo.
        """
        if not GeographicUtils.is_valid_coordinate(lat, lon):
            return False
        return True

    def health_check_sync(self) -> bool:
        """
        Health check síncrono (testa com coordenada global).

        Returns:
            bool: True if API is accessible
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, self._async_health_check()
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._async_health_check())
        except RuntimeError:
            return asyncio.run(self._async_health_check())

    async def _async_health_check(self) -> bool:
        """
        Health check assíncrono interno.

        Testa com coordenadas de Brasília (elevação conhecida ~1172m).
        """
        client = OpenTopoClient(config=self.config, cache=self.cache)

        try:
            # Teste com Brasília (elevação conhecida)
            # Brasília: -15.7801, -47.9292, elevação ≈ 1172m
            location = await client.get_elevation(-15.7801, -47.9292)

            if location and location.elevation:
                logger.info(
                    f"OpenTopoData health check: OK "
                    f"(Brasília elevation = {location.elevation:.1f}m)"
                )
                return True
            else:
                logger.error("OpenTopoData health check: FAIL (no data)")
                return False

        except Exception as e:
            logger.error(f"OpenTopoData health check failed: {e}")
            return False

        finally:
            await client.close()

    def get_coverage_info(self) -> dict:
        """
        Retorna informações sobre cobertura e datasets disponíveis.

        Returns:
            dict: Informações de cobertura com quality tiers
        """
        return {
            "adapter": "OpenTopoSyncAdapter",
            "coverage": "Global with intelligent dataset selection",
            "default_dataset": self.config.default_dataset,
            "datasets": {
                "srtm30m": {
                    "name": "SRTM 30m",
                    "coverage": {
                        "lat_min": -60.0,
                        "lat_max": 60.0,
                        "lon_min": -180.0,
                        "lon_max": 180.0,
                    },
                    "resolution": "~30 meters",
                    "quality": "Excellent where available",
                    "source": "NASA SRTM v3",
                    "default": True,
                },
                "aster30m": {
                    "name": "ASTER 30m",
                    "coverage": {
                        "lat_min": -90.0,
                        "lat_max": 90.0,
                        "lon_min": -180.0,
                        "lon_max": 180.0,
                    },
                    "resolution": "~30 meters",
                    "quality": "Good globally (includes poles)",
                    "source": "ASTER Global DEM v3",
                    "used_for": "Polar regions (lat > 60°)",
                    "auto_fallback": True,
                },
                "mapzen": {
                    "name": "Mapzen Terrarium",
                    "coverage": {
                        "lat_min": -90.0,
                        "lat_max": 90.0,
                        "lon_min": -180.0,
                        "lon_max": 180.0,
                    },
                    "resolution": "~30 meters",
                    "quality": "Good (compiled from multiple sources)",
                    "source": "OpenStreetMap + SRTM + ASTER",
                },
                "etopo1": {
                    "name": "ETOPO1",
                    "coverage": {
                        "lat_min": -90.0,
                        "lat_max": 90.0,
                        "lon_min": -180.0,
                        "lon_max": 180.0,
                    },
                    "resolution": "~1.8 km",
                    "quality": "Good (includes bathymetry)",
                    "source": "NOAA ETOPO1",
                    "note": "Lower resolution, includes ocean depth data",
                },
            },
            "auto_switching": {
                "enabled": True,
                "method": "Native API fallback (multi-dataset)",
                "rule": "POST /v1/srtm30m,aster30m",
                "benefit": (
                    "Automatic per-point fallback "
                    "(no manual switching needed)"
                ),
            },
            "rate_limits": {
                "requests_per_second": 1,
                "requests_per_day": 1000,
                "locations_per_request": 100,
                "note": (
                    "Batch requests recommended (up to 100 locations "
                    "per request)"
                ),
            },
            "cache_strategy": {
                "ttl_seconds": 3600 * 24 * 30,  # 30 days
                "ttl_human": "30 days",
                "reason": "Elevation data is static",
                "key_format": "opentopo:{dataset}:{lat:.6f}:{lon:.6f}",
                "precision_decimals": 6,  # ~0.1m geographic precision
            },
            "fao56_calculations": {
                "atmospheric_pressure": (
                    "P = 101.3 × [(293 - 0.0065 × z) / 293]^5.26"
                ),
                "psychrometric_constant": "γ = 0.665 × 10^-3 × P",
                "solar_radiation": ("Increases ~10% per 1000m elevation"),
                "location": (
                    "backend.api.services.weather_utils.ElevationUtils"
                ),
            },
            "license": "Public Domain (SRTM/ASTER public data)",
            "attribution": "Elevation data from OpenTopoData",
        }
