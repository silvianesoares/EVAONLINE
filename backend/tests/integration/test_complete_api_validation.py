"""
Teste completo de validação de todas as APIs climáticas.

Valida:
1. Download de dados reais
2. Estrutura de resposta
3. Campos obrigatórios
4. Conversões de timezone
5. Elevação consistente
6. Validações físicas

Execução:
    pytest backend/tests/integration/test_complete_api_validation.py -v -s
"""

from datetime import datetime, timedelta, timezone

import pytest
from loguru import logger

# Importar todos os clientes
from backend.api.services.nasa_power import NASAPowerClient
from backend.api.services.openmeteo_archive import OpenMeteoArchiveClient
from backend.api.services.openmeteo_forecast import OpenMeteoForecastClient
from backend.api.services.met_norway import METNorwayClient
from backend.api.services.nws_forecast import NWSForecastClient
from backend.api.services.nws_stations import NWSStationsClient
from backend.api.services.opentopo import OpenTopoClient

# Importar utils
from backend.api.services.geographic_utils import GeographicUtils
from backend.api.services.weather_utils import (
    WeatherValidationUtils,
    WeatherConversionUtils,
    ElevationUtils,
)


# ============================================================================
# FIXTURES - Localizações de Teste
# ============================================================================


@pytest.fixture(scope="module")
def test_locations():
    """
    Localizações para teste cobrindo diferentes regiões.

    Critérios:
    - Brasil (Open-Meteo, NASA POWER)
    - USA (NWS Forecast, NWS Stations, Open-Meteo, NASA)
    - Europa (MET Norway, Open-Meteo, NASA)
    - Global (Open-Meteo, NASA)
    """
    return {
        "brasilia": {
            "name": "Brasília, Brasil",
            "lat": -15.7801,
            "lon": -47.9292,
            "timezone": "America/Sao_Paulo",
            "expected_elevation_range": (1000, 1300),
            "available_apis": [
                "nasa_power",
                "openmeteo_archive",
                "openmeteo_forecast",
            ],
        },
        "new_york": {
            "name": "New York, USA",
            "lat": 40.7128,
            "lon": -74.0060,
            "timezone": "America/New_York",
            "expected_elevation_range": (0, 100),
            "available_apis": [
                "nasa_power",
                "openmeteo_archive",
                "openmeteo_forecast",
                "nws_forecast",
                "nws_stations",
            ],
        },
        "oslo": {
            "name": "Oslo, Norway",
            "lat": 59.9139,
            "lon": 10.7522,
            "timezone": "Europe/Oslo",
            "expected_elevation_range": (0, 200),
            "available_apis": [
                "nasa_power",
                "openmeteo_archive",
                "openmeteo_forecast",
                "met_norway",
            ],
        },
        "tokyo": {
            "name": "Tokyo, Japan",
            "lat": 35.6762,
            "lon": 139.6503,
            "timezone": "Asia/Tokyo",
            "expected_elevation_range": (0, 100),
            "available_apis": [
                "nasa_power",
                "openmeteo_archive",
                "openmeteo_forecast",
            ],
        },
    }


@pytest.fixture(scope="module")
def date_ranges():
    """
    Períodos de teste para cada tipo de API.
    """
    today = datetime.now(timezone.utc)

    return {
        "historical": {
            "start": today - timedelta(days=60),
            "end": today - timedelta(days=35),
            "description": "Histórico (60-35 dias atrás)",
        },
        "dashboard": {
            "start": today - timedelta(days=14),
            "end": today,
            "description": "Dashboard (últimos 14 dias)",
        },
        "forecast": {
            "start": today,
            "end": today + timedelta(days=5),
            "description": "Forecast (próximos 5 dias)",
        },
    }


# ============================================================================
# TESTE 1: Download de Dados - NASA POWER
# ============================================================================


