"""
NWS Forecast Daily Sync Adapter
Synchronous adapter for nws_forecast_client.py (asynchronous client).
Converts hourly NWS Forecast data to aggregated daily data.

- Forecast Data
- Start: Today
- End: Today + 5 days (EVAonline standard)
- Total: 6 days forecast

This adapter:
- Wraps the asynchronous NWSForecastClient in a synchronous interface
- Manages event loop automatically
- Converts hourly data to daily aggregations using pandas
- Maintains compatibility with existing synchronous code

Coverage: USA Continental (-125°W to -66°W, 24°N to 49°N)
Extended: Alaska/Hawaii (18°N to 71°N)

License: US Government Public Domain
API Documentation: https://www.weather.gov/documentation/services-web-api

Related Files:
- nws_forecast_client.py: Asynchronous client (base)
- nws_stations_sync_adapter.py: Adapter for stations/observations
"""

import asyncio
from datetime import datetime
from typing import List, Optional

from loguru import logger
from pydantic import BaseModel

from .nws_forecast_client import (
    create_nws_forecast_client,
)


class NWSDailyForecastRecord(BaseModel):
    """
    Daily record of NWS Forecast data.

    Output format of the adapter for compatibility with
    existing systems that expect daily data.

    Attributes:
        date: Date in YYYY-MM-DD format (string)
        temp_max: Maximum temperature (°C) - official NWS
        temp_min: Minimum temperature (°C) - official NWS
        temp_mean: Mean temperature (°C)
        humidity_mean: Mean relative humidity (%)
        wind_speed_mean: Mean wind speed at 2m (m/s) - FAO-56
        dewpoint_mean: Mean dewpoint (°C) - for ETo
        pressure_mean: Mean atmospheric pressure (hPa) - for ETo
        solar_radiation: Solar radiation (MJ/m²/day) - USA-ASOS calibrated
        precipitation_sum: Total precipitation (mm) - ESTIMATE
        precipitation_probability: Mean precipitation probability (%)
        short_forecast: Short textual forecast
    """

    date: str
    temp_max: Optional[float] = None
    temp_min: Optional[float] = None
    temp_mean: Optional[float] = None
    humidity_mean: Optional[float] = None
    wind_speed_mean: Optional[float] = None
    dewpoint_mean: Optional[float] = None
    pressure_mean: Optional[float] = None
    solar_radiation: Optional[float] = None
    precipitation_sum: Optional[float] = None
    precipitation_probability: Optional[float] = None
    short_forecast: Optional[str] = None


