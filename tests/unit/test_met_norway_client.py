"""
Testes unitários para MET Norway Client.

Testes com mocks respx para httpx:
- Limite de 5 dias de forecast
- Validações regionais (Nordic, Brazil, USA, Global)
- Agregações diárias de dados horários
- Cache e tratamento de erros
- Rate limiting e retries
"""

import pytest
import respx
from datetime import datetime, timedelta
from httpx import Response

from backend.api.services.met_norway.met_norway_client import (
    METNorwayClient,
    METNorwayConfig,
)
from backend.api.services.geographic_utils import GeographicUtils


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def met_config():
    """Config padrão do MET Norway."""
    return METNorwayConfig(
        timeout=10,
        retry_attempts=2,
        retry_delay=0.1,  # Rápido para testes
    )


@pytest.fixture
def met_client(met_config):
    """Cliente MET Norway para testes."""
    return METNorwayClient(config=met_config)


@pytest.fixture
def mock_hourly_response():
    """Mock de resposta horária da API MET Norway."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [10.7522, 59.9139, 0]},
        "properties": {
            "meta": {
                "updated_at": "2025-01-15T00:00:00Z",
                "units": {
                    "air_temperature": "celsius",
                    "precipitation_amount": "mm",
                    "relative_humidity": "percent",
                    "wind_speed": "m/s",
                },
            },
            "timeseries": [
                {
                    "time": "2025-01-15T00:00:00Z",
                    "data": {
                        "instant": {
                            "details": {
                                "air_temperature": 5.0,
                                "relative_humidity": 80.0,
                                "wind_speed": 3.5,
                                "wind_from_direction": 180.0,
                            }
                        },
                        "next_1_hours": {
                            "summary": {"symbol_code": "cloudy"},
                            "details": {"precipitation_amount": 0.5},
                        },
                    },
                },
                {
                    "time": "2025-01-15T01:00:00Z",
                    "data": {
                        "instant": {
                            "details": {
                                "air_temperature": 4.8,
                                "relative_humidity": 82.0,
                                "wind_speed": 3.2,
                                "wind_from_direction": 185.0,
                            }
                        },
                        "next_1_hours": {
                            "summary": {"symbol_code": "cloudy"},
                            "details": {"precipitation_amount": 0.3},
                        },
                    },
                },
                # ... (mais 22 horas para completar 24h)
            ],
        },
    }


# ============================================================================
# TESTES DE VALIDAÇÃO DE COORDENADAS
# ============================================================================


@pytest.mark.asyncio
async def test_invalid_coordinates(met_client):
    """Testa rejeição de coordenadas inválidas."""
    invalid_coords = [
        (91.0, 0.0),  # Latitude > 90
        (-91.0, 0.0),  # Latitude < -90
        (0.0, 181.0),  # Longitude > 180
        (0.0, -181.0),  # Longitude < -180
    ]

    for lat, lon in invalid_coords:
        with pytest.raises(ValueError, match="Coordenadas inválidas"):
            await met_client.get_daily_forecast(
                lat=lat,
                lon=lon,
                start_date=datetime.now(),
                end_date=datetime.now() + timedelta(days=1),
            )


# ============================================================================
# TESTES DE LIMITE DE FORECAST (5 DIAS)
# ============================================================================


@pytest.mark.asyncio
async def test_5_day_forecast_limit(met_client):
    """Testa enforcement do limite de 5 dias."""
    start_date = datetime.now()

    # Teste 1: Requisição de 10 dias deve ser truncada para 5
    end_date_10_days = start_date + timedelta(days=10)

    with respx.mock:
        # Mock da API retornando 5 dias
        respx.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact"
        ).mock(
            return_value=Response(
                200,
                json={
                    "properties": {
                        "timeseries": [
                            {
                                "time": (
                                    start_date + timedelta(days=i)
                                ).isoformat()
                                + "Z",
                                "data": {
                                    "instant": {
                                        "details": {
                                            "air_temperature": 10.0,
                                            "relative_humidity": 70.0,
                                            "wind_speed": 2.0,
                                        }
                                    }
                                },
                            }
                            for i in range(5 * 24)  # 5 dias × 24 horas
                        ]
                    }
                },
            )
        )

        data = await met_client.get_daily_forecast(
            lat=59.9139,
            lon=10.7522,
            start_date=start_date,
            end_date=end_date_10_days,
        )

        # Deve retornar no máximo 5 dias
        assert len(data) <= 5, f"Retornou {len(data)} dias, máximo é 5"

    # Teste 2: Requisição de 3 dias deve retornar 3 dias
    end_date_3_days = start_date + timedelta(days=3)

    with respx.mock:
        respx.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact"
        ).mock(
            return_value=Response(
                200,
                json={
                    "properties": {
                        "timeseries": [
                            {
                                "time": (
                                    start_date + timedelta(days=i)
                                ).isoformat()
                                + "Z",
                                "data": {
                                    "instant": {
                                        "details": {
                                            "air_temperature": 10.0,
                                            "relative_humidity": 70.0,
                                            "wind_speed": 2.0,
                                        }
                                    }
                                },
                            }
                            for i in range(3 * 24)  # 3 dias × 24 horas
                        ]
                    }
                },
            )
        )

        data = await met_client.get_daily_forecast(
            lat=59.9139,
            lon=10.7522,
            start_date=start_date,
            end_date=end_date_3_days,
        )

        assert len(data) <= 3


# ============================================================================
# TESTES DE DETECÇÃO REGIONAL
# ============================================================================


@pytest.mark.asyncio
async def test_regional_detection():
    """Testa detecção de região com get_region."""
    # Nordic Region (Oslo)
    assert GeographicUtils.get_region(59.9139, 10.7522) == "nordic"

    # Brazil Region (Brasília)
    assert GeographicUtils.get_region(-15.7939, -47.8828) == "brazil"

    # USA Region (New York)
    assert GeographicUtils.get_region(40.7128, -74.0060) == "usa"

    # Global Region (Tokyo)
    assert GeographicUtils.get_region(35.6762, 139.6503) == "global"


@pytest.mark.asyncio
async def test_regional_variable_filtering(met_client):
    """Testa filtragem de variáveis por região."""

    # Nordic: Deve incluir precipitation
    nordic_vars = met_client._get_recommended_variables(
        lat=59.9139, lon=10.7522  # Oslo
    )
    assert "precipitation_amount" in nordic_vars

    # Brazil: Não deve incluir precipitation
    brazil_vars = met_client._get_recommended_variables(
        lat=-15.7939, lon=-47.8828  # Brasília
    )
    assert "precipitation_amount" not in brazil_vars

    # Global: Não deve incluir precipitation
    global_vars = met_client._get_recommended_variables(
        lat=35.6762, lon=139.6503  # Tokyo
    )
    assert "precipitation_amount" not in global_vars


# ============================================================================
# TESTES DE AGREGAÇÃO HORÁRIA → DIÁRIA
# ============================================================================


@pytest.mark.asyncio
async def test_hourly_to_daily_aggregation(met_client):
    """Testa agregação de dados horários para diários."""
    start_date = datetime(2025, 1, 15, 0, 0, 0)

    # Mock: 24 horas de dados
    hourly_data = []
    temps = [
        5.0,
        4.5,
        4.0,
        3.5,
        3.0,
        3.5,
        4.0,
        5.0,
        6.0,
        7.0,
        8.0,
        9.0,
        10.0,
        11.0,
        12.0,
        12.5,
        12.0,
        11.0,
        10.0,
        9.0,
        8.0,
        7.0,
        6.0,
        5.5,
    ]

    for hour, temp in enumerate(temps):
        hourly_data.append(
            {
                "time": (start_date + timedelta(hours=hour)).isoformat() + "Z",
                "data": {
                    "instant": {
                        "details": {
                            "air_temperature": temp,
                            "relative_humidity": 75.0,
                            "wind_speed": 2.5,
                        }
                    },
                    "next_1_hours": {"details": {"precipitation_amount": 0.1}},
                },
            }
        )

    with respx.mock:
        respx.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact"
        ).mock(
            return_value=Response(
                200, json={"properties": {"timeseries": hourly_data}}
            )
        )

        daily_data = await met_client.get_daily_forecast(
            lat=59.9139,
            lon=10.7522,
            start_date=start_date,
            end_date=start_date + timedelta(days=1),
        )

        assert len(daily_data) == 1
        day = daily_data[0]

        # Verificar agregações
        assert day.temp_max == max(temps)  # 12.5
        assert day.temp_min == min(temps)  # 3.0
        assert abs(day.temp_mean - sum(temps) / len(temps)) < 0.1
        assert day.precipitation_sum == pytest.approx(0.1 * 24, abs=0.01)


# ============================================================================
# TESTES DE CACHE
# ============================================================================


@pytest.mark.asyncio
async def test_cache_ttl_calculation(met_client):
    """Testa cálculo de TTL baseado em Expires header."""
    from backend.api.services.weather_utils import CacheUtils

    # Teste 1: Expires em 1 hora
    expires_1h = "Thu, 15 Jan 2025 12:00:00 GMT"
    ttl = CacheUtils.calculate_cache_ttl(
        expires_header=expires_1h,
        min_ttl=60,
        max_ttl=86400,
    )
    assert 60 <= ttl <= 86400

    # Teste 2: Expires inválido → default min_ttl
    ttl_invalid = CacheUtils.calculate_cache_ttl(
        expires_header="invalid",
        min_ttl=60,
        max_ttl=86400,
    )
    assert ttl_invalid == 60


# ============================================================================
# TESTES DE RATE LIMITING E RETRIES
# ============================================================================


@pytest.mark.asyncio
async def test_rate_limiting_429(met_client):
    """Testa retry automático em caso de 429 Too Many Requests."""
    call_count = 0

    def handle_request(request):
        nonlocal call_count
        call_count += 1

        if call_count < 2:
            # Primeiras chamadas: 429
            return Response(429, text="Too Many Requests")
        else:
            # Terceira chamada: sucesso
            return Response(
                200,
                json={
                    "properties": {
                        "timeseries": [
                            {
                                "time": "2025-01-15T00:00:00Z",
                                "data": {
                                    "instant": {
                                        "details": {
                                            "air_temperature": 10.0,
                                            "relative_humidity": 70.0,
                                            "wind_speed": 2.0,
                                        }
                                    }
                                },
                            }
                        ]
                    }
                },
            )

    with respx.mock:
        respx.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact"
        ).mock(side_effect=handle_request)

        data = await met_client.get_daily_forecast(
            lat=59.9139,
            lon=10.7522,
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=1),
        )

        # Deve ter feito retry e sucedido
        assert call_count >= 2
        assert len(data) >= 0


# ============================================================================
# TESTES DE HEALTH CHECK
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(met_client):
    """Testa health check com API disponível."""
    with respx.mock:
        respx.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact"
        ).mock(
            return_value=Response(200, json={"properties": {"timeseries": []}})
        )

        is_healthy = await met_client.health_check()
        assert is_healthy is True


@pytest.mark.asyncio
async def test_health_check_failure(met_client):
    """Testa health check com API indisponível."""
    with respx.mock:
        respx.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact"
        ).mock(return_value=Response(500, text="Internal Server Error"))

        is_healthy = await met_client.health_check()
        assert is_healthy is False


# ============================================================================
# TESTES DE ELEVAÇÃO (ALTITUDE)
# ============================================================================


@pytest.mark.asyncio
async def test_altitude_parameter(met_client):
    """Testa passagem de altitude para API."""
    with respx.mock:
        route = respx.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact"
        ).mock(
            return_value=Response(200, json={"properties": {"timeseries": []}})
        )

        await met_client.get_daily_forecast(
            lat=59.9139,
            lon=10.7522,
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=1),
            altitude=500.0,
        )

        # Verificar que altitude foi incluído na query
        assert route.called
        request = route.calls[0].request
        assert "altitude=500" in str(request.url)


# ============================================================================
# TESTES DE VALIDAÇÃO DE DADOS
# ============================================================================


@pytest.mark.asyncio
async def test_temperature_validation():
    """Testa validação de temperatura com limites regionais."""
    from backend.api.services.weather_utils import WeatherValidationUtils

    # Nordic: -50°C a 40°C
    assert (
        WeatherValidationUtils.is_valid_temperature(
            value=5.0, lat=60.0, lon=10.0  # Nordic
        )
        is True
    )

    assert (
        WeatherValidationUtils.is_valid_temperature(
            value=-60.0, lat=60.0, lon=10.0  # Muito frio
        )
        is False
    )

    # Brazil: -10°C a 50°C
    assert (
        WeatherValidationUtils.is_valid_temperature(
            value=35.0, lat=-15.0, lon=-47.0  # Brazil
        )
        is True
    )

    assert (
        WeatherValidationUtils.is_valid_temperature(
            value=-20.0, lat=-15.0, lon=-47.0  # Muito frio para Brasil
        )
        is False
    )


# ============================================================================
# TESTES DE WIND SPEED (FAO-56 CONVERSION)
# ============================================================================


@pytest.mark.asyncio
async def test_wind_speed_fao56_conversion():
    """Testa conversão de vento 10m → 2m (FAO-56)."""
    from backend.api.services.weather_utils import METNorwayAggregationUtils

    # Vento a 10m = 5.0 m/s
    wind_10m = 5.0

    # Conversão FAO-56: u2 = u10 × 4.87 / ln(67.8 × 10 - 5.42)
    wind_2m = METNorwayAggregationUtils._convert_wind_speed_to_2m(wind_10m)

    # Deve ser aproximadamente 3.4 m/s
    assert 3.0 <= wind_2m <= 4.0
    assert wind_2m < wind_10m  # Sempre menor que 10m


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
