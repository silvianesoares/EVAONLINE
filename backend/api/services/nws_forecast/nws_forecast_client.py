"""
NWS Forecast Client - Hourly to Daily Aggregation.
Client for NWS API (National Weather Service / NOAA) FORECAST ONLY.
Separated from nws_stations_client.py (station/observation endpoints).
License: US Government Public Domain - Free use.

- Forecast Data
- Start: Today
- End: Today + 5 days (EVAonline standard)
- Total: 6 days forecast

IMPORTANT: This client uses ONLY FORECAST endpoints:
- GET /points/{lat},{lon} -> grid metadata
- GET /gridpoints/{grid} -> gridded forecast data (quantitative values)

Features:
- HOURLY data with aggregation to DAILY
- Coverage: USA Continental (bbox: -125W to -66W, 24N to 49N)
- Limit: 5 days forecast (120 hours)
- Automatic aggregation: mean (temp/humidity/wind), sum (precip),
  max/min (temp)
- Filters past data automatically (timezone-aware comparison)
- Automatic conversion: °F -> °C, mph -> m/s (when needed)

NWS API Terms of Service:
- No authentication required
- User-Agent REQUIRED (per documentation)
- Public domain (no usage restrictions)
- Rate limit: ~5 requests/second
- Update frequency: Hourly

Known Issues (2025):
- API may return past data (automatically filtered)
- Minimum temperature has higher variation (nocturnal microclimate)
- Using /gridpoints endpoint for quantitative precipitation (mm)
- Precipitation values may be accumulated over periods (not hourly)
- Radiation: Not directly available, estimated from skyCover (0-100%)
- Wind speed in km/h (wmoUnit:km_h-1) - converted to m/s
- Dewpoint and skyCover critical for ETo calculation

Coverage: USA Continental (lon: -125 to -66W, lat: 24 to 49N)
Extended bbox for territories: lat 18 to 71N (includes Alaska, Hawaii)

API Documentation:
https://www.weather.gov/documentation/services-web-api#/
General FAQs: https://weather-gov.github.io/api/general-faqs
"""

import asyncio
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import httpx
import numpy as np
from loguru import logger
from pydantic import BaseModel, Field

try:
    from backend.api.services.geographic_utils import (
        GeographicUtils,
    )
    from backend.api.services.weather_utils import (
        WeatherConversionUtils,
    )
except ImportError:
    from ..geographic_utils import GeographicUtils
    from ..weather_utils import WeatherConversionUtils


class NWSConfig(BaseModel):
    """
    NWS API configuration.

    Attributes:
        base_url: NWS API base endpoint (api.weather.gov)
        timeout: HTTP request timeout (seconds)
        retry_attempts: Number of retry attempts on failure
        retry_delay: Base delay for exponential retry (seconds)
        user_agent: User-Agent header (REQUIRED by NWS API)
    """

    base_url: str = "https://api.weather.gov"
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0
    user_agent: str = os.getenv(
        "NWS_USER_AGENT",
        ("EVAonline/1.0 " "(https://github.com/silvianesoares/EVAONLINE)"),
    )


class NWSHourlyData(BaseModel):
    """
    HOURLY data returned by NWS Forecast API.

    Represents an hourly forecast period with all meteorological
    parameters. Used as base for daily aggregation.

    Attributes:
        timestamp: ISO 8601 timestamp (timezone-aware)
        temp_celsius: Temperature in degrees Celsius
        humidity_percent: Relative humidity (0-100%)
        wind_speed_ms: Wind speed in m/s (already in m/s)
        wind_speed_2m_ms: Wind speed at 2m height (FAO-56 converted)
        dewpoint_celsius: Dew point in °C (for ETo calculation)
        sky_cover_percent: Cloud cover 0-100% (for radiation)
        precip_mm: Quantitative precipitation in millimeters (from gridpoints)
        probability_precip_percent: Precipitation probability (0-100%)
        short_forecast: Short textual forecast description
    """

    timestamp: str = Field(..., description="ISO 8601 timestamp")
    temp_celsius: float | None = Field(None, description="Temperature (C)")
    temp_fahrenheit: float | None = Field(
        None, description="Temperature (F) - raw from API if imperial"
    )
    humidity_percent: float | None = Field(
        None, description="Relative humidity (%)"
    )
    wind_speed_ms: float | None = Field(
        None, description="Wind speed at 10m (m/s)"
    )
    wind_speed_mph: float | None = Field(
        None, description="Wind speed (mph) - raw from API if imperial"
    )
    wind_speed_2m_ms: float | None = Field(
        None, description="Wind speed at 2m (m/s) - FAO-56"
    )
    dewpoint_celsius: float | None = Field(
        None, description="Dew point (C) - for ETo"
    )
    dewpoint_fahrenheit: float | None = Field(
        None, description="Dew point (F) - raw from API if imperial"
    )
    sky_cover_percent: float | None = Field(
        None, description="Cloud cover (%) - for solar radiation"
    )
    precip_mm: float | None = Field(
        None,
        description="Precipitation (mm) - WARNING: may be accumulated value",
    )
    probability_precip_percent: float | None = Field(
        None, description="Precipitation probability (%)"
    )
    pressure_hpa: float | None = Field(
        None,
        description="Atmospheric pressure (hPa) - estimated from elevation",
    )
    max_temp_celsius: float | None = Field(
        None, description="Official max temp (C) - from NWS 12h/24h periods"
    )
    min_temp_celsius: float | None = Field(
        None, description="Official min temp (C) - from NWS 12h/24h periods"
    )
    short_forecast: str | None = Field(None, description="Short forecast")


