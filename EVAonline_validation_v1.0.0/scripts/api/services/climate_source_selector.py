"""
Intelligent climate source selector based on geographic coordinates.

Uses bounding boxes to automatically decide the best climate API
for each location, prioritizing high-quality regional sources.

Available APIs:
    - NWS (Regional - USA only):
        Forecast + Stations real-time

    - Open-Meteo Forecast (Global - Worldwide):
        Global standard, real-time (-30d to +5d)

    - Open-Meteo Archive (Global - Worldwide):
        Historical data (1940-present)

    - MET Norway (Global* - Worldwide):
        Global coverage, optimized for Europe

    - NASA POWER (Global - Worldwide):
        Universal fallback (2-7 day delay)
"""

from typing import Any, Literal

from loguru import logger

from validation_logic_eto.api.services.geographic_utils import GeographicUtils

# Type hints for climate sources
ClimateSource = Literal[
    "nasa_power",
    "met_norway",
    "nws_forecast",
    "nws_stations",
    "openmeteo_archive",
    "openmeteo_forecast",
]


class ClimateSourceSelector:
    """
    Intelligent climate source selector.

    Automatically determines the best API to fetch climate data
    based on provided geographic coordinates.

    IMPORTANT: Uses GeographicUtils for region detection
    (SINGLE SOURCE OF TRUTH for USA, Nordic, etc. bounding boxes)

    MET Norway Strategy:
        - Nordic Region: Temperature, Humidity, Precipitation
          (1km, radar + crowdsourced, hourly updates)
        - Rest of World: Temperature and Humidity only
          (9km ECMWF, lower precipitation quality - use Open-Meteo)

    Priorities:
        1. NWS (USA): Real-time, high regional quality
        2. MET Norway (Nordic): World's best precipitation
        3. Open-Meteo Forecast: Real-time, high global quality
        4. NASA POWER: Fallback with 2-7 day delay
    """

    # Source metadata mapping for client creation
    _SOURCE_TO_CLIENT_MAP = {
        "met_norway": "create_met_norway",
        "nws_forecast": "create_nws",
        "nws_stations": "create_nws",
        "openmeteo_archive": "create_openmeteo_archive",
        "openmeteo_forecast": "create_openmeteo_forecast",
        "nasa_power": "create_nasa_power",
    }

    @classmethod
    def select_source(cls, lat: float, lon: float) -> ClimateSource:
        """
        Select best climate source for coordinates.

        Selection algorithm:
        1. Check if in USA → NWS
        2. Check if in Nordic region → MET Norway (high quality)
        3. Fallback → Open-Meteo Forecast (global coverage, real-time)

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)

        Returns:
            Recommended source name

        Examples:
            # New York, USA
            >>> ClimateSourceSelector.select_source(40.7128, -74.0060)
            'nws_forecast'

            # Oslo, Norway (Nordic region)
            >>> ClimateSourceSelector.select_source(59.9139, 10.7522)
            'met_norway'

            # Paris, France
            >>> ClimateSourceSelector.select_source(48.8566, 2.3522)
            'openmeteo_forecast'

            # Brasília, Brazil
            >>> ClimateSourceSelector.select_source(-15.7939, -47.8828)
            'openmeteo_forecast'
        """
        # Priority 1: USA (NWS Forecast)
        if GeographicUtils.is_in_usa(lat, lon):
            logger.debug(f"Coordinates ({lat}, {lon}) in USA → NWS Forecast")
            return "nws_forecast"

        # Priority 2: Nordic Region (MET Norway high quality)
        if GeographicUtils.is_in_nordic(lat, lon):
            logger.debug(
                f"Coordinates ({lat}, {lon}) in NORDIC region → "
                f"MET Norway (1km, radar, high-quality precipitation)"
            )
            return "met_norway"

        # Fallback: Global (Open-Meteo Forecast - real-time, high quality)
        logger.debug(
            f"Coordinates ({lat}, {lon}) → Open-Meteo Forecast (global)"
        )
        return "openmeteo_forecast"

    @classmethod
    def get_client(cls, lat: float, lon: float):
        """
        Return appropriate client for coordinates.

        Combines select_source() with ClimateClientFactory to
        return pre-configured, ready-to-use client.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Configured climate client

        Examples:
            # Get automatic client for Paris
            >>> client = ClimateSourceSelector.get_client(
            ...     lat=48.8566, lon=2.3522
            ... )
            # → METNorwayClient with injected cache

            >>> data = await client.get_forecast_data(...)
            >>> await client.close()
        """
        # Lazy import to avoid circular dependencies
        from validation_logic_eto.api.services.climate_factory import (
            ClimateClientFactory,
        )

        source = cls.select_source(lat, lon)
        factory_method = cls._SOURCE_TO_CLIENT_MAP.get(source)

        if not factory_method:
            logger.warning(
                f"Unknown source '{source}', falling back to NASA POWER"
            )
            return ClimateClientFactory.create_nasa_power()

        return getattr(ClimateClientFactory, factory_method)()

    @classmethod
    def get_all_sources(cls, lat: float, lon: float) -> list[ClimateSource]:
        """
        Return ALL available sources for coordinates.

        Useful for multi-source fusion or cross-validation.

        Logic:
        - NASA POWER always available (global coverage)
        - MET Norway Locationforecast if in Nordic region (priority)
          or global (temperature/humidity only)
        - NWS Forecast/Stations if in USA
        - Open-Meteo Archive/Forecast always available

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            List of applicable sources, ordered by priority

        Examples:
            # Oslo (Nordic Region)
            >>> ClimateSourceSelector.get_all_sources(59.9139, 10.7522)
            ['met_norway', 'openmeteo_forecast', 'nasa_power', ...]

            # Brasília (global only)
            >>> ClimateSourceSelector.get_all_sources(-15.7939, -47.8828)
            ['openmeteo_forecast', 'met_norway', 'nasa_power', ...]
        """
        sources: list[ClimateSource] = []

        # Regional sources (high priority)
        if GeographicUtils.is_in_usa(lat, lon):
            sources.extend(["nws_forecast", "nws_stations"])

        # MET Norway has priority in Nordic region
        if GeographicUtils.is_in_nordic(lat, lon):
            sources.extend(["met_norway", "openmeteo_forecast"])
        else:
            # Outside Nordic: Open-Meteo has priority
            sources.extend(["openmeteo_forecast", "met_norway"])

        # Additional global sources
        sources.extend(["openmeteo_archive", "nasa_power"])

        logger.debug(f"Available sources for ({lat}, {lon}): {sources}")

        return sources

    @classmethod
    def get_data_availability_summary(cls) -> dict[str, dict[str, str]]:
        """
        Return availability summary for all data sources (6 APIs).

        Returns:
            Dict with availability information per source

        Example:
            >>> summary = ClimateSourceSelector.get_data_availability_summary()
            >>> summary['openmeteo_archive']['period']
            '1940-01-01 to today-2d'
        """
        return {
            "openmeteo_archive": {
                "coverage": "global",
                "period": "1990-01-01 to today-2d",
                "license": "CC-BY-4.0",
                "description": "Historical weather data (1990-present)",
            },
            "openmeteo_forecast": {
                "coverage": "global",
                "period": "today-30d to today+5d",
                "license": "CC-BY-4.0",
                "description": "Forecast weather data (up to 5 days)",
            },
            "nasa_power": {
                "coverage": "global",
                "period": "1990-01-01 to today-2-7d",
                "license": "Public Domain",
                "description": "NASA POWER meteorological data",
            },
            "nws_forecast": {
                "coverage": "usa",
                "period": "today to today+5d",
                "license": "Public Domain",
                "description": "NOAA NWS forecast data (USA only)",
            },
            "nws_stations": {
                "coverage": "usa",
                "period": "today-1d to now",
                "license": "Public Domain",
                "description": "NOAA NWS station observations (USA only)",
            },
            "met_norway": {
                "coverage": "global",
                "period": "today to today+5d",
                "license": "CC-BY-4.0",
                "description": "MET Norway Locationforecast (global)",
            },
        }

    @classmethod
    def get_coverage_info(cls, lat: float, lon: float) -> dict[str, Any]:
        """
        Return detailed coverage information for coordinates.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Dict with coverage information

        Example:
            >>> info = ClimateSourceSelector.get_coverage_info(
            ...     48.8566, 2.3522
            ... )
            >>> info['recommended_source']
            'met_norway'
            >>> info['regional_coverage']['usa']
            False
        """
        recommended = cls.select_source(lat, lon)
        all_sources = cls.get_all_sources(lat, lon)
        is_in_nordic = GeographicUtils.is_in_nordic(lat, lon)

        return {
            "location": {"lat": lat, "lon": lon},
            "recommended_source": recommended,
            "all_sources": all_sources,
            "regional_coverage": {
                "usa": GeographicUtils.is_in_usa(lat, lon),
                "nordic": is_in_nordic,
            },
            "source_details": {
                "nws_forecast": {
                    "bbox": GeographicUtils.USA_BBOX,
                    "description": "USA: -125°W to -66°W, 24°N to 49°N",
                    "quality": "high",
                    "realtime": True,
                },
                "nws_stations": {
                    "bbox": GeographicUtils.USA_BBOX,
                    "description": (
                        "USA stations: -125°W to -66°W, 24°N to 49°N"
                    ),
                    "quality": "high",
                    "realtime": True,
                },
                "met_norway": {
                    "bbox": None,
                    "nordic_bbox": GeographicUtils.NORDIC_BBOX,
                    "description": (
                        "Global coverage. Nordic region "
                        "(NO/SE/FI/DK/Baltics): "
                        "1km resolution, hourly updates, "
                        "radar-corrected precipitation. "
                        "Rest of world: 9km ECMWF, "
                        "temperature/humidity only"
                    ),
                    "quality": {
                        "nordic": "very high (1km + radar + crowdsourced)",
                        "global": "medium (9km ECMWF, skip precipitation)",
                    },
                    "realtime": True,
                },
                "openmeteo_archive": {
                    "bbox": None,
                    "description": "Global historical data",
                    "quality": "high",
                    "realtime": False,
                },
                "openmeteo_forecast": {
                    "bbox": None,
                    "description": "Global forecast data",
                    "quality": "high",
                    "realtime": True,
                },
                "nasa_power": {
                    "bbox": None,
                    "description": "Global coverage",
                    "quality": "medium",
                    "realtime": False,
                    "delay_days": "2-7",
                },
            },
        }


