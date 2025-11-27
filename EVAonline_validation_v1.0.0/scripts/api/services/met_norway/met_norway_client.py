"""
MET Norway Locationforecast 2.0 Client with hourly-to-daily aggregation.
Usar somente "MET Norway" para MET Norway LocationForecast 2.0.

Documentation:
- https://api.met.no/weatherapi/locationforecast/2.0/documentation
- https://docs.api.met.no/doc/locationforecast/datamodel.html
- https://api.met.no/doc/locationforecast/datamodel

IMPORTANT:
- Locationforecast is GLOBAL (works anywhere)
- Returns HOURLY data that must be aggregated to daily
- No separate daily endpoint - aggregation done in backend
- 5-day forecast limit (EVAonline standard)

License: CC-BY 4.0 - Attribution required in all visualizations

Variable (from MET Norway JSON):
Instant values (hourly snapshots):
- air_temperature: Air temperature (°C)
- relative_humidity: Relative humidity (%)
- wind_speed: Wind speed at 10m (m/s)

Next 1 hour:
- precipitation_amount: Hourly precipitation (mm)

Next 6 hours:
- air_temperature_max: Maximum temperature (°C)
- air_temperature_min: Minimum temperature (°C)
- precipitation_amount: 6-hour precipitation (mm)
"""

from datetime import datetime, timedelta
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field

# Import para detecção regional (fonte única)
from validation_logic_eto.api.services.geographic_utils import (
    GeographicUtils,
    validate_coordinates,
)
from validation_logic_eto.api.services.weather_utils import (
    METNorwayAggregationUtils,  # Movido de aqui para weather_utils
    WeatherConversionUtils,
    CacheUtils,  # Utilitários de cache
)


# Pydantic model (definido no topo para evitar forward references)
class METNorwayDailyData(BaseModel):
    """Daily aggregated data from MET Norway API.

    Field names match our standardized output schema, but are calculated
    from MET Norway's API variable names:
    - temp_max/min: from air_temperature_max/min (next_6_hours)
    - temp_mean: calculated from hourly air_temperature (instant)
    - humidity_mean: calculated from hourly relative_humidity (instant)
    - precipitation_sum: calculated from precipitation_amount (next_1_hours)
    - wind_speed_2m_mean: converted from wind_speed (10m) using FAO-56 formula
    """

    date: datetime = Field(..., description="Date of record")
    temp_max: float | None = Field(
        None, description="Maximum temperature (°C) - from air_temperature_max"
    )
    temp_min: float | None = Field(
        None, description="Minimum temperature (°C) - from air_temperature_min"
    )
    temp_mean: float | None = Field(
        None, description="Mean temperature (°C) - from hourly air_temperature"
    )
    humidity_mean: float | None = Field(
        None,
        description=(
            "Mean relative humidity (%) - from hourly relative_humidity"
        ),
    )
    precipitation_sum: float | None = Field(
        None,
        description="Total precipitation (mm/day) - from precipitation_amount",
    )
    wind_speed_2m_mean: float | None = Field(
        None,
        description=(
            "Mean wind speed at 2m (m/s) - converted from 10m using FAO-56"
        ),
    )
    source: str = Field(default="met_norway", description="Data source")


class METNorwayConfig(BaseModel):
    """MET Norway API configuration."""

    # Base URL
    base_url: str = Field(
        default="https://api.met.no/weatherapi/locationforecast/2.0",
        description="MET Norway API base URL",
    )

    # Request timeout
    timeout: int = 30

    # Retry configuration
    retry_attempts: int = 3
    retry_delay: float = 1.0

    # User-Agent required (MET Norway requires identification)
    user_agent: str = Field(
        default="EVAonline/1.0 (https://github.com/angelasmcsores/EVAONLINE)",
        description="User-Agent header (required by MET Norway)",
    )

    # Altitude parameter (optional, improves forecast accuracy)
    altitude: float | None = Field(
        default=None,
        description=(
            "Altitude in meters above sea level. "
            "Improves forecast accuracy when provided. "
            "Optional parameter for MET Norway API."
        ),
    )

    # Connection limits for rate limiting and resource management
    max_keepalive_connections: int = Field(
        default=5,
        description=(
            "Maximum number of keepalive connections in the pool. "
            "Helps prevent excessive connections to MET Norway API."
        ),
    )
    max_connections: int = Field(
        default=10,
        description=(
            "Maximum total number of connections. "
            "Ensures we stay within API rate limits."
        ),
    )