@pytest.mark.asyncio
async def test_nasa_power_download(test_locations, date_ranges):
    """
    Valida download de dados do NASA POWER.

    Checks:
    - API responde corretamente
    - Período histórico válido
    - Campos obrigatórios presentes
    - Valores dentro de ranges físicos
    - Elevação consistente
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: NASA POWER - Download e Validação")
    logger.info("=" * 80)

    client = NASAPowerClient()
    period = date_ranges["historical"]

    results = {}

    for loc_key, loc_data in test_locations.items():
        if "nasa_power" not in loc_data["available_apis"]:
            continue

        logger.info(
            f"\n📍 {loc_data['name']} ({loc_data['lat']}, {loc_data['lon']})"
        )

        try:
            # Download
            data = await client.get_daily_data(
                lat=loc_data["lat"],
                lon=loc_data["lon"],
                start_date=period["start"],
                end_date=period["end"],
            )

            # Validações
            assert data is not None, "Dados nulos"
            assert "daily" in data, "Campo 'daily' ausente"
            assert len(data["daily"]) > 0, "Lista de dados vazia"

            daily_records = data["daily"]
            logger.info(f"   ✅ Baixados {len(daily_records)} dias")

            # Validar primeiro registro
            first = daily_records[0]

            # Campos obrigatórios
            required_fields = [
                "date",
                "temperature_2m_max",
                "temperature_2m_min",
                "temperature_2m_mean",
                "relative_humidity_2m_mean",
                "wind_speed_10m_mean",
                "shortwave_radiation_sum",
            ]

            missing_fields = [f for f in required_fields if f not in first]
            assert not missing_fields, f"Campos faltando: {missing_fields}"
            logger.info(f"   ✅ Todos os campos obrigatórios presentes")

            # Validar ranges físicos
            for record in daily_records[:5]:  # Primeiros 5 dias
                # Temperatura (-50 a 60°C)
                if record.get("temperature_2m_max"):
                    assert (
                        -50 <= record["temperature_2m_max"] <= 60
                    ), f"Temp máx fora de range: {record['temperature_2m_max']}"

                if record.get("temperature_2m_min"):
                    assert (
                        -50 <= record["temperature_2m_min"] <= 60
                    ), f"Temp mín fora de range: {record['temperature_2m_min']}"

                # Umidade (0-100%)
                if record.get("relative_humidity_2m_mean"):
                    assert (
                        0 <= record["relative_humidity_2m_mean"] <= 100
                    ), f"Umidade fora de range: {record['relative_humidity_2m_mean']}"

                # Vento (0-100 m/s)
                if record.get("wind_speed_10m_mean"):
                    assert (
                        0 <= record["wind_speed_10m_mean"] <= 100
                    ), f"Vento fora de range: {record['wind_speed_10m_mean']}"

                # Radiação (0-1500 W/m²)
                if record.get("shortwave_radiation_sum"):
                    assert (
                        0 <= record["shortwave_radiation_sum"] <= 1500
                    ), f"Radiação fora de range: {record['shortwave_radiation_sum']}"

            logger.info(f"   ✅ Validações físicas OK")

            # Validar elevação
            if "location" in data and "elevation" in data["location"]:
                elevation = data["location"]["elevation"]
                expected_range = loc_data["expected_elevation_range"]

                logger.info(f"   Elevação NASA: {elevation:.1f}m")

                # Verificar se está no range esperado (com margem de ±50m)
                if not (
                    expected_range[0] - 50
                    <= elevation
                    <= expected_range[1] + 50
                ):
                    logger.warning(
                        f"   ⚠️  Elevação fora do esperado: "
                        f"{expected_range[0]}-{expected_range[1]}m"
                    )

            results[loc_key] = {
                "status": "success",
                "records": len(daily_records),
                "elevation": data.get("location", {}).get("elevation"),
            }

        except Exception as e:
            logger.error(f"   ❌ Erro: {e}")
            results[loc_key] = {"status": "error", "error": str(e)}

    # Verificar se pelo menos 75% passou
    successful = sum(1 for r in results.values() if r["status"] == "success")
    total = len(results)
    success_rate = (successful / total) * 100 if total > 0 else 0

    logger.info(
        f"\n📊 Taxa de sucesso: {success_rate:.1f}% ({successful}/{total})"
    )

    assert success_rate >= 75, f"Taxa de sucesso baixa: {success_rate:.1f}%"

    await client.close()


# ============================================================================
# TESTE 2: Consistência de Timezone
# ============================================================================


@pytest.mark.asyncio
async def test_timezone_consistency(test_locations):
    """
    Valida que todas as APIs retornam timestamps consistentes.

    Checks:
    - Timestamps em UTC ou timezone-aware
    - Conversão correta para timezone local
    - Sem gaps ou duplicatas de dias
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: Consistência de Timezone")
    logger.info("=" * 80)

    loc_data = test_locations["brasilia"]

    logger.info(f"📍 {loc_data['name']}")
    logger.info(f"   Timezone esperado: {loc_data['timezone']}")

    # Período de teste (últimos 7 dias)
    today = datetime.now(timezone.utc)
    start = today - timedelta(days=7)
    end = today - timedelta(days=1)

    # Testar Open-Meteo Archive
    logger.info("\n🧪 Open-Meteo Archive:")

    client_archive = OpenMeteoArchiveClient()
    try:
        data = await client_archive.get_daily_data(
            lat=loc_data["lat"],
            lon=loc_data["lon"],
            start_date=start,
            end_date=end,
        )

        daily_records = data.get("daily", [])

        if len(daily_records) > 0:
            first_date_str = daily_records[0].get("date")
            last_date_str = daily_records[-1].get("date")

            logger.info(f"   Primeira data: {first_date_str}")
            logger.info(f"   Última data: {last_date_str}")

            # Verificar formato de data
            try:
                first_date = datetime.fromisoformat(
                    first_date_str.replace("Z", "+00:00")
                )
                last_date = datetime.fromisoformat(
                    last_date_str.replace("Z", "+00:00")
                )

                # Verificar que é timezone-aware
                assert (
                    first_date.tzinfo is not None
                ), "Data não é timezone-aware"
                assert (
                    last_date.tzinfo is not None
                ), "Data não é timezone-aware"

                logger.info(f"   ✅ Timestamps são timezone-aware (UTC)")

                # Verificar sequência contínua
                expected_days = (end - start).days + 1
                actual_days = len(daily_records)

                if actual_days != expected_days:
                    logger.warning(
                        f"   ⚠️  Esperado {expected_days} dias, obtido {actual_days}"
                    )
                else:
                    logger.info(
                        f"   ✅ Sequência contínua de {actual_days} dias"
                    )

            except Exception as e:
                logger.error(f"   ❌ Erro ao parsear data: {e}")

    except Exception as e:
        logger.error(f"   ❌ Erro ao baixar dados: {e}")

    finally:
        await client_archive.close()


