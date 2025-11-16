"""
Shared fixtures and configuration for backend tests.

This module contains pytest fixtures that can be used across all test modules
in the backend test suite.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

# Add backend to Python path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))


@pytest.fixture(scope="session")
def sample_coordinates():
    """Session-scoped fixture providing sample coordinates for testing."""
    return {
        "jaú_sp": (-22.2964, -48.5578),
        "são_paulo_sp": (-23.5505, -46.6333),
        "rio_de_janeiro_rj": (-22.9068, -43.1729),
        "brasília_df": (-15.7942, -47.8822),
    }


@pytest.fixture(scope="session")
def sample_date_ranges():
    """Session-scoped fixture providing common date ranges for testing."""
    today = datetime.now()
    return {
        "today": (today, today + timedelta(days=1)),
        "yesterday": (today - timedelta(days=1), today),
        "last_week": (today - timedelta(days=7), today),
        "last_month": (today - timedelta(days=30), today),
        "forecast_range": (
            today - timedelta(days=2),
            today + timedelta(days=5),
        ),
    }


@pytest.fixture
def mock_api_response_success(sample_date_ranges):
    """Fixture providing a successful API response with dynamic dates."""
    # Use dates from the forecast_range fixture
    start, end = sample_date_ranges["forecast_range"]

    # Generate hourly timestamps within the range
    timestamps = []
    current = start
    while current <= end:
        timestamps.append(current.strftime("%Y-%m-%dT%H:%M:%S"))
        current += timedelta(hours=1)
        if len(timestamps) >= 4:  # Limit to 4 timestamps for test
            break

    return {
        "latitude": -22.2964,
        "longitude": -48.5578,
        "generationtime_ms": 0.5,
        "utc_offset_seconds": -10800,  # BRT
        "timezone": "America/Sao_Paulo",
        "timezone_abbreviation": "BRT",
        "hourly": {
            "time": timestamps,
            "temperature_2m": [20.5, 19.8, 18.9, 18.2],
            "relative_humidity_2m": [65, 70, 75, 80],
            "et0_fao_evapotranspiration": [0.15, 0.12, 0.08, 0.05],
            "wind_speed_10m": [15.2, 12.8, 18.5, 14.3],
            "shortwave_radiation": [0, 0, 120, 250],
            "precipitation_probability": [10, 15, 20, 25],
        },
    }


@pytest.fixture
def mock_api_response_incomplete(sample_date_ranges):
    """Fixture providing an API response with missing fields and dynamic dates."""
    # Use dates from the forecast_range fixture
    start, _ = sample_date_ranges["forecast_range"]

    return {
        "hourly": {
            "time": [start.strftime("%Y-%m-%dT%H:%M:%S")],
            "temperature_2m": [20.5],
            # Missing other required fields
        }
    }


@pytest.fixture
def mock_api_response_empty():
    """Fixture providing an empty API response."""
    return {}


@pytest.fixture
def mock_redis_client():
    """Fixture providing a mock Redis client."""
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_client.get.return_value = None
    mock_client.setex.return_value = True
    return mock_client


@pytest.fixture
def sample_dataframe():
    """Fixture providing a sample DataFrame similar to API output."""
    dates = pd.date_range("2025-09-01", periods=4, freq="H")
    return pd.DataFrame(
        {
            "T2M": [20.5, 19.8, 18.9, 18.2],
            "RH2M": [65, 70, 75, 80],
            "ETO": [0.15, 0.12, 0.08, 0.05],
            "WS2M": [54.7, 46.1, 66.6, 51.5],  # Already converted to km/h
            "ALLSKY_SFC_SW_DWN": [0, 0, 120, 250],
            "PRECIP_PROB": [10, 15, 20, 25],
        },
        index=dates,
    )


# @pytest.fixture
# def api_client_factory(sample_coordinates, sample_date_ranges):
#     """Factory fixture for creating API clients - DISABLED (OpenMeteoForecastAPI removed)."""
#     pass


@pytest.fixture(autouse=True)
def disable_network_calls(monkeypatch):
    """Automatically disable network calls for all tests."""

    def mock_get(*args, **kwargs):
        msg = "Network call not mocked! Use @patch or fixtures."
        raise RuntimeError(msg)

    monkeypatch.setattr("requests.get", mock_get)


# Test configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "api: API related tests")


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location and naming."""
    for item in items:
        # Mark API tests
        if "api" in item.nodeid.lower():
            item.add_marker(pytest.mark.api)

        # Mark integration tests
        if "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.integration)

        # Mark slow tests
        if "slow" in item.keywords or "performance" in item.nodeid.lower():
            item.add_marker(pytest.mark.slow)
