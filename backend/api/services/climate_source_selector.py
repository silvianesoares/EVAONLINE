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

from typing import Literal, Union

from loguru import logger

from backend.api.services.climate_factory import ClimateClientFactory
from backend.api.services.nasa_power.nasa_power_client import NASAPowerClient
from backend.api.services.met_norway.met_norway_client import (
    METNorwayClient,
)
from backend.api.services.nws_forecast.nws_forecast_client import (
    NWSForecastClient,
)
from backend.api.services.nws_stations.nws_stations_client import (
    NWSStationsClient,
)
from backend.api.services.openmeteo_archive.openmeteo_archive_client import (
    OpenMeteoArchiveClient,
)
from backend.api.services.openmeteo_forecast.openmeteo_forecast_client import (
    OpenMeteoForecastClient,
)

# Type hints for climate sources
ClimateSource = Literal[
    "nasa_power",
    "met_norway",
    "nws_forecast",
    "nws_stations",
    "openmeteo_archive",
    "openmeteo_forecast",
]
ClimateClient = Union[
    NASAPowerClient,
    METNorwayClient,
    NWSForecastClient,
    NWSStationsClient,
    OpenMeteoArchiveClient,
    OpenMeteoForecastClient,
]


class ClimateSourceSelector:
    """
    Seletor inteligente de fonte climática.

    Determina automaticamente a melhor API para buscar dados climáticos
    baseado nas coordenadas geográficas fornecidas.

    Bounding Boxes:
        - USA: -125°W a -66°W, 24°N a 49°N (NWS)
        - Nordic: 4°E a 31°E, 54°N a 71.5°N (MET Norway alta qualidade)
        - Global: Qualquer coordenada (Open-Meteo, NASA POWER)

    Estratégia MET Norway:
        - Região Nórdica: Temperatura, Umidade, Precipitação
          (1km, radar + crowdsourced, atualizações horárias)
        - Resto do Mundo: Apenas Temperatura e Umidade
          (9km ECMWF, precipitação de menor qualidade - usar Open-Meteo)

    Prioridades:
        1. NWS (USA): Tempo real, alta qualidade regional
        2. MET Norway (Nordic): Melhor precipitação do mundo
        3. Open-Meteo Forecast: Tempo real, alta qualidade global
        4. NASA POWER: Fallback com delay 2-7 dias
    """

    # Bounding boxes das fontes regionais
    # Formato: (lon_min, lat_min, lon_max, lat_max) = (W, S, E, N)

    USA_BBOX = (-125.0, 24.0, -66.0, 49.0)
    """
    Bounding box USA Continental (NWS).

    Cobertura:
        Longitude: -125°W (Costa Oeste) a -66°W (Costa Leste)
        Latitude: 24°N (Sul da Flórida) a 49°N (Fronteira Canadá)

    Estados incluídos:
        Todos os 48 estados contíguos

    Excluídos:
        Alasca, Havaí, Porto Rico, territórios
    """

    NORDIC_BBOX = (4.0, 54.0, 31.0, 71.5)
    """
    Bounding box Região Nórdica (MET Norway 1km alta qualidade).

    Cobertura:
        Longitude: 4°E (Dinamarca Oeste) a 31°E (Finlândia/Bálticos)
        Latitude: 54°N (Dinamarca Sul) a 71.5°N (Noruega Norte)

    Países incluídos:
        Noruega, Dinamarca, Suécia, Finlândia, Estônia, Letônia, Lituânia

    Qualidade especial:
        - Resolução: 1 km (vs 9km global)
        - Atualizações: A cada hora (vs 4x/dia global)
        - Precipitação: Radar + crowdsourced (Netatmo)
        - Pós-processamento: Extensivo com bias correction
    """

    @classmethod
    def select_source(cls, lat: float, lon: float) -> ClimateSource:
        """
        Seleciona melhor fonte climática para coordenadas.

        Algoritmo de seleção:
        1. Verifica se está no USA → NWS
        2. Verifica se está na região Nórdica → MET Norway (alta qualidade)
        3. Fallback → Open-Meteo Forecast (cobertura global, tempo real)

        Args:
            lat: Latitude (-90 a 90)
            lon: Longitude (-180 a 180)

        Returns:
            Nome da fonte recomendada

        Exemplo:
            # Nova York, USA
            source = ClimateSourceSelector.select_source(40.7128, -74.0060)
            # → "nws_forecast"

            # Oslo, Noruega (região nórdica)
            source = ClimateSourceSelector.select_source(59.9139, 10.7522)
            # → "met_norway"

            # Paris, França
            source = ClimateSourceSelector.select_source(48.8566, 2.3522)
            # → "openmeteo_forecast"

            # Brasília, Brasil
            source = ClimateSourceSelector.select_source(-15.7939, -47.8828)
            # → "openmeteo_forecast"
        """
        # Prioridade 1: USA (NWS Forecast)
        if cls._is_in_usa(lat, lon):
            logger.debug(
                f"📍 Coordenadas ({lat}, {lon}) no USA → NWS Forecast"
            )
            return "nws_forecast"

        # Prioridade 2: Região Nórdica (MET Norway alta qualidade)
        if cls._is_in_nordic(lat, lon):
            logger.debug(
                f"📍 Coordenadas ({lat}, {lon}) na região NÓRDICA → "
                f"MET Norway (1km, radar, precipitação alta qualidade)"
            )
            return "met_norway"

        # Fallback: Global (Open-Meteo Forecast - tempo real, alta qualidade)
        logger.debug(f"📍 Coordenadas ({lat}, {lon}) → Open-Meteo Forecast")
        return "openmeteo_forecast"

    @classmethod
    def _is_in_usa(cls, lat: float, lon: float) -> bool:
        """
        Verifica se coordenadas estão no bbox USA Continental.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            True se dentro do bbox NWS
        """
        lon_min, lat_min, lon_max, lat_max = cls.USA_BBOX
        return (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max)

    @classmethod
    def _is_in_nordic(cls, lat: float, lon: float) -> bool:
        """
        Verifica se coordenadas estão no bbox Região Nórdica.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            True se dentro do bbox MET Nordic (alta qualidade)
        """
        lon_min, lat_min, lon_max, lat_max = cls.NORDIC_BBOX
        return (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max)

    @classmethod
    def get_client(cls, lat: float, lon: float) -> ClimateClient:
        """
        Retorna cliente apropriado para coordenadas.

        Combina select_source() com ClimateClientFactory para
        retornar cliente já configurado e pronto para uso.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Cliente climático configurado

        Exemplo:
            # Obter cliente automático para Paris
            client = ClimateSourceSelector.get_client(
                lat=48.8566, lon=2.3522
            )
            # → METNorwayClient com cache injetado

            data = await client.get_forecast_data(...)
            await client.close()
        """
        source = cls.select_source(lat, lon)

        if source == "met_norway":
            return ClimateClientFactory.create_met_norway()
        elif source == "nws_forecast" or source == "nws_stations":
            return ClimateClientFactory.create_nws()
        elif source == "openmeteo_archive":
            return ClimateClientFactory.create_openmeteo_archive()
        elif source == "openmeteo_forecast":
            return ClimateClientFactory.create_openmeteo_forecast()
        else:  # nasa_power
            return ClimateClientFactory.create_nasa_power()

    @classmethod
    def get_all_sources(cls, lat: float, lon: float) -> list[ClimateSource]:
        """
        Retorna TODAS as fontes disponíveis para coordenadas.

        Útil para fusão multi-fonte ou validação cruzada.

        Lógica:
        - NASA POWER sempre disponível (cobertura global)
        - MET Norway Locationforecast se na região nórdica (prioridade)
          ou global (temperatura/umidade apenas)
        - NWS Forecast/Stations se no USA
        - Open-Meteo Archive/Forecast sempre disponível

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Lista de fontes aplicáveis, ordenadas por prioridade

        Exemplo:
            # Oslo (Região Nórdica)
            sources = ClimateSourceSelector.get_all_sources(59.9139, 10.7522)
            # → ["met_norway", "openmeteo_forecast",
            #    "nasa_power", ...]

            # Brasília (apenas global)
            sources = ClimateSourceSelector.get_all_sources(-15.7939, -47.8828)
            # → ["openmeteo_forecast", "met_norway",
            #    "nasa_power", "openmeteo_archive"]
        """
        sources = []

        # Fontes regionais (alta prioridade)
        if cls._is_in_usa(lat, lon):
            sources.append("nws_forecast")
            sources.append("nws_stations")

        # MET Norway tem prioridade na região nórdica
        if cls._is_in_nordic(lat, lon):
            sources.append("met_norway")
            sources.append("openmeteo_forecast")
        else:
            # Fora da região nórdica: Open-Meteo tem prioridade
            sources.append("openmeteo_forecast")
            sources.append("met_norway")

        # Fontes globais adicionais
        sources.extend(["openmeteo_archive", "nasa_power"])

        logger.debug(f"📍 Fontes disponíveis para ({lat}, {lon}): {sources}")

        return sources

    @classmethod
    def get_data_availability_summary(cls) -> dict[str, dict]:
        """
        Retorna resumo da disponibilidade de dados de todas as fontes (6 APIs).

        Returns:
            dict: Informações de disponibilidade por fonte
        """
        from backend.api.services.met_norway.met_norway_client import (
            METNorwayLocationForecastClient,
        )
        from backend.api.services.openmeteo_archive.openmeteo_archive_client import (
            OpenMeteoArchiveClient,
        )
        from backend.api.services.openmeteo_forecast.openmeteo_forecast_client import (
            OpenMeteoForecastClient,
        )
        from backend.api.services.nasa_power.nasa_power_client import (
            NASAPowerClient,
        )
        from backend.api.services.nws_forecast.nws_forecast_client import (
            NWSForecastClient,
        )

        summary = {}

        # Open-Meteo Archive
        try:
            info = OpenMeteoArchiveClient.get_info()
            summary["openmeteo_archive"] = {
                "coverage": info["coverage"],
                "period": info["period"],
                "license": info["license"],
                "description": "Historical weather data (1940-present)",
            }
        except Exception:
            summary["openmeteo_archive"] = {"error": "Failed to get info"}

        # Open-Meteo Forecast
        try:
            info = OpenMeteoForecastClient.get_info()
            summary["openmeteo_forecast"] = {
                "coverage": info["coverage"],
                "period": info.get("period", "Up to 16 days ahead"),
                "license": info["license"],
                "description": "Forecast weather data (up to 16 days)",
            }
        except Exception:
            summary["openmeteo_forecast"] = {"error": "Failed to get info"}

        # NASA POWER
        try:
            info = NASAPowerClient.get_data_availability_info()
            summary["nasa_power"] = {
                "data_start_date": str(info["data_start_date"]),
                "max_historical_years": info["max_historical_years"],
                "coverage": info["coverage"],
                "description": info["description"],
            }
        except Exception:
            summary["nasa_power"] = {"error": "Failed to get info"}

        # NWS
        try:
            nws_client = NWSForecastClient()
            info = nws_client.get_data_availability_info()
            summary["nws_forecast"] = {
                "data_start_date": None,
                "max_historical_years": 0,
                "forecast_horizon_days": info["forecast_horizon_days"],
                "coverage": info["coverage"],
                "description": info["description"],
            }
            summary["nws_stations"] = {
                "data_start_date": None,
                "max_historical_years": 0,
                "coverage": info["coverage"],
                "description": "Recent observations from USA stations",
            }
        except Exception:
            summary["nws"] = {"error": "Failed to get info"}

        # MET Norway Locationforecast
        try:
            info = METNorwayLocationForecastClient.get_data_availability_info()
            summary["met_norway"] = {
                "data_start_date": None,
                "max_historical_years": 0,
                "forecast_horizon_days": info["forecast_horizon_days"],
                "coverage": info["coverage"],
                "description": info["description"],
            }
        except Exception:
            summary["met_norway"] = {"error": "Failed to get info"}

        return summary

    @classmethod
    def get_coverage_info(cls, lat: float, lon: float) -> dict:
        """
        Retorna informações detalhadas sobre cobertura para coordenadas.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Dict com informações de cobertura

        Exemplo:
            info = ClimateSourceSelector.get_coverage_info(48.8566, 2.3522)
            # {
            #     'location': {'lat': 48.8566, 'lon': 2.3522},
            #     'recommended_source': 'met_norway',
            #     'all_sources': ['met_norway', 'nasa_power'],
            #     'regional_coverage': {
            #         'europe': True,
            #         'usa': False
            #     },
            #     'source_details': {...}
            # }
        """
        recommended = cls.select_source(lat, lon)
        all_sources = cls.get_all_sources(lat, lon)

        return {
            "location": {"lat": lat, "lon": lon},
            "recommended_source": recommended,
            "all_sources": all_sources,
            "regional_coverage": {
                "usa": cls._is_in_usa(lat, lon),
                "nordic": cls._is_in_nordic(lat, lon),
            },
            "source_details": {
                "nws_forecast": {
                    "bbox": cls.USA_BBOX,
                    "description": "USA: -125°W a -66°W, 24°N a 49°N",
                    "quality": "high",
                    "realtime": True,
                },
                "nws_stations": {
                    "bbox": cls.USA_BBOX,
                    "description": "USA stations: -125°W a -66°W, 24°N a 49°N",
                    "quality": "high",
                    "realtime": True,
                },
                "met_norway": {
                    "bbox": None,
                    "nordic_bbox": cls.NORDIC_BBOX,
                    "description": (
                        "Global coverage. Nordic region "
                        "(NO/SE/FI/DK/Baltics): "
                        "1km resolution, hourly updates, radar-corrected "
                        "precipitation. Rest of world: 9km ECMWF, "
                        "temperature/humidity only"
                    ),
                    "quality": {
                        "nordic": ("very high (1km + radar + crowdsourced)"),
                        "global": ("medium (9km ECMWF, skip precipitation)"),
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


# Exemplo de uso completo
async def example_usage():
    """Demonstra uso do seletor de fontes."""

    # Exemplos de cidades em diferentes regiões
    locations = [
        {"name": "Paris, França", "lat": 48.8566, "lon": 2.3522},
        {"name": "Nova York, USA", "lat": 40.7128, "lon": -74.0060},
        {"name": "Brasília, Brasil", "lat": -15.7939, "lon": -47.8828},
        {"name": "Tóquio, Japão", "lat": 35.6762, "lon": 139.6503},
        {"name": "Oslo, Noruega", "lat": 59.9139, "lon": 10.7522},
    ]

    for loc in locations:
        print(f"\n📍 {loc['name']} ({loc['lat']}, {loc['lon']})")

        # 1. Seleção automática
        source = ClimateSourceSelector.select_source(loc["lat"], loc["lon"])
        print(f"   Fonte recomendada: {source}")

        # 2. Todas as fontes disponíveis
        all_sources = ClimateSourceSelector.get_all_sources(
            loc["lat"], loc["lon"]
        )
        print(f"   Fontes disponíveis: {all_sources}")

        # 3. Obter cliente
        try:
            client = ClimateSourceSelector.get_client(loc["lat"], loc["lon"])
            print(f"   ✅ Cliente criado: {type(client).__name__}")
        except Exception as e:
            print(f"   ❌ Erro ao criar cliente: {e}")

    # Cleanup global
    await ClimateClientFactory.close_all()


def get_available_sources_for_frontend(lat: float, lon: float) -> dict:
    """
    Retorna fontes disponíveis formatadas para o frontend.

    Usado pela interface dash_eto.py para popular dropdown de fontes.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Dict com informações formatadas:
        {
            "recommended": "openmeteo_forecast",
            "sources": [
                {
                    "value": "fusion",
                    "label": "🔀 Fusão Inteligente (Recomendado)",
                    "description": "Combina múltiplas fontes para melhor qualidade"
                },
                {
                    "value": "openmeteo_forecast",
                    "label": "Open-Meteo Forecast",
                    "description": "Dados globais em tempo real",
                    "icon": "🌍"
                },
                ...
            ],
            "location_info": {
                "in_usa": False,
                "in_nordic": False,
                "region": "Global"
            }
        }
    """
    # Detecta região
    in_usa = ClimateSourceSelector._is_in_usa(lat, lon)
    in_nordic = ClimateSourceSelector._is_in_nordic(lat, lon)

    region = (
        "USA Continental"
        if in_usa
        else ("Região Nórdica" if in_nordic else "Global")
    )

    # Obtém fonte recomendada e todas disponíveis
    recommended = ClimateSourceSelector.select_source(lat, lon)
    all_sources = ClimateSourceSelector.get_all_sources(lat, lon)

    # Mapeamento de ícones e descrições
    source_metadata = {
        "openmeteo_archive": {
            "icon": "📚",
            "label": "Open-Meteo Archive",
            "description": "Dados históricos globais (1990-hoje)",
        },
        "openmeteo_forecast": {
            "icon": "🌍",
            "label": "Open-Meteo Forecast",
            "description": "Dados recentes + previsão global",
        },
        "nasa_power": {
            "icon": "🛰️",
            "label": "NASA POWER",
            "description": "Dados históricos globais (1990-hoje)",
        },
        "met_norway": {
            "icon": "🇳🇴" if in_nordic else "🌐",
            "label": "MET Norway" + (" (Alta Qualidade)" if in_nordic else ""),
            "description": "Previsão meteorológica"
            + (" - Resolução 1km" if in_nordic else " - Global"),
        },
        "nws_forecast": {
            "icon": "🇺🇸",
            "label": "NWS Forecast",
            "description": "Previsão oficial NOAA (USA)",
        },
        "nws_stations": {
            "icon": "📡",
            "label": "NWS Stations",
            "description": "Observações em tempo real (USA)",
        },
    }

    # Monta lista de fontes formatadas
    sources_list = [
        {
            "value": "fusion",
            "label": "🔀 Fusão Inteligente (Recomendado)",
            "description": f"Combina {len(all_sources)} fontes para melhor qualidade e cobertura",
            "is_default": True,
        }
    ]

    # Adiciona fontes individuais
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


if __name__ == "__main__":
    import asyncio

    asyncio.run(example_usage())