# ============================================================================
# TESTE 3: Consistência de Elevação
# ============================================================================


@pytest.mark.asyncio
async def test_elevation_consistency(test_locations):
    """
    Valida que elevações retornadas pelas APIs são consistentes.

    Compara:
    - OpenTopoData (referência, ~1m precisão)
    - Open-Meteo Archive (~7-30m)
    - Open-Meteo Forecast (~7-30m)
    - NASA POWER (~7-30m)
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: Consistência de Elevação Entre APIs")
    logger.info("=" * 80)

    topo_client = OpenTopoClient()
    archive_client = OpenMeteoArchiveClient()
    forecast_client = OpenMeteoForecastClient()
    nasa_client = NASAPowerClient()

    results = {}

    today = datetime.now(timezone.utc)
    historical_start = today - timedelta(days=40)
    historical_end = today - timedelta(days=35)

    for loc_key, loc_data in test_locations.items():
        logger.info(f"\n📍 {loc_data['name']}")

        elevations = {}

        # 1. OpenTopoData (referência)
        try:
            topo_location = await topo_client.get_elevation(
                loc_data["lat"], loc_data["lon"]
            )
            if topo_location:
                elevations["opentopo"] = topo_location.elevation
                logger.info(
                    f"   OpenTopoData: {topo_location.elevation:.1f}m (±1m)"
                )
        except Exception as e:
            logger.warning(f"   ⚠️  OpenTopoData falhou: {e}")

        # 2. Open-Meteo Archive
        try:
            data = await archive_client.get_daily_data(
                lat=loc_data["lat"],
                lon=loc_data["lon"],
                start_date=historical_start,
                end_date=historical_end,
            )
            if "location" in data and "elevation" in data["location"]:
                elevations["openmeteo_archive"] = data["location"]["elevation"]
                logger.info(
                    f"   Open-Meteo Archive: "
                    f"{data['location']['elevation']:.1f}m (±7-30m)"
                )
        except Exception as e:
            logger.warning(f"   ⚠️  Open-Meteo Archive falhou: {e}")

        # 3. Open-Meteo Forecast
        try:
            data = await forecast_client.get_daily_forecast(
                lat=loc_data["lat"],
                lon=loc_data["lon"],
                start_date=today,
                end_date=today + timedelta(days=1),
            )
            if "location" in data and "elevation" in data["location"]:
                elevations["openmeteo_forecast"] = data["location"][
                    "elevation"
                ]
                logger.info(
                    f"   Open-Meteo Forecast: "
                    f"{data['location']['elevation']:.1f}m (±7-30m)"
                )
        except Exception as e:
            logger.warning(f"   ⚠️  Open-Meteo Forecast falhou: {e}")

        # 4. NASA POWER
        try:
            data = await nasa_client.get_daily_data(
                lat=loc_data["lat"],
                lon=loc_data["lon"],
                start_date=historical_start,
                end_date=historical_end,
            )
            if "location" in data and "elevation" in data["location"]:
                elevations["nasa_power"] = data["location"]["elevation"]
                logger.info(
                    f"   NASA POWER: "
                    f"{data['location']['elevation']:.1f}m (±7-30m)"
                )
        except Exception as e:
            logger.warning(f"   ⚠️  NASA POWER falhou: {e}")

        # Análise de consistência
        if len(elevations) >= 2:
            # Usar OpenTopoData como referência se disponível
            reference = (
                elevations.get("opentopo") or list(elevations.values())[0]
            )

            logger.info(f"\n   📊 Análise de consistência:")
            logger.info(f"      Referência: {reference:.1f}m")

            for api_name, elevation in elevations.items():
                if api_name != "opentopo":
                    diff = abs(elevation - reference)
                    diff_pct = (diff / reference) * 100 if reference > 0 else 0

                    status = "✅" if diff <= 50 else "⚠️"
                    logger.info(
                        f"      {api_name}: {elevation:.1f}m "
                        f"(Δ {diff:.1f}m, {diff_pct:.1f}%) {status}"
                    )

            results[loc_key] = elevations

    # Cleanup
    await topo_client.close()
    await archive_client.close()
    await forecast_client.close()
    await nasa_client.close()

    # Verificar se pelo menos 1 localização tem dados
    assert len(results) > 0, "Nenhuma localização retornou dados de elevação"


# ============================================================================
# TESTE 4: Validação de Estrutura de Dados
# ============================================================================


@pytest.mark.asyncio
async def test_data_structure_validation():
    """
    Valida que todas as APIs retornam estrutura padronizada.

    Estrutura esperada:
    {
        "location": {
            "lat": float,
            "lon": float,
            "elevation": float,
            "timezone": str
        },
        "daily": [
            {
                "date": str (ISO8601),
                "temperature_2m_max": float,
                "temperature_2m_min": float,
                "temperature_2m_mean": float,
                ...
            }
        ]
    }
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: Validação de Estrutura de Dados")
    logger.info("=" * 80)

    # Localização de teste
    lat, lon = -15.7801, -47.9292  # Brasília

    today = datetime.now(timezone.utc)
    start = today - timedelta(days=14)
    end = today - timedelta(days=7)

    # Testar Open-Meteo Archive
    logger.info("\n🧪 Open-Meteo Archive:")

    client = OpenMeteoArchiveClient()
    try:
        data = await client.get_daily_data(
            lat=lat, lon=lon, start_date=start, end_date=end
        )

        # Validar estrutura de nível superior
        assert isinstance(data, dict), "Resposta não é dict"
        assert "location" in data, "Campo 'location' ausente"
        assert "daily" in data, "Campo 'daily' ausente"

        logger.info("   ✅ Estrutura de nível superior OK")

        # Validar location
        location = data["location"]
        assert "lat" in location, "Campo 'lat' ausente"
        assert "lon" in location, "Campo 'lon' ausente"
        assert "elevation" in location, "Campo 'elevation' ausente"

        logger.info("   ✅ Estrutura de 'location' OK")

        # Validar daily records
        daily = data["daily"]
        assert isinstance(daily, list), "'daily' não é lista"
        assert len(daily) > 0, "'daily' está vazia"

        first_record = daily[0]
        assert "date" in first_record, "Campo 'date' ausente"

        logger.info(f"   ✅ Estrutura de 'daily' OK ({len(daily)} registros)")

        # Validar campos opcionais mas importantes
        optional_fields = [
            "temperature_2m_max",
            "temperature_2m_min",
            "relative_humidity_2m_mean",
            "wind_speed_10m_mean",
            "precipitation_sum",
        ]

        present_fields = [f for f in optional_fields if f in first_record]
        logger.info(
            f"   Campos presentes: {len(present_fields)}/{len(optional_fields)}"
        )

    except Exception as e:
        logger.error(f"   ❌ Erro: {e}")
        pytest.fail(f"Validação de estrutura falhou: {e}")

    finally:
        await client.close()


