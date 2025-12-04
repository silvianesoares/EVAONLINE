"""
OpenTopoData Client - Elevation and Topographic Data.

API: https://www.opentopodata.org/
Public Instance: https://api.opentopodata.org/v1/

Coverage: Global (multiple datasets with native fallback)

Multi-Dataset Fallback (Nov 2025):
The API supports native fallback: /v1/{dataset1},{dataset2}?locations=...
Default: /v1/srtm30m,aster30m
- Tries SRTM30m first (best quality, -60° to +60°)
- Automatically falls back to ASTER30m if no data
- Each point uses the best available dataset
- Eliminates need for manual auto-switch

Available Datasets:
- srtm30m: SRTM 30m (~30m, best quality where available)
- aster30m: ASTER 30m (global, includes polar regions)
- mapzen: ~30m global compiled (includes bathymetry)
- etopo1: ETOPO1 (~1.8km, global with bathymetry)
- other regional: ned10m (USA), eudem25m (Europe), etc.

Returns:
- elevation: Elevation in meters (can be null if no data)
- location: Original coordinates (bilinear/cubic interpolation)
- dataset: Dataset actually used (SRTM or ASTER, for example)

Current Rate Limit (2025):
- Maximum 1 request per second
- Maximum 1000 requests per day
- Maximum 100 locations per request
- Recommended use of batch + aggressive cache (elevation doesn't change)

Use in FAO-56 ETo Calculation:
1. **Atmospheric Pressure** (P):
   P = 101.3 x [(293 - 0.0065 x z) / 293]^5.26
   where z = elevation (m)

2. **Psychrometric Constant** (Y):
   Y = 0.665 x 10^-3 x P

3. **Extraterrestrial Solar Radiation** (Ra):
   Increases ~10% per 1000m altitude

License: Public (SRTM/ASTER data are public domain)
"""

import os
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field

from scripts.api.services.geographic_utils import GeographicUtils


class OpenTopoConfig(BaseModel):
    """OpenTopoData API configuration."""

    base_url: str = os.getenv(
        "OPENTOPO_URL",
        "https://api.opentopodata.org/v1",
    )

    default_dataset: str = "srtm30m,aster30m"  # Native API multi-fallback

    timeout: int = 15
    cache_ttl: int = 3600 * 24 * 30  # 30 dias


class OpenTopoLocation(BaseModel):
    """Location data returned by OpenTopoData
    (grid-adjusted coordinates)."""

    lat: float = Field(..., description="Latitude (adjusted)")
    lon: float = Field(
        ..., description="Longitude (adjusted)"
    )  # API uses "lng"
    elevation: float = Field(..., description="Elevation in meters")
    dataset: str = Field(..., description="Dataset used")


class OpenTopoClient:
    """Client for OpenTopoData elevation service."""

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
            f"OpenTopoClient initialized | "
            f"default dataset={self.config.default_dataset}"
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
        Fetch elevation for a single point (with native API fallback).

        Uses OpenTopoData API's native multi-dataset fallback:
        /v1/srtm30m,aster30m?locations=lat,lon
        The API tries SRTM30m first, then ASTER30m if necessary.

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
        # Basic coordinate validation
        if not GeographicUtils.is_valid_coordinate(lat, lon):
            logger.warning(f"Invalid coordinates: ({lat}, {lon})")
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
                logger.warning(f"Cache read error: {e}")

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
                logger.warning("No results returned")
                return None

            result = results[0]
            elevation = result.get("elevation")

            if elevation is None:
                logger.info("No elevation data for this point")
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
                    logger.warning(f"Cache write error: {e}")

            logger.info(
                f"Elevation obtained | ({lat_out:.4f}, {lon_out:.4f}) = "
                f"{elevation:.1f}m | {dataset}"
            )
            return location

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error("Rate limit exceeded")
            else:
                logger.error(f"HTTP error {e.response.status_code}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None

    async def get_elevations_batch(
        self,
        locations: list[tuple[float, float]],
        dataset: str | None = None,
    ) -> list[OpenTopoLocation]:
        """
        Fetch multiple points in a single request (max 100).

        Uses OpenTopoData API's native multi-dataset fallback.
        Each point uses best dataset (SRTM→ASTER as needed).

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

        # Basic validation
        if any(
            not GeographicUtils.is_valid_coordinate(lat, lon)
            for lat, lon in locations
        ):
            logger.warning("Batch contains invalid coordinates")
            return []

        dataset = dataset or self.config.default_dataset

        if len(locations) > 100:
            # Recursive split
            results = []
            for i in range(0, len(locations), 100):
                chunk = locations[i : i + 100]
                # pass already adjusted dataset
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
                    continue  # skip points without data

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
                f"Batch obtained | {len(results)}/{len(locations)} points | "
                f"dataset={dataset}"
            )
            return results

        except Exception as e:
            logger.error(f"Batch error: {e}")
            return []
