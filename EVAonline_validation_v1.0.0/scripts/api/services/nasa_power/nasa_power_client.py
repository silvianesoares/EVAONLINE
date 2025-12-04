"""
Client for NASA POWER API.
Public Domain.
POWER Daily API
Return a daily data for a region on a 0.5 x 0.5 degree grid.

- Archived Data
- Start: 1990/01/01
- End: Today (EVAonline standard)

Data Source:
-----------
The data was obtained from the Prediction Of Worldwide Energy Resources
(POWER) Project, funded through the NASA Earth Science Directorate
Applied Science Program.

POWER Data Reference:
--------------------
The data was obtained from the POWER Project's Daily 2.x.x version.

NASA POWER: https://power.larc.nasa.gov/
Documentation: https://power.larc.nasa.gov/docs/services/api/
Citation Guide: https://power.larc.nasa.gov/docs/referencing/

When using POWER data in publications, please reference:
"Data obtained from NASA Langley Research Center POWER Project
funded through the NASA Earth Science Directorate Applied Science Program."

Contact: larc-power-project@mail.nasa.gov

IMPORTANT:
- Community 'ag' (agronomy): Solar radiation in MJ/m²/day (ready for ETo)
- Always use community='ag' for agroclimatic data

7 DAILY VARIABLES AVAILABLE:
1. ALLSKY_SFC_SW_DWN: CERES SYN1deg All Sky Surface Shortwave
   Downward Irradiance (MJ/m^2/day)
Spatial Resolution: 1 x 1 Degrees

2. T2M: MERRA-2 Temperature at 2 Meters (C)
Spatial Resolution: 0.5 x 0.625 Degrees

3. T2M_MAX: MERRA-2 Temperature at 2 Meters Maximum (C)
Spatial Resolution: 0.5 x 0.625 Degrees

4. T2M_MIN: MERRA-2 Temperature at 2 Meters Minimum (C)
Spatial Resolution: 0.5 x 0.625 Degrees

5. RH2M: MERRA-2 Relative Humidity at 2 Meters (%)
Spatial Resolution: 0.5 x 0.625 Degrees

6. WS2M: MERRA-2 Wind Speed at 2 Meters (m/s)
Spatial Resolution: 0.5 x 0.625 Degrees

7. PRECTOTCORR: MERRA-2 Precipitation Corrected (mm/day)
Spatial Resolution: 0.5 x 0.625 Degrees

"""

from datetime import datetime, timedelta
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field

from scripts.api.services.geographic_utils import GeographicUtils


class NASAPowerConfig(BaseModel):
    """NASA POWER API configuration."""

    base_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point"
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0


class NASAPowerData(BaseModel):
    """Data returned by NASA POWER."""

    date: str = Field(..., description="Date ISO 8601")
    temp_max: float | None = Field(None, description="Max temperature (°C)")
    temp_min: float | None = Field(None, description="Min temperature (°C)")
    temp_mean: float | None = Field(None, description="Mean temperature (°C)")
    humidity: float | None = Field(None, description="Relative humidity (%)")
    wind_speed: float | None = Field(None, description="Wind speed (m/s)")
    solar_radiation: float | None = Field(
        None, description="Solar radiation (MJ/m²/day)"
    )
    precipitation: float | None = Field(
        None, description="Precipitation (mm/day)"
    )