class METNorwayCacheMetadata(BaseModel):
    """Metadata for cached MET Norway responses."""

    last_modified: str | None = Field(
        None, description="Last-Modified header from API (RFC 1123 format)"
    )
    expires: datetime | None = Field(
        None, description="Expiration timestamp (parsed from Expires header)"
    )
    data: list[METNorwayDailyData] = Field(
        ..., description="Cached forecast data"
    )

    # Método para serialização JSON (para Redis)
    def to_json(self) -> str:
        return self.model_dump_json()  # Pydantic v2


class METNorwayClient:
    """
    MET Norway client with
    GLOBAL coverage and DAILY data support.

    Regional Quality Strategy:
    - Nordic Region (NO, SE, FI, DK, Baltics): High-quality precipitation
      with radar + crowdsourced bias-correction (1km MET Nordic)
    - Rest of World: Temperature and humidity only (9km ECMWF base)
      Precipitation has lower quality without post-processing
    """

    # Daily variables available from MET Norway
    # Note: Solar radiation NOT available - use other APIs
    # API variable names (from MET Norway JSON):
    #   - air_temperature (instant, hourly)
    #   - air_temperature_max (next_6_hours)
    #   - air_temperature_min (next_6_hours)
    #   - relative_humidity (instant, hourly)
    #   - precipitation_amount (next_1_hours, next_6_hours)
    #   - wind_speed (instant, hourly)
    DAILY_VARIABLES_FOR_ETO = [
        "air_temperature_max",
        "air_temperature_min",
        "air_temperature_mean",  # Calculated from hourly air_temperature
        "precipitation_sum",  # Calculated from precipitation_amount
        "relative_humidity_mean",  # Calculated from hourly relative_humidity
    ]

    # Variables for Nordic region (high quality with bias correction)
    NORDIC_VARIABLES = [
        "air_temperature_max",
        "air_temperature_min",
        "air_temperature_mean",
        "precipitation_sum",  # High quality: radar + crowdsourced
        "relative_humidity_mean",
    ]

    # Variables for rest of world (basic ECMWF, skip precipitation)
    GLOBAL_VARIABLES = [
        "air_temperature_max",
        "air_temperature_min",
        "air_temperature_mean",
        "relative_humidity_mean",
    ]

    def __init__(
        self,
        config: METNorwayConfig | None = None,
        cache: Any | None = None,
    ):
        """
        Initialize MET Norway client (GLOBAL).

        Args:
            config: Custom configuration (optional)
            cache: ClimateCacheService (optional)
        """
        self.config = config or METNorwayConfig()

        # Required headers
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json",
        }

        # Rate limiting usando valores configurados
        limits = httpx.Limits(
            max_keepalive_connections=self.config.max_keepalive_connections,
            max_connections=self.config.max_connections,
        )
        self.client = httpx.AsyncClient(
            timeout=self.config.timeout, headers=headers, limits=limits
        )
        self.cache = cache

    async def close(self):
        """Close HTTP connection."""
        await self.client.aclose()

    @staticmethod
    def _round_coordinates(lat: float, lon: float) -> tuple[float, float]:
        """
        Round coordinates to 4 decimal places as required by MET Norway API.

        From API documentation:
        "Most forecast models are fairly coarse, e.g. using a 1km resolution
        grid. This means there is no need to send requests with any higher
        resolution coordinates. For this reason you should never use more
        than 4 decimals in lat/lon coordinates."

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees

        Returns:
            Tuple of (rounded_lat, rounded_lon)
        """
        return round(lat, 4), round(lon, 4)

    @staticmethod
    @staticmethod
    def is_in_nordic_region(lat: float, lon: float) -> bool:
        """
        Check if coordinates are in Nordic region (MET Nordic 1km dataset).

        The MET Nordic dataset provides high-quality weather data with:
        - 1km resolution (vs 9km global)
        - Hourly updates (vs 4x/day global)
        - Extensive post-processing with radar and crowdsourced data
        - Bias correction for precipitation using radar + Netatmo stations

        Coverage: Norway, Denmark, Sweden, Finland, Baltic countries

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees

        Returns:
            True if in Nordic region (high quality), False otherwise
        """
        in_nordic = GeographicUtils.is_in_nordic(lat, lon)
        # Log bbox para debug (útil em PostGIS queries)
        logger.debug(
            f"Nordic check ({lat}, {lon}): {in_nordic} "
            f"(bbox: {GeographicUtils.NORDIC_BBOX})"
        )
        return in_nordic

    @classmethod
    def get_recommended_variables(cls, lat: float, lon: float) -> list[str]:
        """
        Get recommended variables based on location quality.

        Strategy:
        - Nordic region: Include precipitation (radar + bias-corrected)
        - Rest of world: Exclude precipitation (use Open-Meteo instead)

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees

        Returns:
            List of recommended variable names for the location
        """
        if cls.is_in_nordic_region(lat, lon):
            logger.debug(
                f"📍 Location ({lat}, {lon}) in NORDIC region: "
                f"Using high-quality precipitation (1km + radar)"
            )
            return cls.NORDIC_VARIABLES
        else:
            logger.debug(
                f"📍 Location ({lat}, {lon}) OUTSIDE Nordic region: "
                f"Skipping precipitation (use Open-Meteo)"
            )
            return cls.GLOBAL_VARIABLES

    @validate_coordinates
    async def get_daily_forecast(
        self,
        lat: float,
        lon: float,
        altitude: float | None = None,  # [MELHORIA] Novo param opcional da doc
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        timezone: str | None = None,
        variables: list[str] | None = None,
    ) -> list[METNorwayDailyData]:
        """
        Fetch DAILY weather forecast with pre-calculated aggregations.

        Implements MET Norway API best practices:
        - Coordinates rounded to 4 decimals (cache efficiency)
        - If-Modified-Since headers (avoid unnecessary downloads)
        - Dynamic TTL based on Expires header
        - Status code 203/429 handling
        - Optional altitude for elevation adjustments (as per documentation)

        Performs hourly-to-daily aggregation of MET Norway data including:
        - Temperature extremes and means
        - Humidity
        - Precipitation sums

        Note: Solar radiation and wind speed are NOT provided.
        Use other APIs (Open-Meteo) for radiation and wind data.

        Args:
            lat: Latitude in decimal degrees (-90 to 90)
            lon: Longitude in decimal degrees (-180 to 180)
            altitude: Altitude in meters (optional; uses topographic
                     model as fallback)
            start_date: Start date (default: today)
            end_date: End date (default: start + 5 days)
            timezone: Timezone name (e.g., 'America/Sao_Paulo')
            variables: List of variables to fetch (default: all for ETo)

        Returns:
            List of daily aggregated weather records

        Raises:
            ValueError: Invalid coordinates or date range exceeds 5-day limit
        """
        # NOTE: Coordinate and date validation should happen
        # in climate_validation.py + climate_source_availability.py
        # BEFORE calling this client. This method assumes pre-validated data.

        # Round coordinates to 4 decimals (API best practice)
        lat, lon = self._round_coordinates(lat, lon)

        # Default dates
        if not start_date:
            start_date = datetime.now()
        if not end_date:
            end_date = start_date + timedelta(
                days=5
            )  # EVAonline standard: 5-day forecast

        if start_date > end_date:
            msg = "start_date must be <= end_date"
            raise ValueError(msg)

        # ENFORCE: Limite de 5 dias (EVAonline standard)
        delta_days = (end_date - start_date).days
        if delta_days > 5:
            original_end = end_date
            end_date = start_date + timedelta(days=5)
            logger.warning(
                f"⚠️ Forecast limitado a 5 dias: "
                f"{delta_days} dias solicitados → ajustado para 5 dias "
                f"(era: {original_end.date()}, agora: {end_date.date()})"
            )

        # Default variables (optimized for location quality)
        if not variables:
            variables = self.get_recommended_variables(lat, lon)

        # Check if we're in Nordic region for logging
        in_nordic = self.is_in_nordic_region(lat, lon)
        region_label = "NORDIC (1km)" if in_nordic else "GLOBAL (9km)"

        logger.info(
            f"📍 MET Norway ({region_label}): "
            f"lat={lat}, lon={lon}, altitude={altitude}m, "
            f"variables={len(variables)}"
        )

        # Build cache key
        vars_str = "_".join(sorted(variables)) if variables else "default"
        cache_key = (
            f"met_lf_{lat}_{lon}_{altitude or 'default'}_"
            f"{start_date.date()}_{end_date.date()}_{vars_str}"
        )
        cache_metadata_key = f"{cache_key}_metadata"

        # 1. Check cache and expiration
        last_modified = None
        if self.cache:
            # Assuma cache.get retorna JSON; parse para model
            cached_json = await self.cache.get(cache_metadata_key)
            if cached_json:
                try:
                    cached_metadata = (
                        METNorwayCacheMetadata.model_validate_json(cached_json)
                    )
                    # Check if data has expired
                    if (
                        cached_metadata.expires
                        and datetime.now(cached_metadata.expires.tzinfo)
                        < cached_metadata.expires
                    ):
                        logger.info(
                            "🎯 Cache HIT (not expired): " "MET Norway"
                        )
                        return cached_metadata.data

                    # Data expired - try conditional request with
                    # If-Modified-Since
                    logger.info(
                        "Cache expired, checking with If-Modified-Since..."
                    )
                    last_modified = cached_metadata.last_modified
                except Exception as e:
                    logger.warning(f"Cache parse error: {e}")
                    last_modified = None
            else:
                last_modified = None
        else:
            last_modified = None

        # 2. Fetch from API (with conditional request if possible)
        logger.info("Querying MET Norway API...")

        # Endpoint completo: base_url + /complete
        endpoint = f"{self.config.base_url}/complete"

        # Request parameters
        params: dict[str, float | str] = {
            "lat": lat,
            "lon": lon,
        }
        if altitude is not None:
            params["altitude"] = (
                altitude  # [MELHORIA] Adiciona altitude se fornecido
            )
        if timezone:
            params["timezone"] = timezone
            logger.warning(
                "Timezone parameter may affect date boundaries. "
                "Ensure proper handling in aggregation."
            )

        # Request with retry
        for attempt in range(self.config.retry_attempts):
            try:
                logger.debug(
                    f"MET Norway request "
                    f"(attempt {attempt + 1}/{self.config.retry_attempts}): "
                    f"lat={lat}, lon={lon}, alt={altitude}"
                )

                # Add If-Modified-Since header if we have cached data
                headers = {}
                if last_modified:
                    headers["If-Modified-Since"] = last_modified
                    logger.debug(f"Using If-Modified-Since: {last_modified}")

                response = await self.client.get(
                    endpoint, params=params, headers=headers
                )

                # Handle 304 Not Modified
                if response.status_code == 304:
                    logger.info("✅ 304 Not Modified: Using cached data")
                    if self.cache:
                        cached_json = await self.cache.get(cache_metadata_key)
                        if cached_json:
                            try:
                                cached_metadata = (
                                    METNorwayCacheMetadata.model_validate_json(
                                        cached_json
                                    )
                                )
                                # Update expiration time
                                expires_header = response.headers.get(
                                    "Expires"
                                )
                                if expires_header:
                                    # Usar CacheUtils
                                    new_expires = (
                                        CacheUtils.parse_rfc1123_date(
                                            expires_header
                                        )
                                    )
                                    cached_metadata.expires = new_expires
                                    # Re-cache with updated expiration
                                    ttl = CacheUtils.calculate_cache_ttl(
                                        new_expires
                                    )
                                    await self.cache.set(
                                        cache_metadata_key,
                                        cached_metadata.to_json(),  # Serialize
                                        ttl=ttl,
                                    )
                                return cached_metadata.data
                            except Exception as e:
                                logger.warning(f"Cache update error: {e}")
                    # Fallback if cache unavailable
                    return []

                # Handle 203 Non-Authoritative (deprecated/beta)
                if response.status_code == 203:
                    logger.warning(
                        "⚠️ 203 Non-Authoritative Information: "
                        "This product version is deprecated or in beta. "
                        "Check documentation for updates."
                    )

                # Handle 429 Too Many Requests (rate limiting)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "60")
                    logger.error(
                        f"❌ 429 Too Many Requests: Rate limit exceeded. "
                        f"Retry after {retry_after}s. "
                        f"Consider reducing request frequency."
                    )
                    raise httpx.HTTPStatusError(
                        f"Rate limited (429). Retry after {retry_after}s",
                        request=response.request,
                        response=response,
                    )

                response.raise_for_status()

                # Extract headers
                last_modified_header = response.headers.get("Last-Modified")
                expires_header = response.headers.get("Expires")

                logger.debug(
                    f"Response headers - "
                    f"Last-Modified: {last_modified_header}, "
                    f"Expires: {expires_header}"
                )

                # Parse expires timestamp usando CacheUtils
                expires_dt = CacheUtils.parse_rfc1123_date(expires_header)

                # Process response
                data = response.json()
                parsed_data = self._parse_daily_response(
                    data, variables, start_date, end_date
                )

                logger.info(
                    f"MET Norway: " f"{len(parsed_data)} days retrieved"
                )

                # 3. Save to cache with metadata
                if self.cache and parsed_data:
                    # Create metadata object
                    metadata = METNorwayCacheMetadata(
                        last_modified=last_modified_header,
                        expires=expires_dt,
                        data=parsed_data,
                    )

                    # Calculate TTL from Expires header usando CacheUtils
                    ttl = CacheUtils.calculate_cache_ttl(expires_dt)

                    # Save to cache
                    await self.cache.set(
                        cache_metadata_key, metadata.to_json(), ttl=ttl
                    )  # Serialize
                    logger.debug(
                        f"Cache SAVE: MET Norway"
                        f"(TTL: {ttl}s, expires: {expires_dt})"
                    )

                return parsed_data

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Don't retry on rate limiting
                    raise
                logger.warning(
                    f"MET Norway request failed "
                    f"(attempt {attempt + 1}): {e}"
                )
                if attempt == self.config.retry_attempts - 1:
                    raise
                await self._delay_retry()

            except httpx.HTTPError as e:
                logger.warning(
                    f"MET Norway request failed "
                    f"(attempt {attempt + 1}): {e}"
                )
                if attempt == self.config.retry_attempts - 1:
                    raise
                await self._delay_retry()

        return []

    def _parse_daily_response(
        self,
        data: dict,
        variables: list[str],
        start_date: datetime,
        end_date: datetime,
    ) -> list[METNorwayDailyData]:
        """
        Process MET Norway API response usando METNorwayAggregator.

        Args:
            data: API response JSON
            variables: Requested variable names (for validation)
            start_date: Start of period
            end_date: End of period

        Returns:
            List of daily aggregated records
        """
        try:
            # Extract geometry for calculations
            geometry = data.get("geometry", {})
            coordinates = geometry.get("coordinates", [])

            if len(coordinates) >= 2:
                api_lon, api_lat = coordinates[0], coordinates[1]
                api_elevation = (
                    coordinates[2] if len(coordinates) > 2 else None
                )
                logger.debug(
                    f"API geometry: lat={api_lat}, lon={api_lon}, "
                    f"elev={api_elevation}m"
                )
            else:
                api_lat, api_lon, api_elevation = None, None, None
                logger.warning("No geometry in API response")

            timeseries = data.get("properties", {}).get("timeseries", [])

            if not timeseries:
                logger.warning("MET Norway: no data")
                return []

            # Usar METNorwayAggregationUtils de weather_utils
            aggregator = METNorwayAggregationUtils()

            # 1. Agregar dados horários em diários
            daily_raw_data = aggregator.aggregate_hourly_to_daily(
                timeseries, start_date, end_date
            )

            # 2. Calcular agregações finais
            daily_data = aggregator.calculate_daily_aggregations(
                daily_raw_data, WeatherConversionUtils()
            )

            # 3. Validar dados agregados
            if not aggregator.validate_daily_data(daily_data):
                logger.warning("Dados diários falharam na validação")

            # Log padronizado
            self._log_fetch_summary(
                len(daily_data), start_date, end_date, len(timeseries)
            )
            return daily_data

        except Exception as e:
            logger.error(
                f"❌ Error processing MET Norway response: {e}",
                exc_info=True,
            )
            msg = f"Invalid MET Norway response: {e}"
            raise ValueError(msg) from e

    def _log_fetch_summary(
        self,
        days_count: int,
        start_date: datetime,
        end_date: datetime,
        hourly_entries: int = 0,
    ):
        """
        Log padronizado para fetches.

        Args:
            days_count: Número de dias retornados
            start_date: Data inicial
            end_date: Data final
            hourly_entries: Número de entradas horárias processadas
        """
        if hourly_entries > 0:
            logger.info(
                f"MET Norway: {days_count} days retrieved "
                f"({start_date.date()} to {end_date.date()}) "
                f"from {hourly_entries} hourly entries"
            )
        else:
            logger.info(
                f"MET Norway: {days_count} days retrieved "
                f"({start_date.date()} to {end_date.date()})"
            )

    async def _delay_retry(self):
        """Wait before retry attempt."""
        import asyncio

        await asyncio.sleep(self.config.retry_delay)

    async def health_check(self) -> bool:
        """
        Check if MET Norway API is accessible.

        Returns:
            True if API responds successfully, False otherwise
        """
        try:
            # Use endpoint completo e params mínimos
            endpoint = f"{self.config.base_url}/complete"
            params: dict[str, float | str] = {
                "lat": -15.7939,  # Brasília
                "lon": -47.8828,
            }

            response = await self.client.get(endpoint, params=params)
            response.raise_for_status()

            logger.info("MET Norway health check: OK")
            return True

        except Exception as e:
            logger.error(f"MET Norway health check failed: {e}")
            return False

    def get_attribution(self) -> str:
        """
        Return CC-BY 4.0 attribution text.

        Returns:
            Attribution text as required by license
        """
        return "Weather data from MET Norway (CC BY 4.0)"

    def get_coverage_info(self) -> dict[str, Any]:
        """
        Return geographic coverage information.

        Returns:
            dict: Coverage information with regional quality tiers
        """
        return {
            "region": "GLOBAL",
            "bbox": {
                "lon_min": -180,
                "lat_min": -90,
                "lon_max": 180,
                "lat_max": 90,
            },
            "description": (
                "Global coverage with regional quality optimization"
            ),
            # 5 days ahead (EVAonline standard)
            "forecast_horizon": "5 days ahead (EVAonline standard)",
            "data_type": "Forecast (no historical data)",
            "update_frequency": "Updated every 6 hours",
            "quality_tiers": {
                "nordic": {
                    "region": "Norway, Denmark, Sweden, Finland, Baltics",
                    "bbox": GeographicUtils.NORDIC_BBOX,
                    "resolution": "1 km",
                    "model": "MEPS 2.5km + downscaling",
                    "updates": "Hourly",
                    "post_processing": "Extensive (radar + crowdsourced)",
                    "variables": (
                        "Temperature, Humidity, Precipitation (high quality)"
                    ),
                    "precipitation_quality": (
                        "High (radar + Netatmo bias correction)"
                    ),
                },
                "global": {
                    "region": "Rest of World",
                    "resolution": "9 km",
                    "model": "ECMWF",
                    "updates": "4x per day",
                    "post_processing": "Minimal",
                    "variables": "Temperature, Humidity only",
                    "precipitation_quality": "Lower (use Open-Meteo instead)",
                },
            },
        }

    @classmethod
    def get_data_availability_info(cls) -> dict[str, Any]:
        """
        Return data availability information.

        Returns:
            dict: Information about temporal coverage and limitations
        """
        return {
            "data_start_date": None,  # Forecast only
            "max_historical_years": 0,
            "forecast_horizon_days": 9,  # [MELHORIA] Atualizado para 9
            "description": "Forecast data only, global coverage",
            "coverage": "Global",
            "update_frequency": "Every 6 hours",
        }


# Factory function
def create_met_norway_client(
    cache: Any | None = None,
) -> METNorwayClient:
    """
    Factory function to create MET Norway client
    (GLOBAL coverage).

    Args:
        cache: Optional ClimateCacheService instance

    Returns:
        Configured METNorwayClient instance
    """
    return METNorwayClient(cache=cache)
