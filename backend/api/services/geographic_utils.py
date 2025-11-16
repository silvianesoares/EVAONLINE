"""
Utilidades geográficas centralizadas para detecção de região.

Este módulo centraliza TODAS as operações de geolocalização,
eliminando duplicação de código em múltiplos módulos.

SINGLE SOURCE OF TRUTH para:
- Detecção de coordenadas USA
- Detecção de coordenadas Nordic (MET Norway 1km)
- Detecção de coordenadas Brazil (validações rigorosas)
- Detecção de coordenadas Global

Bounding Boxes:
- USA Continental: -125°W a -66°W, 24°N a 49°N (NWS coverage)
- Nordic Region: 4°E a 31°E, 54°N a 71.5°N (MET Norway 1km)
- Brazil: -74°W a -34°W, -34°S a 5°N (Xavier et al. 2016)
- Global: Qualquer coordenada dentro (-180, -90) a (180, 90)

Uso:
    from backend.api.services.geographic_utils import GeographicUtils

    if GeographicUtils.is_in_usa(lat, lon):
        # Use NWS
        pass
    elif GeographicUtils.is_in_nordic(lat, lon):
        # Use MET Norway com precipitação de alta qualidade
        pass
    elif GeographicUtils.is_in_brazil(lat, lon):
        # Use validações Brazil-specific
        pass
    else:
        # Use Open-Meteo ou NASA POWER (global)
        pass
"""

from datetime import datetime, date, timezone
from loguru import logger
from typing import Literal
from functools import wraps
import inspect