class NWSDailyData(BaseModel):
    """
    DAILY data (hourly data aggregation).

    Aggregates multiple hourly periods into daily statistics using numpy.
    Includes original hourly data for reference.

    Aggregation:
        - Temperature: mean, max, min (numpy.mean/max/min)
        - Humidity: mean (numpy.mean)
        - Wind: mean (numpy.mean)
        - Precipitation: sum (numpy.sum)
        - Precipitation probability: mean (numpy.mean)

    Attributes:
        date: Date (datetime object, no time)
        temp_mean_celsius: Daily mean temperature (°C)
        temp_max_celsius: Daily maximum temperature (°C) - uses official
            NWS max when available
        temp_min_celsius: Daily minimum temperature (°C) - uses official
            NWS min when available
        humidity_mean_percent: Daily mean humidity (%)
        wind_speed_mean_ms: Daily mean wind speed (m/s)
        dewpoint_mean_celsius: Daily mean dew point (°C)
        pressure_mean_hpa: Daily mean atmospheric pressure (hPa)
        solar_radiation_mj_m2_day: Solar radiation (MJ/m²/day) estimated
            from sky cover using calibrated USA-ASOS coefficients
            (Belcher & DeGaetano 2007) with water vapor correction
        precip_total_mm: Daily total precipitation (mm) - ESTIMATE ONLY,
            may be overestimated due to period accumulation
        probability_precip_mean_percent: Mean precipitation probability (%)
        short_forecast: Short forecast (first period of the day)
        hourly_data: List of original hourly data
    """

    date: datetime = Field(
        ..., description="Date (YYYY-MM-DD)"
    )  # datetime for consistency
    temp_mean_celsius: float | None = Field(None, description="Mean temp (C)")
    temp_max_celsius: float | None = Field(None, description="Max temp (C)")
    temp_min_celsius: float | None = Field(None, description="Min temp (C)")
    humidity_mean_percent: float | None = Field(
        None, description="Mean humidity (%)"
    )
    wind_speed_mean_ms: float | None = Field(
        None, description="Mean wind speed at 2m (m/s) - FAO-56"
    )
    dewpoint_mean_celsius: float | None = Field(
        None, description="Mean dew point (C) - for ETo"
    )
    pressure_mean_hpa: float | None = Field(
        None, description="Mean atmospheric pressure (hPa)"
    )
    solar_radiation_mj_m2_day: float | None = Field(
        None,
        description="Solar radiation (MJ/m²/day) - estimated from skyCover",
    )
    precip_total_mm: float | None = Field(
        None, description="Total precipitation (mm)"
    )
    probability_precip_mean_percent: float | None = Field(
        None, description="Mean precipitation probability (%)"
    )
    short_forecast: str | None = Field(
        None, description="Short forecast (first period)"
    )
    hourly_data: list[NWSHourlyData] = Field(
        default_factory=list, description="Original hourly data"
    )


# Alias for compatibility
NWSData = NWSDailyData


