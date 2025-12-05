"""
Unit tests for OperationModeDetector

Tests the automatic mode detection and validation logic for the 3 operational
modes: HISTORICAL_EMAIL, DASHBOARD_CURRENT, DASHBOARD_FORECAST.
"""

import pytest
from datetime import date, timedelta
from frontend.utils.mode_detector import (
    OperationModeDetector,
    parse_date_from_ui,
    format_date_for_display,
)


class TestModeDetection:
    """Test mode detection from UI selections"""

    def test_detect_mode_historical(self):
        """Test detection of HISTORICAL_EMAIL mode"""
        mode, config = OperationModeDetector.detect_mode("historical")

        assert mode == "HISTORICAL_EMAIL"
        assert config["requires_email"] is True
        assert config["min_period"] == 1
        assert config["max_period"] == 90
        assert config["ui_selection"] == "historical"

    def test_detect_mode_recent(self):
        """Test detection of DASHBOARD_CURRENT mode"""
        mode, config = OperationModeDetector.detect_mode("recent")

        assert mode == "DASHBOARD_CURRENT"
        assert config["requires_email"] is False
        assert config["allowed_periods"] == [7, 14, 21, 30]
        assert config["ui_selection"] == "recent"

    def test_detect_mode_forecast(self):
        """Test detection of DASHBOARD_FORECAST mode"""
        mode, config = OperationModeDetector.detect_mode("forecast")

        assert mode == "DASHBOARD_FORECAST"
        assert config["requires_email"] is False
        assert config["fixed_period"] == 6
        assert config["ui_selection"] == "forecast"

    def test_detect_mode_invalid(self):
        """Test that invalid UI selection raises ValueError"""
        with pytest.raises(ValueError, match="Unknown operation mode"):
            OperationModeDetector.detect_mode("invalid_mode")


class TestDateValidation:
    """Test date validation for each mode"""

    def test_validate_historical_valid(self):
        """Test valid historical date range"""
        start = date(2023, 1, 1)
        end = date(2023, 1, 30)  # 30 days

        is_valid, message = OperationModeDetector.validate_dates(
            "HISTORICAL_EMAIL", start, end
        )

        assert is_valid is True
        assert "30 days" in message

    def test_validate_historical_too_old(self):
        """Test historical dates before minimum date"""
        start = date(1989, 12, 31)  # Before 1990-01-01
        end = date(1990, 1, 5)

        is_valid, message = OperationModeDetector.validate_dates(
            "HISTORICAL_EMAIL", start, end
        )

        assert is_valid is False
        assert "1990-01-01" in message

    def test_validate_historical_too_recent(self):
        """Test historical dates too close to today"""
        today = date.today()
        start = today - timedelta(days=5)
        end = today  # Should be today-2 or earlier

        is_valid, message = OperationModeDetector.validate_dates(
            "HISTORICAL_EMAIL", start, end
        )

        assert is_valid is False
        assert "today-2d" in message

    def test_validate_historical_exceeds_90_days(self):
        """Test historical period exceeding 90 days limit"""
        start = date(2023, 1, 1)
        end = date(2023, 4, 15)  # 104 days

        is_valid, message = OperationModeDetector.validate_dates(
            "HISTORICAL_EMAIL", start, end
        )

        assert is_valid is False
        assert "90 days" in message

    def test_validate_current_valid_7_days(self):
        """Test valid dashboard current mode (7 days)"""
        today = date.today()
        start = today - timedelta(days=6)
        end = today

        is_valid, message = OperationModeDetector.validate_dates(
            "DASHBOARD_CURRENT", start, end
        )

        assert is_valid is True
        assert "7 days" in message

    def test_validate_current_valid_30_days(self):
        """Test valid dashboard current mode (30 days)"""
        today = date.today()
        start = today - timedelta(days=29)
        end = today

        is_valid, message = OperationModeDetector.validate_dates(
            "DASHBOARD_CURRENT", start, end
        )

        assert is_valid is True
        assert "30 days" in message

    def test_validate_current_end_not_today(self):
        """Test dashboard current requires end date = today"""
        today = date.today()
        start = today - timedelta(days=6)
        end = today - timedelta(days=1)  # Yesterday, not today

        is_valid, message = OperationModeDetector.validate_dates(
            "DASHBOARD_CURRENT", start, end
        )

        assert is_valid is False
        assert "end_date = today" in message

    def test_validate_current_invalid_period(self):
        """Test dashboard current with invalid period (not 7/14/21/30)"""
        today = date.today()
        start = today - timedelta(days=9)  # 10 days (invalid)
        end = today

        is_valid, message = OperationModeDetector.validate_dates(
            "DASHBOARD_CURRENT", start, end
        )

        assert is_valid is False
        assert "must be one of" in message

    def test_validate_forecast_valid(self):
        """Test valid forecast period (6 days)"""
        today = date.today()
        start = today
        end = today + timedelta(days=5)  # 6 days total

        is_valid, message = OperationModeDetector.validate_dates(
            "DASHBOARD_FORECAST", start, end
        )

        assert is_valid is True
        assert "6-day" in message

    def test_validate_forecast_not_starting_today(self):
        """Test forecast requires start date = today (with 1-day tolerance)"""
        today = date.today()
        start = today + timedelta(days=2)  # 2 days ahead (outside tolerance)
        end = today + timedelta(days=7)

        is_valid, message = OperationModeDetector.validate_dates(
            "DASHBOARD_FORECAST", start, end
        )

        assert is_valid is False
        assert "start today" in message

    def test_validate_forecast_wrong_period(self):
        """Test forecast with wrong period (not 6 days)"""
        today = date.today()
        start = today
        end = today + timedelta(days=10)  # 11 days, not 6

        is_valid, message = OperationModeDetector.validate_dates(
            "DASHBOARD_FORECAST", start, end
        )

        assert is_valid is False
        # Error message mentions expected end date, not "exactly 6 days"
        assert "today+5d" in message


