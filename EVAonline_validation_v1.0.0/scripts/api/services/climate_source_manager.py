"""
Climate data source manager.

Detects which sources are available for a given location
and manages data fusion from multiple sources.

IMPORTANT: This module does NOT perform date/period validations.
Input validations: climate_validation.py
Temporal availability: climate_source_availability.py
Intelligent selection: climate_source_selector.py
"""

from datetime import date, datetime, timedelta
from typing import Any

from loguru import logger

from scripts.api.services.climate_source_availability import (
    ClimateSourceAvailability,
    OperationMode,
)
from scripts.api.services.climate_source_selector import ClimateSourceSelector
from scripts.api.services.geographic_utils import GeographicUtils


def normalize_operation_mode(period_type: str | None) -> OperationMode:
    """
    Normalize period_type to OperationMode consistently.

    Args:
        period_type: String representing period type

    Returns:
        OperationMode: Normalized enum

    Example:
        mode = normalize_operation_mode("historical")
        # Returns: OperationMode.HISTORICAL_EMAIL
    """
    period_type_str = (period_type or "dashboard_current").lower()

    # Complete alias mapping
    mapping = {
        "historical": OperationMode.HISTORICAL_EMAIL,
        "historical_email": OperationMode.HISTORICAL_EMAIL,
        "dashboard": OperationMode.DASHBOARD_CURRENT,
        "dashboard_current": OperationMode.DASHBOARD_CURRENT,
        "forecast": OperationMode.DASHBOARD_FORECAST,
        "dashboard_forecast": OperationMode.DASHBOARD_FORECAST,
    }

    return mapping.get(period_type_str, OperationMode.DASHBOARD_CURRENT)


