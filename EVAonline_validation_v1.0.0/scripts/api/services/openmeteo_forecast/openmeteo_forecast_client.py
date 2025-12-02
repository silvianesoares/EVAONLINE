"""
Open-Meteo Forecast API Client - Recent + Future Climate Data.

API: https://api.open-meteo.com/v1/forecast

Coverage: Global

Period: (today - 25 days) to (today + 5 days)
Total: 30 days (25 past + 5 future)

Resolution: Daily (aggregated from hourly data)

License: CC BY 4.0 (attribution required)

Open-Meteo is open-source
Source code is available on GitHub under the GNU Affero General
Public Licence Version 3 AGPLv3 or any later version.
GitHub Open-Meteo: https://github.com/open-meteo/open-meteo

Variables (10):
- Temperature: max, mean, min (°C)
- Relative Humidity: max, mean, min (%)
- Wind Speed: mean at 10m (m/s)
- Shortwave Radiation: sum (MJ/m²)
- Precipitation: sum (mm)
- ET0 FAO Evapotranspiration (mm)

CACHE STRATEGY (Nov 2025):
- Redis cache via ClimateCache (optional)
- Fallback: requests_cache local (if Redis not available)
- Dynamic TTL:
  * Forecast (future): 1h
  * Recent (past): 6h
"""

from datetime import datetime, timedelta
from typing import Any, Dict

import numpy as np
import pandas as pd
import openmeteo_requests
import requests_cache
from loguru import logger
from retry_requests import retry

from scripts.api.services.geographic_utils import GeographicUtils


class OpenMeteoForecastConfig:
    """Configuration for Open-Meteo Forecast API."""

    # API URL
    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    # IMPORTANT: Timeline constraints (MAX_PAST_DAYS, MAX_FUTURE_DAYS)
    # are defined in climate_source_availability.py (SOURCE OF TRUTH).
    # This client ASSUMES pre-validated dates from climate_validation.py.
    # - MAX_PAST: 25 days (today - 25d)
    # - MAX_FUTURE: 5 days (today + 5d)
    # Validation should happen BEFORE calling this client.
    MAX_PAST_DAYS = 25  # today - 25 days
    MAX_FUTURE_DAYS = 5  # today + 5 days

    # Cache TTL (data updates daily)
    CACHE_TTL = 3600 * 6  # 6 hours

    # 10 Climate variables
    DAILY_VARIABLES = [
        "temperature_2m_max",
        "temperature_2m_mean",
        "temperature_2m_min",
        "relative_humidity_2m_max",
        "relative_humidity_2m_mean",
        "relative_humidity_2m_min",
        "wind_speed_10m_mean",
        "shortwave_radiation_sum",
        "precipitation_sum",
        "et0_fao_evapotranspiration",
    ]

    # Network settings
    TIMEOUT = 30
    RETRY_ATTEMPTS = 5
    BACKOFF_FACTOR = 0.2