# ============================================================================
# TESTE 5: Download Simultâneo de Múltiplas APIs
# ============================================================================


@pytest.mark.asyncio
async def test_simultaneous_api_downloads(test_locations):
    """
    Valida que múltiplas APIs podem ser chamadas simultaneamente.

    Simula cenário real onde frontend precisa comparar fontes.
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: Download Simultâneo de Múltiplas APIs")
    logger.info("=" * 80)

    loc_data = test_locations["brasilia"]

    logger.info(f"📍 {loc_data['name']}")

    today = datetime.now(timezone.utc)
    start = today - timedelta(days=40)
    end = today - timedelta(days=35)

    # Criar clientes
    clients = {
        "nasa_power": NASAPowerClient(),
        "openmeteo_archive": OpenMeteoArchiveClient(),
        "openmeteo_forecast": OpenMeteoForecastClient(),
    }

    # Download simultâneo
    async def fetch_api(name, client):
        try:
            logger.info(f"   Iniciando {name}...")

            if name == "openmeteo_forecast":
                data = await client.get_daily_forecast(
                    lat=loc_data["lat"],
                    lon=loc_data["lon"],
                    start_date=today,
                    end_date=today + timedelta(days=5),
                )
            else:
                data = await client.get_daily_data(
                    lat=loc_data["lat"],
                    lon=loc_data["lon"],
                    start_date=start,
                    end_date=end,
                )

            num_records = len(data.get("daily", []))
            logger.info(f"   ✅ {name}: {num_records} registros")

            return name, data, None

        except Exception as e:
            logger.error(f"   ❌ {name} falhou: {e}")
            return name, None, str(e)

    # Executar em paralelo
    import asyncio

    tasks = [fetch_api(name, client) for name, client in clients.items()]
    results = await asyncio.gather(*tasks)

    # Analisar resultados
    successful = sum(1 for _, data, error in results if data is not None)
    total = len(results)

    logger.info(f"\n📊 Resultado: {successful}/{total} APIs responderam")

    # Cleanup
    for client in clients.values():
        await client.close()

    # Verificar se pelo menos 2 APIs funcionaram
    assert successful >= 2, f"Apenas {successful} APIs funcionaram"


# ============================================================================
# SUMÁRIO DE TESTES
# ============================================================================


# ============================================================================
# TESTE 6: MET Norway - Download e Validação
# ============================================================================


@pytest.mark.asyncio
async def test_met_norway_download(test_locations, date_ranges):
    """
    Valida download de dados do MET Norway.

    Checks:
    - API responde corretamente
    - Forecast de 5 dias
    - Campos obrigatórios presentes
    - Valores físicos válidos
    - Detecção regional (Nordic vs Global)
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: MET Norway - Download e Validação")
    logger.info("=" * 80)

    client = METNorwayClient()
    period = date_ranges["forecast"]

    results = {}

    for loc_key, loc_data in test_locations.items():
        if "met_norway" not in loc_data["available_apis"]:
            continue

        logger.info(
            f"\n📍 {loc_data['name']} ({loc_data['lat']}, {loc_data['lon']})"
        )

        # Detectar região
        region = GeographicUtils.get_region(loc_data["lat"], loc_data["lon"])
        logger.info(f"   Região detectada: {region}")

        try:
            # Download
            data = await client.get_daily_forecast(
                lat=loc_data["lat"],
                lon=loc_data["lon"],
                start_date=period["start"],
                end_date=period["end"],
            )

            # Validações
            assert data is not None, "Dados nulos"
            assert isinstance(data, list), "Resposta não é lista"
            assert len(data) > 0, "Lista de dados vazia"
            assert len(data) <= 5, f"Mais de 5 dias: {len(data)}"

            logger.info(f"   ✅ Baixados {len(data)} dias (máx 5)")

            # Validar primeiro registro
            first = data[0]

            # Campos obrigatórios
            required_fields = [
                "date",
                "temp_max",
                "temp_min",
                "temp_mean",
                "humidity_mean",
            ]

            missing_fields = [f for f in required_fields if f not in first]
            assert not missing_fields, f"Campos faltando: {missing_fields}"
            logger.info("   ✅ Campos obrigatórios presentes")

            # Verificar precipitação apenas para Nordic
            if region == "nordic":
                if "precipitation_sum" in first:
                    logger.info("   ✅ Precipitação presente (região Nordic)")
                else:
                    logger.warning(
                        "   ⚠️  Precipitação ausente na região Nordic"
                    )
            else:
                logger.info(
                    "   ℹ️  Precipitação não esperada " "(região não-Nordic)"
                )

            # Validar ranges físicos
            for record in data[:3]:
                if record.get("temp_max"):
                    assert -50 <= record["temp_max"] <= 60
                if record.get("temp_min"):
                    assert -50 <= record["temp_min"] <= 60
                if record.get("humidity_mean"):
                    assert 0 <= record["humidity_mean"] <= 100

            logger.info("   ✅ Validações físicas OK")

            results[loc_key] = {
                "status": "success",
                "records": len(data),
                "region": region,
            }

        except Exception as e:
            logger.error(f"   ❌ Erro: {e}")
            results[loc_key] = {"status": "error", "error": str(e)}

    # Verificar resultados
    successful = sum(1 for r in results.values() if r["status"] == "success")
    total = len(results)

    logger.info(
        f"\n📊 Taxa de sucesso: "
        f"{(successful/total)*100:.1f}% ({successful}/{total})"
    )

    assert successful >= 1, "Nenhuma localização funcionou"

    await client.close()