class GeographicUtils:
    """Centraliza detecção geográfica com bounding boxes padronizadas."""

    # Bounding boxes: (lon_min, lat_min, lon_max, lat_max) = (W, S, E, N)

    USA_BBOX = (-125.0, 24.0, -66.0, 49.0)
    """
    Bounding box USA Continental (NWS coverage).

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

    BRAZIL_BBOX = (-74.0, -34.0, -34.0, 5.0)
    """
    Bounding box Brasil (Xavier et al. 2016).

    Cobertura:
        Longitude: -74°W (Fronteira Oeste) a -34°W (Costa Leste)
        Latitude: -34°S (Sul) a 5°N (Norte)

    Descrição:
        Limites continentais do Brasil, incluindo todas as regiões.
        Usado para validações específicas e otimização de fontes.
    """

    GLOBAL_BBOX = (-180.0, -90.0, 180.0, 90.0)
    """Bounding box Global (qualquer coordenada válida)."""

    @staticmethod
    def is_in_usa(lat: float, lon: float) -> bool:
        """
        Verifica se coordenadas estão nos EUA continental.

        Usa bounding box: (-125.0, 24.0, -66.0, 49.0)
        Cobertura: NWS API (National Weather Service)

        Args:
            lat: Latitude (-90 a 90)
            lon: Longitude (-180 a 180)

        Returns:
            bool: True se dentro do bbox USA, False caso contrário

        Exemplo:
            if GeographicUtils.is_in_usa(39.7392, -104.9903):
                # Denver, CO - dentro dos USA
                pass
        """
        lon_min, lat_min, lon_max, lat_max = GeographicUtils.USA_BBOX
        in_usa = (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max)

        if not in_usa:
            logger.debug(
                f"⚠️  Coordenadas ({lat:.4f}, {lon:.4f}) "
                f"FORA da cobertura USA Continental"
            )

        return in_usa

    @staticmethod
    def is_in_nordic(lat: float, lon: float) -> bool:
        """
        Verifica se coordenadas estão na região Nórdica.

        Usa bounding box: (4.0, 54.0, 31.0, 71.5)
        Cobertura: MET Norway 1km alta qualidade com radar

        Args:
            lat: Latitude (-90 a 90)
            lon: Longitude (-180 a 180)

        Returns:
            bool: True se dentro do bbox Nordic, False caso contrário

        Exemplo:
            if GeographicUtils.is_in_nordic(60.1699, 24.9384):
                # Helsinki, Finland - dentro da região Nordic
                pass
        """
        lon_min, lat_min, lon_max, lat_max = GeographicUtils.NORDIC_BBOX
        in_nordic = (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max)

        if in_nordic:
            logger.debug(
                f"✅ Coordenadas ({lat:.4f}, {lon:.4f}) "
                f"na região NORDIC (MET Norway 1km)"
            )

        return in_nordic

    @staticmethod
    def is_in_brazil(lat: float, lon: float) -> bool:
        """
        Verifica se coordenadas estão no Brasil.

        Usa bounding box: (-74.0, -34.0, -34.0, 5.0)
        Cobertura: Território continental brasileiro

        Args:
            lat: Latitude (-90 a 90)
            lon: Longitude (-180 a 180)

        Returns:
            bool: True se dentro do bbox Brasil, False caso contrário

        Exemplo:
            if GeographicUtils.is_in_brazil(-23.5505, -46.6333):
                # São Paulo, Brasil - dentro do território
                pass
        """
        lon_min, lat_min, lon_max, lat_max = GeographicUtils.BRAZIL_BBOX
        in_brazil = (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max)

        if in_brazil:
            logger.debug(
                f"✅ Coordenadas ({lat:.4f}, {lon:.4f}) " f"na região BRASIL"
            )

        return in_brazil

    @staticmethod
    def is_valid_coordinate(lat: float, lon: float) -> bool:
        """
        Verifica se coordenadas são válidas (dentro de (-180, -90) a
        (180, 90)).

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            bool: True se válido, False caso contrário
        """
        lon_min, lat_min, lon_max, lat_max = GeographicUtils.GLOBAL_BBOX
        return (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max)

    @staticmethod
    def is_in_bbox(lat: float, lon: float, bbox: tuple) -> bool:
        """
        Verifica se coordenadas estão dentro de um bounding box.

        Args:
            lat: Latitude
            lon: Longitude
            bbox: Tupla (west, south, east, north)

        Returns:
            bool: True se dentro do bbox

        Exemplo:
            # Verificar se está na região USA
            if GeographicUtils.is_in_bbox(40.7, -74.0,
                                          GeographicUtils.USA_BBOX):
                # Dentro da região USA
                pass
        """
        if not GeographicUtils.is_valid_coordinate(lat, lon):
            return False

        west, south, east, north = bbox
        return (west <= lon <= east) and (south <= lat <= north)

    @staticmethod
    def get_region(
        lat: float, lon: float
    ) -> Literal["usa", "nordic", "brazil", "global"]:
        """
        Detecta região geográfica com prioridade:
        USA > Nordic > Brazil > Global.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            str: Uma de "usa", "nordic", "brazil", "global"

        Exemplo:
            region = GeographicUtils.get_region(39.7392, -104.9903)
            # Retorna: "usa"

            region = GeographicUtils.get_region(60.1699, 24.9384)
            # Retorna: "nordic"

            region = GeographicUtils.get_region(-23.5505, -46.6333)
            # Retorna: "brazil"
        """
        if GeographicUtils.is_in_usa(lat, lon):
            return "usa"
        elif GeographicUtils.is_in_nordic(lat, lon):
            return "nordic"
        elif GeographicUtils.is_in_brazil(lat, lon):
            return "brazil"
        else:
            return "global"

    @staticmethod
    def get_recommended_sources(lat: float, lon: float) -> list[str]:
        """
        Retorna lista de fontes climáticas recomendadas por região,
        em ordem de prioridade. Padronizado para forecast (5 dias).

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            list[str]: Lista ordenada de nomes de fontes (API priority)

        Regiões:
            USA:
                1. nws_forecast (previsão alta qualidade)
                2. nws_stations (observações tempo real)
                3. openmeteo_forecast (fallback global)
                4. openmeteo_archive (histórico)
                5. nasa_power (fallback universal)

            Nordic:
                1. met_norway (previsão 1km com radar)
                2. openmeteo_forecast (fallback global)
                3. openmeteo_archive (histórico)
                4. nasa_power (fallback universal)

            Brazil:
                1. openmeteo_forecast (melhor global para BR)
                2. nasa_power (histórico validado)
                3. openmeteo_archive (histórico)

            Global:
                1. openmeteo_forecast (melhor global)
                2. openmeteo_archive (histórico)
                3. nasa_power (fallback universal)

        Exemplo:
            sources = GeographicUtils.get_recommended_sources(
                39.7392, -104.9903
            )
            # Retorna: ["nws_forecast", "nws_stations",
            #           "openmeteo_forecast", ...]
        """
        region = GeographicUtils.get_region(lat, lon)

        # Fontes base comuns (evita repetição)
        base_sources = [
            "openmeteo_forecast",  # Forecast global (5 dias)
            "openmeteo_archive",  # Histórico fallback
            "nasa_power",  # Universal
        ]

        # Mapeamento região -> fontes prioritárias
        region_sources = {
            "usa": [
                "nws_forecast",  # Melhor para previsão
                "nws_stations",  # Observações tempo real
            ]
            + base_sources,
            "nordic": [
                "met_norway",  # Melhor: 1km + radar
            ]
            + base_sources,
            "brazil": [
                # Otimizado para Brasil: skip MET (precip baixa qualidade)
                "openmeteo_forecast",  # Melhor global
                "nasa_power",  # Histórico validado
                "openmeteo_archive",  # Histórico
            ],
        }

        return region_sources.get(region, base_sources)


class TimezoneUtils:
    """
    Utilitários para manipulação consistente de timezone.

    Garante comparações corretas entre datetimes com/sem timezone.
    Centralizado aqui para evitar importação circular com weather_utils.
    """

    @staticmethod
    def ensure_naive(dt) -> datetime:
        """
        Converte datetime para naive (sem timezone).

        Args:
            dt: Datetime possivelmente timezone-aware

        Returns:
            Datetime naive (sem timezone)
        """
        if not isinstance(dt, datetime):
            raise TypeError("dt must be a datetime instance")
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    @staticmethod
    def ensure_utc(dt) -> datetime:
        """
        Converte datetime para UTC timezone-aware.

        Args:
            dt: Datetime possivelmente naive

        Returns:
            Datetime UTC timezone-aware
        """
        if not isinstance(dt, datetime):
            raise TypeError("dt must be a datetime instance")
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def make_aware(dt, tz=None) -> datetime:
        """
        Converte datetime naive para timezone-aware.

        Args:
            dt: Datetime possivelmente naive
            tz: Timezone (default: UTC)

        Returns:
            Datetime timezone-aware
        """
        if not isinstance(dt, datetime):
            raise TypeError("dt must be a datetime instance")
        if dt.tzinfo is None:
            target_tz = tz or timezone.utc
            return dt.replace(tzinfo=target_tz)
        return dt

    @staticmethod
    def compare_dates_safe(dt1, dt2, comparison: str = "lt") -> bool:
        """
        Compara duas datas de forma segura (ignorando timezone).

        Args:
            dt1: Primeira data
            dt2: Segunda data
            comparison: 'lt', 'le', 'gt', 'ge', 'eq'

        Returns:
            Resultado da comparação
        """
        if not isinstance(dt1, (datetime, date)) or not isinstance(
            dt2, (datetime, date)
        ):
            raise TypeError("dt1 and dt2 must be datetime or date instances")

        date1 = dt1.date() if isinstance(dt1, datetime) else dt1
        date2 = dt2.date() if isinstance(dt2, datetime) else dt2

        if comparison == "lt":
            return date1 < date2
        elif comparison == "le":
            return date1 <= date2
        elif comparison == "gt":
            return date1 > date2
        elif comparison == "ge":
            return date1 >= date2
        elif comparison == "eq":
            return date1 == date2
        else:
            raise ValueError(f"Invalid comparison: {comparison}")


def validate_coordinates(func):
    """
    Decorador para validar coordenadas antes de executar função.

    Valida que lat/lon são floats válidos dentro de (-180, -90) a (180, 90).
    Levanta ValueError se inválidas. Usa inspect para parsing robusto.

    Uso:
        @validate_coordinates
        def get_weather(lat: float, lon: float):
            # lat/lon já validadas aqui
            pass
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Parsing robusto usando inspect.signature
        sig = inspect.signature(func)
        try:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
        except TypeError:
            # Fallback para args posicionais se bind falhar
            if len(args) >= 2:
                lat, lon = args[-2], args[-1]
            elif "lat" in kwargs and "lon" in kwargs:
                lat = kwargs["lat"]
                lon = kwargs["lon"]
            else:
                raise ValueError("Function must provide 'lat' and 'lon'")
        else:
            # Extrai lat/lon de forma robusta (prioriza kwargs nomeados)
            lat = bound.arguments.get("lat")
            lon = bound.arguments.get("lon")
            if lat is None or lon is None:
                # Fallback para args posicionais
                if len(args) >= 2:
                    lat, lon = args[-2], args[-1]
                else:
                    raise ValueError("Function must provide 'lat' and 'lon'")

        # Converter para float se necessário
        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            raise ValueError("lat and lon must be numeric")

        # Validar coordenadas
        if not GeographicUtils.is_valid_coordinate(lat, lon):
            raise ValueError(
                f"Invalid coordinates: lat={lat}, lon={lon}. "
                "Must be within lon (-180 to 180), lat (-90 to 90)"
            )

        return func(*args, **kwargs)

    return wrapper