class NASAPowerClient:
    """
    Client for NASA POWER API with intelligent caching.
    """

    def __init__(
        self, config: NASAPowerConfig | None = None, cache: Any | None = None
    ):
        """
        Initialize NASA POWER client.

        Args:
            config: Custom configuration (optional)
            cache: ClimateCacheService (optional, injected via DI)
        """
        self.config = config or NASAPowerConfig()
        self.client = httpx.AsyncClient(timeout=self.config.timeout)
        self.cache = cache  # Optional cache service

    async def close(self):
        """Close HTTP connection."""
        await self.client.aclose()

    async def get_daily_data(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
        community: str = "AG",  # UPPERCASE: AG, RE, SB
    ) -> list[NASAPowerData]:
        """
        Fetch daily climate data for a point with intelligent caching.

        NOTE: Range validations must be done in climate_validation.py
        before calling this method. This client assumes pre-validated data.

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)
            start_date: Start date (datetime) - MUST be validated
            end_date: End date (datetime) - MUST be validated
            community: NASA POWER community (UPPERCASE required):
                - AG: Agronomy (default)
                - RE: Renewable Energy
                - SB: Sustainable Buildings

        Returns:
            List of NASAPowerData with daily climate data
        """
        # Basic validations - use GeographicUtils (SINGLE SOURCE OF TRUTH)
        if not GeographicUtils.is_valid_coordinate(lat, lon):
            msg = f"Invalid coordinates: ({lat}, {lon})"
            raise ValueError(msg)

        if start_date > end_date:
            msg = "start_date must be <= end_date"
            raise ValueError(msg)

        # IMPORTANT: Range validations (7-30 days) must be done
        # in climate_validation.py BEFORE calling this method.
        # This client assumes data pre-validated by climate_validation.

        # 1. Try to fetch from cache (if available)
        if self.cache:
            cached_data = await self.cache.get(
                source="nasa_power",
                lat=lat,
                lon=lon,
                start=start_date,
                end=end_date,
            )
            if cached_data:
                logger.info(f"Cache HIT: NASA POWER lat={lat}, lon={lon}")
                return cached_data

        # 2. Cache MISS - fetch from API
        logger.info(f"Fetching NASA API: lat={lat}, lon={lon}")

        # Format dates (YYYYMMDD)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        # Request parameters
        params = {
            "parameters": ",".join(
                [
                    "T2M_MAX",  # Max temp 2m (°C)
                    "T2M_MIN",  # Min temp 2m (°C)
                    "T2M",  # Mean temp 2m (°C)
                    "RH2M",  # Relative humidity 2m (%)
                    "WS2M",  # Wind speed 2m (m/s)
                    "ALLSKY_SFC_SW_DWN",  # Solar radiation (MJ/m²/day)
                    "PRECTOTCORR",  # Precipitation (mm/day)
                ]
            ),
            "community": community,
            "longitude": lon,
            "latitude": lat,
            "start": start_str,
            "end": end_str,
            "format": "JSON",
        }

        # Request with retry
        for attempt in range(self.config.retry_attempts):
            try:
                logger.info(
                    f"NASA POWER request: lat={lat}, lon={lon}, "
                    f"dates={start_str} to {end_str} (attempt {attempt + 1})"
                )

                response = await self.client.get(
                    self.config.base_url, params=params
                )
                response.raise_for_status()

                data = response.json()
                parsed_data = self._parse_response(data)

                # 3. Save to cache (if available)
                if self.cache and parsed_data:
                    await self.cache.set(
                        source="nasa_power",
                        lat=lat,
                        lon=lon,
                        start=start_date,
                        end=end_date,
                        data=parsed_data,
                    )
                    logger.info(f"Cache SAVE: NASA POWER lat={lat}, lon={lon}")

                return parsed_data

            except httpx.HTTPError as e:
                logger.warning(
                    f"NASA POWER request failed (attempt {attempt + 1}): {e}"
                )
                if attempt == self.config.retry_attempts - 1:
                    raise
                await self._delay_retry()

        msg = "NASA POWER: All attempts failed"
        raise httpx.HTTPError(msg)

    def _parse_response(self, data: dict) -> list[NASAPowerData]:
        """
        Parse NASA POWER JSON response.

        Args:
            data: JSON response

        Returns:
            List[NASAPowerData]: Parsed data
        """
        if "properties" not in data or "parameter" not in data["properties"]:
            msg = "Invalid NASA POWER response (missing 'parameter')"
            raise ValueError(msg)

        parameters = data["properties"]["parameter"]

        # Extract dates (first key from any parameter)
        first_param = next(iter(parameters.values()))
        dates = sorted(first_param.keys())

        results = []
        for date_str in dates:
            # Radiation already comes in MJ/m²/day with community=ag
            solar_mj = parameters.get("ALLSKY_SFC_SW_DWN", {}).get(date_str)

            record = NASAPowerData(
                date=self._format_date(date_str),
                temp_max=parameters.get("T2M_MAX", {}).get(date_str),
                temp_min=parameters.get("T2M_MIN", {}).get(date_str),
                temp_mean=parameters.get("T2M", {}).get(date_str),
                humidity=parameters.get("RH2M", {}).get(date_str),
                wind_speed=parameters.get("WS2M", {}).get(date_str),
                solar_radiation=solar_mj,
                precipitation=parameters.get("PRECTOTCORR", {}).get(date_str),
            )
            results.append(record)

        logger.info(f"NASA POWER: Parsed {len(results)} records")
        return results

    def _format_date(self, date_str: str) -> str:
        """
        Convert date YYYYMMDD → ISO 8601 (YYYY-MM-DD).

        Args:
            date_str: Date in YYYYMMDD format

        Returns:
            str: ISO 8601 date
        """
        year = date_str[:4]
        month = date_str[4:6]
        day = date_str[6:8]
        return f"{year}-{month}-{day}"

    async def _delay_retry(self):
        """Delay between retry attempts."""
        import asyncio

        await asyncio.sleep(self.config.retry_delay)

    @classmethod
    def get_data_availability_info(cls) -> dict[str, Any]:
        """
        Return information about historical data availability.

        Returns:
            dict: Information about temporal coverage and limitations
        """
        start_date = datetime(1990, 1, 1).date()
        today = datetime.now().date()

        return {
            "data_start_date": start_date,
            "max_historical_years": (today - start_date).days // 365,
            "delay_days": 7,  # Typical delay
            "description": "Historical data from 1990, global coverage",
            "coverage": "Global",
            "update_frequency": "Daily (with 2-7 day delay)",
        }

    async def health_check(self) -> bool:
        """
        Check if API is accessible.

        Returns:
            bool: True if API responds
        """
        try:
            # Try to fetch 7 days (minimum) for any point
            end_date = datetime.now() - timedelta(days=7)
            start_date = end_date - timedelta(days=6)  # 7 days total
            await self.get_daily_data(
                lat=0.0, lon=0.0, start_date=start_date, end_date=end_date
            )
            return True
        except Exception as e:
            logger.error(f"NASA POWER health check failed: {e}")
            return False
