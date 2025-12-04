"""
Station Finder with PostGIS
- Search by radius using spatial indexes
- Distance-based weight calculation
- Integration with historical data
"""

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session


class StationFinder:
    """
    Station Locator with PostGIS support

    Methods:
    - find_stations_in_radius: Search by radius (using spatial index)
    - get_weighted_climate_data: Distance-weighted data
    - find_studied_city: Search for city with historical data in DB
    """

    def __init__(self, db_session: Optional[Session] = None):
        self.db_session = db_session
        logger.info("StationFinder initialized with PostGIS support")

    async def find_stations_in_radius(
        self,
        target_lat: float,
        target_lon: float,
        radius_km: float = 50,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find stations within a radius using PostGIS

        Optimized query with GIST index:
        - Uses ST_DWithin for fast search
        - Orders by distance
        - Returns complete metadata

        Args:
            target_lat: Target latitude
            target_lon: Target longitude
            radius_km: Search radius in km
            limit: Maximum number of stations

        Returns:
            List of stations ordered by distance
        """
        if not self.db_session:
            logger.warning("No DB session provided, using fallback")
            return []

        try:
            query = text(
                """
            SELECT
                id,
                station_code,
                station_name,
                latitude,
                longitude,
                elevation_m,
                country,
                data_source,
                data_available_from,
                data_available_to,
                variables_available,
                ST_Distance(
                    location::geography,
                    ST_Point(:lon, :lat)::geography
                ) / 1000.0 AS distance_km,
                ST_Distance(
                    location::geography,
                    ST_Point(:lon, :lat)::geography
                ) / 1000.0 / :radius_km AS proximity_weight
            FROM climate_history.weather_stations
            WHERE ST_DWithin(
                location::geography,
                ST_Point(:lon, :lat)::geography,
                :radius_m
            )
            ORDER BY distance_km ASC
            LIMIT :limit
            """
            )

            result = self.db_session.execute(
                query,
                {
                    "lat": target_lat,
                    "lon": target_lon,
                    "radius_m": radius_km * 1000,  # Convert to meters
                    "radius_km": radius_km,
                    "limit": limit,
                },
            )

            stations = []
            for row in result:
                station = {
                    "id": row[0],
                    "station_code": row[1],
                    "station_name": row[2],
                    "latitude": row[3],
                    "longitude": row[4],
                    "elevation_m": row[5],
                    "country": row[6],
                    "data_source": row[7],
                    "data_available_from": row[8],
                    "data_available_to": row[9],
                    "variables_available": row[10],
                    "distance_km": row[11],
                    "proximity_weight": row[12],
                }
                stations.append(station)

            logger.info(
                f"Found {len(stations)} stations within {radius_km}km "
                f"of ({target_lat}, {target_lon})"
            )
            return stations

        except Exception as e:
            logger.error(f"Error finding stations: {e}")
            return []

    async def find_studied_city(
        self,
        target_lat: float,
        target_lon: float,
        max_distance_km: float = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Search for a studied city near the coordinates.

        Returns historical data (monthly normals) if found, otherwise None

        Args:
            target_lat: Target latitude
            target_lon: Target longitude
            max_distance_km: Maximum distance to consider "nearby"

        Returns:
            Dict with city data and monthly normals, or None
            Format:
            {
                "id": 1,
                "city_name": "Piracicaba",
                "distance_km": 2.5,
                "monthly_data": {
                    1: {
                        "eto_normal": 5.2,
                        "eto_daily_mean": 5.3,
                        "eto_daily_std": 1.2,
                        "precip_normal": 120.5,
                        "precip_daily_std": 15.3,
                        "rain_probability": 0.65,
                    },
                    ...
                }
            }
        """
        if not self.db_session:
            logger.warning("No DB session for city lookup")
            return None

        try:
            # 1. Search for nearby city
            query = text(
                """
            SELECT
                id,
                city_name,
                country,
                state,
                latitude,
                longitude,
                elevation,
                timezone,
                data_sources,
                reference_periods,
                ST_Distance(
                    location::geography,
                    ST_Point(:lon, :lat)::geography
                ) / 1000.0 AS distance_km
            FROM climate_history.studied_cities
            WHERE ST_DWithin(
                location::geography,
                ST_Point(:lon, :lat)::geography,
                :max_distance_m
            )
            ORDER BY distance_km ASC
            LIMIT 1
            """
            )

            result = self.db_session.execute(
                query,
                {
                    "lat": target_lat,
                    "lon": target_lon,
                    "max_distance_m": max_distance_km * 1000,
                },
            ).first()

            if not result:
                logger.info(
                    f"No studied city found within {max_distance_km}km "
                    f"of ({target_lat}, {target_lon})"
                )
                return None

            city_id = result[0]
            city_name = result[1]
            distance_km = result[10]

            logger.info(
                f"Found studied city '{city_name}' at distance {distance_km:.2f}km"
            )

            # 2. Fetch all monthly normals for this city
            normals_query = text(
                """
            SELECT
                month,
                eto_normal,
                eto_daily_mean,
                eto_daily_std,
                eto_p95,
                eto_p99,
                precip_normal,
                precip_daily_mean,
                precip_daily_std,
                precip_p95,
                rain_probability,
                period_key
            FROM climate_history.monthly_climate_normals
            WHERE city_id = :city_id
            ORDER BY period_key DESC, month ASC
            """
            )

            normals_result = self.db_session.execute(
                normals_query, {"city_id": city_id}
            ).fetchall()

            # Group by month (use most recent period)
            monthly_data = {}
            seen_months = set()

            for row in normals_result:
                month = row[0]
                if month not in seen_months:  # Use most recent period
                    monthly_data[month] = {
                        "eto_normal": row[1],
                        "eto_daily_mean": row[2],
                        "eto_daily_std": row[3],
                        "eto_p95": row[4],
                        "eto_p99": row[5],
                        "precip_normal": row[6],
                        "precip_daily_mean": row[7],
                        "precip_daily_std": row[8],
                        "precip_p95": row[9],
                        "rain_probability": row[10],
                        "period_key": row[11],
                    }
                    seen_months.add(month)

            # Build response
            city_data = {
                "id": city_id,
                "city_name": city_name,
                "country": result[2],
                "state": result[3],
                "latitude": result[4],
                "longitude": result[5],
                "elevation_m": result[6],
                "timezone": result[7],
                "data_sources": result[8],
                "reference_periods": result[9],
                "distance_km": distance_km,
                "monthly_data": monthly_data,
            }

            logger.info(
                f"Loaded {len(monthly_data)} months of historical data for {city_name}"
            )
            return city_data

        except Exception as e:
            logger.error(f"Error finding studied city: {e}")
            return None

    async def get_monthly_normals(
        self,
        city_id: int,
        month: int,
        period_key: Optional[str] = None,
    ) -> Optional[Dict[str, float]]:
        """
        Fetch monthly climate normals for a city

        Args:
            city_id: City ID
            month: Month (1-12)
            period_key: Specific period (e.g., "1991-2020"), uses latest if None

        Returns:
            Dict with normals or None if not found
        """
        if not self.db_session:
            return None

        try:
            # If period not specified, use most recent
            if period_key is None:
                query = text(
                    """
                SELECT
                    eto_normal, precip_normal, rain_probability,
                    eto_daily_std, precip_daily_std, eto_p95, precip_p95,
                    period_key
                FROM climate_history.monthly_climate_normals
                WHERE city_id = :city_id AND month = :month
                ORDER BY period_key DESC
                LIMIT 1
                """
                )
            else:
                query = text(
                    """
                SELECT
                    eto_normal, precip_normal, rain_probability,
                    eto_daily_std, precip_daily_std, eto_p95, precip_p95,
                    period_key
                FROM climate_history.monthly_climate_normals
                WHERE city_id = :city_id AND month = :month AND period_key = :period_key
                LIMIT 1
                """
                )

            result = self.db_session.execute(
                query,
                {
                    "city_id": city_id,
                    "month": month,
                    "period_key": period_key,
                },
            ).first()

            if result:
                return {
                    "eto_normal": result[0],
                    "precip_normal": result[1],
                    "rain_probability": result[2],
                    "eto_daily_std": result[3],
                    "precip_daily_std": result[4],
                    "eto_p95": result[5],
                    "precip_p95": result[6],
                    "period_key": result[7],
                }
            return None

        except Exception as e:
            logger.error(f"Error fetching monthly normals: {e}")
            return None

    async def get_weighted_climate_data(
        self,
        target_lat: float,
        target_lon: float,
        radius_km: float = 50,
        stations_data: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, float]:
        """
        Calculate distance-weighted climate data

        Weight = 1 / (distance + 0.1)
        Normalizes so sum of weights = 1

        Args:
            target_lat: Latitude
            target_lon: Longitude
            radius_km: Search radius
            stations_data: List of stations (if None, searches in DB)

        Returns:
            Dict with weighted data
        """
        if stations_data is None:
            stations_data = await self.find_stations_in_radius(
                target_lat, target_lon, radius_km
            )

        if not stations_data:
            logger.warning("No stations available for weighting")
            return {}

        weighted_data = {}
        total_weight = 0.0

        for station in stations_data:
            distance_km = station.get("distance_km", float("inf"))

            # Avoid division by zero
            if distance_km == 0:
                distance_km = 0.001

            # Weight inversely proportional to distance
            weight = 1.0 / (distance_km + 0.1)
            total_weight += weight

            # Accumulate weighted data
            for key, value in station.items():
                if isinstance(value, (int, float)) and key not in [
                    "distance_km",
                    "proximity_weight",
                    "latitude",
                    "longitude",
                    "id",
                    "elevation_m",
                ]:
                    if key not in weighted_data:
                        weighted_data[key] = 0.0
                    weighted_data[key] += value * weight

        # Normalize weights
        for key in weighted_data:
            weighted_data[key] /= total_weight

        logger.info(
            f"Weighted climate data calculated from {len(stations_data)} "
            f"stations (total_weight={total_weight:.2f})"
        )
        return weighted_data

    async def get_nearby_stations_for_city(
        self,
        city_id: int,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch pre-calculated nearby stations for a city

        Args:
            city_id: Studied city ID
            limit: Maximum number of stations

        Returns:
            List of stations with pre-calculated weights
        """
        if not self.db_session:
            return []

        try:
            query = text(
                """
            SELECT
                ws.id,
                ws.station_code,
                ws.station_name,
                ws.latitude,
                ws.longitude,
                ws.elevation_m,
                ws.country,
                ws.data_source,
                cns.distance_km,
                cns.proximity_weight,
                cns.confidence_score,
                ws.variables_available
            FROM climate_history.city_nearby_stations cns
            JOIN climate_history.weather_stations ws ON ws.id = cns.station_id
            WHERE cns.city_id = :city_id
            ORDER BY cns.distance_km ASC
            LIMIT :limit
            """
            )

            result = self.db_session.execute(
                query, {"city_id": city_id, "limit": limit}
            )

            stations = []
            for row in result:
                stations.append(
                    {
                        "id": row[0],
                        "station_code": row[1],
                        "station_name": row[2],
                        "latitude": row[3],
                        "longitude": row[4],
                        "elevation_m": row[5],
                        "country": row[6],
                        "data_source": row[7],
                        "distance_km": row[8],
                        "proximity_weight": row[9],
                        "confidence_score": row[10],
                        "variables_available": row[11],
                    }
                )

            logger.info(
                f"Found {len(stations)} nearby stations for city {city_id}"
            )
            return stations

        except Exception as e:
            logger.error(f"Error fetching nearby stations: {e}")
            return []

    def find_studied_city_sync(
        self,
        target_lat: float,
        target_lon: float,
        max_distance_km: float = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Synchronous wrapper for find_studied_city() - compatible with synchronous code.

        Uses asyncio.run() internally to execute coroutine.

        Args:
            target_lat: Target latitude
            target_lon: Target longitude
            max_distance_km: Maximum distance to consider "nearby"

        Returns:
            Dict with city data and monthly normals, or None
        """
        import asyncio

        try:
            # Try to execute directly with asyncio.run
            return asyncio.run(
                self.find_studied_city(target_lat, target_lon, max_distance_km)
            )
        except RuntimeError as e:
            if "already running" in str(e):
                # If event loop already running, create new task
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.find_studied_city(
                            target_lat, target_lon, max_distance_km
                        ),
                    )
                    return future.result()
            else:
                raise

    def find_stations_in_radius_sync(
        self,
        target_lat: float,
        target_lon: float,
        radius_km: float = 50,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Synchronous wrapper for find_stations_in_radius() - compatible with synchronous code.

        Uses asyncio.run() internally to execute coroutine.

        Args:
            target_lat: Target latitude
            target_lon: Target longitude
            radius_km: Search radius in km
            limit: Maximum number of stations

        Returns:
            List of stations ordered by distance
        """
        import asyncio

        try:
            # Try to execute directly with asyncio.run
            return asyncio.run(
                self.find_stations_in_radius(
                    target_lat, target_lon, radius_km, limit
                )
            )
        except RuntimeError as e:
            if "already running" in str(e):
                # If event loop already running, create new task
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.find_stations_in_radius(
                            target_lat, target_lon, radius_km, limit
                        ),
                    )
                    return future.result()
            else:
                raise
