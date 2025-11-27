"""
OpenTopoData Client - Elevation and Topographic Data.

API: https://www.opentopodata.org/
Public Instance: https://api.opentopodata.org/v1/

Cobertura: Global (múltiplos datasets com fallback nativo)

Multi-Dataset Fallback (Nov 2025):
A API suporta fallback nativo: /v1/{dataset1},{dataset2}?locations=...
Padrão: /v1/srtm30m,aster30m
- Tenta SRTM30m primeiro (melhor qualidade, -60° a +60°)
- Automáticamente cai para ASTER30m se sem dados
- Cada ponto usa o melhor dataset disponível
- Elimina necessidade de auto-switch manual

Datasets Disponíveis:
- srtm30m: SRTM 30m (~30m, melhor qualidade onde disponível)
- aster30m: ASTER 30m (global, inclui regiões polares)
- mapzen: ~30m global compilado (inclui batimetria)
- etopo1: ETOPO1 (~1.8km, global com batimetria)
- outros regionais: ned10m (USA), eudem25m (Europa), etc.

Retorna:
- elevation: Elevação em metros (pode ser null se sem dados)
- location: Coordenadas originais (interpolação bilinear/cubic)
- dataset: Dataset realmente usado (SRTM ou ASTER, por exemplo)

Rate Limit Atual (2025):
- Máximo 1 request por segundo
- Máximo 1000 requests por dia
- Máximo 100 localizações por request
- Recomendado uso de batch + cache agressivo (elevação não muda)

Uso no Cálculo de ETo FAO-56:
1. **Pressão Atmosférica** (P):
   P = 101.3 x [(293 - 0.0065 x z) / 293]^5.26
   onde z = elevação (m)

2. **Psychrometric Constant** (Y):
   Y = 0.665 x 10^-3 x P

3. **Radiação Solar Extraterrestre** (Ra):
   Aumenta ~10% por 1000m de altitude

Licença: Pública (dados SRTM/ASTER são domínio público)
"""

import os
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field

from scripts.api.services.geographic_utils import GeographicUtils


class OpenTopoConfig(BaseModel):
    """Configuração da API OpenTopoData."""

    base_url: str = os.getenv(
        "OPENTOPO_URL",
        "https://api.opentopodata.org/v1",
    )

    default_dataset: str = "srtm30m,aster30m"  # Multi-fallback nativo da API

    timeout: int = 15
    cache_ttl: int = 3600 * 24 * 30  # 30 dias


class OpenTopoLocation(BaseModel):
    """Dados de localização retornados pela OpenTopoData
    (coordenadas ajustadas à grade)."""

    lat: float = Field(..., description="Latitude (ajustada)")
    lon: float = Field(
        ..., description="Longitude (ajustada)"
    )  # API usa "lng"
    elevation: float = Field(..., description="Elevação em metros")
    dataset: str = Field(..., description="Dataset utilizado")


