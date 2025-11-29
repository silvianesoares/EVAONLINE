"""
NWS Stations Client Optimized for Interactive Map + Daily ETo Calculation
"""

import os
from datetime import datetime, timedelta
from typing import Any, List

import httpx
import pandas as pd
import geopy.distance
from loguru import logger
from pydantic import BaseModel, Field

# Para lidar com timezone da estação
import pytz


# Import opcional para fallback geográfico
class _GeographicUtilsFallback:
    @staticmethod
    def is_in_usa(lat: float, lon: float) -> bool:
        return -125 <= lon <= -66 and 24 <= lat <= 50


try:
    from scripts.api.services.geographic_utils import (
        GeographicUtils as _GeographicUtils,
    )
except ImportError:
    try:
        from ..geographic_utils import GeographicUtils as _GeographicUtils
    except ImportError:
        logger.warning("GeographicUtils not found - using simple fallback")
        _GeographicUtils = _GeographicUtilsFallback

GeographicUtils = _GeographicUtils


class NWSStationsConfig(BaseModel):
    base_url: str = "https://api.weather.gov"
    timeout: int = 30
    # retry_attempts: int = 3
    # retry_delay: float = 1.0
    user_agent: str = os.getenv(
        "NWS_USER_AGENT",
        "EVAonline (+https://github.com/silvianesoares/EVAONLINE)",
    )
    # max_stations: int = 10
    # observation_delay_threshold: int = 30  # minutes (20min normal)
    # max_days_back: int = 5  # Official NWS API limit = 7 days
    observation_delay_threshold: int = 30  # minutes
    max_days_back: int = 7  # NWS: up to ~7 days (3-4 in practice)


class NWSStation(BaseModel):
    model_config = {"populate_by_name": True}

    station_id: str = Field(..., alias="stationIdentifier")
    name: str
    latitude: float
    longitude: float
    elevation_m: float | None = None
    timezone: str | None = None
    distance_km: float | None = None
    is_active: bool = False  # Filled after verification


class NWSObservation(BaseModel):
    station_id: str
    timestamp: datetime
    temp_celsius: float | None = None
    temp_max_24h: float | None = None
    temp_min_24h: float | None = None
    dewpoint_celsius: float | None = None
    humidity_percent: float | None = None
    wind_speed_ms: float | None = None  # 10m
    wind_speed_2m_ms: float | None = None  # Converted for FAO-56
    is_delayed: bool = False


class DailyEToData(BaseModel):
    date: datetime
    station_id: str
    station_name: str
    latitude: float
    longitude: float
    elevation_m: float | None
    distance_km: float | None
    T_max: float
    T_min: float
    T_mean: float
    RH_mean: float | None
    wind_2m_mean_ms: float | None


