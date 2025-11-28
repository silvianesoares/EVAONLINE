"""
Open-Meteo Archive API Client - Historical Climate Data.

API: https://archive-api.open-meteo.com/v1/archive

Cobertura: Global

Período: 1990-01-01 até (hoje - 2 dias)

Resolução: Diária

Licença: CC BY 4.0 (atribuição obrigatória)

Open-Meteo is open-source
Source code is available on GitHub under the GNU Affero General
Public Licence Version 3 AGPLv3 or any later version.
GitHub Open-Meteo: https://github.com/open-meteo/open-meteo
Historical Weather API: https://open-meteo.com/en/docs/historical-weather-api

Variables (10):
- Temperature: mean, max, min (°C)
- Precipitation: sum (mm)
- ET0 FAO Evapotranspiration (mm)
- Shortwave Radiation: sum (MJ/m²)
- Relative Humidity: mean, max, min (%)
- Wind Speed: mean at 10m (m/s)

CACHE STRATEGY (Nov 2025):
- Redis cache via ClimateCache (recomendado)
- Fallback: requests_cache local
- TTL: 24h (dados históricos são estáveis, mas podem ter correções)
"""

from datetime import datetime, timedelta
from typing import Any, Dict

import openmeteo_requests
import requests_cache
from loguru import logger
from retry_requests import retry

from scripts.api.services.geographic_utils import GeographicUtils
from scripts.api.services.weather_utils import (
    WeatherConversionUtils,
)


class OpenMeteoArchiveConfig:
    """Configuration for Open-Meteo Archive API."""

    # API URL
    BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

    # IMPORTANT: Timeline constraints (MIN_DATE, MAX_DATE_OFFSET)
    # are defined in climate_source_availability.py (SOURCE OF TRUTH).
    # This client ASSUMES pre-validated dates from climate_validation.py.
    # - MIN_DATE: 1990-01-01 (in climate_source_availability.py)
    # - MAX_DATE: hoje - 2d (in climate_source_availability.py)
    MIN_DATE = datetime(1990, 1, 1)
    MAX_DATE_OFFSET = 2  # hoje - 2d

    # Cache TTL (dados históricos são estáveis)
    CACHE_TTL = 86400  # 24 hours (pode ter correções)

    # 10 Climate variables
    DAILY_VARIABLES = [
        "temperature_2m_mean",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "et0_fao_evapotranspiration",
        "shortwave_radiation_sum",
        "relative_humidity_2m_mean",
        "relative_humidity_2m_max",
        "relative_humidity_2m_min",
        "wind_speed_10m_mean",
    ]

    # Network settings
    TIMEOUT = 30
    RETRY_ATTEMPTS = 5
    BACKOFF_FACTOR = 0.2