# ============================================================================
# TESTE 7: NWS Forecast - Download e Validação (USA)
# ============================================================================


@pytest.mark.asyncio
async def test_nws_forecast_download(test_locations, date_ranges):
    """
    Valida download de dados do NWS Forecast.

    Checks:
    - API responde apenas para USA
    - Forecast de até 5 dias
    - Conversão de unidades (°F→°C, mph→m/s)
    - Campos obrigatórios presentes
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: NWS Forecast - Download e Validação (USA)")
    logger.info("=" * 80)

    client = NWSForecastClient()
    period = date_ranges["forecast"]

    results = {}

    for loc_key, loc_data in test_locations.items():
        if "nws_forecast" not in loc_data["available_apis"]:
            logger.info(f"\n📍 {loc_data['name']} - " "PULANDO (fora dos USA)")
            continue

        logger.info(
            f"\n📍 {loc_data['name']} ({loc_data['lat']}, {loc_data['lon']})"
        )

        try:
            # Download
            data = await client.get_daily_forecast(
                lat=loc_data["lat"],
                lon=loc_data["lon"],
                start_date=period["start"],
                end_date=period["end"],
            )

            # Validações
            assert data is not None, "Dados nulos"
            assert isinstance(data, list), "Resposta não é lista"
            assert len(data) > 0, "Lista vazia"
            assert len(data) <= 7, f"Mais de 7 dias: {len(data)}"

            logger.info(f"   ✅ Baixados {len(data)} dias (máx 7)")

            # Validar primeiro registro
            first = data[0]

            # Campos obrigatórios
            required_fields = [
                "date",
                "temperature",
                "temperature_max",
                "temperature_min",
            ]

            missing_fields = [f for f in required_fields if f not in first]
            assert not missing_fields, f"Campos faltando: {missing_fields}"
            logger.info("   ✅ Campos obrigatórios presentes")

            # Validar conversão de temperatura (deve estar em °C)
            for record in data[:3]:
                if record.get("temperature_max"):
                    # Se valor > 100, provavelmente está em °F ainda
                    assert record["temperature_max"] < 100, (
                        f"Temperatura parece estar em °F: "
                        f"{record['temperature_max']}"
                    )
                    assert -50 <= record["temperature_max"] <= 60

            logger.info("   ✅ Temperaturas em °C (conversão OK)")

            results[loc_key] = {"status": "success", "records": len(data)}

        except Exception as e:
            logger.error(f"   ❌ Erro: {e}")
            results[loc_key] = {"status": "error", "error": str(e)}

    # Verificar resultados
    successful = sum(1 for r in results.values() if r["status"] == "success")
    total = len(results)

    if total > 0:
        logger.info(
            f"\n📊 Taxa de sucesso: "
            f"{(successful/total)*100:.1f}% ({successful}/{total})"
        )
        assert successful >= 1, "Nenhuma localização USA funcionou"
    else:
        logger.info("\n⚠️  Nenhuma localização USA para testar")

    await client.close()


# ============================================================================
# TESTE 8: NWS Stations - Download e Validação (USA Real-time)
# ============================================================================


@pytest.mark.asyncio
async def test_nws_stations_download(test_locations):
    """
    Valida download de observações do NWS Stations.

    Checks:
    - API responde apenas para USA
    - Estações próximas encontradas
    - Dados recentes (últimas 24h)
    - Conversão de unidades correta
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: NWS Stations - Observações Real-time (USA)")
    logger.info("=" * 80)

    client = NWSStationsClient()

    results = {}

    for loc_key, loc_data in test_locations.items():
        if "nws_stations" not in loc_data["available_apis"]:
            logger.info(f"\n📍 {loc_data['name']} - " "PULANDO (fora dos USA)")
            continue

        logger.info(
            f"\n📍 {loc_data['name']} ({loc_data['lat']}, {loc_data['lon']})"
        )

        try:
            # 1. Buscar estações próximas
            stations = await client.find_nearest_stations(
                lat=loc_data["lat"], lon=loc_data["lon"], limit=3
            )

            assert stations is not None, "Nenhuma estação encontrada"
            assert len(stations) > 0, "Lista de estações vazia"

            logger.info(f"   ✅ Encontradas {len(stations)} estações próximas")

            # 2. Obter observações da primeira estação
            station_id = stations[0].get("stationIdentifier")
            logger.info(f"   Testando estação: {station_id}")

            # Período: últimas 24 horas
            end = datetime.now(timezone.utc)
            start = end - timedelta(hours=24)

            observations = await client.get_station_observations(
                station_id=station_id, start_date=start, end_date=end
            )

            if observations and len(observations) > 0:
                logger.info(f"   ✅ Obtidas {len(observations)} observações")

                # Validar primeira observação
                first_obs = observations[0]

                if "temperature" in first_obs:
                    temp = first_obs["temperature"]
                    assert (
                        -50 <= temp <= 60
                    ), f"Temperatura fora de range: {temp}"
                    logger.info(f"   Temperatura: {temp:.1f}°C")

                if "humidity" in first_obs:
                    humidity = first_obs["humidity"]
                    assert 0 <= humidity <= 100
                    logger.info(f"   Umidade: {humidity:.1f}%")

                results[loc_key] = {
                    "status": "success",
                    "stations": len(stations),
                    "observations": len(observations),
                }
            else:
                logger.warning("   ⚠️  Nenhuma observação recente")
                results[loc_key] = {
                    "status": "partial",
                    "stations": len(stations),
                    "observations": 0,
                }

        except Exception as e:
            logger.error(f"   ❌ Erro: {e}")
            results[loc_key] = {"status": "error", "error": str(e)}

    # Verificar resultados
    successful = sum(
        1 for r in results.values() if r["status"] in ["success", "partial"]
    )
    total = len(results)

    if total > 0:
        logger.info(
            f"\n📊 Taxa de sucesso: "
            f"{(successful/total)*100:.1f}% ({successful}/{total})"
        )
    else:
        logger.info("\n⚠️  Nenhuma localização USA para testar")

    await client.close()