class NWSDailyForecastSyncAdapter:
    """
    Synchronous adapter for NWS Forecast with daily aggregation.

    Synchronous wrapper for NWSForecastClient (async) that provides
    aggregated daily data with all ETo variables:
    - Official NWS temperatures (max/min from 12h/24h periods)
    - Solar radiation (USA-ASOS calibrated with vapor correction)
    - Dewpoint and atmospheric pressure
    - Wind at 2m (FAO-56 converted)
    - Precipitation (estimate, may overestimate)

    This adapter:
        - Wraps NWSForecastClient (async) in synchronous interface
        - Creates/reuses event loop as needed
        - Uses get_daily_forecast_data() from client (no pandas)
        - Filters data by requested period
        - Removes timezone for compatibility with naive dates

    Methods:
        - health_check_sync(): Check API availability
        - get_daily_data_sync(): Get aggregated daily data
        - get_attribution(): Return attribution information
        - get_info(): General API information

    Example:
        adapter = NWSDailyForecastSyncAdapter()
        if adapter.health_check_sync():
            data = adapter.get_daily_data_sync(
                39.7392, -104.9903,
                start_date, end_date
            )
            print(f"Rs = {data[0].solar_radiation} MJ/m²/day")
    """

    def __init__(self):
        """Initialize adapter with asynchronous NWS client."""
        self.client = create_nws_forecast_client()

    def health_check_sync(self) -> bool:
        """
        Check if NWS API is accessible (synchronous).

        Creates event loop if necessary and executes health check
        of asynchronous client in blocking manner.

        Returns:
            bool: True if API is working, False otherwise

        Example:
            adapter = NWSDailyForecastSyncAdapter()
            if adapter.health_check_sync():
                print("NWS API available")
        """

        async def _health_check_async():
            client = create_nws_forecast_client()
            try:
                result = await client.health_check()
                return result.get("status") == "ok"
            finally:
                await client.close()

        try:
            # Always create new event loop to avoid conflicts
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_health_check_async())
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"NWS Forecast health check failed: {e}")
            return False

    async def _get_daily_data_async(
        self, lat: float, lon: float, start_date: datetime, end_date: datetime
    ) -> List[NWSDailyForecastRecord]:
        """
        Get aggregated daily data asynchronously.

        Now uses get_daily_forecast_data() from client which already returns
        aggregated data with all ETo variables including:
        - Official NWS temperatures (max/min from 12h/24h periods)
        - Estimated solar radiation (USA-ASOS calibrated method)
        - Dewpoint and atmospheric pressure
        - Wind at 2m (FAO-56 converted)
        """
        # Create new client for this request (avoids loop conflicts)
        client = create_nws_forecast_client()
        try:
            # Client already returns aggregated daily data!
            daily_forecast = await client.get_daily_forecast_data(lat, lon)

            if not daily_forecast:
                logger.warning(f"No forecast data for ({lat}, {lon})")
                return []

            # Filter requested period
            filtered_data = []
            for day in daily_forecast:
                # Remove timezone for comparison
                day_date = day.date.replace(tzinfo=None)

                if start_date.date() <= day_date.date() <= end_date.date():
                    record = NWSDailyForecastRecord(
                        date=day.date.strftime("%Y-%m-%d"),
                        temp_max=day.temp_max_celsius,
                        temp_min=day.temp_min_celsius,
                        temp_mean=day.temp_mean_celsius,
                        humidity_mean=day.humidity_mean_percent,
                        wind_speed_mean=day.wind_speed_mean_ms,
                        dewpoint_mean=day.dewpoint_mean_celsius,
                        pressure_mean=day.pressure_mean_hpa,
                        solar_radiation=day.solar_radiation_mj_m2_day,
                        precipitation_sum=day.precip_total_mm,
                        precipitation_probability=(
                            day.probability_precip_mean_percent
                        ),
                        short_forecast=day.short_forecast,
                    )
                    filtered_data.append(record)

            logger.info(
                f"NWS Forecast: {len(filtered_data)} days in requested "
                f"period for ({lat}, {lon})"
            )

            return filtered_data

        except ValueError:
            # Re-raise validation errors (coverage, dates, etc)
            raise
        except Exception as e:
            logger.error(f"Error processing NWS Forecast data: {e}")
            return []
        finally:
            # Close client to release resources
            await client.close()

    def get_daily_data_sync(
        self, lat: float, lon: float, start_date: datetime, end_date: datetime
    ) -> List[NWSDailyForecastRecord]:
        """
        Synchronous wrapper to get aggregated daily data.
        Compatible with Celery (non-async).

        Returns daily data with ALL variables for ETo:
        - Official NWS temperatures (max/min/mean)
        - Mean relative humidity
        - Mean wind at 2m (FAO-56)
        - Mean dewpoint
        - Mean atmospheric pressure
        - Solar radiation (USA-ASOS calibrated)
        - Total precipitation (estimate)

        Args:
            lat: Point latitude
            lon: Point longitude
            start_date: Start date
            end_date: End date

        Returns:
            List of aggregated daily records with ETo variables
        """
        try:
            # Create new event loop (avoids "Event loop is closed")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self._get_daily_data_async(lat, lon, start_date, end_date)
                )
                return result
            finally:
                # Ensure loop cleanup
                loop.close()
        except Exception as e:
            logger.error(f"NWS Forecast sync wrapper failed: {e}")
            return []

    def get_attribution(self) -> str:
        """
        Return NWS data attribution text.

        Returns:
            str: Formatted text with attribution information
        """
        attr = self.client.get_attribution()
        return (
            f"{attr['source']} | "
            f"License: {attr['license']} | "
            f"API: {attr['api_docs']}"
        )

    def get_info(self) -> dict:
        """
        Get general information about the NWS Forecast API.

        Returns:
            dict: API information including name, coverage, license,
                attribution, and ETo variables
        """
        return {
            "api_name": "National Weather Service (NOAA)",
            "coverage": "USA Continental + Alaska/Hawaii",
            "coverage_details": {
                "continental": "-125°W to -66°W, 24°N to 49°N",
                "extended": "Alaska/Hawaii (18°N to 71°N)",
            },
            "license": "US Government Public Domain",
            "attribution": self.get_attribution(),
            "forecast_period": "5 days",
            "temporal_resolution": "Hourly (aggregated to daily by client)",
            "eto_variables": [
                "Temperature (official max/min from NWS)",
                "Humidity (mean)",
                "Wind speed at 2m (FAO-56 converted)",
                "Dewpoint (mean)",
                "Atmospheric pressure (estimated from elevation)",
                "Solar radiation (USA-ASOS calibrated with vapor correction)",
                "Precipitation (estimate, may be overestimated)",
            ],
            "solar_radiation_method": (
                "Ångström-Prescott (USA-ASOS a=0.20, b=0.79)"
            ),
            "solar_radiation_reference": (
                "Belcher & DeGaetano (2007) Solar Energy 81(3):329-345 "
                "DOI:10.1016/j.solener.2006.07.003"
            ),
        }