class NWSStationsClient:
    def __init__(
        self, config: NWSStationsConfig | None = None, cache: Any | None = None
    ):
        self.config = config or NWSStationsConfig()
        self.cache = cache

        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/geo+json",
        }

        self.client = httpx.AsyncClient(
            timeout=self.config.timeout,
            headers=headers,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=50),
        )
        logger.success("NWSStationsClient initialized")

    async def close(self):
        await self.client.aclose()

    async def _get_grid(
        self, lat: float, lon: float
    ) -> tuple[str, int, int] | None:
        """Get WFO, gridX, gridY from lat/lon"""
        try:
            url = f"{self.config.base_url}/points/{lat:.5f},{lon:.5f}"
            resp = await self.client.get(url)
            resp.raise_for_status()
            data = resp.json()["properties"]
            wfo = data["gridId"]  # Actually the WFO (e.g., OKX)
            if wfo == "grid":  # Rare API bug
                wfo = data["forecastOffice"].split("/")[-1]
            return wfo.upper(), data["gridX"], data["gridY"]
        except Exception as e:
            logger.debug(f"Failed to get grid: {e}")
            return None

    async def find_nearest_active_station(
        self, lat: float, lon: float, max_candidates: int = 5
    ) -> NWSStation | None:
        """
        Returns the nearest station that is active (with recent valid
        observation). Ideal for direct use in interactive map.
        """
        if not GeographicUtils.is_in_usa(lat, lon):
            logger.warning(
                f"Coordinates ({lat}, {lon}) outside main USA coverage"
            )
            return None

        logger.info(
            f"Searching for active station near ({lat:.4f}, {lon:.4f})"
        )

        grid = await self._get_grid(lat, lon)
        url = None
        if grid:
            wfo, x, y = grid
            url = (
                f"{self.config.base_url}/gridpoints/{wfo}/{x},{y}/"
                f"stations?limit={max_candidates}"
            )

        if not url:
            # Fallback: old endpoint
            url = f"{self.config.base_url}/points/{lat:.4f},{lon:.4f}/stations"

        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            features = resp.json().get("features", [])

            for feature in features:
                props = feature["properties"]
                geom = feature["geometry"]["coordinates"]  # [lon, lat]

                station = NWSStation(
                    stationIdentifier=props["stationIdentifier"],
                    name=props.get("name", "Unknown"),
                    latitude=geom[1],
                    longitude=geom[0],
                    elevation_m=props.get("elevation", {}).get("value"),
                    timezone=props.get("timeZone"),
                )

                # Calculate distance
                station.distance_km = round(
                    geopy.distance.distance(
                        (lat, lon), (station.latitude, station.longitude)
                    ).km,
                    3,
                )

                # Check if active
                latest = await self.get_latest_observation(station.station_id)
                if (
                    latest
                    and not latest.is_delayed
                    and latest.temp_celsius is not None
                ):
                    station.is_active = True
                    logger.success(
                        f"ACTIVE station found: {station.station_id} "
                        f"({station.name}) - {station.distance_km} km - "
                        f"elev: {station.elevation_m or 'N/A'} m"
                    )
                    return station

            # If none active, return nearest
            if features:
                first = features[0]["properties"]
                geom = features[0]["geometry"]["coordinates"]
                fallback = NWSStation(
                    stationIdentifier=first["stationIdentifier"],
                    name=first.get("name", "Unknown"),
                    latitude=geom[1],
                    longitude=geom[0],
                    elevation_m=first.get("elevation", {}).get("value"),
                    distance_km=round(
                        geopy.distance.distance(
                            (lat, lon), (geom[1], geom[0])
                        ).km,
                        3,
                    ),
                    is_active=False,
                )
                logger.warning(
                    f"No active station - using fallback: "
                    f"{fallback.station_id}"
                )
                return fallback

        except Exception as e:
            logger.error(f"Error searching for stations: {e}")

        return None

    async def get_observations(
        self,
        station_id: str,
        days_back: int = 7,
    ) -> List[NWSObservation]:
        """
        Fetch up to 7 days of hourly station observations.
        NWS API ignores start/end → we get last 500 records and filter locally.
        """
        days_back = min(days_back, 7)
        cutoff_time = datetime.now(pytz.UTC) - timedelta(days=days_back)

        url = f"{self.config.base_url}/stations/{station_id}/observations"
        params = {"limit": 500}  # Maximum allowed

        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            features = resp.json().get("features", [])

            observations = []

            for f in features:
                p = f["properties"]
                ts_str = p.get("timestamp")
                if not ts_str:
                    continue

                try:
                    timestamp = datetime.fromisoformat(
                        ts_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    continue

                # Filter by date (API doesn't do this)
                if timestamp < cutoff_time:
                    continue

                # Calculate delay (for logging and optional filtering)
                delay_minutes = (
                    datetime.now(pytz.UTC) - timestamp
                ).total_seconds() / 60
                is_delayed = (
                    delay_minutes > self.config.observation_delay_threshold
                )

                # Wind: km/h → m/s → 2m (FAO-56 official)
                wind_10m_kmh = self._val(
                    p.get("windSpeed")
                )  # None or value in km/h
                wind_10m_ms = (
                    wind_10m_kmh / 3.6 if wind_10m_kmh is not None else None
                )
                wind_2m_ms = self.convert_wind_to_2m(wind_10m_ms, z=10.0)

                obs = NWSObservation(
                    station_id=station_id,
                    timestamp=timestamp,
                    temp_celsius=self._val(p.get("temperature")),
                    temp_max_24h=self._val(p.get("maxTemperatureLast24Hours")),
                    temp_min_24h=self._val(p.get("minTemperatureLast24Hours")),
                    dewpoint_celsius=self._val(p.get("dewpoint")),
                    humidity_percent=self._val(p.get("relativeHumidity")),
                    wind_speed_ms=wind_10m_ms,
                    wind_speed_2m_ms=wind_2m_ms,
                    is_delayed=is_delayed,
                )
                observations.append(obs)

            # Sort from oldest to newest (important for aggregation!)
            observations.sort(key=lambda x: x.timestamp)

            logger.info(
                f"{len(observations)} observations kept "
                f"(requested: {days_back} days) - {station_id}"
            )
            return observations

        except Exception as e:
            logger.error(f"Failed to get observations from {station_id}: {e}")
            return []

    async def get_latest_observation(
        self, station_id: str
    ) -> NWSObservation | None:
        try:
            url = (
                f"{self.config.base_url}/stations/{station_id}/"
                f"observations/latest"
            )
            resp = await self.client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            p = resp.json()["properties"]
            ts = datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00"))
            delay_min = (datetime.now(pytz.UTC) - ts).total_seconds() / 60

            # Extract wind speed (NWS returns km/h, convert to m/s)
            wind_10m_ms = self._extract_wind_speed_ms(p.get("windSpeed"))

            # Apply FAO-56 official conversion (10m → 2m)
            wind_2m_ms = self.convert_wind_to_2m(wind_10m_ms, z=10.0)

            obs = NWSObservation(
                station_id=station_id,
                timestamp=ts,
                temp_celsius=self._val(p.get("temperature")),
                humidity_percent=self._val(p.get("relativeHumidity")),
                wind_speed_ms=wind_10m_ms,
                wind_speed_2m_ms=wind_2m_ms,
                is_delayed=delay_min > self.config.observation_delay_threshold,
            )
            return obs
        except Exception:
            return None

    def _val(self, data: dict | None) -> float | None:
        if not data or data.get("value") is None:
            return None
        return float(data["value"])

    @staticmethod
    def _extract_wind_speed_ms(wind_data: dict | None) -> float | None:
        """
        Extract wind speed from NWS API and convert to m/s.
        NWS returns in km/h → we convert to m/s.

        Args:
            wind_data: Wind data dict from NWS API with 'value' in km/h

        Returns:
            Wind speed in m/s, or None if invalid
        """
        if not wind_data or wind_data.get("value") is None:
            return None
        kmh = float(wind_data["value"])
        return round(kmh / 3.6, 3)  # km/h → m/s

    @staticmethod
    def convert_wind_to_2m(u_z: float | None, z: float = 10.0) -> float | None:
        """
        FAO-56 Eq. 47 - Convert wind from any height z to 2m reference.

        Uses logarithmic wind profile equation from FAO-56 for accurate
        conversion, ensuring consistency with ETo calculations.

        Formula: u2 = uz * [4.87 / ln(67.8*z - 5.42)]

        Args:
            u_z: Wind speed at height z (m/s)
            z: Measurement height (m) - default 10m for NWS

        Returns:
            Wind speed at 2m (m/s), minimum 0.5 m/s for stability

        Reference:
            Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998).
            Crop evapotranspiration - FAO Irrigation and drainage paper 56.
        """
        if u_z is None:
            return None

        if z == 2.0:
            return max(float(u_z), 0.5)

        import numpy as np

        factor = 4.87 / np.log(67.8 * z - 5.42)
        u2 = u_z * factor
        return max(float(u2), 0.5)  # Physical minimum for stability

    def aggregate_to_daily(
        self, observations: List[NWSObservation], station: NWSStation
    ) -> List[DailyEToData]:
        """Aggregate hourly data to daily ready for ETo"""
        if not observations:
            return []

        df = pd.DataFrame([o.dict() for o in observations])
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date

        daily = (
            df.groupby("date")
            .agg(
                T_max=("temp_celsius", "max"),
                T_min=("temp_celsius", "min"),
                T_mean=("temp_celsius", "mean"),
                RH_mean=("humidity_percent", "mean"),
                wind_2m_mean_ms=("wind_speed_2m_ms", "mean"),
            )
            .round(2)
            .reset_index()
        )

        result = []
        for _, row in daily.iterrows():
            result.append(
                DailyEToData(
                    date=datetime.combine(row["date"], datetime.min.time()),
                    station_id=station.station_id,
                    station_name=station.name,
                    latitude=station.latitude,
                    longitude=station.longitude,
                    elevation_m=station.elevation_m,
                    distance_km=station.distance_km,
                    T_max=row["T_max"],
                    T_min=row["T_min"],
                    T_mean=row["T_mean"],
                    RH_mean=row["RH_mean"],
                    wind_2m_mean_ms=row["wind_2m_mean_ms"],
                )
            )
        return result

    @staticmethod
    def get_data_availability_info() -> dict[str, Any]:
        """
        Returns information about data availability.

        Includes documented known issues.

        Returns:
            Dict with coverage, limits, and issues information
        """
        return {
            "source": "NWS Stations (NOAA)",
            "coverage": "USA (including Alaska, Hawaii, territories)",
            "stations": "~1800 active stations",
            "data_type": "Hourly observations",
            "bbox": {
                "lon_min": -180.0,
                "lon_max": -66.0,
                "lat_min": 18.0,
                "lat_max": 71.5,
            },
            "temporal_resolution": "Hourly",
            "update_frequency": "Real-time (continuous)",
            "typical_delay": "Up to 20 minutes (MADIS processing)",
            "license": "US Government Public Domain",
            "attribution": "National Weather Service / NOAA",
            "api_docs": (
                "https://www.weather.gov/documentation/services-web-api"
            ),
            "known_issues": {
                "observation_delay": "Up to 20 minutes normal (MADIS)",
                "null_temps": (
                    "Max/min temps may be null outside CST timezone"
                ),
                "station_variability": (
                    "Not all stations report all parameters"
                ),
            },
        }

    # Factory


def create_nws_client() -> NWSStationsClient:
    return NWSStationsClient()