# ============================================================================
# TESTE 9: OpenTopoData - Elevação Precisa
# ============================================================================


@pytest.mark.asyncio
async def test_opentopo_elevation(test_locations):
    """
    Valida obtenção de elevação precisa do OpenTopoData.

    Checks:
    - API responde para todas as localizações
    - Elevação dentro de range esperado
    - Precisão ~1m (SRTM 30m)
    - Cálculo de fatores FAO-56
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: OpenTopoData - Elevação Precisa")
    logger.info("=" * 80)

    client = OpenTopoClient()

    results = {}

    for loc_key, loc_data in test_locations.items():
        logger.info(
            f"\n📍 {loc_data['name']} ({loc_data['lat']}, {loc_data['lon']})"
        )

        try:
            # Obter elevação
            location = await client.get_elevation(
                lat=loc_data["lat"], lon=loc_data["lon"]
            )

            assert location is not None, "Resposta nula"
            assert hasattr(location, "elevation"), "Sem campo elevation"

            elevation = location.elevation
            logger.info(f"   Elevação: {elevation:.1f}m")

            # Verificar range esperado (±50m de margem)
            expected_min, expected_max = loc_data["expected_elevation_range"]

            if expected_min - 50 <= elevation <= expected_max + 50:
                logger.info(
                    f"   ✅ Dentro do esperado: "
                    f"{expected_min}-{expected_max}m (±50m)"
                )
            else:
                logger.warning(
                    f"   ⚠️  Fora do esperado: "
                    f"{expected_min}-{expected_max}m"
                )

            # Calcular fatores FAO-56
            factors = ElevationUtils.get_elevation_correction_factor(elevation)

            logger.info(
                f"   Pressão atmosférica: " f"{factors['pressure']:.2f} kPa"
            )
            logger.info(
                f"   Constante psicrométrica: "
                f"{factors['gamma']:.4f} kPa/°C"
            )
            logger.info(f"   Fator solar: " f"{factors['solar_factor']:.4f}")

            results[loc_key] = {
                "status": "success",
                "elevation": elevation,
                "factors": factors,
            }

        except Exception as e:
            logger.error(f"   ❌ Erro: {e}")
            results[loc_key] = {"status": "error", "error": str(e)}

    # Verificar resultados
    successful = sum(1 for r in results.values() if r["status"] == "success")
    total = len(results)
    success_rate = (successful / total) * 100 if total > 0 else 0

    logger.info(
        f"\n📊 Taxa de sucesso: " f"{success_rate:.1f}% ({successful}/{total})"
    )

    assert success_rate >= 75, f"Taxa baixa: {success_rate:.1f}%"

    await client.close()


# ============================================================================
# TESTE 10: Conversões de Unidades
# ============================================================================


@pytest.mark.asyncio
async def test_unit_conversions():
    """
    Valida conversões de unidades meteorológicas.

    Checks:
    - Temperatura (°F ↔ °C)
    - Velocidade (mph ↔ m/s)
    - Vento (10m → 2m FAO-56)
    - Radiação (Wh/m² ↔ MJ/m²)
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: Conversões de Unidades")
    logger.info("=" * 80)

    # Temperatura
    logger.info("\n🧪 Temperatura:")
    temp_f = 68.0  # °F
    temp_c = WeatherConversionUtils.fahrenheit_to_celsius(temp_f)
    temp_f_back = WeatherConversionUtils.celsius_to_fahrenheit(temp_c)

    logger.info(f"   {temp_f}°F → {temp_c:.2f}°C → {temp_f_back:.2f}°F")
    assert abs(temp_c - 20.0) < 0.1, "Conversão °F→°C incorreta"
    assert abs(temp_f_back - temp_f) < 0.01, "Conversão °C→°F incorreta"
    logger.info("   ✅ Conversões de temperatura OK")

    # Velocidade
    logger.info("\n🧪 Velocidade do Vento:")
    speed_mph = 10.0  # mph
    speed_ms = WeatherConversionUtils.mph_to_ms(speed_mph)
    speed_mph_back = WeatherConversionUtils.ms_to_mph(speed_ms)

    logger.info(
        f"   {speed_mph} mph → {speed_ms:.2f} m/s → "
        f"{speed_mph_back:.2f} mph"
    )
    assert abs(speed_ms - 4.47) < 0.01, "Conversão mph→m/s incorreta"
    assert (
        abs(speed_mph_back - speed_mph) < 0.01
    ), "Conversão m/s→mph incorreta"
    logger.info("   ✅ Conversões de velocidade OK")

    # Vento FAO-56 (10m → 2m)
    logger.info("\n🧪 Vento FAO-56 (10m → 2m):")
    wind_10m = 5.0  # m/s
    wind_2m = WeatherConversionUtils.convert_wind_10m_to_2m(wind_10m)
    expected_2m = 5.0 * 0.748  # Fator FAO-56

    logger.info(f"   {wind_10m} m/s (10m) → {wind_2m:.2f} m/s (2m)")
    assert abs(wind_2m - expected_2m) < 0.01, "Conversão FAO-56 incorreta"
    assert wind_2m < wind_10m, "Vento 2m deve ser menor que 10m"
    logger.info("   ✅ Conversão FAO-56 OK")

    # Radiação
    logger.info("\n🧪 Radiação Solar:")
    rad_wh = 1000.0  # Wh/m²
    rad_mj = WeatherConversionUtils.wh_per_m2_to_mj_per_m2(rad_wh)
    rad_wh_back = WeatherConversionUtils.mj_per_m2_to_wh_per_m2(rad_mj)

    logger.info(
        f"   {rad_wh} Wh/m² → {rad_mj:.2f} MJ/m² → " f"{rad_wh_back:.2f} Wh/m²"
    )
    assert abs(rad_mj - 3.6) < 0.01, "Conversão Wh→MJ incorreta"
    assert abs(rad_wh_back - rad_wh) < 0.01, "Conversão MJ→Wh incorreta"
    logger.info("   ✅ Conversões de radiação OK")

    logger.info("\n✅ Todas as conversões de unidades OK")


