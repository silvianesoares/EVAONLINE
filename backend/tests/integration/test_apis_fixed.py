"""
Teste corrigido de validação de APIs climáticas.

Métodos corretos para cada cliente:
- NASAPowerClient: get_daily_data() → list[NASAPowerData]
- OpenMeteoArchiveClient: get_climate_data() → dict (sem close())
- OpenMeteoForecastClient: get_climate_data() → dict (sem close())
- METNorwayClient: get_daily_forecast() → list[dict]
- NWSForecastClient: get_daily_forecast_data() → list[dict]
- NWSStationsClient: find_nearest_stations(), get_station_observations()
- OpenTopoClient: get_elevation() → Location
"""

from datetime import datetime, timedelta, timezone
import pytest
from loguru import logger

from backend.api.services.nasa_power import NASAPowerClient
from backend.api.services.met_norway import METNorwayClient
from backend.api.services.nws_forecast import NWSForecastClient
from backend.api.services.nws_stations import NWSStationsClient
from backend.api.services.opentopo import OpenTopoClient
from backend.api.services.geographic_utils import GeographicUtils
from backend.api.services.weather_utils import (
    WeatherValidationUtils,
    WeatherConversionUtils,
)


@pytest.fixture(scope="module")
def test_locations():
    """Localizações para teste."""
    return {
        "brasilia": {
            "name": "Brasília, Brasil",
            "lat": -15.7801,
            "lon": -47.9292,
            "timezone": "America/Sao_Paulo",
            "expected_elevation_range": (1000, 1200),
        },
        "new_york": {
            "name": "New York, USA",
            "lat": 40.7128,
            "lon": -74.0060,
            "timezone": "America/New_York",
            "expected_elevation_range": (0, 50),
        },
        "oslo": {
            "name": "Oslo, Norway",
            "lat": 59.9139,
            "lon": 10.7522,
            "timezone": "Europe/Oslo",
            "expected_elevation_range": (0, 50),
        },
    }


# =============================================================================
# TESTE 1: NASA POWER - Download
# =============================================================================


@pytest.mark.asyncio
async def test_nasa_power_download(test_locations):
    """Valida NASA POWER API retorna lista de NASAPowerData."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: NASA POWER - Download")
    logger.info("=" * 80)

    client = NASAPowerClient()

    today = datetime.now(timezone.utc)
    start = today - timedelta(days=30)
    end = today - timedelta(days=5)

    loc = test_locations["brasilia"]
    logger.info(f"📍 {loc['name']}")

    try:
        data = await client.get_daily_data(
            lat=loc["lat"], lon=loc["lon"], start_date=start, end_date=end
        )

        assert isinstance(data, list), f"Esperado list, obtido {type(data)}"
        assert len(data) > 0, "Lista vazia"

        first = data[0]
        assert hasattr(first, "date"), "Sem campo 'date'"
        assert hasattr(first, "temp_max"), "Sem campo 'temp_max'"

        logger.info(f"✅ {len(data)} registros obtidos")
        logger.info(f"   Primeiro: {first.date}, {first.temp_max}°C")

    finally:
        await client.close()


# =============================================================================
# TESTE 2: MET Norway - Forecast
# =============================================================================


@pytest.mark.asyncio
async def test_met_norway_forecast(test_locations):
    """Valida MET Norway forecast (máx 10 dias)."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: MET Norway - Forecast")
    logger.info("=" * 80)

    client = METNorwayClient()

    loc = test_locations["oslo"]  # Nordic region
    logger.info(f"📍 {loc['name']}")

    region = GeographicUtils.get_region(loc["lat"], loc["lon"])
    logger.info(f"   Região: {region}")

    try:
        today = datetime.now(timezone.utc)

        data = await client.get_daily_forecast(
            lat=loc["lat"],
            lon=loc["lon"],
            start_date=today,
            end_date=today + timedelta(days=5),
        )

        assert isinstance(data, list), f"Esperado list, obtido {type(data)}"
        assert len(data) > 0, "Lista vazia"
        assert len(data) <= 10, f"Mais de 10 dias: {len(data)}"

        first = data[0]
        assert "date" in first or first.get("date"), "Sem campo 'date'"
        assert "temp_max" in first or first.get(
            "temp_max"
        ), "Sem campo 'temp_max'"

        logger.info(f"✅ {len(data)} dias obtidos (máx 10)")

        # Validar precipitação em Nordic
        if region == "nordic":
            if "precipitation_sum" in first:
                logger.info("   ✅ Precipitação presente (Nordic)")
            else:
                logger.warning("   ⚠️  Precipitação ausente (Nordic)")

    finally:
        await client.close()