class OpenTopoClient:
    """Client para serviço OpenTopoData de elevação."""

    def __init__(
        self,
        config: OpenTopoConfig | None = None,
        cache: Any | None = None,
    ):
        """
        Initialize OpenTopoData client.

        Args:
            config: Optional configuration
            cache: Optional ClimateCache instance (Redis)
        """
        self.config = config or OpenTopoConfig()
        self.cache = cache
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            follow_redirects=True,
        )
        logger.info(
            f"OpenTopoClient inicializado | "
            f"dataset padrão={self.config.default_dataset}"
        )

    async def close(self):
        """Close HTTP connection."""
        await self.client.aclose()

    async def get_elevation(
        self,
        lat: float,
        lon: float,
        dataset: str | None = None,
    ) -> OpenTopoLocation | None:
        """
        Busca elevação para um ponto único (com fallback nativo da API).

        Usa multi-dataset fallback nativo da OpenTopoData API:
        /v1/srtm30m,aster30m?locations=lat,lon
        A API tenta SRTM30m primeiro, depois ASTER30m se necessário.

        Args:
            lat: Latitude
            lon: Longitude
            dataset: Optional dataset override (default: srtm30m,aster30m)

        Returns:
            OpenTopoLocation with elevation, or None if error

        Example:
            > client = OpenTopoClient()
            > location = await client.get_elevation(-15.7801, -47.9292)
            > print(f"Elevation: {location.elevation}m")
            Elevation: 1172m
        """
        # Validação básica de coordenadas
        if not GeographicUtils.is_valid_coordinate(lat, lon):
            logger.warning(f"Coordenadas inválidas: ({lat}, {lon})")
            return None

        dataset = dataset or self.config.default_dataset

        cache_key = f"opentopo:{lat:.6f}:{lon:.6f}"

        # Try cache first
        if self.cache:
            try:
                cached = await self.cache.get(cache_key)
                if cached:
                    logger.debug(f"Cache hit: {cache_key}")
                    return cached
            except Exception as e:
                logger.warning(f"Erro leitura cache: {e}")

        # Fetch from API
        try:
            url = f"/{dataset}"
            params = {"locations": f"{lat},{lon}"}

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "OK":
                logger.error(f"API error: {data.get('error', 'Unknown')}")
                return None

            results = data.get("results", [])
            if not results:
                logger.warning("Nenhum resultado retornado")
                return None

            result = results[0]
            elevation = result.get("elevation")

            if elevation is None:
                logger.info("Sem dados de elevação para este ponto")
                return None

            loc = result.get("location", {})
            lat_out = loc.get("lat", lat)
            lon_out = loc.get("lng", lon)  # API usa "lng"

            location = OpenTopoLocation(
                lat=lat_out,
                lon=lon_out,
                elevation=float(elevation),
                dataset=result.get("dataset") or dataset,
            )

            # Cache result
            if self.cache:
                try:
                    await self.cache.set(
                        cache_key,
                        location,
                        ttl=self.config.cache_ttl,
                    )
                except Exception as e:
                    logger.warning(f"Erro escrita cache: {e}")

            logger.info(
                f"Elevação obtida | ({lat_out:.4f}, {lon_out:.4f}) = "
                f"{elevation:.1f}m | {dataset}"
            )
            return location

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error("Rate limit excedido")
            else:
                logger.error(f"HTTP error {e.response.status_code}")
            return None

        except Exception as e:
            logger.error(f"Erro inesperado: {e}")
            return None

    async def get_elevations_batch(
        self,
        locations: list[tuple[float, float]],
        dataset: str | None = None,
    ) -> list[OpenTopoLocation]:
        """
        Busca múltiplos pontos em uma única request (máx 100).

        Usa multi-dataset fallback nativo da OpenTopoData API.
        Cada ponto usa melhor dataset (SRTM→ASTER conforme necessário).

        Args:
            locations: List of (lat, lon) tuples
            dataset: Optional dataset override (default: srtm30m,aster30m)

        Returns:
            List of OpenTopoLocation objects

        Example:
            > locations = [
                 (-15.7801, -47.9292),  # Brasília
                 (-23.5505, -46.6333),  # São Paulo
             ]
            > results = await client.get_elevations_batch(locations)
            > for loc in results:
                print(f"{loc.lat}, {loc.lon}: {loc.elevation}m")
        """
        if not locations:
            return []

        # Validação básica
        if any(
            not GeographicUtils.is_valid_coordinate(lat, lon)
            for lat, lon in locations
        ):
            logger.warning("Batch contém coordenadas inválidas")
            return []

        dataset = dataset or self.config.default_dataset

        if len(locations) > 100:
            # Split recursivo
            results = []
            for i in range(0, len(locations), 100):
                chunk = locations[i : i + 100]
                # passa dataset já ajustado
                chunk_results = await self.get_elevations_batch(
                    chunk, dataset=dataset
                )
                results.extend(chunk_results)
            return results

        locations_str = "|".join(f"{lat},{lon}" for lat, lon in locations)

        try:
            url = f"/{dataset}"
            params = {"locations": locations_str}

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "OK":
                logger.error(
                    f"Batch API error: {data.get('error', 'Unknown')}"
                )
                return []

            results_data = data.get("results", [])

            results = []
            for i, result_dict in enumerate(results_data):
                elevation = result_dict.get("elevation")
                if elevation is None:
                    continue  # pula pontos sem dados

                loc = result_dict.get("location", {})
                lat_out = loc.get("lat", locations[i][0])
                lon_out = loc.get("lng", locations[i][1])

                results.append(
                    OpenTopoLocation(
                        lat=lat_out,
                        lon=lon_out,
                        elevation=float(elevation),
                        dataset=result_dict.get("dataset") or dataset,
                    )
                )

            logger.info(
                f"Batch obtido | {len(results)}/{len(locations)} pontos | "
                f"dataset={dataset}"
            )
            return results

        except Exception as e:
            logger.error(f"Erro no batch: {e}")
            return []