class TestAPIRequestPreparation:
    """Test API request payload preparation"""

    def test_prepare_historical_with_email(self):
        """Test historical mode request with email"""
        start = date(2023, 1, 1)
        end = date(2023, 1, 30)

        payload = OperationModeDetector.prepare_api_request(
            ui_selection="historical",
            latitude=-15.7801,
            longitude=-47.9292,
            start_date=start,
            end_date=end,
            email="user@example.com",
        )

        assert payload["mode"] == "HISTORICAL_EMAIL"
        assert payload["latitude"] == -15.7801
        assert payload["longitude"] == -47.9292
        assert payload["start_date"] == "2023-01-01"
        assert payload["end_date"] == "2023-01-30"
        assert payload["email"] == "user@example.com"

    def test_prepare_historical_missing_email_ignored(self):
        """Test historical mode validates without email in prepare"""
        start = date(2023, 1, 1)
        end = date(2023, 1, 30)

        payload = OperationModeDetector.prepare_api_request(
            ui_selection="historical",
            latitude=-15.7801,
            longitude=-47.9292,
            start_date=start,
            end_date=end,
            email=None,  # Should set to None, validation in callback
        )

        assert payload["email"] is None

    def test_prepare_recent_7_days(self):
        """Test recent mode request (7 days)"""
        payload = OperationModeDetector.prepare_api_request(
            ui_selection="recent",
            latitude=-15.7801,
            longitude=-47.9292,
            period_days=7,
        )

        assert payload["mode"] == "DASHBOARD_CURRENT"
        assert payload["email"] is None

        # Check dates are calculated correctly
        today = date.today()
        expected_start = today - timedelta(days=6)
        assert payload["start_date"] == expected_start.isoformat()
        assert payload["end_date"] == today.isoformat()

    def test_prepare_recent_30_days(self):
        """Test recent mode request (30 days)"""
        payload = OperationModeDetector.prepare_api_request(
            ui_selection="recent",
            latitude=-23.5505,
            longitude=-46.6333,
            period_days=30,
        )

        assert payload["mode"] == "DASHBOARD_CURRENT"

        # Check dates
        today = date.today()
        expected_start = today - timedelta(days=29)
        assert payload["start_date"] == expected_start.isoformat()
        assert payload["end_date"] == today.isoformat()

    def test_prepare_forecast(self):
        """Test forecast mode request"""
        payload = OperationModeDetector.prepare_api_request(
            ui_selection="forecast",
            latitude=-15.7801,
            longitude=-47.9292,
        )

        assert payload["mode"] == "DASHBOARD_FORECAST"
        assert payload["email"] is None

        # Check dates
        today = date.today()
        expected_end = today + timedelta(days=5)
        assert payload["start_date"] == today.isoformat()
        assert payload["end_date"] == expected_end.isoformat()

    def test_prepare_forecast_usa_stations(self):
        """Test forecast mode with USA stations option (future feature)"""
        # Note: DASHBOARD_FORECAST_STATIONS not yet in BACKEND_MODES
        # This test documents the intended behavior for future implementation
        payload = OperationModeDetector.prepare_api_request(
            ui_selection="forecast",
            latitude=40.7128,  # New York
            longitude=-74.0060,
            usa_forecast_source="fusion",  # Use fusion for now
        )

        # Currently returns regular DASHBOARD_FORECAST
        assert payload["mode"] == "DASHBOARD_FORECAST"
        # TODO: Add DASHBOARD_FORECAST_STATIONS mode when stations supported