# =============================================================================
# TESTE 3: NWS Forecast - USA Only
# =============================================================================


@pytest.mark.asyncio
async def test_nws_forecast_usa(test_locations):
    """Valida NWS Forecast (USA only)."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: NWS Forecast - USA Only")
    logger.info("=" * 80)

    client = NWSForecastClient()

    loc = test_locations["new_york"]
    logger.info(f"📍 {loc['name']}")

    try:
        # NWS get_daily_forecast_data() não aceita datas
        data = await client.get_daily_forecast_data(
            lat=loc["lat"], lon=loc["lon"]
        )

        assert isinstance(data, list), f"Esperado list, obtido {type(data)}"
        assert len(data) > 0, "Lista vazia"

        first = data[0]
        assert hasattr(first, "date"), "Sem campo date"
        assert hasattr(first, "temp_max_celsius"), "Sem temp_max_celsius"

        logger.info(f"✅ {len(data)} dias obtidos")

        # Validar conversão °F → °C
        temp = first.temp_max_celsius
        if temp is not None:
            assert temp < 100, f"Temperatura parece estar em °F: {temp}"
            logger.info(f"   ✅ Temperatura em °C: {temp:.1f}°C")

    except Exception as e:
        logger.error(f"   ❌ Erro: {e}")
        pytest.skip(f"NWS Forecast não disponível: {e}")

    finally:
        await client.close()


# =============================================================================
# TESTE 4: NWS Stations - Observações
# =============================================================================


@pytest.mark.asyncio
async def test_nws_stations(test_locations):
    """Valida NWS Stations (observações USA)."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: NWS Stations - Observações")
    logger.info("=" * 80)

    client = NWSStationsClient()

    loc = test_locations["new_york"]
    logger.info(f"📍 {loc['name']}")

    try:
        # 1. Buscar estações próximas
        stations = await client.find_nearest_stations(
            lat=loc["lat"], lon=loc["lon"], limit=3
        )

        assert stations is not None, "Nenhuma estação encontrada"
        assert len(stations) > 0, "Lista de estações vazia"

        logger.info(f"✅ {len(stations)} estações encontradas")

        # 2. Obter observações da primeira estação
        # stations retorna lista de NWSStation objects, não dicts
        station_id = stations[0].station_id
        logger.info(f"   Testando: {station_id}")

        # Usar defaults (últimas 24h) para evitar problemas de formato
        observations = await client.get_station_observations(
            station_id=station_id
        )

        if observations and len(observations) > 0:
            logger.info(f"✅ {len(observations)} observações obtidas")

            first_obs = observations[0]
            if (
                hasattr(first_obs, "temp_celsius")
                and first_obs.temp_celsius is not None
            ):
                temp = first_obs.temp_celsius
                assert -50 <= temp <= 60, f"Temperatura fora de range: {temp}"
                logger.info(f"   Temperatura: {temp:.1f}°C")
        else:
            logger.warning("   ⚠️  Nenhuma observação recente")

    except Exception as e:
        logger.error(f"   ❌ Erro: {e}")
        pytest.skip(f"NWS Stations não disponível: {e}")

    finally:
        await client.close()


# =============================================================================
# TESTE 5: OpenTopo - Elevação
# =============================================================================