class ClimateSourceManager:
    """Manages climate source availability and selection.

    Temporal Resolution Strategy:
    ------------------------------------
    All sources: DAILY
        * Used for world map dashboard (any point)
        * Daily data with 3 operation modes:
          - Historical_email: 1-90 days (end <= today-29d, email delivery)
          - Dashboard_current: [7,14,21,30] days (end = today, web)
          - Dashboard_forecast: 6 fixed days (today -> today+5d, web)
        * On-demand (user click)
        * Multi-source fusion available

    Configured Sources (6 sources):
    -------------------------------
    Global:
    - Open-Meteo Archive: Historical (1990 -> Today-2d), CC-BY-4.0
    - Open-Meteo Forecast: Forecast (Today-29d -> Today+5d), CC-BY-4.0
    - NASA POWER: Historical (1990 -> Today-2-7d), Public Domain
    - MET Norway: Global forecast (Today -> Today+5d), CC-BY-4.0

    USA Continental:
    - NWS Forecast: Forecast (Today -> Today+5d), Public Domain
    - NWS Stations: Observations (Today-1d -> Now), Public Domain

    IMPORTANT: Bounding boxes centralized in GeographicUtils
    """

    # Available data source configuration
    SOURCES_CONFIG: dict[str, dict[str, Any]] = {
        "openmeteo_archive": {
            "id": "openmeteo_archive",
            "name": "Open-Meteo Archive",
            "coverage": "global",
            "temporal": "daily",
            "bbox": None,
            "license": "CC-BY-4.0",
            "realtime": False,
            "priority": 1,
            "url": "https://archive-api.open-meteo.com/v1/archive",
            "variables": [
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
            ],
            "delay_hours": 48,
            "update_frequency": "daily",
            "historical_start": "1990-01-01",
            "restrictions": {"attribution_required": True},
            "use_case": (
                "Global historical ETo validation. "
                "Aligned with MIN_HISTORICAL_DATE (1990-01-01)"
            ),
        },
        "openmeteo_forecast": {
            "id": "openmeteo_forecast",
            "name": "Open-Meteo Forecast",
            "coverage": "global",
            "temporal": "daily",
            "bbox": None,
            "license": "CC-BY-4.0",
            "realtime": True,
            "priority": 1,
            "url": "https://api.open-meteo.com/v1/forecast",
            "variables": [
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
            ],
            "delay_hours": 1,
            "update_frequency": "daily",
            "historical_start": None,
            "forecast_horizon_days": 5,
            "restrictions": {"attribution_required": True},
            "use_case": "Global forecast ETo calculations",
        },
        "nasa_power": {
            "id": "nasa_power",
            "name": "NASA POWER",
            "coverage": "global",
            "temporal": "daily",
            "bbox": None,
            "license": "public_domain",
            "realtime": False,
            "priority": 2,
            "url": "https://power.larc.nasa.gov/api/temporal/daily/point",
            "variables": [
                "T2M_MAX",
                "T2M_MIN",
                "T2M",
                "RH2M",
                "WS2M",
                "ALLSKY_SFC_SW_DWN",
                "PRECTOTCORR",
            ],
            "delay_hours": 72,
            "update_frequency": "daily",
            "historical_start": "1990-01-01",
            "restrictions": {"limit_requests": 1000},
            "use_case": (
                "Global daily ETo, data fusion. "
                "Aligned with MIN_HISTORICAL_DATE (1990-01-01)"
            ),
        },
        "nws_forecast": {
            "id": "nws_forecast",
            "name": "NWS Forecast",
            "coverage": "usa",
            "temporal": "hourly",
            "bbox": GeographicUtils.USA_BBOX,
            "license": "public_domain",
            "realtime": True,
            "priority": 3,
            "url": "https://api.weather.gov/",
            "variables": [
                "temperature",
                "relativeHumidity",
                "windSpeed",
                "windDirection",
                "skyCover",
                "quantitativePrecipitation",
            ],
            "delay_hours": 1,
            "update_frequency": "hourly",
            "forecast_horizon_days": 5,
            "restrictions": {
                "attribution_required": True,
                "user_agent_required": True,
            },
            "use_case": "USA hourly ETo forecasts",
        },
        "nws_stations": {
            "id": "nws_stations",
            "name": "NWS Stations",
            "coverage": "usa",
            "temporal": "hourly",
            "bbox": GeographicUtils.USA_BBOX,
            "license": "public_domain",
            "realtime": True,
            "priority": 3,
            "url": "https://api.weather.gov/",
            "variables": [
                "temperature",
                "relativeHumidity",
                "windSpeed",
                "windDirection",
                "skyCover",
                "quantitativePrecipitation",
            ],
            "delay_hours": 1,
            "update_frequency": "hourly",
            "historical_start": None,
            "restrictions": {
                "attribution_required": True,
                "user_agent_required": True,
                "data_window_days": 30,
            },
            "use_case": "USA station observations",
        },
        "met_norway": {
            "id": "met_norway",
            "name": "MET Norway Locationforecast",
            "coverage": "global",
            "temporal": "daily",
            "bbox": None,
            "license": "NLOD-2.0+CC-BY-4.0",
            "realtime": True,
            "priority": 4,
            "url": (
                "https://api.met.no/weatherapi/" "locationforecast/2.0/compact"
            ),
            "variables": [
                "air_temperature_max",
                "air_temperature_min",
                "air_temperature_mean",
                "relative_humidity_mean",
                "precipitation_sum",
            ],
            "delay_hours": 1,
            "update_frequency": "daily",
            "forecast_horizon_days": 5,
            "restrictions": {
                "attribution_required": True,
                "user_agent_required": True,
                "limit_requests": "20 req/s",
            },
            "use_case": (
                "Regional quality strategy: Nordic (NO/SE/FI/DK) = "
                "high-quality precipitation (1km + radar). "
                "Global = temperature/humidity only "
                "(skip precipitation, use Open-Meteo)"
            ),
            "regional_strategy": {
                "nordic": {
                    "bbox": GeographicUtils.NORDIC_BBOX,
                    "resolution": "1km (MET Nordic)",
                    "model": "MEPS 2.5km + downscaling",
                    "updates": "Hourly",
                    "post_processing": (
                        "Radar + Netatmo crowdsourced bias correction"
                    ),
                    "variables": [
                        "air_temperature_max",
                        "air_temperature_min",
                        "air_temperature_mean",
                        "relative_humidity_mean",
                        "precipitation_sum",
                    ],
                    "precipitation_quality": "HIGH (use MET Norway)",
                },
                "global": {
                    "resolution": "9km (ECMWF IFS)",
                    "model": "ECMWF IFS HRES",
                    "updates": "4x daily (00/06/12/18 UTC)",
                    "post_processing": "Minimal",
                    "variables": [
                        "air_temperature_max",
                        "air_temperature_min",
                        "air_temperature_mean",
                        "relative_humidity_mean",
                    ],
                    "precipitation_quality": (
                        "LOW (use Open-Meteo multi-model instead)"
                    ),
                },
            },
        },
    }

    # Validation datasets (offline, documentation only)
    VALIDATION_DATASETS = {
        "xavier_brazil": {
            "name": "Xavier et al. Daily Weather Gridded Data",
            "period": "1961-01-01 to 2024-03-20",
            "resolution": "0.25° x 0.25°",
            "coverage": "brazil",
            "cities": [
                {"name": "Brasilia", "lat": -15.7939, "lon": -47.8828},
                {"name": "Sao Paulo", "lat": -23.5505, "lon": -46.6333},
            ],
            "reference": "https://doi.org/10.1002/joc.5325",
            "validation_metric": "ETo_FAO56",
        },
        "openmeteo_global": {
            "name": "Open-Meteo ETo (FAO-56 Penman-Monteith)",
            "period": "1990-01-01 to present (forecast)",
            "resolution": "Variable (depends on model)",
            "coverage": "global",
            "license": "CC-BY-4.0",
            "delay": "~1-2 days (forecast), ~2 days (archive)",
            "use_case": "Global ETo validation and comparison",
            "reference": "https://open-meteo.com/en/docs",
            "validation_metric": "et0_fao_evapotranspiration",
            "note": (
                "Open-Meteo provides pre-calculated ETo using FAO-56 "
                "Penman-Monteith method. Perfect for validating our "
                "application's ETo calculations against a reliable "
                "reference. Available through both Archive API "
                "(historical) and Forecast API (recent/current)."
            ),
            "api_endpoints": {
                "archive": "https://archive-api.open-meteo.com/v1/archive",
                "forecast": "https://api.open-meteo.com/v1/forecast",
            },
            "variable": "et0_fao_evapotranspiration",
        },
    }

    def __init__(self) -> None:
        """Initialize source manager."""
        self.enabled_sources: dict[str, dict[str, Any]] = dict(
            self.SOURCES_CONFIG
        )
        logger.info(
            "ClimateSourceManager initialized with %d sources",
            len(self.enabled_sources),
        )

    def get_available_sources(
        self, lat: float, lon: float
    ) -> list[dict[str, Any]]:
        """
        Return simple list of available sources (for compatibility).

        Simplified version that returns list of dicts with basic info.
        For complete metadata, use get_available_sources_for_location().

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)

        Returns:
            List[Dict]: List of available sources
        """
        result_dict = self.get_available_sources_for_location(lat, lon)
        available = [
            {
                "id": source_id,
                "name": metadata["name"],
                "coverage": metadata["coverage"],
                "temporal": metadata["temporal"],
                "realtime": metadata["realtime"],
                "priority": metadata["priority"],
                "delay_hours": metadata.get("delay_hours", 0),
                "variables": metadata.get("variables", []),
            }
            for source_id, metadata in result_dict.items()
            if metadata["available"]
        ]
        available.sort(key=lambda x: x["priority"])
        return available

    def get_best_source_for_location(
        self, lat: float, lon: float
    ) -> str | None:
        """
        Return BEST source for a location.

        Uses ClimateSourceSelector for intelligent selection based on:
        1. Geographic coverage (USA -> NWS, Nordic -> MET Norway)
        2. Regional quality (priority by region)
        3. Temporal availability

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            str: Best source ID, or None if none available
        """
        # Use ClimateSourceSelector for intelligent selection
        best_source = ClimateSourceSelector.select_source(lat, lon)

        logger.bind(lat=lat, lon=lon, source=best_source).debug(
            "Best source selected"
        )
        return best_source

    def get_available_sources_by_mode(
        self, lat: float, lon: float, mode: OperationMode | str
    ) -> list[str]:
        """
        Return sources compatible with operation mode AND location.

        Combines:
        1. Geographic filter (USA, Nordic, Global)
        2. Temporal filter (Historical, Current, Forecast)
        3. API availability

        Args:
            lat: Latitude
            lon: Longitude
            mode: Operation mode (OperationMode enum or string)

        Returns:
            List[str]: Compatible source IDs, ordered by priority
        """
        # Convert string to enum if needed
        if isinstance(mode, str):
            mode_mapping = {
                "historical_email": OperationMode.HISTORICAL_EMAIL,
                "dashboard_current": OperationMode.DASHBOARD_CURRENT,
                "dashboard_forecast": OperationMode.DASHBOARD_FORECAST,
            }
            mode = mode_mapping.get(mode, OperationMode.DASHBOARD_CURRENT)

        # Step 1: Get ALL available sources at location
        available_sources = ClimateSourceSelector.get_all_sources(lat, lon)

        # Step 2: Filter by temporal capability of mode
        # Use typical temporal limits of each mode for validation
        today = date.today()

        # Define representative period for each mode
        if mode == OperationMode.HISTORICAL_EMAIL:
            # Historical: end <= today - 30d
            start_date = today - timedelta(days=60)
            end_date = today - timedelta(days=30)
        elif mode == OperationMode.DASHBOARD_CURRENT:
            # Current: end = today, period in [7,14,21,30]
            start_date = today - timedelta(days=30)
            end_date = today
        elif mode == OperationMode.DASHBOARD_FORECAST:
            # Forecast: today -> today+5d
            start_date = today
            end_date = today + timedelta(days=5)
        else:
            # Default: use current
            start_date = today - timedelta(days=7)
            end_date = today

        compatible_sources = []

        for source_id in available_sources:
            # Check temporal compatibility
            availability = ClimateSourceAvailability.check_source_availability(
                source_id, lat, lon, start_date, end_date
            )
            if availability["available"]:
                compatible_sources.append(source_id)

        # Sort by priority
        compatible_sources.sort(
            key=lambda s: self.SOURCES_CONFIG[s]["priority"]
        )

        logger.bind(
            mode=mode.value, lat=lat, lon=lon, sources=compatible_sources
        ).debug("Compatible sources by mode obtained")
        return compatible_sources

    def get_sources_for_data_download(
        self,
        lat: float,
        lon: float,
        start_date: date | datetime,
        end_date: date | datetime,
        mode: OperationMode | str | None = None,
        preferred_sources: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        MAIN METHOD for data_download.py.

        Returns optimized sources for data download, considering:
        1. Geographic location (USA, Nordic, Global)
        2. Operation mode (Historical, Current, Forecast)
        3. Temporal availability of APIs
        4. User preferences

        Args:
            lat: Latitude
            lon: Longitude
            start_date: Start date
            end_date: End date
            mode: Operation mode (auto-detected if None)
            preferred_sources: User-preferred sources

        Returns:
            Dict with structure:
            {
                "sources": ["openmeteo_forecast", "met_norway"],
                "mode": "dashboard_forecast",
                "location_info": {
                    "lat": 59.9139,
                    "lon": 10.7522,
                    "in_usa": False,
                    "in_nordic": True,
                    "region": "Nordic Region"
                },
                "temporal_coverage": {
                    "start": "2024-01-15",
                    "end": "2024-01-20",
                    "period_days": 6
                },
                "warnings": []
            }
        """
        # Convert datetime to date if needed
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()

        warnings: list[str] = []

        # Auto-detect mode if not provided
        if mode is None:
            # Use simple heuristic
            today = date.today()
            period_days = (end_date - start_date).days + 1

            if end_date <= today - timedelta(days=30):
                mode = OperationMode.HISTORICAL_EMAIL
            elif end_date == today:
                mode = OperationMode.DASHBOARD_CURRENT
            elif end_date > today:
                mode = OperationMode.DASHBOARD_FORECAST
            else:
                mode = OperationMode.DASHBOARD_CURRENT

            warnings.append(
                f"Mode auto-detected: {mode.value} "
                f"(period: {period_days} days)"
            )

        # Convert string to enum if needed
        if isinstance(mode, str):
            mode = normalize_operation_mode(mode)

        # Validate temporal limits of mode (ensures conformance)
        today = date.today()
        period_days = (end_date - start_date).days + 1

        if mode == OperationMode.HISTORICAL_EMAIL:
            # Historical: end <= today - 30d
            max_end = today - timedelta(days=30)
            if end_date > max_end:
                warnings.append(
                    f"Historical mode: end_date {end_date} > "
                    f"maximum {max_end} (today-30d). "
                    f"Some sources may not have data."
                )
            # VALIDATION MODE: Allow flexible period (not just 1-90)
            if period_days < 1:
                raise ValueError(
                    f"Period must be >= 1 day, got {period_days}"
                )

        elif mode == OperationMode.DASHBOARD_CURRENT:
            # Current: end = today, period in [7,14,21,30]
            if end_date != today:
                warnings.append(
                    f"Dashboard current: end_date {end_date} != "
                    f"today {today}. Expected end_date = today."
                )
            if period_days not in [7, 14, 21, 30]:
                warnings.append(
                    f"Dashboard current: period {period_days} days "
                    f"not standard [7,14,21,30]. Proceeding anyway."
                )

        elif mode == OperationMode.DASHBOARD_FORECAST:
            # Forecast: today -> today+5d = 6 days
            expected_start = today
            expected_end = today + timedelta(days=5)
            if abs((start_date - expected_start).days) > 1:
                warnings.append(
                    f"Forecast mode: start_date {start_date} differs "
                    f"from expected {expected_start}."
                )
            if abs((end_date - expected_end).days) > 1:
                warnings.append(
                    f"Forecast mode: end_date {end_date} differs "
                    f"from expected {expected_end} (today+5d)."
                )

        # Detect region
        in_usa = GeographicUtils.is_in_usa(lat, lon)
        in_nordic = GeographicUtils.is_in_nordic(lat, lon)
        region = (
            "USA Continental"
            if in_usa
            else ("Nordic Region" if in_nordic else "Global")
        )

        # Get available sources for mode and location
        available_sources = self.get_available_sources_by_mode(lat, lon, mode)

        # Filter by preferred sources if specified
        if preferred_sources:
            # Normalize source names
            preferred_normalized = [s.lower() for s in preferred_sources]
            # Filter available sources
            selected_sources = [
                s for s in available_sources if s in preferred_normalized
            ]

            # Warn if some preferred sources not available
            unavailable = set(preferred_normalized) - set(selected_sources)
            if unavailable:
                warnings.append(
                    f"Preferred sources unavailable: {unavailable}. "
                    f"Available: {selected_sources}"
                )
        else:
            selected_sources = available_sources

        if not selected_sources:
            raise ValueError(
                f"No sources available for mode={mode.value}, "
                f"location=({lat}, {lon}), period={start_date} to {end_date}"
            )

        return {
            "sources": selected_sources,
            "mode": mode.value,
            "location_info": {
                "lat": lat,
                "lon": lon,
                "in_usa": in_usa,
                "in_nordic": in_nordic,
                "region": region,
            },
            "temporal_coverage": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "period_days": period_days,
            },
            "warnings": warnings,
        }

    def get_available_sources_for_location(
        self, lat: float, lon: float
    ) -> dict[str, dict[str, Any]]:
        """
        Return detailed metadata for all sources at location.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Dict mapping source_id -> metadata with 'available' field
        """
        result = {}

        for source_id, config in self.enabled_sources.items():
            # Check geographic coverage
            if config["coverage"] == "usa":
                available = GeographicUtils.is_in_usa(lat, lon)
            elif config.get("bbox"):
                available = GeographicUtils.is_in_bbox(
                    lat, lon, config["bbox"]
                )
            else:
                # Global coverage
                available = True

            result[source_id] = {
                **config,
                "available": available,
                "location": {"lat": lat, "lon": lon},
            }

        logger.bind(lat=lat, lon=lon).debug(
            "Source availability checked for location"
        )
        return result

    def get_fusion_weights(
        self, sources: list[str], lat: float, lon: float
    ) -> dict[str, float]:
        """
        Calculate fusion weights for multiple sources.

        Weights based on:
        1. Source priority
        2. Regional quality
        3. Temporal characteristics

        Args:
            sources: List of source IDs
            lat: Latitude
            lon: Longitude

        Returns:
            Dict mapping source_id -> weight (0.0 to 1.0)
        """
        if not sources:
            return {}

        weights = {}
        total_weight = 0.0

        # Base weights from priority (inverse: lower priority = higher weight)
        for source_id in sources:
            if source_id not in self.SOURCES_CONFIG:
                logger.warning(f"Unknown source for weights: {source_id}")
                continue

            config = self.SOURCES_CONFIG[source_id]
            # Inverse priority: priority 1 -> weight 4, priority 4 -> weight 1
            base_weight = 5.0 - config["priority"]

            # Regional bonuses
            if source_id == "met_norway" and GeographicUtils.is_in_nordic(
                lat, lon
            ):
                # MET Norway in Nordic: +50% weight (high quality)
                base_weight *= 1.5
            elif source_id in ["nws_forecast", "nws_stations"]:
                # NWS in USA: +30% weight (high quality)
                if GeographicUtils.is_in_usa(lat, lon):
                    base_weight *= 1.3

            weights[source_id] = base_weight
            total_weight += base_weight

        # Normalize to sum = 1.0
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}

        logger.bind(sources=sources, weights=weights).debug(
            "Fusion weights calculated"
        )
        return weights

    def _format_bbox(self, bbox: tuple | None) -> str:
        """Format bounding box for display."""
        if bbox is None:
            return "Global"
        west, south, east, north = bbox
        return (
            f"[{west:.1f}W, {south:.1f}S] to [{east:.1f}E, {north:.1f}N]"
        )

    def _is_point_covered(
        self, lat: float, lon: float, metadata: dict[str, Any]
    ) -> bool:
        """Check if point is covered by source."""
        if metadata["coverage"] == "global":
            return True
        elif metadata["coverage"] == "usa":
            return GeographicUtils.is_in_usa(lat, lon)
        elif metadata.get("bbox"):
            return GeographicUtils.is_in_bbox(lat, lon, metadata["bbox"])
        return False