class TestValidationErrors:
    """Test error handling for invalid inputs"""

    def test_prepare_historical_missing_dates(self):
        """Test historical mode requires start and end dates"""
        with pytest.raises(
            ValueError, match="requires start_date and end_date"
        ):
            OperationModeDetector.prepare_api_request(
                ui_selection="historical",
                latitude=-15.7801,
                longitude=-47.9292,
                email="user@example.com",
                # Missing start_date and end_date
            )

    def test_prepare_recent_missing_period(self):
        """Test recent mode requires period_days"""
        with pytest.raises(ValueError, match="requires period_days"):
            OperationModeDetector.prepare_api_request(
                ui_selection="recent",
                latitude=-15.7801,
                longitude=-47.9292,
                # Missing period_days
            )

    def test_prepare_with_invalid_dates(self):
        """Test that invalid date ranges raise ValueError"""
        start = date(2023, 1, 1)
        end = date(2023, 5, 1)  # 120 days, exceeds limit

        with pytest.raises(ValueError, match="Invalid dates for mode"):
            OperationModeDetector.prepare_api_request(
                ui_selection="historical",
                latitude=-15.7801,
                longitude=-47.9292,
                start_date=start,
                end_date=end,
                email="user@example.com",
            )


class TestHelperFunctions:
    """Test utility functions"""

    def test_format_date_for_display(self):
        """Test date formatting for UI display"""
        test_date = date(2023, 3, 15)
        formatted = format_date_for_display(test_date)

        assert formatted == "15/03/2023"

    def test_parse_date_from_ui_iso(self):
        """Test parsing ISO format dates"""
        date_str = "2023-03-15"
        parsed = parse_date_from_ui(date_str)

        assert parsed == date(2023, 3, 15)

    def test_parse_date_from_ui_brazilian(self):
        """Test parsing Brazilian format dates"""
        date_str = "15/03/2023"
        parsed = parse_date_from_ui(date_str)

        assert parsed == date(2023, 3, 15)

    def test_parse_date_from_ui_invalid(self):
        """Test parsing invalid date format raises ValueError"""
        with pytest.raises(ValueError, match="Unable to parse date"):
            parse_date_from_ui("invalid_date")


class TestModeInfo:
    """Test mode information retrieval"""

    def test_get_mode_info_historical(self):
        """Test retrieving historical mode configuration"""
        info = OperationModeDetector.get_mode_info("HISTORICAL_EMAIL")

        assert info["requires_email"] is True
        assert info["min_period"] == 1
        assert info["max_period"] == 90

    def test_get_available_sources_historical(self):
        """Test retrieving available sources for historical mode"""
        sources = OperationModeDetector.get_available_sources(
            "HISTORICAL_EMAIL"
        )

        assert "nasa_power" in sources
        assert "openmeteo_archive" in sources

    def test_get_available_sources_forecast(self):
        """Test retrieving available sources for forecast mode"""
        sources = OperationModeDetector.get_available_sources(
            "DASHBOARD_FORECAST"
        )

        assert "openmeteo_forecast" in sources
        assert "met_norway" in sources
        assert "nws_forecast" in sources


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