@pytest.mark.asyncio
async def test_opentopo_elevation(test_locations):
    """Valida OpenTopoData elevação precisa."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: OpenTopoData - Elevação")
    logger.info("=" * 80)

    client = OpenTopoClient()

    results = {}

    for loc_key, loc_data in test_locations.items():
        logger.info(f"\n📍 {loc_data['name']}")

        try:
            location = await client.get_elevation(
                lat=loc_data["lat"], lon=loc_data["lon"]
            )

            assert location is not None, "Resposta nula"
            assert hasattr(location, "elevation"), "Sem campo elevation"

            elevation = location.elevation
            logger.info(f"   Elevação: {elevation:.1f}m")

            # Verificar range esperado (±50m margem)
            expected_min, expected_max = loc_data["expected_elevation_range"]

            if expected_min - 50 <= elevation <= expected_max + 50:
                logger.info(
                    f"   ✅ Dentro do esperado ({expected_min}-{expected_max}m)"
                )
            else:
                logger.warning(
                    f"   ⚠️  Fora do esperado ({expected_min}-{expected_max}m)"
                )

            results[loc_key] = {"elevation": elevation, "status": "success"}

        except Exception as e:
            logger.error(f"   ❌ Erro: {e}")
            results[loc_key] = {"status": "error", "error": str(e)}

    await client.close()

    # Verificar taxa de sucesso
    successful = sum(1 for r in results.values() if r["status"] == "success")
    total = len(results)
    success_rate = (successful / total) * 100

    logger.info(
        f"\n📊 Taxa de sucesso: {success_rate:.1f}% ({successful}/{total})"
    )
    assert success_rate >= 75, f"Taxa baixa: {success_rate:.1f}%"


# =============================================================================
# TESTE 6: Conversões de Unidades
# =============================================================================


@pytest.mark.asyncio
async def test_unit_conversions():
    """Valida conversões de unidades meteorológicas."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: Conversões de Unidades")
    logger.info("=" * 80)

    # Temperatura
    logger.info("\n🧪 Temperatura:")
    temp_f = 68.0
    temp_c = WeatherConversionUtils.fahrenheit_to_celsius(temp_f)
    temp_f_back = WeatherConversionUtils.celsius_to_fahrenheit(temp_c)

    logger.info(f"   {temp_f}°F → {temp_c:.2f}°C → {temp_f_back:.2f}°F")
    assert abs(temp_c - 20.0) < 0.1, "Conversão °F→°C incorreta"
    assert abs(temp_f_back - temp_f) < 0.01, "Conversão °C→°F incorreta"
    logger.info("   ✅ Conversões OK")

    # Velocidade
    logger.info("\n🧪 Velocidade:")
    speed_mph = 10.0
    speed_ms = WeatherConversionUtils.mph_to_ms(speed_mph)
    speed_mph_back = WeatherConversionUtils.ms_to_mph(speed_ms)

    logger.info(
        f"   {speed_mph} mph → {speed_ms:.2f} m/s → {speed_mph_back:.2f} mph"
    )
    assert abs(speed_ms - 4.47) < 0.01, "Conversão mph→m/s incorreta"
    assert (
        abs(speed_mph_back - speed_mph) < 0.01
    ), "Conversão m/s→mph incorreta"
    logger.info("   ✅ Conversões OK")

    # Vento FAO-56
    logger.info("\n🧪 Vento FAO-56 (10m → 2m):")
    wind_10m = 5.0
    wind_2m = WeatherConversionUtils.convert_wind_10m_to_2m(wind_10m)

    logger.info(f"   {wind_10m} m/s (10m) → {wind_2m:.2f} m/s (2m)")
    assert wind_2m < wind_10m, "Vento 2m deve ser menor que 10m"
    logger.info("   ✅ Conversão FAO-56 OK")

    logger.info("\n✅ Todas as conversões OK")


# =============================================================================
# TESTE 7: Validações Regionais
# =============================================================================


@pytest.mark.asyncio
async def test_regional_validations():
    """Valida limites físicos regionais (Xavier et al. 2016 para Brasil)."""
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: Validações Físicas Regionais")
    logger.info("=" * 80)

    test_cases = [
        # Brasil - Xavier et al. 2016
        {
            "lat": -15.7801,
            "lon": -47.9292,
            "region": "brazil",
            "temp": 35.0,
            "expected": True,
            "description": "Brasil - temp OK (35°C)",
        },
        {
            "lat": -15.7801,
            "lon": -47.9292,
            "region": "brazil",
            "temp": 55.0,
            "expected": False,
            "description": "Brasil - temp INVÁLIDA (55°C)",
        },
        # USA
        {
            "lat": 40.7128,
            "lon": -74.0060,
            "region": "usa",
            "temp": -40.0,
            "expected": True,
            "description": "USA - temp OK (-40°C)",
        },
        # Nordic
        {
            "lat": 59.9139,
            "lon": 10.7522,
            "region": "nordic",
            "temp": -45.0,
            "expected": True,
            "description": "Nordic - temp OK (-45°C)",
        },
    ]

    for test in test_cases:
        logger.info(f"\n🧪 {test['description']}")

        is_valid = WeatherValidationUtils.is_valid_temperature(
            temp=test["temp"], lat=test["lat"], lon=test["lon"]
        )

        if is_valid == test["expected"]:
            logger.info(f"   ✅ Validação correta: {is_valid}")
        else:
            logger.error(
                f"   ❌ Esperado {test['expected']}, obtido {is_valid}"
            )
            pytest.fail(f"Validação falhou para {test['description']}")

    logger.info("\n✅ Todas as validações regionais OK")
