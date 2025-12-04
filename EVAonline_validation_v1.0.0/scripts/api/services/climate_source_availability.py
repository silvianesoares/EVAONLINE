"""
Climate data source availability service.

EVAonline rules (3 operation modes):
1. HISTORICAL_EMAIL: 1-90 days (email, free choice)
   - NASA POWER: start 1990/01/01, end today (no delay)
   - Open-Meteo Archive: start 1990/01/01, end today-2d (with 2d delay)

2. DASHBOARD_CURRENT: [7,14,21,30] days, end=today fixed (web, dropdown)
   - NASA POWER: start today-29d, end today (30 days max, no delay)
   - Open-Meteo Archive: start today-29d, end today-2d (28 days max, 2d delay)
   - Open-Meteo Forecast: start today-29d, end today (30 days max, no delay)

3. DASHBOARD_FORECAST: 6 days fixed (today -> today+5d), web forecasts
   IF USA: radio button "Data Fusion" OR "Real station data"
   3.1. Fusion (default):
     * Open-Meteo Forecast: start today, end today+5d
     * MET Norway: start today, end today+5d (global, nordic region)
     * NWS Forecast: start today, end today+5d (USA only)

   3.2. Stations (USA only):
     * NWS Stations: start today-2d, end today (realtime)

Responsibilities:
1. Define temporal limits for each API by mode
2. Filter APIs by context (date + location + type)
3. Determine available variables by region
4. Return which APIs work for a specific request

IMPORTANT: Geographic detection delegates to GeographicUtils
(SINGLE SOURCE OF TRUTH for USA, Nordic bounding boxes, etc)
"""

from datetime import date, timedelta
from enum import StrEnum
from typing import Any
from loguru import logger

from scripts.api.services.geographic_utils import GeographicUtils


class OperationMode(StrEnum):  # StrEnum for Pydantic v2 compatibility
    """Enum for the 3 EVAonline operation modes."""

    HISTORICAL_EMAIL = "historical_email"
    DASHBOARD_CURRENT = "dashboard_current"
    DASHBOARD_FORECAST = "dashboard_forecast"


