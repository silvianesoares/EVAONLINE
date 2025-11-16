"""
Integration tests for data_download.py.

Tests the main download_weather_data function that coordinates
all climate APIs, validating source selection, data fusion,
and multi-location support.

This tests the complete workflow from user request to final DataFrame.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta

from backend.api.services.data_download import (
    download_weather_data,
)


TEST_LOCATIONS = {
    "brazil": {"lat": -15.7939, "lon": -47.8828, "name": "Brasília"},
    "usa": {"lat": 40.7128, "lon": -74.0060, "name": "New York"},
    "europe": {"lat": 52.5200, "lon": 13.4050, "name": "Berlin"},
    "asia": {"lat": 35.6762, "lon": 139.6503, "name": "Tokyo"},
}


class TestDataDownloadBasic:
    """Test basic download_weather_data functionality."""

    def test_download_nasa_power(self):
        """Test downloading from NASA POWER (global source)."""
        location = TEST_LOCATIONS["brazil"]

        # Recent period (avoiding NASA delay)
        end_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")

        print(f"\n🌍 Testing NASA POWER for {location['name']}")

        df, warnings = download_weather_data(
            data_source="nasa_power",
            data_inicial=start_date,
            data_final=end_date,
            longitude=location["lon"],
            latitude=location["lat"],
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 5, f"Expected >= 5 days, got {len(df)}"
        assert isinstance(warnings, list)

        print(f"   ✅ Downloaded {len(df)} days")
        print(f"   Variables: {list(df.columns)}")

    def test_download_openmeteo_archive(self):
        """Test downloading from Open-Meteo Archive."""
        location = TEST_LOCATIONS["europe"]

        start_date = "2023-06-01"
        end_date = "2023-06-07"

        print(f"\n🌍 Testing Open-Meteo Archive for {location['name']}")

        df, warnings = download_weather_data(
            data_source="openmeteo_archive",
            data_inicial=start_date,
            data_final=end_date,
            longitude=location["lon"],
            latitude=location["lat"],
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 6
        print(f"   ✅ Downloaded {len(df)} days")

    def test_download_openmeteo_forecast(self):
        """Test downloading from Open-Meteo Forecast."""
        location = TEST_LOCATIONS["asia"]

        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")

        print(f"\n🌍 Testing Open-Meteo Forecast for {location['name']}")

        df, warnings = download_weather_data(
            data_source="openmeteo_forecast",
            data_inicial=start_date,
            data_final=end_date,
            longitude=location["lon"],
            latitude=location["lat"],
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        print(f"   ✅ Downloaded {len(df)} forecast days")


class TestDataDownloadUSAOnly:
    """Test USA-specific sources."""

    def test_download_nws_forecast(self):
        """Test NWS Forecast (USA only)."""
        location = TEST_LOCATIONS["usa"]

        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

        print(f"\n🇺🇸 Testing NWS Forecast for {location['name']}")

        df, warnings = download_weather_data(
            data_source="nws_forecast",
            data_inicial=start_date,
            data_final=end_date,
            longitude=location["lon"],
            latitude=location["lat"],
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        print(f"   ✅ NWS Forecast: {len(df)} days")

    def test_download_nws_stations(self):
        """Test NWS Stations (USA only)."""
        location = TEST_LOCATIONS["usa"]

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

        print(f"\n🇺🇸 Testing NWS Stations for {location['name']}")

        df, warnings = download_weather_data(
            data_source="nws_stations",
            data_inicial=start_date,
            data_final=end_date,
            longitude=location["lon"],
            latitude=location["lat"],
        )

        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        print(f"   ✅ NWS Stations: {len(df)} days")

    def test_nws_rejected_outside_usa(self):
        """Test that NWS sources reject non-USA locations."""
        location = TEST_LOCATIONS["brazil"]

        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        print(f"\n⚠️  Testing NWS with non-USA location: {location['name']}")

        with pytest.raises(ValueError, match="disponível|coverage|USA"):
            download_weather_data(
                data_source="nws_forecast",
                data_inicial=start_date,
                data_final=end_date,
                longitude=location["lon"],
                latitude=location["lat"],
            )

        print("   ✅ Correctly rejected non-USA location")


class TestDataDownloadValidation:
    """Test input validation."""

    def test_invalid_source(self):
        """Test that invalid source names are rejected."""
        location = TEST_LOCATIONS["brazil"]

        print("\n⚠️  Testing invalid source name")

        with pytest.raises(ValueError, match="Fonte inválida"):
            download_weather_data(
                data_source="invalid_source",
                data_inicial="2024-01-01",
                data_final="2024-01-07",
                longitude=location["lon"],
                latitude=location["lat"],
            )

        print("   ✅ Invalid source rejected")

    def test_invalid_coordinates(self):
        """Test that invalid coordinates are rejected."""
        print("\n⚠️  Testing invalid coordinates")

        with pytest.raises(ValueError, match="Latitude|Longitude"):
            download_weather_data(
                data_source="nasa_power",
                data_inicial="2024-01-01",
                data_final="2024-01-07",
                longitude=200,  # Invalid longitude
                latitude=40,
            )

        print("   ✅ Invalid coordinates rejected")

    def test_invalid_date_format(self):
        """Test that invalid date formats are rejected."""
        location = TEST_LOCATIONS["brazil"]

        print("\n⚠️  Testing invalid date format")

        with pytest.raises(ValueError, match="formato|AAAA-MM-DD"):
            download_weather_data(
                data_source="nasa_power",
                data_inicial="01/01/2024",  # Wrong format
                data_final="2024-01-07",
                longitude=location["lon"],
                latitude=location["lat"],
            )

        print("   ✅ Invalid date format rejected")

    def test_end_before_start(self):
        """Test that end date before start date is rejected."""
        location = TEST_LOCATIONS["brazil"]

        print("\n⚠️  Testing end date before start date")

        with pytest.raises(ValueError, match="posterior"):
            download_weather_data(
                data_source="nasa_power",
                data_inicial="2024-01-07",
                data_final="2024-01-01",  # Before start
                longitude=location["lon"],
                latitude=location["lat"],
            )

        print("   ✅ Invalid date order rejected")


class TestDataDownloadMultiLocation:
    """Test downloads across different geographic locations."""

    @pytest.mark.parametrize("location_key", list(TEST_LOCATIONS.keys()))
    def test_nasa_power_all_locations(self, location_key):
        """Test NASA POWER works for all global locations."""
        location = TEST_LOCATIONS[location_key]

        end_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        print(f"\n🌍 Testing {location['name']} with NASA POWER")

        df, warnings = download_weather_data(
            data_source="nasa_power",
            data_inicial=start_date,
            data_final=end_date,
            longitude=location["lon"],
            latitude=location["lat"],
        )

        assert len(df) >= 2
        print(f"   ✅ {location['name']}: {len(df)} days")

    @pytest.mark.parametrize("location_key", list(TEST_LOCATIONS.keys()))
    def test_openmeteo_all_locations(self, location_key):
        """Test Open-Meteo Archive works for all locations."""
        location = TEST_LOCATIONS[location_key]

        start_date = "2023-06-01"
        end_date = "2023-06-03"

        print(f"\n🌍 Testing {location['name']} with Open-Meteo")

        df, warnings = download_weather_data(
            data_source="openmeteo_archive",
            data_inicial=start_date,
            data_final=end_date,
            longitude=location["lon"],
            latitude=location["lat"],
        )

        assert len(df) >= 2
        print(f"   ✅ {location['name']}: {len(df)} days")


class TestDataDownloadDateRanges:
    """Test different date ranges."""

    def test_single_day(self):
        """Test downloading single day."""
        location = TEST_LOCATIONS["brazil"]

        target_date = (datetime.now() - timedelta(days=10)).strftime(
            "%Y-%m-%d"
        )

        print(f"\n📅 Testing single day download: {target_date}")

        df, warnings = download_weather_data(
            data_source="nasa_power",
            data_inicial=target_date,
            data_final=target_date,
            longitude=location["lon"],
            latitude=location["lat"],
        )

        assert len(df) == 1
        print("   ✅ Single day downloaded")

    def test_one_month(self):
        """Test downloading one month of data."""
        location = TEST_LOCATIONS["europe"]

        start_date = "2023-06-01"
        end_date = "2023-06-30"

        print("\n📅 Testing one month download (June 2023)")

        df, warnings = download_weather_data(
            data_source="openmeteo_archive",
            data_inicial=start_date,
            data_final=end_date,
            longitude=location["lon"],
            latitude=location["lat"],
        )

        assert len(df) == 30
        print(f"   ✅ One month: {len(df)} days")

    def test_one_year(self):
        """Test downloading one full year."""
        location = TEST_LOCATIONS["asia"]

        start_date = "2020-01-01"
        end_date = "2020-12-31"

        print("\n📅 Testing one year download (2020)")

        df, warnings = download_weather_data(
            data_source="openmeteo_archive",
            data_inicial=start_date,
            data_final=end_date,
            longitude=location["lon"],
            latitude=location["lat"],
        )

        # 2020 is leap year
        assert len(df) == 366
        print(f"   ✅ Full year: {len(df)} days")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