class OpenMeteoArchiveClient:
    """
    Client for Open-Meteo Archive API (historical data only).

    Supports Redis cache (via ClimateCache) with fallback to local cache.
    """

    def __init__(self, cache: Any | None = None, cache_dir: str = ".cache"):
        """
        Initialize Archive client with caching and retry logic.

        Args:
            cache: Optional ClimateCache instance (Redis)
            cache_dir: Directory for fallback requests_cache
        """
        self.config = OpenMeteoArchiveConfig()
        self.cache = cache  # Redis cache (opcional)
        self._setup_client(cache_dir)

        cache_type = "Redis" if cache else "Local"
        logger.info(
            f"OpenMeteoArchiveClient initialized ({cache_type} cache, "
            f"1990-present)"
        )

    def _setup_client(self, cache_dir: str):
        """Setup requests cache and retry session."""
        cache_session = requests_cache.CachedSession(
            cache_dir, expire_after=self.config.CACHE_TTL
        )
        retry_session = retry(
            cache_session,
            retries=self.config.RETRY_ATTEMPTS,
            backoff_factor=self.config.BACKOFF_FACTOR,
        )
        self.client = openmeteo_requests.Client(session=retry_session)  # type: ignore[arg-type]  # noqa: E501
        logger.debug(f"Cache dir: {cache_dir}, TTL: 24 hours")

    async def get_climate_data(
        self,
        lat: float,
        lng: float,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """
        Get historical climate data from Archive API.

        IMPORTANTE: Este cliente ASSUME que:
        - Coordenadas validadas em climate_validation.py
        - Period (1990-01-01 até hoje-2d) validado em
          climate_source_availability.py
        Este cliente APENAS busca dados, sem re-validar datas.

        Uses Redis cache if available, with TTL 24h
        (dados históricos estáveis).

        Args:
            lat: Latitude (-90 to 90)
            lng: Longitude (-180 to 180)
            start_date: Start date (YYYY-MM-DD, >= 1990-01-01)
            end_date: End date (YYYY-MM-DD, <= hoje - 2 dias)
        """
        # 1. Validate inputs
        self._validate_inputs(lat, lng, start_date, end_date)

        # 2. Try Redis cache first (if available)
        if self.cache:
            cache_key = self._get_cache_key(lat, lng, start_date, end_date)
            cached_data = await self.cache.get(cache_key)

            if cached_data:
                logger.info(
                    f"✅ Cache HIT (Redis): OpenMeteo Archive "
                    f"({lat:.4f}, {lng:.4f})"
                )
                return cached_data

        # 3. Prepare API parameters
        params = {
            "latitude": lat,
            "longitude": lng,
            "start_date": start_date,
            "end_date": end_date,
            "daily": self.config.DAILY_VARIABLES,
            "models": "best_match",
            "timezone": "auto",
            "wind_speed_unit": "ms",
        }

        logger.info(
            f"⚠️ Cache MISS: Archive API {start_date} to {end_date} | "
            f"({lat:.4f}, {lng:.4f})"
        )

        # Check if period is too long (>10 years) and split into chunks
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days_diff = (end_dt - start_dt).days

        # If period > 3650 days (10 years), split into 5-year chunks
        if days_diff > 3650:
            logger.warning(
                f"📦 Período longo ({days_diff} dias) → "
                f"Dividindo em chunks de 5 anos"
            )
            return await self._fetch_in_chunks(lat, lng, start_date, end_date)

        # 4. Fetch data from Archive API (normal flow for < 10 years)
        try:
            responses = self.client.weather_api(
                self.config.BASE_URL, params=params
            )
            response = responses[0]  # Single location

            # 4. Extract location metadata
            location = {
                "latitude": response.Latitude(),
                "longitude": response.Longitude(),
                "elevation": response.Elevation(),
                "timezone": response.Timezone(),
                "timezone_abbreviation": response.TimezoneAbbreviation(),
                "utc_offset_seconds": response.UtcOffsetSeconds(),
            }

            # 5. Extract climate data
            daily = response.Daily()

            # Extract time range - use TimeEnd() to get both start and end
            time_start = daily.Time()  # type: ignore
            time_end = daily.TimeEnd()  # type: ignore
            time_interval = daily.Interval()  # type: ignore (usually 86400 for daily)

            logger.debug(
                f"time_start: {time_start}, time_end: {time_end}, "
                f"interval: {time_interval}"
            )

            # Generate full date range
            if time_start == time_end:
                # Single day
                timestamps = [int(time_start)]
            else:
                # Multiple days - generate range
                # NOTE: time_end is already INCLUSIVE, don't add +1
                timestamps = list(
                    range(int(time_start), int(time_end), int(time_interval))
                )

            logger.debug(f"Generated {len(timestamps)} timestamps")

            dates = [datetime.fromtimestamp(ts) for ts in timestamps]

            climate_data = {"dates": dates}

            # Map variables to data
            for i, var_name in enumerate(self.config.DAILY_VARIABLES):
                try:
                    values = daily.Variables(i).ValuesAsNumpy()  # type: ignore
                    # Handle scalar values (single day) vs arrays
                    if hasattr(values, "tolist"):
                        climate_data[var_name] = values.tolist()  # type: ignore  # noqa: E501
                    else:
                        # Scalar value - wrap in list
                        climate_data[var_name] = [float(values)]  # type: ignore  # noqa: E501
                except Exception as e:
                    logger.warning(f"Variable {var_name} not available: {e}")
                    climate_data[var_name] = [None] * len(dates)  # type: ignore  # noqa: E501

            # Convert wind from 10m to 2m for FAO-56 PM equation
            if "wind_speed_10m_mean" in climate_data:
                wind_10m = climate_data["wind_speed_10m_mean"]  # type: ignore
                wind_2m = [
                    WeatherConversionUtils.convert_wind_10m_to_2m(w) if w is not None else None  # type: ignore  # noqa: E501
                    for w in wind_10m  # type: ignore
                ]
                climate_data["wind_speed_2m_mean"] = wind_2m  # type: ignore
                logger.debug(
                    f"✅ Converted wind 10m→2m: {len(wind_2m)} values"
                )

            # 6. Add metadata
            metadata = {
                "api": "archive",
                "url": self.config.BASE_URL,
                "data_points": len(dates),
                "cache_ttl_hours": 24,
            }

            result = {
                "location": location,
                "climate_data": climate_data,
                "metadata": metadata,
            }

            logger.info(
                f"✅ Archive: {len(dates)} days | "
                f"Elevation: {location['elevation']:.0f}m"
            )

            # 7. Save to Redis cache (if available)
            if self.cache:
                ttl = 86400  # 24h
                cache_key = self._get_cache_key(lat, lng, start_date, end_date)
                await self.cache.set(cache_key, result, ttl=ttl)
                logger.debug(f"💾 Cached with TTL {ttl}s (24h)")

            return result

        except Exception as e:
            logger.error(f"Archive API error: {str(e)}")
            raise

    async def _fetch_in_chunks(
        self, lat: float, lng: float, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """
        Fetch data in 5-year chunks to avoid buffer overflow errors.

        Args:
            lat: Latitude
            lng: Longitude
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Merged climate data from all chunks
        """
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # Split into 5-year chunks (1826 days)
        chunk_size_days = 1826
        chunks = []
        current_start = start_dt

        while current_start < end_dt:
            current_end = min(
                current_start + timedelta(days=chunk_size_days - 1), end_dt
            )
            chunks.append(
                {
                    "start": current_start.strftime("%Y-%m-%d"),
                    "end": current_end.strftime("%Y-%m-%d"),
                }
            )
            current_start = current_end + timedelta(days=1)

        logger.info(f"📦 Fetching {len(chunks)} chunks (5 anos cada)")

        # Fetch all chunks
        all_results = []
        for i, chunk in enumerate(chunks, 1):
            logger.info(
                f"  📥 Chunk {i}/{len(chunks)}: "
                f"{chunk['start']} → {chunk['end']}"
            )

            # Recursive call with smaller period
            params = {
                "latitude": lat,
                "longitude": lng,
                "start_date": chunk["start"],
                "end_date": chunk["end"],
                "daily": self.config.DAILY_VARIABLES,
                "models": "best_match",
                "timezone": "auto",
                "wind_speed_unit": "ms",
            }

            try:
                responses = self.client.weather_api(
                    self.config.BASE_URL, params=params
                )
                response = responses[0]

                # Extract data
                daily = response.Daily()
                time_start = daily.Time()
                time_end = daily.TimeEnd()
                time_interval = daily.Interval()

                if time_start == time_end:
                    timestamps = [int(time_start)]
                else:
                    timestamps = list(
                        range(
                            int(time_start), int(time_end), int(time_interval)
                        )
                    )

                dates = [datetime.fromtimestamp(ts) for ts in timestamps]
                climate_data = {"dates": dates}

                for j, var_name in enumerate(self.config.DAILY_VARIABLES):
                    try:
                        values = daily.Variables(j).ValuesAsNumpy()
                        if hasattr(values, "tolist"):
                            climate_data[var_name] = values.tolist()
                        else:
                            climate_data[var_name] = [float(values)]
                    except Exception as e:
                        logger.warning(
                            f"Variable {var_name} not available: {e}"
                        )
                        climate_data[var_name] = [None] * len(dates)

                # Convert wind 10m to 2m
                if "wind_speed_10m_mean" in climate_data:
                    wind_10m = climate_data["wind_speed_10m_mean"]
                    wind_2m = [
                        (
                            WeatherConversionUtils.convert_wind_10m_to_2m(w)
                            if w is not None
                            else None
                        )
                        for w in wind_10m
                    ]
                    climate_data["wind_speed_2m_mean"] = wind_2m

                # Get location metadata from first chunk
                if i == 1:
                    location = {
                        "latitude": response.Latitude(),
                        "longitude": response.Longitude(),
                        "elevation": response.Elevation(),
                        "timezone": response.Timezone(),
                        "timezone_abbreviation": (
                            response.TimezoneAbbreviation()
                        ),
                        "utc_offset_seconds": response.UtcOffsetSeconds(),
                    }

                all_results.append(climate_data)
                logger.success(f"  ✅ Chunk {i}: {len(dates)} dias")

                # Rate limiting: aguardar 12s entre chunks
                # 600 calls/min máximo → 5 chunks/min seguro (12s cada)
                if i < len(chunks):  # Não aguardar após último chunk
                    import time

                    time.sleep(12)
                    logger.debug("  ⏸️ Aguardando 12s (rate limit: 600/min)")

            except Exception as e:
                logger.error(f"  ❌ Chunk {i} falhou: {str(e)}")
                # Se falhar por rate limit, aguardar 60s e tentar novamente
                if "request limit exceeded" in str(e).lower():
                    import time

                    logger.warning(
                        "  ⏸️ Rate limit atingido! Aguardando 60s..."
                    )
                    time.sleep(60)
                    logger.info(f"  🔄 Retry chunk {i}...")
                    # Não fazer raise, continuar para próximo chunk
                    continue
                raise

        # Merge all chunks
        logger.info("🔗 Mesclando chunks...")
        merged_data = {"dates": []}

        for var_name in ["dates"] + self.config.DAILY_VARIABLES:
            if var_name == "dates":
                for chunk_data in all_results:
                    merged_data["dates"].extend(chunk_data["dates"])
            else:
                merged_data[var_name] = []
                for chunk_data in all_results:
                    if var_name in chunk_data:
                        merged_data[var_name].extend(chunk_data[var_name])

        # Add wind_speed_2m_mean
        if "wind_speed_2m_mean" in all_results[0]:
            merged_data["wind_speed_2m_mean"] = []
            for chunk_data in all_results:
                merged_data["wind_speed_2m_mean"].extend(
                    chunk_data["wind_speed_2m_mean"]
                )

        metadata = {
            "api": "archive",
            "url": self.config.BASE_URL,
            "data_points": len(merged_data["dates"]),
            "cache_ttl_hours": 24,
            "chunked": True,
            "num_chunks": len(chunks),
        }

        result = {
            "location": location,
            "climate_data": merged_data,
            "metadata": metadata,
        }

        logger.success(
            f"✅ Merged {len(chunks)} chunks → {len(merged_data['dates'])} dias"
        )

        # Cache the merged result
        if self.cache:
            ttl = 86400
            cache_key = self._get_cache_key(lat, lng, start_date, end_date)
            await self.cache.set(cache_key, result, ttl=ttl)
            logger.debug(f"💾 Cached merged result with TTL {ttl}s")

        return result

    def _get_cache_key(
        self, lat: float, lng: float, start_date: str, end_date: str
    ) -> str:
        """Generate Redis cache key."""
        lat_rounded = round(lat, 2)
        lng_rounded = round(lng, 2)
        return (
            f"climate:openmeteo:archive:{lat_rounded}:{lng_rounded}:"
            f"{start_date}:{end_date}"
        )

    def _validate_inputs(
        self, lat: float, lng: float, start_date: str, end_date: str
    ):
        """
        Validate coordinate and date range inputs.

        IMPORTANTE: Validação básica de coordenadas e datas.
        Validações de período (7-30 dias) são feitas em climate_validation.py.

        Raises:
            ValueError: Invalid inputs
        """
        # Coordinates - usar GeographicUtils (SINGLE SOURCE OF TRUTH)
        if not GeographicUtils.is_valid_coordinate(lat, lng):
            msg = f"Invalid coordinates: ({lat}, {lng})"
            raise ValueError(msg)

        # Date format
        try:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date)
        except ValueError:
            msg = "Dates must be in YYYY-MM-DD format"
            raise ValueError(msg)

        # Date logic
        if start > end:
            msg = "start_date must be <= end_date"
            raise ValueError(msg)

        # Archive constraints
        max_date = datetime.now() - timedelta(days=self.config.MAX_DATE_OFFSET)

        if start.date() < self.config.MIN_DATE.date():
            msg = (
                f"Archive API: start_date must be >= "
                f"{self.config.MIN_DATE.date()}"
            )
            raise ValueError(msg)

        if end.date() > max_date.date():
            msg = (
                f"Archive API: end_date must be <= {max_date.date()} "
                f"(hoje - 2 dias). Use Forecast API para dados recentes."
            )
            raise ValueError(msg)

    async def close(self) -> None:
        """
        Close client resources (no-op for this client).
        """
        pass

    @staticmethod
    def get_info() -> Dict[str, Any]:
        """
        Get information about Archive API.

        Returns:
            Dict with API metadata
        """
        max_date = datetime.now() - timedelta(days=2)
        return {
            "api": "Open-Meteo Archive",
            "url": "https://archive-api.open-meteo.com/v1/archive",
            "coverage": "Global",
            "period": f"Padrão EVAonline: 1990-01-01 até {max_date.date()}",
            "resolution": "Diária",
            "license": "CC BY 4.0",
            "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)",
            "cache_ttl": "24 horas (dados históricos estáveis)",
        }


# Factory helper
def create_archive_client(
    cache: Any | None = None, cache_dir: str = ".cache"
) -> OpenMeteoArchiveClient:
    """
    Factory function to create Archive client.

    Args:
        cache: Optional ClimateCache instance (Redis)
        cache_dir: Fallback cache directory

    Returns:
        Configured OpenMeteoArchiveClient
    """
    return OpenMeteoArchiveClient(cache=cache, cache_dir=cache_dir)