def get_available_sources_for_frontend(
    lat: float, lon: float
) -> dict[str, Any]:
    """
    Return available sources formatted for frontend.

    Used by dash_eto.py interface to populate source dropdown.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Dict with formatted information:
        {
            "recommended": "openmeteo_forecast",
            "sources": [
                {
                    "value": "fusion",
                    "label": "🔀 Smart Fusion (Recommended)",
                    "description": "Combines multiple sources..."
                },
                {
                    "value": "openmeteo_forecast",
                    "label": "Open-Meteo Forecast",
                    "description": "Real-time global data",
                    "icon": "🌍"
                },
                ...
            ],
            "location_info": {
                "in_usa": False,
                "in_nordic": False,
                "region": "Global"
            },
            "total_sources": 6
        }

    Example:
        >>> sources = get_available_sources_for_frontend(
        ...     lat=59.9139, lon=10.7522
        ... )
        >>> sources['location_info']['region']
        'Nordic Region'
        >>> len(sources['sources'])
        7  # fusion + 6 individual sources
    """
    # Detect region
    in_usa = GeographicUtils.is_in_usa(lat, lon)
    in_nordic = GeographicUtils.is_in_nordic(lat, lon)

    region = (
        "USA Continental"
        if in_usa
        else ("Nordic Region" if in_nordic else "Global")
    )

    # Get recommended source and all available
    recommended = ClimateSourceSelector.select_source(lat, lon)
    all_sources = ClimateSourceSelector.get_all_sources(lat, lon)

    # Icon and description mapping
    source_metadata = {
        "openmeteo_archive": {
            "icon": "📚",
            "label": "Open-Meteo Archive",
            "description": "Global historical data (1990-present)",
        },
        "openmeteo_forecast": {
            "icon": "🌍",
            "label": "Open-Meteo Forecast",
            "description": "Recent data + global forecast",
        },
        "nasa_power": {
            "icon": "🛰️",
            "label": "NASA POWER",
            "description": "Global historical data (1990-present)",
        },
        "met_norway": {
            "icon": "🇳🇴" if in_nordic else "🌐",
            "label": (
                "MET Norway"
                + (" (High Quality)" if in_nordic else " (Global)")
            ),
            "description": (
                "Weather forecast"
                + (" - 1km resolution" if in_nordic else " - Global")
            ),
        },
        "nws_forecast": {
            "icon": "🇺🇸",
            "label": "NWS Forecast",
            "description": "Official NOAA forecast (USA)",
        },
        "nws_stations": {
            "icon": "📡",
            "label": "NWS Stations",
            "description": "Real-time observations (USA)",
        },
    }

    # Build formatted source list
    sources_list = [
        {
            "value": "fusion",
            "label": "🔀 Smart Fusion (Recommended)",
            "description": (
                f"Combines {len(all_sources)} sources for "
                f"best quality and coverage"
            ),
            "is_default": True,
        }
    ]

    # Add individual sources
    for source in all_sources:
        if source in source_metadata:
            meta = source_metadata[source]
            sources_list.append(
                {
                    "value": source,
                    "label": f"{meta['icon']} {meta['label']}",
                    "description": meta["description"],
                    "is_recommended": source == recommended,
                }
            )

    return {
        "recommended": recommended,
        "sources": sources_list,
        "location_info": {
            "in_usa": in_usa,
            "in_nordic": in_nordic,
            "region": region,
        },
        "total_sources": len(all_sources),
    }