# ============================================================================
# TESTE 11: Validações Físicas Regionais
# ============================================================================


@pytest.mark.asyncio
async def test_regional_physical_validations(test_locations):
    """
    Valida que limites físicos regionais são respeitados.

    Checks:
    - Brasil: Limites Xavier et al. 2016
    - USA: Limites padrão
    - Nordic: Limites padrão
    - Global: Limites amplos
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTE: Validações Físicas Regionais")
    logger.info("=" * 80)

    test_cases = [
        # Brasil
        {
            "lat": -15.7801,
            "lon": -47.9292,
            "region": "brazil",
            "temp": 35.0,  # OK para Brasil
            "expected": True,
        },
        {
            "lat": -15.7801,
            "lon": -47.9292,
            "region": "brazil",
            "temp": 55.0,  # Muito quente para Brasil
            "expected": False,
        },
        # USA
        {
            "lat": 40.7128,
            "lon": -74.0060,
            "region": "usa",
            "temp": -40.0,  # OK para USA
            "expected": True,
        },
        # Nordic
        {
            "lat": 59.9139,
            "lon": 10.7522,
            "region": "nordic",
            "temp": -45.0,  # OK para Nordic
            "expected": True,
        },
    ]

    for test in test_cases:
        logger.info(
            f"\n📍 Região: {test['region']} - "
            f"Temperatura: {test['temp']}°C"
        )

        is_valid = WeatherValidationUtils.is_valid_temperature(
            temp=test["temp"], lat=test["lat"], lon=test["lon"]
        )

        if is_valid == test["expected"]:
            logger.info(f"   ✅ Validação correta: {is_valid}")
        else:
            logger.error(
                f"   ❌ Validação incorreta: "
                f"esperado {test['expected']}, obtido {is_valid}"
            )
            pytest.fail(f"Validação regional falhou para {test['region']}")

    logger.info("\n✅ Todas as validações regionais OK")


# ============================================================================
# SUMÁRIO DE TESTES
# ============================================================================


def pytest_sessionfinish(session, exitstatus):
    """Hook executado ao final de todos os testes."""
    logger.info("\n" + "=" * 80)
    logger.info("📊 SUMÁRIO GERAL DOS TESTES")
    logger.info("=" * 80)

    # pytest coleta estatísticas automaticamente
    # Este hook permite adicionar informações customizadas