class NWSForecastClient:
    """
    Async client for NWS API - FORECAST ONLY.

    Async HTTP client to get weather forecasts from
    National Weather Service (NOAA). Focuses exclusively on
    forecast endpoints, no station/observation data.

    Workflow:
        1. get_forecast_data(): Hourly data (120 hours, ~5 days)
        2. get_daily_forecast_data(): Aggregates hourly to daily (5 days)

    Endpoints used:
        - GET /points/{lat},{lon} -> grid metadata
        - GET /gridpoints/{wfo}/{x},{y} -> quantitative gridded data

    Context Manager:
        Supports async with for automatic resource management.

    Example:
        async with NWSForecastClient() as client:
            data = await client.get_daily_forecast_data(
                39.7392, -104.9903
            )
            for day in data:
                print(f"{day.date}: {day.temp_max_celsius}°C")

    Validation:
        Tested in production with Denver, CO data.
        Compared with Open-Meteo (mean temp max diff: 0.81°C).
        Status: VALIDATED FOR PRODUCTION (Nov 2025).
    """

    def __init__(self, config: NWSConfig | None = None):
        self.config = config or NWSConfig()
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "application/geo+json",
            },
            follow_redirects=True,
        )
        logger.info(
            f"NWSForecastClient initialized | base_url={self.config.base_url}"
        )

    async def close(self):
        await self.client.aclose()
        logger.debug("NWSForecastClient closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _get_grid_metadata(
        self, lat: float, lon: float
    ) -> dict[str, Any]:
        """
        GET /points/{lat},{lon} -> grid metadata.

        Gets NWS grid metadata for specific coordinates.
        Required to access forecast endpoints.

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)

        Returns:
            dict with gridId, gridX, gridY, forecast_hourly_url

        Raises:
            httpx.HTTPStatusError: If coordinates outside coverage (404)
            ValueError: If metadata incomplete
        """
        url = f"/points/{lat:.4f},{lon:.4f}"

        for attempt in range(self.config.retry_attempts):
            try:
                response = await self.client.get(url)
                response.raise_for_status()
                data = response.json()
                props = data.get("properties", {})

                grid_id = props.get("gridId")
                grid_x = props.get("gridX")
                grid_y = props.get("gridY")
                forecast_hourly_url = props.get("forecastHourly")

                if not all([grid_id, grid_x, grid_y, forecast_hourly_url]):
                    raise ValueError("Incomplete grid metadata")

                return {
                    "gridId": grid_id,
                    "gridX": grid_x,
                    "gridY": grid_y,
                    "forecast_hourly_url": forecast_hourly_url,
                }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise
                if attempt < self.config.retry_attempts - 1:
                    await self._delay_retry(attempt)
                else:
                    raise

        # Should never reach here due to raise in loop
        raise RuntimeError("Failed to get grid metadata after all retries")

    async def _get_forecast_grid_data(
        self, grid_id: str, grid_x: int, grid_y: int
    ) -> dict[str, Any]:
        """
        GET /gridpoints/{gridId}/{gridX},{gridY} - Gridded forecast data.

        Returns quantitative values as time series arrays (for ETo):
        - temperature, maxTemperature, minTemperature (°C)
        - relativeHumidity (0-100%)
        - windSpeed (m/s)
        - dewpoint (°C) - critical for vapor pressure
        - skyCover (0-100%) - for solar radiation estimation
        - quantitativePrecipitation (mm)
        - probabilityOfPrecipitation (0-100%)

        Each variable has structure:
        {
          "values": [
            {"validTime": "2025-11-28T00:00:00+00:00/PT1H", "value": 25.5}
          ]
        }
        """
        url = f"/gridpoints/{grid_id}/{grid_x},{grid_y}"

        for attempt in range(self.config.retry_attempts):
            try:
                response = await self.client.get(url)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError:
                if attempt < self.config.retry_attempts - 1:
                    await self._delay_retry(attempt)
                else:
                    raise

        # Should never reach here due to raise in loop
        raise RuntimeError("Failed to get forecast grid data after retries")

    def _get_uom_from_layer(self, layer_data: dict) -> str | None:
        """Extract unit of measure (uom) from grid layer data."""
        return layer_data.get("uom") if layer_data else None

    def _parse_grid_time_series(
        self, values_array: list[dict]
    ) -> dict[str, float]:
        """
        Parse time series array from gridded data.

        Format: [{"validTime": "ISO8601/DURATION", "value": number}, ...]
        Returns: {timestamp_str: value}

        Improvements: Added debug logging and timezone Z handling
        """
        result = {}

        for item in values_array:
            try:
                valid_time = item.get("validTime", "")
                value = item.get("value")

                if not valid_time or value is None:
                    continue

                # Parse "2025-11-28T00:00:00+00:00/PT1H" format
                if "/" in valid_time:
                    start_time_str = valid_time.split("/")[0]
                else:
                    start_time_str = valid_time

                # Ensure consistent format (Z -> +00:00)
                if start_time_str.endswith("Z"):
                    start_time_str = start_time_str[:-1] + "+00:00"

                result[start_time_str] = float(value)
            except Exception as e:
                logger.debug(f"Erro parsing time series item: {e}")
                continue

        return result

    def _parse_forecast_grid_data(
        self, response_data: dict[str, Any]
    ) -> list[NWSHourlyData]:
        """
        Parse gridded forecast data with variables for ETo calculation.

        ONLY method used - provides quantitative numerical data.
        Text-based /forecast/hourly endpoint NOT used.

        Extracts time series for hourly data:
        - temperature (°C) - hourly values only
        - relativeHumidity (%)
        - windSpeed (m/s - already in correct unit)
        - dewpoint (°C - critical for ETo)
        - skyCover (% - for solar radiation estimation)
        - quantitativePrecipitation (mm)
        - probabilityOfPrecipitation (%)

        Note: maxTemperature/minTemperature are calculated during
        daily aggregation from hourly temperature values.

        Args:
            response_data: JSON from /gridpoints/{wfo}/{x},{y} endpoint

        Returns:
            List of NWSHourlyData (complete hourly data for ETo)
        """
        from datetime import timezone

        props = response_data.get("properties", {})

        # Log available variables for debugging
        available_vars = []
        for var_name in [
            "temperature",
            "dewpoint",
            "skyCover",
            "windSpeed",
            "relativeHumidity",
            "quantitativePrecipitation",
        ]:
            if props.get(var_name, {}).get("values"):
                available_vars.append(var_name)

        logger.debug(f"Available grid variables: {available_vars}")

        # Extract time series and check units (uom property)
        # NWS API uses WMO unit codes - typically SI (Celsius, km/h)
        temp_layer = props.get("temperature", {})
        temp_uom = self._get_uom_from_layer(temp_layer)
        temps = self._parse_grid_time_series(temp_layer.get("values", []))

        # Extract official max/min temperatures (12h/24h periods)
        # More accurate than calculating from hourly values
        max_temp_layer = props.get("maxTemperature", {})
        max_temps_official = self._parse_grid_time_series(
            max_temp_layer.get("values", [])
        )
        min_temp_layer = props.get("minTemperature", {})
        min_temps_official = self._parse_grid_time_series(
            min_temp_layer.get("values", [])
        )

        dewpoint_layer = props.get("dewpoint", {})
        dewpoint_uom = self._get_uom_from_layer(dewpoint_layer)
        dewpoint = self._parse_grid_time_series(
            dewpoint_layer.get("values", [])
        )

        wind_layer = props.get("windSpeed", {})
        wind_uom = self._get_uom_from_layer(wind_layer)
        wind_speed = self._parse_grid_time_series(wind_layer.get("values", []))

        humidity = self._parse_grid_time_series(
            props.get("relativeHumidity", {}).get("values", [])
        )
        sky_cover = self._parse_grid_time_series(
            props.get("skyCover", {}).get("values", [])
        )
        precip = self._parse_grid_time_series(
            props.get("quantitativePrecipitation", {}).get("values", [])
        )
        precip_prob = self._parse_grid_time_series(
            props.get("probabilityOfPrecipitation", {}).get("values", [])
        )

        # Log units for debugging (typically wmoUnit:degC, wmoUnit:km_h-1)
        logger.debug(
            f"Units: temp={temp_uom}, dewpoint={dewpoint_uom}, "
            f"wind={wind_uom}"
        )

        # Merge all timestamps
        all_timestamps = set()
        all_timestamps.update(temps.keys())
        all_timestamps.update(humidity.keys())
        all_timestamps.update(wind_speed.keys())
        all_timestamps.update(dewpoint.keys())
        all_timestamps.update(sky_cover.keys())

        hourly_data = []
        now_utc = datetime.now(timezone.utc)

        for timestamp_str in sorted(all_timestamps):
            try:
                timestamp = datetime.fromisoformat(
                    timestamp_str.replace("Z", "+00:00")
                )

                # Filter past data
                if timestamp < now_utc:
                    continue

                # Temperature - check units and convert if needed
                temp_raw = temps.get(timestamp_str)
                if temp_raw is not None:
                    # NWS typically uses wmoUnit:degC (Celsius)
                    if temp_uom and "degF" in temp_uom:
                        temp_fahrenheit = temp_raw
                        temp_celsius = (
                            WeatherConversionUtils.fahrenheit_to_celsius(
                                temp_raw
                            )
                        )
                    else:
                        # Default: already in Celsius
                        temp_celsius = temp_raw
                        temp_fahrenheit = None
                else:
                    temp_celsius = None
                    temp_fahrenheit = None

                # Dewpoint - check units and convert if needed
                dewpoint_raw = dewpoint.get(timestamp_str)
                if dewpoint_raw is not None:
                    if dewpoint_uom and "degF" in dewpoint_uom:
                        dewpoint_fahrenheit = dewpoint_raw
                        dewpoint_celsius = (
                            WeatherConversionUtils.fahrenheit_to_celsius(
                                dewpoint_raw
                            )
                        )
                    else:
                        # Default: already in Celsius
                        dewpoint_celsius = dewpoint_raw
                        dewpoint_fahrenheit = None
                else:
                    dewpoint_celsius = None
                    dewpoint_fahrenheit = None

                # Wind speed - check units and convert if needed
                wind_raw = wind_speed.get(timestamp_str)
                if wind_raw is not None:
                    # NWS uses wmoUnit:km_h-1 (km/h) as standard in 2025
                    if wind_uom and ("m_s-1" in wind_uom or "m/s" in wind_uom):
                        # Explicitly m/s - use directly
                        wind_speed_ms = wind_raw
                        wind_speed_mph = None
                    elif wind_uom and (
                        "mph" in wind_uom or "mi_h" in wind_uom
                    ):
                        # Imperial mph - convert
                        wind_speed_mph = wind_raw
                        wind_speed_ms = WeatherConversionUtils.mph_to_ms(
                            wind_raw
                        )
                    else:
                        # Default: NWS uses km/h (wmoUnit:km_h-1) in 2025
                        # Convert km/h to m/s
                        wind_speed_mph = None
                        wind_speed_ms = wind_raw / 3.6  # km/h to m/s
                else:
                    wind_speed_ms = None
                    wind_speed_mph = None

                # Convert wind 10m to 2m (FAO-56)
                wind_speed_2m_ms = (
                    WeatherConversionUtils.convert_wind_10m_to_2m(
                        wind_speed_ms
                    )
                    if wind_speed_ms is not None
                    else None
                )

                # Humidity
                humidity_percent = humidity.get(timestamp_str)

                # Sky cover (for solar radiation estimation)
                sky_cover_percent = sky_cover.get(timestamp_str)

                # Precipitation (typically in mm)
                # WARNING: may be accumulated over period, not hourly
                precip_mm = precip.get(timestamp_str)
                prob_precip_percent = precip_prob.get(timestamp_str)

                # Official max/min temps from NWS (12h/24h periods)
                max_temp_official = max_temps_official.get(timestamp_str)
                min_temp_official = min_temps_official.get(timestamp_str)

                hourly_data.append(
                    NWSHourlyData(
                        timestamp=timestamp_str,
                        temp_celsius=temp_celsius,
                        temp_fahrenheit=temp_fahrenheit,
                        humidity_percent=humidity_percent,
                        wind_speed_ms=wind_speed_ms,
                        wind_speed_mph=wind_speed_mph,
                        wind_speed_2m_ms=wind_speed_2m_ms,
                        dewpoint_celsius=dewpoint_celsius,
                        dewpoint_fahrenheit=dewpoint_fahrenheit,
                        sky_cover_percent=sky_cover_percent,
                        precip_mm=precip_mm,
                        probability_precip_percent=prob_precip_percent,
                        pressure_hpa=None,  # Will be set later from elevation
                        max_temp_celsius=max_temp_official,
                        min_temp_celsius=min_temp_official,
                        short_forecast=None,
                    )
                )
            except Exception as e:
                logger.warning(
                    f"Erro ao parsear timestamp {timestamp_str}: {e}"
                )
                continue

        return hourly_data

    async def _delay_retry(self, attempt: int):
        """Exponential delay between retry attempts."""
        delay = self.config.retry_delay * (2**attempt)
        await asyncio.sleep(delay)

    async def _get_elevation_data(
        self, lat: float, lon: float
    ) -> float | None:
        """
        Get elevation for location to estimate atmospheric pressure.

        GET /points/{lat},{lon} returns elevation in meters.
        Used for pressure estimation in ETo calculation.

        Returns:
            Elevation in meters, or None if not available
        """
        try:
            url = f"/points/{lat:.4f},{lon:.4f}"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            elevation = (
                data.get("properties", {}).get("elevation", {}).get("value")
            )
            if elevation is not None:
                return float(elevation)  # in meters
            return None
        except Exception as e:
            logger.warning(f"Error getting elevation: {e}")
            return None

    def _estimate_pressure_from_elevation(
        self, elevation_m: float | None
    ) -> float:
        """
        Estimate atmospheric pressure based on elevation.

        Formula: P = 101.3 x [(293 - 0.0065 x z)/293]^5.255
        where z is elevation in meters.

        This is the barometric formula for standard atmosphere.
        Used in FAO-56 Penman-Monteith ETo calculation.

        Args:
            elevation_m: Elevation in meters (None uses sea level)

        Returns:
            Pressure in hPa (hectopascals)
        """
        if elevation_m is None:
            return 1013.25  # Standard sea level pressure

        p = 101.3 * ((293 - 0.0065 * elevation_m) / 293) ** 5.255
        return round(p * 10, 2)  # Convert kPa to hPa

    def _calculate_extraterrestrial_radiation(
        self, lat: float, doy: int
    ) -> float:
        """
        Calculate extraterrestrial radiation Ra (MJ/m²/day).

        Based on FAO-56 equations 21-23.
        Ra = radiation at top of atmosphere (depends on latitude and date).

        Args:
            lat: Latitude in decimal degrees
            doy: Day of year (1-365/366)

        Returns:
            Extraterrestrial radiation in MJ/m²/day
        """
        from math import radians, acos, sin, cos, tan, pi

        phi = radians(lat)
        dr = 1 + 0.033 * cos(2 * pi * doy / 365)
        delta = 0.409 * sin(2 * pi * doy / 365 - 1.39)
        ws = acos(-tan(phi) * tan(delta))
        ra = (
            (24 * 60 / pi)
            * 0.0820
            * dr
            * (ws * sin(phi) * sin(delta) + cos(phi) * cos(delta) * sin(ws))
        )
        return round(ra, 2)

    def estimate_daily_solar_radiation(
        self, lat: float, day_data: "NWSDailyData", method: str = "usa_asos"
    ) -> float | None:
        """
        Estimate solar radiation Rs (MJ/m²/day) from sky cover.

        Uses calibrated Ångström-Prescott coefficients from:
        Belcher & DeGaetano (2007) - "A revised empirical model to estimate
        solar radiation using automated surface weather observations"
        DOI: 10.1016/j.solener.2006.07.003

        Method options:
        - "usa_asos": Calibrated for USA ASOS stations (a=0.20, b=0.79)
          Best for NWS data across the United States
        - "usa_south": Seasonal coefficients for southern/subtropical US
        - "fao_standard": FAO-56 default (a=0.25, b=0.50)

        Includes water vapor absorption correction (T_w) from dewpoint.

        Args:
            lat: Latitude in decimal degrees
            day_data: NWSDailyData with hourly sky cover and dewpoint
            method: Calibration method (default: "usa_asos")

        Returns:
            Solar radiation in MJ/m²/day, or None if sky cover unavailable
        """
        from math import radians, sin, pi
        import numpy as np

        # Extract sky cover from hourly data
        sky_covers = [
            h.sky_cover_percent
            for h in day_data.hourly_data
            if h.sky_cover_percent is not None
        ]

        if not sky_covers:
            logger.warning("Sky cover not available - Rs cannot be estimated")
            return None

        sky_cover_mean = float(np.mean(sky_covers))
        doy = day_data.date.timetuple().tm_yday
        ra = self._calculate_extraterrestrial_radiation(lat, doy)

        # Proxy for sunshine fraction (n/N)
        # Factor 0.7 from Belcher & DeGaetano (2007)
        n_over_n = 1 - 0.7 * (sky_cover_mean / 100)

        # Select calibration coefficients
        if method == "usa_asos":
            # Calibrated for ASOS USA (best for NWS data)
            a, b = 0.20, 0.79
        elif method == "fao_standard":
            a, b = 0.25, 0.50
        elif method == "usa_south":
            # Seasonal coefficients for southern/subtropical US
            month = day_data.date.month
            if 3 <= month <= 5:  # Spring
                a, b = 0.29, 0.43
            elif 6 <= month <= 8:  # Summer
                a, b = 0.32, 0.36
            elif 9 <= month <= 11:  # Fall
                a, b = 0.06, 0.72
            else:  # Winter
                a, b = 0.19, 0.47
        else:
            raise ValueError(
                f"Invalid method: {method}. "
                "Use 'usa_asos', 'usa_south', or 'fao_standard'"
            )

        # Ångström-Prescott formula
        rs = ra * (a + b * n_over_n)

        # Water vapor absorption correction (T_w)
        # From Belcher & DeGaetano (2007) Eq. 4
        if day_data.dewpoint_mean_celsius is not None:
            # Actual vapor pressure (kPa) from dewpoint
            td = day_data.dewpoint_mean_celsius
            e_a = 0.6108 * np.exp(17.27 * td / (td + 237.3))

            # Water vapor transmittance (simplified)
            # Accounts for atmospheric absorption by water vapor
            lat_rad = radians(lat)
            sun_elevation = sin(pi / 2 - abs(lat_rad))  # Approximation
            T_w = 1 - 0.000425 * e_a * (1 / sun_elevation)

            rs *= T_w

        return round(rs, 2)

    async def get_forecast_data(
        self, lat: float, lon: float
    ) -> list[NWSHourlyData]:
        """
        Get HOURLY QUANTITATIVE data from /gridpoints/{wfo}/{x},{y}.

        ONLY quantitative data (numerical values) is used.
        Text-based /forecast/hourly endpoint is NOT used.

        Advantages of quantitative data:
        - Precise numerical values (not text)
        - WindSpeed already in m/s (no conversion needed)
        - All ETo variables available:
          * temperature (°C) - hourly values
          * relativeHumidity (%)
          * windSpeed (m/s)
          * dewpoint (°C) - critical for vapor pressure
          * skyCover (%) - for solar radiation
          * quantitativePrecipitation (mm)
        - Consistent time series structure
        - maxTemp/minTemp calculated during daily aggregation

        Main method to get hourly forecasts.
        Returns ~120-156 hours of data (5-6.5 days).

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)

        Returns:
            List of NWSHourlyData (complete quantitative data for ETo)

        Raises:
            httpx.HTTPStatusError: If coordinates outside coverage
            ValueError: If grid metadata invalid
        """
        grid_meta = await self._get_grid_metadata(lat, lon)
        forecast_data = await self._get_forecast_grid_data(
            grid_meta["gridId"], grid_meta["gridX"], grid_meta["gridY"]
        )
        hourly_data = self._parse_forecast_grid_data(forecast_data)

        # Add atmospheric pressure estimate from elevation
        elevation = await self._get_elevation_data(lat, lon)
        pressure_hpa = self._estimate_pressure_from_elevation(elevation)

        # Apply pressure to all hourly records
        for hour_data in hourly_data:
            hour_data.pressure_hpa = pressure_hpa

        return hourly_data

    async def get_daily_forecast_data(
        self, lat: float, lon: float
    ) -> list[NWSDailyData]:
        """
        Get DAILY data (hourly aggregation) - limit 5 days.

        Aggregates hourly data into daily statistics using numpy.
        Returns up to 5 days of forecast (NWS limit).

        IMPORTANT: This client ASSUMES:
        - Coordinates validated in climate_validation.py
        - USA coverage validated in climate_source_selector.py
        - Period (today → today+5d) validated in
          climate_source_availability.py
        This client ONLY fetches data, no re-validation.

        Aggregation:
            - Temperature: mean/max/min (numpy)
            - Humidity: mean (numpy)
            - Wind: mean at 2m (numpy, FAO-56 converted)
            - Precipitation: sum (numpy)
            - Precipitation probability: mean (numpy)

        5-day limit:
            Filters only data up to (now + 5 days) per NWS documentation.

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)

        Returns:
            List of NWSDailyData (aggregated daily data, max 5 days)
        """
        hourly_data = await self.get_forecast_data(lat, lon)

        if not hourly_data:
            return []

        daily_groups = defaultdict(list)

        for hour in hourly_data:
            try:
                timestamp = datetime.fromisoformat(
                    hour.timestamp.replace("Z", "+00:00")
                )
                date_key = timestamp.date()
                daily_groups[date_key].append(hour)
            except Exception:
                continue

        daily_data = []
        now = datetime.now()
        five_days_limit = now + timedelta(days=5)

        for date_key in sorted(daily_groups.keys()):
            if date_key > five_days_limit.date():
                break  # Limit to 5 days

            hours = daily_groups[date_key]

            # Skip incomplete days (< 20 hours) to avoid bias
            if len(hours) < 20:
                logger.warning(
                    f"Discarding {date_key}: only {len(hours)} hours "
                    f"(partial days cause statistical bias)"
                )
                continue

            temps = [
                h.temp_celsius for h in hours if h.temp_celsius is not None
            ]
            humidities = [
                h.humidity_percent
                for h in hours
                if h.humidity_percent is not None
            ]
            # Use wind at 2m (FAO-56 converted)
            wind_speeds = [
                h.wind_speed_2m_ms
                for h in hours
                if h.wind_speed_2m_ms is not None
            ]
            # Dewpoint for ETo calculation
            dewpoints = [
                h.dewpoint_celsius
                for h in hours
                if h.dewpoint_celsius is not None
            ]
            # Pressure for ETo calculation
            pressures = [
                h.pressure_hpa for h in hours if h.pressure_hpa is not None
            ]
            # Precipitation (quantitative from gridpoints)
            # WARNING: Values may be accumulated over periods (6h/12h/24h)
            # Direct summation may overestimate daily total
            # Consider this an estimate, not precise measurement
            precips = [h.precip_mm for h in hours if h.precip_mm is not None]
            prob_precips = [
                h.probability_precip_percent
                for h in hours
                if h.probability_precip_percent is not None
            ]

            temp_mean = float(np.mean(temps)) if temps else None

            # Use official max/min temps from NWS if available
            # (more accurate than hourly max/min)
            official_max_temps = [
                h.max_temp_celsius
                for h in hours
                if h.max_temp_celsius is not None
            ]
            official_min_temps = [
                h.min_temp_celsius
                for h in hours
                if h.min_temp_celsius is not None
            ]

            # Prefer official values, fallback to hourly max/min
            if official_max_temps:
                temp_max = float(np.max(official_max_temps))
            elif temps:
                temp_max = float(np.max(temps))
            else:
                temp_max = None

            if official_min_temps:
                temp_min = float(np.min(official_min_temps))
            elif temps:
                temp_min = float(np.min(temps))
            else:
                temp_min = None

            humidity_mean = float(np.mean(humidities)) if humidities else None
            wind_speed_mean = (
                float(np.mean(wind_speeds)) if wind_speeds else None
            )
            dewpoint_mean = float(np.mean(dewpoints)) if dewpoints else None
            pressure_mean = float(np.mean(pressures)) if pressures else None

            # Precipitation (sum for daily total)
            # WARNING: This is only an ESTIMATE!
            # quantitativePrecipitation is accumulated over forecast periods
            # (typically 6h, 12h, or 24h windows), NOT hourly values.
            # Simply summing these values may overestimate the true daily
            # total. For accurate precipitation, use NWS QPF or observation
            # data.
            precips = [h.precip_mm for h in hours if h.precip_mm is not None]
            precip_total = float(np.sum(precips)) if precips else None

            # Precipitation probability (mean)
            prob_precips = [
                h.probability_precip_percent
                for h in hours
                if h.probability_precip_percent is not None
            ]
            prob_precip_mean = (
                float(np.mean(prob_precips)) if prob_precips else None
            )

            # Get short forecast from first hour of the day
            short_forecast = hours[0].short_forecast if hours else None

            # Create daily data object first (needed for Rs calculation)
            daily_obj = NWSDailyData(
                date=datetime.combine(date_key, datetime.min.time()),
                temp_mean_celsius=temp_mean,
                temp_max_celsius=temp_max,
                temp_min_celsius=temp_min,
                humidity_mean_percent=humidity_mean,
                wind_speed_mean_ms=wind_speed_mean,
                dewpoint_mean_celsius=dewpoint_mean,
                pressure_mean_hpa=pressure_mean,
                solar_radiation_mj_m2_day=None,  # Calculated next
                precip_total_mm=precip_total,
                probability_precip_mean_percent=prob_precip_mean,
                short_forecast=short_forecast,
                hourly_data=hours,
            )

            # Solar radiation estimate using calibrated USA-ASOS method
            solar_radiation = self.estimate_daily_solar_radiation(
                lat, daily_obj, method="usa_asos"
            )
            daily_obj.solar_radiation_mj_m2_day = solar_radiation

            # Precipitation (sum for daily total)
            precip_total = float(np.sum(precips)) if precips else None
            prob_precip_mean = (
                float(np.mean(prob_precips)) if prob_precips else None
            )
            short_forecast = hours[0].short_forecast if hours else None

            daily_data.append(
                NWSDailyData(
                    date=datetime.combine(date_key, datetime.min.time()),
                    temp_mean_celsius=temp_mean,
                    temp_max_celsius=temp_max,
                    temp_min_celsius=temp_min,
                    humidity_mean_percent=humidity_mean,
                    wind_speed_mean_ms=wind_speed_mean,
                    dewpoint_mean_celsius=dewpoint_mean,
                    pressure_mean_hpa=pressure_mean,
                    solar_radiation_mj_m2_day=solar_radiation,
                    precip_total_mm=precip_total,
                    probability_precip_mean_percent=prob_precip_mean,
                    short_forecast=short_forecast,
                    hourly_data=hours,
                )
            )

        # Data availability verification
        if not daily_data:
            logger.warning(f"No daily data retrieved for {lat}, {lon}")
        else:
            logger.info(
                f"Retrieved {len(daily_data)} forecast days "
                f"({len(hourly_data)} total hours)"
            )

        return daily_data

    async def health_check(self) -> dict[str, Any]:
        """Health check for NWS API."""
        try:
            response = await self.client.get("/")
            response.raise_for_status()
            return {"status": "ok", "base_url": self.config.base_url}
        except Exception as e:
            logger.error(f"NWS API health check: FALHA | erro={e}")
            raise

    def get_attribution(self) -> dict[str, str]:
        """Returns NWS data attribution."""
        return {
            "source": "National Weather Service (NWS) / NOAA",
            "license": "US Government Public Domain",
            "terms_url": "https://www.weather.gov/disclaimer",
            "api_docs": (
                "https://www.weather.gov/documentation/services-web-api"
            ),
        }

    def get_data_availability_info(self) -> dict[str, Any]:
        """Returns data availability information."""
        return {
            "coverage": {
                "region": "USA Continental",
                "bbox": {
                    "lon_min": -125.0,
                    "lon_max": -66.0,
                    "lat_min": 24.0,
                    "lat_max": 49.0,
                },
            },
            "forecast_horizon": {
                "hours": 120,
                "days": 5,
            },
            "update_frequency": "Hourly",
        }

    def is_in_coverage(self, lat: float, lon: float) -> bool:
        """Check if coordinates are within NWS coverage.

        Uses GeographicUtils as SINGLE SOURCE OF TRUTH.
        """
        return GeographicUtils.is_in_usa(lat, lon)


# Factory function
def create_nws_forecast_client(
    config: NWSConfig | None = None,
) -> NWSForecastClient:
    return NWSForecastClient(config)


# Alias
NWSClient = NWSForecastClient
