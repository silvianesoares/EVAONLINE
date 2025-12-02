"""
Centralized validation service for climate data.

Responsibilities:
1. Validate coordinates (-90 to 90, -180 to 180)
2. Validate date format (YYYY-MM-DD)
3. Validate period (7, 14, 21 or 30 days) for online real-time dashboard
4. Validate period (1-90 days) for historical requests sent by email
5. Validate fixed period (6 days: today->today+5d) for dashboard forecast
6. Validate climate variables
7. Validate source name (string)
"""

from datetime import date, timedelta
from typing import Any

from loguru import logger

from .climate_source_availability import OperationMode


class ClimateValidationService:
    """Centralizes climate coordinate and date validations."""

    # Validation constants
    LAT_MIN, LAT_MAX = -90.0, 90.0
    LON_MIN, LON_MAX = -180.0, 180.0

    # Minimum date supported by APIs (NASA POWER, OpenMeteo Archive)
    MIN_HISTORICAL_DATE = date(1990, 1, 1)

    # Valid variables (standardized for all APIs)
    # Set for O(1) lookup
    VALID_CLIMATE_VARIABLES: set[str] = {
        # Temperature
        "temperature_2m",
        "temperature_2m_max",
        "temperature_2m_min",
        "temperature_2m_mean",
        # Humidity
        "relative_humidity_2m",
        "relative_humidity_2m_max",
        "relative_humidity_2m_min",
        "relative_humidity_2m_mean",
        # Wind (IMPORTANT: all APIs provide at 2m after conversion)
        "wind_speed_2m",
        "wind_speed_2m_mean",
        "wind_speed_2m_ms",
        # Precipitation
        "precipitation",
        "precipitation_sum",
        # Solar radiation
        "solar_radiation",
        "shortwave_radiation_sum",
        # Evapotranspiration
        "evapotranspiration",
        "et0_fao_evapotranspiration",
    }

    # Valid sources (all 6 implemented APIs)
    # Set for O(1) lookup
    VALID_SOURCES: set[str] = {
        # Global - Historical Data
        "openmeteo_archive",  # Historical (1990-01-01 -> today-2d)
        "nasa_power",  # Historical (1990-01-01 -> today)
        # Global - Forecast/Recent
        "openmeteo_forecast",  # Recent+Forecast (today-30d -> today+5d)
        "met_norway",  # Forecast (today -> today+5d)
        # USA Continental - Forecast
        "nws_forecast",  # Forecast (today -> today+5d)
        "nws_stations",  # Real-time observations (current day only)
    }

    @staticmethod
    def _parse_date(date_str: str) -> date:
        """Private parser for dates (YYYY-MM-DD)."""
        try:
            return date.fromisoformat(
                date_str
            )  # More robust and efficient than strptime
        except ValueError as e:
            logger.bind(date_str=date_str).error(
                f"Invalid date format: {e}"
            )
            raise ValueError(
                f"Invalid date '{date_str}': use YYYY-MM-DD"
            ) from e

    @staticmethod
    def validate_request_mode(
        mode: str,
        start_date: str,
        end_date: str,
        period_days: int | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Validate operation mode and its specific constraints.

        Args:
            mode: Operation mode:
                'historical_email', 'dashboard_current', 'dashboard_forecast'
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            period_days: Number of days (optional, will be calculated if omitted)

        Returns:
            Tuple (valid, details)
        """
        valid_modes = [
            OperationMode.HISTORICAL_EMAIL.value,
            OperationMode.DASHBOARD_CURRENT.value,
            OperationMode.DASHBOARD_FORECAST.value,
        ]
        if mode not in valid_modes:
            return False, {
                "error": f"Invalid mode '{mode}'. Valid: {valid_modes}"
            }

        # Validated parser
        try:
            start = ClimateValidationService._parse_date(start_date)
            end = ClimateValidationService._parse_date(end_date)
        except ValueError as e:
            return False, {"error": str(e)}

        if period_days is None:
            period_days = (end - start).days + 1

        today = date.today()  # Consistent with date.today()
        errors: list[str] = []

        # MODE 1: HISTORICAL_EMAIL (old data, email delivery)
        if mode == OperationMode.HISTORICAL_EMAIL.value:
            # VALIDATION MODE: Allow any period length (not just 1-90 days)
            # Original: if not (1 <= period_days <= 90)
            # For validation purposes, we need to support 1990-2024 (33 years)
            if period_days < 1:
                errors.append(
                    f"Historical period must be >= 1 day, "
                    f"got {period_days}"
                )
            # Constraint: end_date <= today - 30 days
            max_end = today - timedelta(days=30)
            if end > max_end:
                errors.append(
                    f"Historical end_date must be <= {max_end} "
                    f"(today - 30 days), got {end_date}"
                )
            # Constraint: start_date >= 1990-01-01
            if start < ClimateValidationService.MIN_HISTORICAL_DATE:
                errors.append(
                    f"Historical start_date must be >= "
                    f"{ClimateValidationService.MIN_HISTORICAL_DATE} "
                    f"(minimum supported), got {start_date}"
                )

        # MODE 2: DASHBOARD_CURRENT (recent data, real-time web)
        elif mode == OperationMode.DASHBOARD_CURRENT.value:
            # Period: exactly 7, 14, 21 or 30 days (dropdown)
            if period_days not in [7, 14, 21, 30]:
                errors.append(
                    f"Dashboard period must be [7, 14, 21, 30] days, "
                    f"got {period_days}"
                )
            # Constraint: end_date = today (fixed)
            if end != today:
                errors.append(
                    f"Dashboard end_date must be today ({today}), "
                    f"got {end_date}"
                )
            # Constraint: start_date cannot be before 1990-01-01
            if start < ClimateValidationService.MIN_HISTORICAL_DATE:
                errors.append(
                    f"Dashboard start_date must be >= "
                    f"{ClimateValidationService.MIN_HISTORICAL_DATE}, "
                    f"got {start_date}"
                )

        # MODE 3: DASHBOARD_FORECAST (5-day forecast, web)
        elif mode == OperationMode.DASHBOARD_FORECAST.value:
            # Period: today -> today+5d = 6 days (with timezone tolerance)
            if period_days not in [5, 6, 7]:  # Tolerance ±1 day
                errors.append(
                    f"Forecast period must be 5-7 days "
                    f"(today -> today+5d with tolerance), got {period_days}"
                )
            # Constraint: start_date ≈ today (tolerance ±1 day for timezone)
            if abs((start - today).days) > 1:
                errors.append(
                    f"Forecast start_date must be today±1d "
                    f"({today}), got {start_date}"
                )
            # Constraint: end_date ≈ today + 5 days (tolerance ±1 day)
            expected_end = today + timedelta(days=5)
            if abs((end - expected_end).days) > 1:
                errors.append(
                    f"Forecast end_date must be {expected_end}±1d "
                    f"(today+5d), got {end_date}"
                )

        if errors:
            logger.bind(
                mode=mode, start=start_date, end=end_date, period=period_days
            ).warning(f"Mode validation failed: {errors}")
            return False, {"errors": errors, "mode": mode}

        logger.bind(mode=mode, start=start, end=end, period=period_days).debug(
            "Mode validated successfully"
        )
        return True, {
            "mode": mode,
            "start": start,
            "end": end,
            "period_days": period_days,
            "valid": True,
        }

    @staticmethod
    def validate_coordinates(
        lat: float, lon: float, location_name: str = "Location"
    ) -> tuple[bool, dict[str, Any]]:
        """
        Validate geographic coordinates.

        Args:
            lat: Latitude
            lon: Longitude
            location_name: Location name (for error messages)

        Returns:
            Tuple (valid, details)
        """
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            return False, {
                "error": (
                    f"Invalid coordinate format " f"for {location_name}"
                )
            }

        errors: list[str] = []

        lat_min = ClimateValidationService.LAT_MIN
        lat_max = ClimateValidationService.LAT_MAX
        lon_min = ClimateValidationService.LON_MIN
        lon_max = ClimateValidationService.LON_MAX

        if not lat_min <= lat <= lat_max:
            errors.append(
                f"Latitude {lat} outside range ({lat_min} to {lat_max})"
            )

        if not lon_min <= lon <= lon_max:
            errors.append(
                f"Longitude {lon} outside range ({lon_min} to {lon_max})"
            )

        if errors:
            logger.bind(location=location_name, lat=lat, lon=lon).warning(
                f"Coordinate validation failed: {errors}"
            )
            return False, {"errors": errors}

        logger.bind(location=location_name, lat=lat, lon=lon).debug(
            "Coordinates validated"
        )
        return True, {"lat": lat, "lon": lon, "valid": True}

    @staticmethod
    def validate_date_range(
        start_date: str,
        end_date: str,
        allow_future: bool = False,
        max_future_days: int = 0,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Validate date FORMAT and future limits.

        NOTE: Does NOT validate period in days (min/max).
        Each mode validates its specific period in validate_request_mode().
        Each API validates its own temporal limits in
        climate_source_availability.py.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            allow_future: If future dates are allowed in range
            max_future_days: Maximum days in future allowed
                (0 = up to today, 5 = up to today+5d for forecast)

        Returns:
            Tuple (valid, details)
        """
        # Validated parser
        try:
            start = ClimateValidationService._parse_date(start_date)
            end = ClimateValidationService._parse_date(end_date)
        except ValueError as e:
            return False, {"error": str(e)}

        errors: list[str] = []
        today = date.today()
        max_allowed_date = today + timedelta(days=max_future_days)

        # Validation 1: start <= end
        if start > end:
            errors.append(f"start_date {start} > end_date {end}")

        # Validation 2: Future limits
        if allow_future:
            # When future allowed, validate against max_future_days
            if end > max_allowed_date:
                errors.append(
                    f"end_date {end} exceeds maximum "
                    f"({max_allowed_date}, today+{max_future_days}d)"
                )
        else:
            # When future NOT allowed, only end_date must be <= today
            # (start_date can be today for dashboard_current)
            if end > today:
                errors.append(
                    f"end_date {end} cannot be in future (today is {today})"
                )

        # Validation 3: Minimum historical date (applied universally)
        if start < ClimateValidationService.MIN_HISTORICAL_DATE:
            errors.append(
                f"start_date {start} is before minimum supported date "
                f"({ClimateValidationService.MIN_HISTORICAL_DATE})"
            )

        if errors:
            logger.bind(start=start_date, end=end_date).warning(
                f"Date range validation failed: {errors}"
            )
            return False, {"errors": errors}

        period_days = (end - start).days + 1
        logger.bind(start=start, end=end, period=period_days).debug(
            "Date range validated"
        )
        return True, {
            "start": start,
            "end": end,
            "period_days": period_days,
            "valid": True,
        }

    @staticmethod
    def validate_variables(
        variables: list[str],
    ) -> tuple[bool, dict[str, Any]]:
        """
        Validate list of climate variables.

        Args:
            variables: List of desired variables

        Returns:
            Tuple (valid, details)
        """
        if not variables:
            return False, {"error": "At least one variable is required"}

        invalid_vars = (
            set(variables) - ClimateValidationService.VALID_CLIMATE_VARIABLES
        )

        if invalid_vars:
            logger.bind(invalid=list(invalid_vars)).warning(
                "Invalid climate variables detected"
            )
            return False, {
                "error": f"Invalid variables: {invalid_vars}",
                "valid_options": sorted(
                    ClimateValidationService.VALID_CLIMATE_VARIABLES
                ),
            }

        logger.bind(variables=variables).debug("Variables validated")
        return True, {"variables": variables, "valid": True}

    @staticmethod
    def validate_source(source: str) -> tuple[bool, dict[str, Any]]:
        """
        Validate data source.

        Args:
            source: Source name

        Returns:
            Tuple (valid, details)
        """
        if source not in ClimateValidationService.VALID_SOURCES:
            logger.bind(source=source).warning("Invalid source")
            return False, {
                "error": f"Invalid source: {source}",
                "valid_options": sorted(
                    ClimateValidationService.VALID_SOURCES
                ),
            }

        logger.bind(source=source).debug("Source validated")
        return True, {"source": source, "valid": True}

    @staticmethod
    def detect_mode_from_dates(
        start_date: str, end_date: str
    ) -> tuple[str | None, str | None]:
        """
        Auto-detect operation mode based on dates.
        NOTE: Interface has buttons, but detector useful for validation.

        Logic:
        1. If start ≈ today AND end ≈ today+5d -> DASHBOARD_FORECAST
        2. If end = today AND period in [7,14,21,30] -> DASHBOARD_CURRENT
        3. If end <= today-30d AND period <= 90 -> HISTORICAL_EMAIL
        4. Otherwise -> None (mode not identifiable)

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Tuple (detected mode or None, error message)
        """
        # Validated parser
        try:
            start = ClimateValidationService._parse_date(start_date)
            end = ClimateValidationService._parse_date(end_date)
        except ValueError as e:
            return None, str(e)

        today = date.today()
        period_days = (end - start).days + 1

        # Rule 1: DASHBOARD_FORECAST (with ±1 day tolerance for timezone)
        expected_forecast_end = today + timedelta(days=5)
        is_start_today = abs((start - today).days) <= 1
        is_end_forecast = abs((end - expected_forecast_end).days) <= 1

        if is_start_today and is_end_forecast and period_days in [5, 6, 7]:
            return OperationMode.DASHBOARD_FORECAST.value, None

        # Rule 2: DASHBOARD_CURRENT
        if end == today and period_days in [7, 14, 21, 30]:
            return OperationMode.DASHBOARD_CURRENT.value, None

        # Rule 3: HISTORICAL_EMAIL
        # end <= today - 30 days AND 1 <= period <= 90 days
        if end <= today - timedelta(days=30) and 1 <= period_days <= 90:
            return OperationMode.HISTORICAL_EMAIL.value, None

        # Otherwise: ambiguous
        error_msg = (
            f"Could not detect mode from dates "
            f"{start_date} to {end_date}. "
            f"Period: {period_days} days. "
            f"Specify mode explicitly."
        )
        logger.bind(
            start=start_date, end=end_date, period=period_days
        ).warning(error_msg)
        return None, error_msg

    @staticmethod
    def validate_all(
        lat: float,
        lon: float,
        start_date: str,
        end_date: str,
        variables: list[str],
        source: str = "openmeteo_forecast",
        allow_future: bool = False,
        mode: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Validate all parameters at once.

        Args:
            lat, lon: Coordinates
            start_date, end_date: Date range
            variables: Climate variables
            source: Data source
            allow_future: Allow future dates
            mode: Operation mode (None = auto-detect)

        Returns:
            Tuple (valid, details)
        """
        # Auto-detect mode if not provided
        if mode is None:
            detected_mode, error = (
                ClimateValidationService.detect_mode_from_dates(
                    start_date, end_date
                )
            )
            if detected_mode:
                mode = detected_mode
                logger.bind(mode=mode).info("Mode auto-detected")
            else:
                logger.bind(error=error).warning(
                    "Failed to auto-detect mode"
                )
                # Continue without mode (for compatibility)

        validations = [
            (
                "coordinates",
                ClimateValidationService.validate_coordinates(lat, lon),
            ),
        ]

        # Determine max_future_days and allow_future based on mode
        max_future_days = 0
        effective_allow_future = allow_future

        if mode == OperationMode.DASHBOARD_FORECAST.value:
            max_future_days = 5
            effective_allow_future = True  # Forecast ALWAYS allows future
        elif mode == OperationMode.DASHBOARD_CURRENT.value:
            max_future_days = 0
            effective_allow_future = False  # Current ends today
        elif mode == OperationMode.HISTORICAL_EMAIL.value:
            max_future_days = 0
            effective_allow_future = False  # Historical is past

        validations.append(
            (
                "date_range",
                ClimateValidationService.validate_date_range(
                    start_date,
                    end_date,
                    allow_future=effective_allow_future,
                    max_future_days=max_future_days,
                ),
            )
        )

        validations.extend(
            [
                (
                    "variables",
                    ClimateValidationService.validate_variables(variables),
                ),
                ("source", ClimateValidationService.validate_source(source)),
            ]
        )

        # Add mode validation if detected/provided
        if mode:
            validations.append(
                (
                    "mode",
                    ClimateValidationService.validate_request_mode(
                        mode, start_date, end_date
                    ),
                )
            )

        errors: dict[str, Any] = {}
        details: dict[str, Any] = {}

        for name, (valid, detail) in validations:
            if not valid:
                errors[name] = detail
            else:
                details[name] = detail

        if errors:
            logger.bind(errors=list(errors.keys())).warning(
                "Validation errors found"
            )
            return False, {"errors": errors, "details": details}

        logger.bind(lat=lat, lon=lon, mode=mode).info(
            "All validations passed"
        )
        return True, {"all_valid": True, "details": details}