class ClimateSourceAvailability:
    """Determines API availability based on context."""

    # Centralized constant for historical start date (avoids duplication)
    HISTORICAL_START_DATE = date(1990, 1, 1)

    # API temporal limits (EVA standardized)
    API_LIMITS: dict[str, dict[str, Any]] = {
        # Historical
        "nasa_power": {
            "type": "historical_email+dashboard_current",
            "start_date": HISTORICAL_START_DATE,  # Centralized reference
            "end_date_offset": 0,  # today (no delay)
            "coverage": "global",
        },
        "openmeteo_archive": {
            "type": "historical_email+dashboard_current",
            "start_date": HISTORICAL_START_DATE,  # 1990-01-01
            "end_date_offset": -2,  # today-2d (HISTORICAL_EMAIL)
            "coverage": "global",
        },
        # Forecast/Recent
        "openmeteo_forecast": {
            "type": "dashboard_current+dashboard_forecast",
            "start_date_offset": -29,  # today (DASHBOARD_FORECAST)
            "end_date_offset": +5,  # today+5d
            "coverage": "global",
        },
        "met_norway": {
            "type": "dashboard_forecast",
            "start_date_offset": 0,  # today
            "end_date_offset": +5,  # today+5d
            "coverage": "global+nordic_region",
            "global": "temp+humidity",
            "nordic_region": "temp+humidity+wind+precipitation",
            "regional_variables": True,
        },
        "nws_forecast": {
            "type": "dashboard_forecast",
            "start_date_offset": 0,  # today
            "end_date_offset": +5,  # today+5d
            "coverage": "usa",
        },
        "nws_stations": {
            "type": "dashboard_current",
            "start_date_offset": -2,  # today-2d
            "end_date_offset": 0,  # now
            "coverage": "usa",
        },
    }

    @classmethod
    def _parse_date(cls, date_input: date | str) -> date:
        """Private and validated parser for dates (ISO or date)."""
        try:
            if isinstance(date_input, str):
                return date.fromisoformat(
                    date_input
                )  # More robust than strptime
            return date_input
        except ValueError as e:
            logger.error(f"Invalid date '{date_input}': {e}")
            raise ValueError("Invalid date format: use YYYY-MM-DD") from e

    @classmethod
    def get_available_sources(
        cls,
        start_date: date | str,
        end_date: date | str,
        lat: float,
        lon: float,
    ) -> dict[str, dict[str, Any]]:
        """
        Determines which APIs are available for the provided context.

        NOTE: Does NOT validate period (min/max days).
        Only checks:
        1. Geographic coverage (USA, Nordic, Global)
        2. Temporal limits (each API has its own limits)

        Mode validation (1-90 days, etc) is responsibility of
        climate_validation.py::validate_request_mode()

        Args:
            start_date: Start date (date or YYYY-MM-DD)
            end_date: End date (date or YYYY-MM-DD)
            lat: Latitude
            lon: Longitude

        Returns:
            Dict with available APIs and their characteristics:
            {
                "nasa_power": {
                    "available": True,
                    "variables": ["all"],
                    "reason": "..."
                },
                ...
            }
        """
        # Validated parser (raises if invalid)
        start_parsed = cls._parse_date(start_date)
        end_parsed = cls._parse_date(end_date)

        # Basic validation: start <= end
        if start_parsed > end_parsed:
            raise ValueError(
                f"start_date ({start_parsed}) must be <= "
                f"end_date ({end_parsed})"
            )

        today = date.today()  # Always use today() for consistency
        result: dict[str, dict[str, Any]] = {}

        # Check location (with log bind for context)
        in_usa = GeographicUtils.is_in_usa(lat, lon)
        in_nordic = GeographicUtils.is_in_nordic(lat, lon)

        logger.bind(
            start=start_parsed,
            end=end_parsed,
            lat=lat,
            lon=lon,
            usa=in_usa,
            nordic=in_nordic,
        ).debug("Checking climate source availability")

        # Evaluate each API
        for api_name, limits in cls.API_LIMITS.items():
            available = True
            reasons: list[str] = []  # List to join reasons
            variables: list[str] = []

            # 1. Check geographic coverage
            if limits["coverage"] == "usa" and not in_usa:
                available = False
                reasons.append("Not available outside USA")

            # 2. Check temporal limits
            if available:
                api_type = limits["type"]
                if api_type == "historical_email+dashboard_current":
                    # Historical APIs: check absolute limits
                    api_start = limits["start_date"]
                    api_end = today + timedelta(days=limits["end_date_offset"])

                    if start_parsed < api_start:
                        available = False
                        reasons.append(f"Start date before {api_start}")
                    if end_parsed > api_end:
                        available = False
                        reasons.append(f"End date after {api_end}")

                elif api_type in ["dashboard_forecast", "dashboard_current"]:
                    # Forecast/realtime APIs: check offsets
                    api_start = today + timedelta(
                        days=limits.get("start_date_offset", 0)
                    )
                    api_end = today + timedelta(
                        days=limits.get("end_date_offset", 0)
                    )

                    logger.bind(api=api_name).debug(
                        f"API range: {api_start} to {api_end}, "
                        f"requested: {start_parsed} to {end_parsed}"
                    )

                    if start_parsed < api_start:
                        available = False
                        reasons.append(f"Start date before {api_start}")
                    if end_parsed > api_end:
                        available = False
                        reasons.append(f"End date after {api_end}")

            # 3. Determine available variables (if available)
            if available:
                if api_name == "met_norway" and limits.get(
                    "regional_variables"
                ):
                    if in_nordic:
                        variables = [
                            "temperature_2m_mean",
                            "relative_humidity_2m_mean",
                            "wind_speed_10m_mean",
                            "precipitation_sum",
                        ]
                        reasons.append(
                            "Nordic region: temp+humidity+wind+precip"
                        )
                    else:
                        variables = [
                            "temperature_2m_mean",
                            "relative_humidity_2m_mean",
                        ]
                        reasons.append("Global: temp+humidity only")
                else:
                    variables = ["all"]
                    reasons.append("All variables available")

            # Add to result
            result[api_name] = {
                "available": available,
                "variables": variables,
                "type": api_type,
                "coverage": limits["coverage"],
                "reason": (
                    " | ".join(reasons)
                    if reasons
                    else "Available without restrictions"
                ),
            }

        return result

    @classmethod
    def get_compatible_sources_list(
        cls,
        start_date: date | str,
        end_date: date | str,
        lat: float,
        lon: float,
    ) -> list[str]:
        """
        Returns list of available APIs (names only).

        Args:
            start_date: Start date
            end_date: End date
            lat: Latitude
            lon: Longitude

        Returns:
            List of available API names
        """
        available = cls.get_available_sources(start_date, end_date, lat, lon)
        return [
            api_name
            for api_name, info in available.items()
            if info["available"]
        ]

    @classmethod
    def is_source_available(
        cls,
        source_id: str,
        mode: OperationMode | str,
        start_date: date | str,
        end_date: date | str,
    ) -> bool:
        """
        Checks if a specific source is available for the context.

        Args:
            source_id: Source ID (e.g., 'nasa_power', 'openmeteo_archive')
            mode: Operation mode
            start_date: Start date
            end_date: End date

        Returns:
            True if the source is available
        """
        try:
            # Convert mode to OperationMode if needed
            if isinstance(mode, str):
                mode = OperationMode(mode)

            # Get API limits for context
            limits = cls.get_api_date_limits_for_context(mode)

            if source_id not in limits:
                return False

            api_limits = limits[source_id]

            # Check if dates are within limits
            start_parsed = cls._parse_date(start_date)
            end_parsed = cls._parse_date(end_date)

            min_date = api_limits["start_date"]
            max_date = api_limits["end_date"]

            return (
                min_date <= start_parsed <= max_date
                and min_date <= end_parsed <= max_date
            )

        except Exception:
            return False

    @classmethod
    def get_api_date_limits_for_context(
        cls,
        context: str | OperationMode,
        today: date | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Returns date limits specific to each API and context.
        """
        if today is None:
            today = date.today()

        # Normalize context to string
        context_str = (
            context.value if isinstance(context, OperationMode) else context
        )

        limits: dict[str, dict[str, Any]] = {}

        if context_str == OperationMode.HISTORICAL_EMAIL.value:
            # Historical_email: APIs provide from 1990 to today-2 days
            # User chooses FREELY within this range
            # Restrictions: 1-90 days period
            # Limit today-2d avoids overlap with dashboard_current
            historical_end = today - timedelta(days=2)
            common_reason = (
                f"Historical email: 1990 to {historical_end} "
                "(user free choice, 1-90 days period)"
            )

            limits["nasa_power"] = {
                "start_date": cls.HISTORICAL_START_DATE,
                "end_date": today,
                "min_period_days": 1,
                "max_period_days": 90,
                "reason": common_reason,
            }

            limits["openmeteo_archive"] = {
                "start_date": cls.HISTORICAL_START_DATE,
                "end_date": historical_end,
                "min_period_days": 1,
                "max_period_days": 90,
                "reason": common_reason,
            }

        elif context_str == OperationMode.DASHBOARD_CURRENT.value:
            # Dashboard_current: [7,14,21,30] days dropdown, end=today fixed
            # NASA POWER: 2d delay, end=today-2d
            # Open-Meteo Archive: 2d delay, end=today-2d
            # Open-Meteo Forecast: today-29d, end=today

            dashboard_start_30d = today - timedelta(days=29)  # 30 days max
            archive_end = today - timedelta(days=2)
            nasapower_end = today - timedelta(days=2)

            limits["nasa_power"] = {
                "start_date": dashboard_start_30d,
                "end_date": nasapower_end,
                "reason": (
                    f"Dashboard current: {dashboard_start_30d} to {nasapower_end} "
                    "(2-day delay, complete coverage)"
                ),
            }

            limits["openmeteo_archive"] = {
                "start_date": dashboard_start_30d,
                "end_date": archive_end,
                "reason": (
                    f"Dashboard current: {dashboard_start_30d} to "
                    f"{archive_end} (2-day delay)"
                ),
            }

            limits["openmeteo_forecast"] = {
                "start_date": today - timedelta(days=29),
                "end_date": today,
                "reason": (
                    f"Dashboard current: {today - timedelta(days=29)} to "
                    f"{today} (fills archive gap, recent data)"
                ),
            }

        elif context_str == OperationMode.DASHBOARD_FORECAST.value:
            # Dashboard_forecast: next 5 days fixed (today -> today+5d)
            # Fixed period: 6 total days (inclusive)
            forecast_end = today + timedelta(days=5)
            common_reason = (
                f"Dashboard forecast: {today} to {forecast_end} "
                "(6 days fixed period)"
            )

            limits["openmeteo_forecast"] = {
                "start_date": today,
                "end_date": forecast_end,
                "reason": common_reason,
            }

            limits["met_norway"] = {
                "start_date": today,
                "end_date": forecast_end,
                "reason": common_reason,
            }

            limits["nws_forecast"] = {
                "start_date": today,
                "end_date": forecast_end,
                "reason": f"{common_reason} (USA only)",
                "coverage": "usa",
            }

            # NWS Stations: alternative option for USA
            # (radio button: "Fusion" vs "Real stations")
            limits["nws_stations"] = {
                "start_date": today - timedelta(days=2),
                "end_date": today,
                "reason": (
                    f"Dashboard forecast: {today} only "
                    "(realtime stations, USA only, alternative mode)"
                ),
                "coverage": "usa",
            }

        return limits