class OpenMeteoForecastClient:
    """
    Client for Open-Meteo Forecast API (recent + future data).

    Supports Redis cache (via ClimateCache) with fallback to local cache.
    """

    def __init__(self, cache: Any | None = None, cache_dir: str = ".cache"):
        """
        Initialize Forecast client with caching and retry logic.

        Args:
            cache: Optional ClimateCache instance (Redis)
            cache_dir: Directory for fallback requests_cache
        """
        self.config = OpenMeteoForecastConfig()
        self.cache = cache  # Redis cache (opcional)
        self._setup_client(cache_dir)

        cache_type = "Redis" if cache else "Local"
        logger.info(
            f"OpenMeteoForecastClient initialized ({cache_type} cache, "
            f"-25d to +5d)"
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
        self.client = openmeteo_requests.Client(session=retry_session)
        logger.debug(f"Cache dir: {cache_dir}, TTL: 6 hours")

    async def get_climate_data(
        self,
        lat: float,
        lng: float,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """
        Get recent/future climate data from Forecast API.

        IMPORTANT: This client ASSUMES that:
        - Coordinates validated in climate_validation.py
        - Period (today-25d to today+5d) validated in
          climate_source_availability.py
        This client ONLY fetches data, without re-validating dates.

        Uses Redis cache if available, with TTL based on data type:
        - Forecast (future): TTL 1h
        - Recent (past): TTL 6h
        """
        # 1. Validate inputs
        self._validate_inputs(lat, lng, start_date, end_date)

        # Ajustar datas para limites da API
        from datetime import datetime, timedelta

        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        today = datetime.now().date()

        # Forecast API: (hoje - 25d) até (hoje + 5d)
        min_date = today - timedelta(days=25)
        max_date = today + timedelta(days=5)

        if start_dt.date() < min_date:
            logger.warning(
                f"Ajustando start_date de {start_date} para {min_date}"
            )
            start_date = min_date.isoformat()

        if end_dt.date() > max_date:
            logger.warning(f"Ajustando end_date de {end_date} para {max_date}")
            end_date = max_date.isoformat()

        # 2. Try Redis cache first (if available)
        if self.cache:
            cache_key = self._get_cache_key(lat, lng, start_date, end_date)
            cached_data = await self.cache.get(cache_key)

            if cached_data:
                days_cached = len(
                    cached_data.get("climate_data", {}).get("dates", [])
                )
                logger.info(
                    f"Cache HIT (Redis): OpenMeteo Forecast "
                    f"({lat:.4f}, {lng:.4f}) - {days_cached} days cached"
                )
                return cached_data

        # 3. Prepare API parameters
        # OpenMeteo Forecast API: usa past_days e forecast_days
        from datetime import datetime, timedelta

        # Recalcular datas após ajustes
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        today_date = datetime.now().date()

        # Calcular past_days e forecast_days
        # Forecast API usa hoje como ponto de referência
        if start_dt.date() <= today_date:
            past_days = (today_date - start_dt.date()).days
        else:
            past_days = 0

        if end_dt.date() > today_date:
            # forecast_days conta a partir de amanhã, não hoje
            forecast_days = (end_dt.date() - today_date).days
        else:
            forecast_days = 0

        # Limites da API (conforme configurado no projeto)
        past_days = min(past_days, 25)  # Project limit: 25 past days
        forecast_days = min(forecast_days, 16)  # API supports up to 16

        # API Forecast sempre inclui hoje (day 0) automaticamente
        # past_days=15 + hoje + forecast_days=5 = 21 dias
        params = {
            "latitude": lat,
            "longitude": lng,
            "daily": self.config.DAILY_VARIABLES,
            "models": "best_match",
            "timezone": "auto",
            "wind_speed_unit": "ms",
        }

        # Adicionar past_days e forecast_days apenas se > 0
        if past_days > 0:
            params["past_days"] = past_days
        if forecast_days > 0:
            params["forecast_days"] = forecast_days

        logger.info(f"Cache MISS: Forecast API | ({lat:.4f}, {lng:.4f})")
        logger.info(f"Requested period: {start_date} to {end_date}")
        logger.info(
            f"Calculated: past_days={past_days}, "
            f"forecast_days={forecast_days}"
        )
        logger.info(f"API params: {params}")

        # 4. Fetch data from Forecast API
        try:
            responses = self.client.weather_api(
                self.config.BASE_URL, params=params
            )
            response = responses[0]  # Single location

            # 5. Extract location metadata
            location = {
                "latitude": response.Latitude(),
                "longitude": response.Longitude(),
                "elevation": response.Elevation(),
                "timezone": response.Timezone(),
                "timezone_abbreviation": response.TimezoneAbbreviation(),
                "utc_offset_seconds": response.UtcOffsetSeconds(),
            }

            # 6. Extract climate data
            daily = response.Daily()

            # Use Time(), TimeEnd() and Interval() para criar date range
            # conforme documentação Open-Meteo
            start_time = daily.Time()
            end_time = daily.TimeEnd()
            interval = daily.Interval()

            logger.info(
                f"Time range: {start_time} to {end_time}, "
                f"interval: {interval}s"
            )

            # Criar date range usando pandas (método oficial Open-Meteo)
            dates_range = pd.date_range(
                start=pd.to_datetime(start_time, unit="s", utc=True),
                end=pd.to_datetime(end_time, unit="s", utc=True),
                freq=pd.Timedelta(seconds=interval),
                inclusive="left",
            )

            dates = dates_range.tolist()

            logger.info(
                f"API returned {len(dates)} days: "
                f"{dates[0].date()} to {dates[-1].date()} | "
                f"Elevation: {location['elevation']}m"
            )

            climate_data = {"dates": dates}

            # Map variables to data
            for i, var_name in enumerate(self.config.DAILY_VARIABLES):
                try:
                    values = daily.Variables(i).ValuesAsNumpy()
                    # Handle scalar values (single day) vs arrays
                    if hasattr(values, "tolist"):
                        climate_data[var_name] = values.tolist()
                    else:
                        # Scalar value - wrap in list
                        climate_data[var_name] = [float(values)]
                except Exception as e:
                    logger.warning(f"Variable {var_name} not available: {e}")
                    climate_data[var_name] = [None] * len(dates)

            # Convert wind from 10m to 2m for FAO-56 PM equation
            if "wind_speed_10m_mean" in climate_data:
                wind_10m = climate_data["wind_speed_10m_mean"]
                wind_10m_array = np.array(wind_10m, dtype=float)
                wind_2m_array = self.convert_wind_10m_to_2m(wind_10m_array)
                climate_data["wind_speed_2m_mean"] = wind_2m_array.tolist()
                logger.debug(
                    f"Converted wind 10m to 2m: "
                    f"{len(wind_2m_array)} values"
                )

            # 7. Add metadata
            metadata = {
                "api": "forecast",
                "url": self.config.BASE_URL,
                "data_points": len(dates),
                "cache_ttl_hours": self._get_ttl_hours(start_date, end_date),
            }

            result = {
                "location": location,
                "climate_data": climate_data,
                "metadata": metadata,
            }

            logger.info(
                f"Forecast: {len(dates)} days | "
                f"Elevation: {location['elevation']:.0f}m"
            )

            # 8. Save to Redis cache (if available)
            if self.cache:
                ttl = self._get_ttl_seconds(start_date, end_date)
                cache_key = self._get_cache_key(lat, lng, start_date, end_date)
                await self.cache.set(cache_key, result, ttl=ttl)
                logger.debug(f"Cached with TTL {ttl}s")

            return result

        except Exception as e:
            logger.error(f"Forecast API error: {str(e)}")
            raise

    @staticmethod
    def convert_wind_10m_to_2m(
        u_height: np.ndarray, height: float = 10.0
    ) -> np.ndarray:
        """
        Eq. 47 - Logarithmic wind speed conversion to 2m height

        Args:
            u_height: Wind speed at measurement height (m/s)
            height: Measurement height (m) - default 10m for Open-Meteo
                    NASA POWER data is already at 2m, so height=2.0

        Returns:
            Wind speed at 2m height (m/s)
        """
        if height == 2.0:
            # NASA POWER is already at 2m
            return np.maximum(u_height, 0.5)

        # FAO-56 Eq. 47 logarithmic conversion
        u2 = u_height * (4.87 / np.log(67.8 * height - 5.42))
        return np.maximum(u2, 0.5)  # Physical minimum limit

    def _get_cache_key(
        self, lat: float, lng: float, start_date: str, end_date: str
    ) -> str:
        """Generate Redis cache key."""
        lat_rounded = round(lat, 2)
        lng_rounded = round(lng, 2)
        return (
            f"climate:openmeteo:forecast:{lat_rounded}:{lng_rounded}:"
            f"{start_date}:{end_date}"
        )

    def _get_ttl_seconds(self, start_date: str, end_date: str) -> int:
        """
        Calculate TTL based on data type.

        - Forecast (future): 1h (data changes frequently)
        - Recent (past): 6h (data more stable)
        """
        today = datetime.now().date()
        end = datetime.fromisoformat(end_date).date()

        if end > today:
            # Forecast data (future)
            return 3600  # 1 hour
        else:
            # Recent data (past)
            return 3600 * 6  # 6 hours

    def _get_ttl_hours(self, start_date: str, end_date: str) -> int:
        """Get TTL in hours for metadata."""
        return self._get_ttl_seconds(start_date, end_date) // 3600

    def _validate_inputs(
        self, lat: float, lng: float, start_date: str, end_date: str
    ):
        """
        Validate coordinate and date range inputs.

        IMPORTANT: Basic validation of coordinates and dates.
        Period validations (7-30 days) are done in climate_validation.py.

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

        # Forecast constraints
        today = datetime.now().date()
        min_date = today - timedelta(days=self.config.MAX_PAST_DAYS)
        max_date = today + timedelta(days=self.config.MAX_FUTURE_DAYS)

        if start.date() < min_date:
            msg = (
                f"Forecast API: start_date must be >= {min_date} "
                f"(today - 25 days). Use Archive API for older "
                f"data."
            )
            raise ValueError(msg)

        if end.date() > max_date:
            msg = (
                f"Forecast API: end_date must be <= {max_date} "
                f"(today + 5 days)"
            )
            raise ValueError(msg)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        """
        Get information about Forecast API.

        Returns:
            Dict with API metadata
        """
        today = datetime.now().date()
        min_date = today - timedelta(days=25)  # API supports 25 past days
        max_date = today + timedelta(days=5)  # API supports 5 future days

        return {
            "api": "Open-Meteo Forecast",
            "url": "https://api.open-meteo.com/v1/forecast",
            "coverage": "Global",
            "period": f"{min_date} to {max_date}",
            "resolution": "Daily",
            "license": "CC BY 4.0",
            "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)",
            "cache_ttl": "6 hours",
        }


# Factory helper
def create_forecast_client(
    cache: Any | None = None, cache_dir: str = ".cache"
) -> OpenMeteoForecastClient:
    """
    Factory function to create Forecast client.

    Args:
        cache: Optional ClimateCache instance (Redis)
        cache_dir: Fallback cache directory

    Returns:
        Configured OpenMeteoForecastClient
    """
    return OpenMeteoForecastClient(cache=cache, cache_dir=cache_dir)
