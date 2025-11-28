"""
Weather conversion and aggregation utilities.

Centraliza todas as conversões de unidades e fórmulas meteorológicas
para eliminar duplicação de código entre os clientes climáticos.

SINGLE SOURCE OF TRUTH para:
- Conversão de vento (10m → 2m usando FAO-56)
- Conversão de temperatura (°F → °C)
- Conversão de velocidade (mph → m/s)
- Conversão de radiação solar
- Validações meteorológicas comuns
- Agregação hourly-to-daily (ex.: MET Norway)
- Cache handling para APIs
- Correções de elevação FAO-56
- Métricas Prometheus para validações
"""

from datetime import datetime, timezone
from typing import Any, Dict, List
from collections import defaultdict

import numpy as np
from email.utils import parsedate_to_datetime
from loguru import logger

try:
    import prometheus_client as prom

    # Counter para validações falhas (Prometheus)
    VALIDATION_ERRORS = prom.Counter(
        "weather_validation_errors_total",
        "Total validation errors",
        ["region", "variable"],
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    logger.warning("prometheus_client not available. Metrics disabled.")
    PROMETHEUS_AVAILABLE = False
    VALIDATION_ERRORS = None


class WeatherConversionUtils:
    """
    Utilitários de conversão de unidades meteorológicas.

    Todas as conversões seguem padrões internacionais:
    - FAO-56 para vento e evapotranspiração
    - Unidades SI (Sistema Internacional)
    """

    @staticmethod
    def convert_wind_10m_to_2m(wind_10m: float | None) -> float | None:
        """
        Converte velocidade do vento de 10m para 2m usando FAO-56.

        Fórmula FAO-56: u₂ = u₁₀ × 0.748

        Esta conversão é necessária porque:
        - Sensores medem vento a 10m de altura (padrão)
        - ETo FAO-56 requer vento a 2m de altura
        - Fator 0.748 considera perfil logarítmico de vento

        Args:
            wind_10m: Velocidade do vento a 10m (m/s)

        Returns:
            Velocidade do vento a 2m (m/s) ou None

        Referência:
            Allen et al. (1998). FAO Irrigation and Drainage Paper 56
            Chapter 3, Equation 47, page 56
        """
        if wind_10m is None:
            return None
        return wind_10m * 0.748

    @staticmethod
    def fahrenheit_to_celsius(fahrenheit: float | None) -> float | None:
        """
        Converte temperatura de Fahrenheit para Celsius.

        Fórmula: °C = (°F - 32) x 5/9

        Args:
            fahrenheit: Temperatura em °F

        Returns:
            Temperatura em °C ou None
        """
        if fahrenheit is None:
            return None
        return (fahrenheit - 32) * 5.0 / 9.0

    @staticmethod
    def celsius_to_fahrenheit(celsius: float | None) -> float | None:
        """
        Converte temperatura de Celsius para Fahrenheit.

        Fórmula: °F = °C x 9/5 + 32

        Args:
            celsius: Temperatura em °C

        Returns:
            Temperatura em °F ou None
        """
        if celsius is None:
            return None
        return celsius * 9.0 / 5.0 + 32.0

    @staticmethod
    def mph_to_ms(mph: float | None) -> float | None:
        """
        Converte velocidade de milhas por hora para metros por segundo.

        Fórmula: 1 mph = 0.44704 m/s

        Args:
            mph: Velocidade em mph

        Returns:
            Velocidade em m/s ou None
        """
        if mph is None:
            return None
        return mph * 0.44704

    @staticmethod
    def ms_to_mph(ms: float | None) -> float | None:
        """
        Converte velocidade de metros por segundo para milhas por hora.

        Fórmula: 1 m/s = 2.23694 mph

        Args:
            ms: Velocidade em m/s

        Returns:
            Velocidade em mph ou None
        """
        if ms is None:
            return None
        return ms * 2.23694

    @staticmethod
    def wh_per_m2_to_mj_per_m2(wh_per_m2: float | None) -> float | None:
        """
        Converte radiação solar de Wh/m² para MJ/m².

        Fórmula: 1 Wh = 0.0036 MJ

        Args:
            wh_per_m2: Radiação em Wh/m²

        Returns:
            Radiação em MJ/m² ou None
        """
        if wh_per_m2 is None:
            return None
        return wh_per_m2 * 0.0036

    @staticmethod
    def mj_per_m2_to_wh_per_m2(mj_per_m2: float | None) -> float | None:
        """
        Converte radiação solar de MJ/m² para Wh/m².

        Fórmula: 1 MJ = 277.778 Wh

        Args:
            mj_per_m2: Radiação em MJ/m²

        Returns:
            Radiação em Wh/m² ou None
        """
        if mj_per_m2 is None:
            return None
        return mj_per_m2 * 277.778


class WeatherValidationUtils:
    """
    Validações de dados meteorológicos.

    Verifica ranges válidos para variáveis meteorológicas
    baseado em limites físicos e práticos.
    """

    # ═══════════════════════════════════════════════════════════════
    # LIMITES GLOBAIS (Mundo inteiro)
    # Baseado em records mundiais e limites físicos
    # ═══════════════════════════════════════════════════════════════
    TEMP_MIN = (
        -90.0
    )  # °C (Record mundial: -89.2°C: https://svs.gsfc.nasa.gov/4126/)
    TEMP_MAX = 60.0  # °C (Record mundial: 56.7°C: https://www.ncei.noaa.gov/news/earths-hottest-temperature)
    HUMIDITY_MIN = 0.0  # % (https://www.psu.edu/news/research/story/humans-cant-endure-temperatures-and-humidities-high-previously-thought)
    HUMIDITY_MAX = 100.0  # % (https://www.psu.edu/news/research/story/humans-cant-endure-temperatures-and-humidities-high-previously-thought)
    WIND_MIN = (
        0.0  # m/s (https://mountwashington.org/remembering-the-big-wind/)
    )
    WIND_MAX = 120.0  # m/s (~432 km/h, furacão categoria 5: https://mountwashington.org/remembering-the-big-wind/)
    PRECIP_MIN = 0.0  # mm (https://www.weather.gov/owp/hdsc_world_record)
    PRECIP_MAX = 2000.0  # mm/dia (record: ~1825mm: (https://www.weather.gov/owp/hdsc_world_record)
    SOLAR_MIN = 0.0  # MJ/m²/dia (https://www.bom.gov.au/climate/austmaps/metadata-daily-solar-exposure.shtml)
    SOLAR_MAX = 35.0  # MJ/m²/dia (https://www.bom.gov.au/climate/austmaps/metadata-daily-solar-exposure.shtml)

    # ═══════════════════════════════════════════════════════════════
    # LIMITES BRASIL (Xavier et al. 2016, 2022)
    # "New improved Brazilian daily weather gridded data (1961–2020)"
    # https://rmets.onlinelibrary.wiley.com/doi/abs/10.1002/joc.7731
    # Validações mais rigorosas para dados brasileiros
    # ═══════════════════════════════════════════════════════════════
    BRAZIL_TEMP_MIN = -30.0  # °C (limites Xavier)
    BRAZIL_TEMP_MAX = 50.0  # °C (limites Xavier)
    BRAZIL_HUMIDITY_MIN = 0.0  # %
    BRAZIL_HUMIDITY_MAX = 100.0  # %
    BRAZIL_WIND_MIN = 0.0  # m/s
    BRAZIL_WIND_MAX = 100.0  # m/s (limites Xavier)
    BRAZIL_PRECIP_MIN = 0.0  # mm
    BRAZIL_PRECIP_MAX = 450.0  # mm/dia (limites Xavier)
    BRAZIL_SOLAR_MIN = 0.0  # MJ/m²/dia
    BRAZIL_SOLAR_MAX = 40.0  # MJ/m²/dia (limites Xavier)
    BRAZIL_PRESSURE_MIN = 900.0  # hPa
    BRAZIL_PRESSURE_MAX = 1100.0  # hPa

    # Dicionário de limites por região
    REGIONAL_LIMITS = {
        "global": {
            "temperature": (TEMP_MIN, TEMP_MAX),
            "humidity": (HUMIDITY_MIN, HUMIDITY_MAX),
            "wind": (WIND_MIN, WIND_MAX),
            "precipitation": (PRECIP_MIN, PRECIP_MAX),
            "solar": (SOLAR_MIN, SOLAR_MAX),
            "pressure": (800.0, 1150.0),
        },
        "brazil": {
            "temperature": (BRAZIL_TEMP_MIN, BRAZIL_TEMP_MAX),
            "humidity": (BRAZIL_HUMIDITY_MIN, BRAZIL_HUMIDITY_MAX),
            "wind": (BRAZIL_WIND_MIN, BRAZIL_WIND_MAX),
            "precipitation": (BRAZIL_PRECIP_MIN, BRAZIL_PRECIP_MAX),
            "solar": (BRAZIL_SOLAR_MIN, BRAZIL_SOLAR_MAX),
            "pressure": (BRAZIL_PRESSURE_MIN, BRAZIL_PRESSURE_MAX),
        },
    }

    @classmethod
    def get_validation_limits(
        cls,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> dict[str, tuple[float, float]]:
        """
        Retorna limites de validação por região detectada.

        Args:
            lat: Latitude (para detecção automática de região)
            lon: Longitude (para detecção automática de região)
            region: Região explícita ("global", "brazil", "usa", "nordic")
                   Sobrescreve detecção automática se fornecido.

        Returns:
            Dict com limites (min, max) para cada variável

        Exemplo:
            # Detecção automática
            limits = WeatherValidationUtils.get_validation_limits(
                lat=-23.5505, lon=-46.6333
            )
            # São Paulo → limites do Brasil

            # Região explícita
            limits = WeatherValidationUtils.get_validation_limits(
                region="brazil"
            )
        """
        # Import local para evitar circular
        from .geographic_utils import GeographicUtils

        # Determinar região
        if region is None and lat is not None and lon is not None:
            detected_region = GeographicUtils.get_region(lat, lon)
            region_lower = detected_region.lower()
        elif region is not None:
            region_lower = region.lower()
        else:
            region_lower = "global"

        # Mapear região para limites
        if region_lower not in cls.REGIONAL_LIMITS:
            logger.warning(
                f"Região '{region_lower}' não reconhecida. "
                f"Usando limites globais."
            )
            region_lower = "global"

        return cls.REGIONAL_LIMITS[region_lower]

    @classmethod
    def is_valid_temperature(
        cls,
        temp: float | None,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Valida temperatura em °C.

        Args:
            temp: Temperatura em °C
            lat: Latitude (para detecção de região)
            lon: Longitude (para detecção de região)
            region: Região explícita (sobrescreve detecção)
        """
        if temp is None:
            return True
        limits = cls.get_validation_limits(lat, lon, region)
        temp_min, temp_max = limits["temperature"]
        is_valid = temp_min <= temp <= temp_max

        # Registrar erro em Prometheus
        if not is_valid and PROMETHEUS_AVAILABLE:
            from .geographic_utils import GeographicUtils

            detected_region = (
                region
                if region
                else (
                    GeographicUtils.get_region(lat, lon)
                    if lat and lon
                    else "global"
                )
            )
            VALIDATION_ERRORS.labels(
                region=detected_region, variable="temperature"
            ).inc()

        return is_valid

    @classmethod
    def is_valid_humidity(
        cls,
        humidity: float | None,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Valida umidade relativa em %.
        """
        if humidity is None:
            return True
        limits = cls.get_validation_limits(lat, lon, region)
        hum_min, hum_max = limits["humidity"]
        return hum_min <= humidity <= hum_max

    @classmethod
    def is_valid_wind_speed(
        cls,
        wind: float | None,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Valida velocidade do vento em m/s.
        """
        if wind is None:
            return True
        limits = cls.get_validation_limits(lat, lon, region)
        wind_min, wind_max = limits["wind"]
        return wind_min <= wind <= wind_max

    @classmethod
    def is_valid_precipitation(
        cls,
        precip: float | None,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Valida precipitação em mm.
        """
        if precip is None:
            return True
        limits = cls.get_validation_limits(lat, lon, region)
        precip_min, precip_max = limits["precipitation"]
        return precip_min <= precip <= precip_max

    @classmethod
    def is_valid_solar_radiation(
        cls,
        solar: float | None,
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Valida radiação solar em MJ/m²/dia.
        """
        if solar is None:
            return True
        limits = cls.get_validation_limits(lat, lon, region)
        solar_min, solar_max = limits["solar"]
        return solar_min <= solar <= solar_max

    @classmethod
    def validate_daily_data(
        cls,
        data: dict[str, Any],
        lat: float | None = None,
        lon: float | None = None,
        region: str | None = None,
    ) -> bool:
        """
        Valida conjunto completo de dados diários com limites regionais.

        Args:
            data: Dicionário com dados meteorológicos diários
            lat: Latitude (para detecção de região)
            lon: Longitude (para detecção de região)
            region: Região explícita ("global", "brazil", "usa", "nordic")

        Returns:
            True se todos os campos válidos estão dentro dos limites

        Exemplo:
            >>> data = {
            ...     'temp_max': 35.0,
            ...     'temp_min': 20.0,
            ...     'precipitation_sum': 10.5
            ... }
            >>> valid = WeatherValidationUtils.validate_daily_data(
            ...     data, lat=-23.5505, lon=-46.6333
            ... )
            >>> print(valid)
            True
        """
        validations = [
            cls.is_valid_temperature(data.get("temp_max"), lat, lon, region),
            cls.is_valid_temperature(data.get("temp_min"), lat, lon, region),
            cls.is_valid_temperature(data.get("temp_mean"), lat, lon, region),
            cls.is_valid_humidity(data.get("humidity_mean"), lat, lon, region),
            cls.is_valid_wind_speed(
                data.get("wind_speed_2m_mean"), lat, lon, region
            ),
            cls.is_valid_precipitation(
                data.get("precipitation_sum"), lat, lon, region
            ),
            cls.is_valid_solar_radiation(
                data.get("solar_radiation"), lat, lon, region
            ),
        ]
        return all(validations)


class WeatherAggregationUtils:
    """
    Utilitários para agregação de dados meteorológicos.

    Métodos comuns para agregar dados horários em diários
    seguindo convenções meteorológicas padrão.
    """

    @staticmethod
    def aggregate_temperature(
        values: list[float], method: str = "mean"
    ) -> float | None:
        """
        Agrega valores de temperatura.

        Args:
            values: Lista de temperaturas
            method: 'mean', 'max', 'min'

        Returns:
            Temperatura agregada ou None
        """
        if not values:
            return None

        valid_values = [v for v in values if v is not None]
        if not valid_values:
            return None

        if method == "mean":
            return float(np.mean(valid_values))
        elif method == "max":
            return float(np.max(valid_values))
        elif method == "min":
            return float(np.min(valid_values))
        else:
            logger.warning(f"Unknown method: {method}, using mean")
            return float(np.mean(valid_values))

    @staticmethod
    def aggregate_precipitation(values: list[float]) -> float | None:
        """
        Agrega precipitação (sempre soma).

        Args:
            values: Lista de precipitações horárias

        Returns:
            Precipitação total ou None
        """
        if not values:
            return None

        valid_values = [v for v in values if v is not None]
        if not valid_values:
            return None

        return float(np.sum(valid_values))

    @staticmethod
    def safe_division(
        numerator: float | None, denominator: float | None
    ) -> float | None:
        """
        Divisão segura que retorna None se inputs inválidos.

        Args:
            numerator: Numerador
            denominator: Denominador

        Returns:
            Resultado da divisão ou None
        """
        if numerator is None or denominator is None:
            return None
        if denominator == 0:
            return None
        return numerator / denominator

    @staticmethod
    def parse_rfc1123_date(date_str: str | None) -> datetime | None:
        """
        Parse RFC 1123 date format from HTTP headers.

        Used by weather API clients to parse Last-Modified and Expires headers.

        Args:
            date_str: Date string in RFC 1123 format
                     (e.g., "Tue, 16 Jun 2020 12:13:49 GMT")

        Returns:
            Parsed datetime (timezone-aware UTC) or None if parsing fails

        Example:
            >>> from weather_utils import WeatherAggregationUtils
            >>> dt = WeatherAggregationUtils.parse_rfc1123_date(
            ...     "Tue, 16 Jun 2020 12:13:49 GMT"
            ... )
            >>> print(dt)
            2020-06-16 12:13:49+00:00
        """
        if not date_str:
            return None
        try:
            dt = parsedate_to_datetime(date_str)
            # Ensure timezone-aware (UTC)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception as e:
            logger.warning(f"Failed to parse RFC1123 date '{date_str}': {e}")
            return None

    @staticmethod
    def calculate_cache_ttl(
        expires: datetime | None, default_ttl: int = 3600
    ) -> int:
        """
        Calculate cache TTL from Expires header.

        Used by weather API clients to determine how long to cache responses.

        Args:
            expires: Expiration datetime from Expires header
            default_ttl: Default TTL in seconds if no Expires header
                        (default: 3600 = 1 hour)

        Returns:
            TTL in seconds (min: 60s, max: 86400s = 24h)

        Example:
            >>> from datetime import datetime, timezone, timedelta
            >>> expires = datetime.now(timezone.utc) + timedelta(hours=2)
            >>> ttl = WeatherAggregationUtils.calculate_cache_ttl(expires)
            >>> print(f"Cache for {ttl} seconds")
            Cache for 7200 seconds
        """
        if not expires:
            return default_ttl

        now = datetime.now(timezone.utc)
        # Ensure expires is timezone-aware (UTC)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)

        ttl_seconds = int((expires - now).total_seconds())

        # Ensure TTL is positive and reasonable
        if ttl_seconds <= 0:
            return 60  # Minimum 1 minute
        if ttl_seconds > 86400:  # Max 24 hours
            return 86400

        return ttl_seconds

    @staticmethod
    def aggregate_hourly_to_daily(
        timeseries: list[dict[str, Any]],
        start_date: datetime,
        end_date: datetime,
        field_mapping: dict[str, str],
        timezone_utils=None,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Aggregate hourly weather data into daily buckets.

        Generic aggregation function used by multiple weather API clients
        (MET Norway, Open-Meteo, NWS) to convert hourly forecasts into
        daily data.

        Args:
            timeseries: List of hourly data points with 'time' and data
                       fields
            start_date: Start date for aggregation (timezone-aware)
            end_date: End date for aggregation (timezone-aware)
            field_mapping: Mapping of API field names to internal names
                          e.g., {'air_temperature': 'temperature_2m'}
            timezone_utils: Optional TimezoneUtils instance for timezone
                           handling (if None, uses datetime.date() for
                           grouping)

        Returns:
            Dictionary mapping dates (YYYY-MM-DD) to lists of hourly data

        Example:
            >>> from datetime import datetime, timezone
            >>> timeseries = [
            ...     {'time': '2024-01-15T12:00:00Z', 'air_temperature': 20.5},
            ...     {'time': '2024-01-15T13:00:00Z', 'air_temperature': 21.0},
            ... ]
            >>> result = WeatherAggregationUtils.aggregate_hourly_to_daily(
            ...     timeseries=timeseries,
            ...     start_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            ...     end_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
            ...     field_mapping={'air_temperature': 'temperature_2m'}
            ... )
            >>> print(result.keys())
            dict_keys(['2024-01-15'])
        """
        daily_data: dict[str, list[dict[str, Any]]] = {}

        for entry in timeseries:
            try:
                time_str = entry.get("time")
                if not time_str:
                    continue

                # Parse timestamp
                if isinstance(time_str, str):
                    # Handle ISO 8601 format
                    if "T" in time_str:
                        dt = datetime.fromisoformat(
                            time_str.replace("Z", "+00:00")
                        )
                    else:
                        dt = datetime.fromisoformat(time_str)
                elif isinstance(time_str, datetime):
                    dt = time_str
                else:
                    logger.warning(f"Invalid time format: {time_str}")
                    continue

                # Make timezone-aware if needed
                if timezone_utils and hasattr(timezone_utils, "make_aware"):
                    dt = timezone_utils.make_aware(dt)
                elif dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                # Filter by date range
                if not (start_date <= dt <= end_date):
                    continue

                # Extract date key (YYYY-MM-DD)
                date_key = dt.date().isoformat()

                # Initialize daily bucket
                if date_key not in daily_data:
                    daily_data[date_key] = []

                # Map fields to internal names
                mapped_entry = {"time": dt}
                for api_field, internal_field in field_mapping.items():
                    if api_field in entry:
                        value = entry[api_field]
                        # Handle nested data structures
                        if isinstance(value, dict):
                            mapped_entry[internal_field] = value
                        else:
                            mapped_entry[internal_field] = value

                daily_data[date_key].append(mapped_entry)

            except Exception as e:
                logger.warning(f"Error processing hourly entry: {e}")
                continue

        return daily_data


class CacheUtils:
    """
    Utilitários para cache de respostas HTTP de APIs climáticas.

    Centraliza parsing de headers HTTP e cálculo de TTL para cache.
    Usado por clientes como MET Norway para implementar conditional requests.
    """

    @staticmethod
    def parse_rfc1123_date(header: str | None) -> datetime | None:
        """
        Parse RFC1123 date format (usado em Expires/Last-Modified headers).

        Args:
            header: Header string (e.g., "Tue, 16 Jun 2020 12:13:49 GMT")

        Returns:
            Datetime timezone-aware UTC ou None

        Exemplo:
            >>> expires = CacheUtils.parse_rfc1123_date(
            ...     "Tue, 16 Jun 2020 12:13:49 GMT"
            ... )
            >>> print(expires)
            2020-06-16 12:13:49+00:00
        """
        if not header:
            return None
        try:
            dt = datetime.strptime(header, "%a, %d %b %Y %H:%M:%S GMT")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning(f"Invalid RFC1123 date: {header}")
            return None

    @staticmethod
    def calculate_cache_ttl(
        expires_dt: datetime | None, default_ttl: int = 3600
    ) -> int:
        """
        Calcula TTL em segundos a partir de Expires datetime.

        Args:
            expires_dt: Datetime de expiração (timezone-aware)
            default_ttl: TTL padrão se expires_dt for None (default: 3600s)

        Returns:
            TTL em segundos (min: 60s, max: 86400s = 24h)

        Exemplo:
            >>> from datetime import datetime, timezone, timedelta
            >>> expires = datetime.now(timezone.utc) + timedelta(hours=2)
            >>> ttl = CacheUtils.calculate_cache_ttl(expires)
            >>> print(f"TTL: {ttl}s")
            TTL: 7200s
        """
        if not expires_dt:
            return default_ttl

        now = datetime.now(timezone.utc)
        # Ensure timezone-aware
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)

        ttl = int((expires_dt - now).total_seconds())
        # Cap entre 60s e 86400s (24h)
        return max(60, min(ttl, 86400))


class METNorwayAggregationUtils:
    """
    Utilitários especializados para agregação de dados MET Norway.

    Movido de met_norway_client.py para centralizar lógica de agregação
    e evitar duplicação de código.

    Responsabilidades:
    - Agregar dados horários em diários
    - Calcular estatísticas (mean, max, min, sum)
    - Validar consistência de dados agregados
    """

    @staticmethod
    def aggregate_hourly_to_daily(
        timeseries: List[Dict[str, Any]],
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Agrega dados horários MET Norway em buckets diários.

        Args:
            timeseries: Lista de entradas horárias da API
            start_date: Data inicial (timezone-aware)
            end_date: Data final (timezone-aware)

        Returns:
            Dict mapeando date -> dados agregados brutos

        Exemplo:
            >>> daily_raw = METNorwayAggregationUtils
            ...     .aggregate_hourly_to_daily(
            ...         timeseries, start_date, end_date
            ...     )
            >>> print(daily_raw.keys())
            dict_keys([datetime.date(2024, 1, 15), ...])
        """
        from .geographic_utils import TimezoneUtils

        tz_utils = TimezoneUtils()
        daily_data: Dict[Any, Dict[str, Any]] = defaultdict(
            lambda: {
                "temp_values": [],
                "humidity_values": [],
                "wind_speed_values": [],
                "precipitation_1h": [],
                "precipitation_6h": [],
                "temp_max_6h": [],
                "temp_min_6h": [],
                "count": 0,
            }
        )

        # Ensure timezone-aware dates
        if start_date.tzinfo is None:
            start_date = tz_utils.make_aware(start_date)
        if end_date.tzinfo is None:
            end_date = tz_utils.make_aware(end_date)

        for entry in timeseries:
            try:
                time_str = entry.get("time")
                if not time_str:
                    continue

                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                date_key = dt.date()

                # Filtrar por período usando comparação segura
                if not (start_date <= dt <= end_date):
                    continue

                day_data = daily_data[date_key]

                # Extrair valores instantâneos
                instant = (
                    entry.get("data", {}).get("instant", {}).get("details", {})
                )

                # Temperatura
                if (temp := instant.get("air_temperature")) is not None:
                    day_data["temp_values"].append(temp)

                # Umidade
                if (humidity := instant.get("relative_humidity")) is not None:
                    day_data["humidity_values"].append(humidity)

                # Vento
                if (wind_speed := instant.get("wind_speed")) is not None:
                    day_data["wind_speed_values"].append(wind_speed)

                # Precipitação 1h
                next_1h = (
                    entry.get("data", {})
                    .get("next_1_hours", {})
                    .get("details", {})
                )
                precip_1h = next_1h.get("precipitation_amount")
                if precip_1h is not None:
                    day_data["precipitation_1h"].append(precip_1h)

                # Precipitação 6h
                next_6h = (
                    entry.get("data", {})
                    .get("next_6_hours", {})
                    .get("details", {})
                )
                precip_6h = next_6h.get("precipitation_amount")
                if precip_6h is not None:
                    day_data["precipitation_6h"].append(precip_6h)

                # Temperaturas extremas 6h
                temp_max = next_6h.get("air_temperature_max")
                if temp_max is not None:
                    day_data["temp_max_6h"].append(temp_max)
                temp_min = next_6h.get("air_temperature_min")
                if temp_min is not None:
                    day_data["temp_min_6h"].append(temp_min)

                day_data["count"] += 1

            except Exception as e:
                logger.warning(
                    f"Erro processando entrada horária MET Norway: {e}"
                )
                continue

        return dict(daily_data)

    @staticmethod
    def calculate_daily_aggregations(
        daily_raw_data: Dict[Any, Dict[str, Any]],
        weather_utils: WeatherConversionUtils,
    ) -> List[Any]:
        """
        Calcula agregações diárias finais (mean, max, min, sum).

        Args:
            daily_raw_data: Dados brutos agrupados por data
            weather_utils: Instância de WeatherConversionUtils

        Returns:
            Lista de registros diários agregados

        Melhorias:
        - Precipitação 6h: soma ponderada se múltiplos valores
        - Conversão de vento 10m → 2m usando FAO-56
        - Logging detalhado com logger.bind
        """
        result = []

        for date_key, day_values in daily_raw_data.items():
            try:
                # Temperatura média
                temp_mean = (
                    float(np.nanmean(day_values["temp_values"]))
                    if day_values["temp_values"]
                    else None
                )

                # Temperaturas extremas: preferir 6h, fallback instant
                temp_max = (
                    float(np.nanmax(day_values["temp_max_6h"]))
                    if day_values["temp_max_6h"]
                    else (
                        float(np.nanmax(day_values["temp_values"]))
                        if day_values["temp_values"]
                        else None
                    )
                )

                temp_min = (
                    float(np.nanmin(day_values["temp_min_6h"]))
                    if day_values["temp_min_6h"]
                    else (
                        float(np.nanmin(day_values["temp_values"]))
                        if day_values["temp_values"]
                        else None
                    )
                )

                # Umidade média
                humidity_mean = (
                    float(np.nanmean(day_values["humidity_values"]))
                    if day_values["humidity_values"]
                    else None
                )

                # Vento: converter 10m → 2m usando FAO-56
                wind_10m_mean = (
                    float(np.nanmean(day_values["wind_speed_values"]))
                    if day_values["wind_speed_values"]
                    else None
                )
                wind_2m_mean = (
                    weather_utils.convert_wind_10m_to_2m(wind_10m_mean)
                    if wind_10m_mean is not None
                    else None
                )

                # Precipitação: priorizar 1h, fallback 6h ponderado
                if day_values["precipitation_1h"]:
                    precipitation_sum = float(
                        np.sum(day_values["precipitation_1h"])
                    )
                elif day_values["precipitation_6h"]:
                    # MELHORIA: Soma ponderada se múltiplos valores
                    if len(day_values["precipitation_6h"]) > 1:
                        # Média dos valores 6h (assume overlap)
                        precipitation_sum = float(
                            np.mean(day_values["precipitation_6h"])
                        )
                    else:
                        # Valor único: usar direto
                        precipitation_sum = float(
                            day_values["precipitation_6h"][0]
                        )
                    logger.bind(date=date_key).debug(
                        f"Precip 6h: {len(day_values['precipitation_6h'])} "
                        f"valores → {precipitation_sum:.2f}mm"
                    )
                else:
                    precipitation_sum = 0.0

                # Criar registro diário (dict genérico)
                daily_record = {
                    "date": date_key,
                    "temp_max": temp_max,
                    "temp_min": temp_min,
                    "temp_mean": temp_mean,
                    "humidity_mean": humidity_mean,
                    "precipitation_sum": precipitation_sum,
                    "wind_speed_2m_mean": wind_2m_mean,
                }

                result.append(daily_record)

            except Exception as e:
                logger.bind(date=date_key).error(f"Erro agregando dia: {e}")
                continue

        # Ordenar por data
        result.sort(key=lambda x: x["date"])
        return result

    @staticmethod
    def validate_daily_data(daily_data: List[Dict[str, Any]]) -> bool:
        """
        Valida consistência dos dados diários agregados.

        Args:
            daily_data: Lista de registros diários (dicts)

        Returns:
            True se dados consistentes, False caso contrário

        Validações:
        - temp_max >= temp_min
        - 0 <= humidity <= 100
        - precipitation >= 0
        """
        if not daily_data:
            logger.warning("Dados diários vazios")
            return False

        issues = []

        for record in daily_data:
            date = record.get("date")

            # Verificar temperaturas
            temp_max = record.get("temp_max")
            temp_min = record.get("temp_min")
            if (
                temp_max is not None
                and temp_min is not None
                and temp_max < temp_min
            ):
                issues.append(
                    f"Temperatura inconsistente em {date}: "
                    f"max={temp_max} < min={temp_min}"
                )

            # Verificar umidade
            humidity = record.get("humidity_mean")
            if humidity is not None and not (0 <= humidity <= 100):
                issues.append(f"Umidade fora do range em {date}: {humidity}%")

            # Verificar precipitação
            precip = record.get("precipitation_sum")
            if precip is not None and precip < 0:
                issues.append(f"Precipitação negativa em {date}: {precip}mm")

        if issues:
            for issue in issues:
                logger.bind(validation="failed").warning(issue)
            return False

        logger.bind(validation="passed").debug(
            f"Dados diários validados: {len(daily_data)} registros OK"
        )
        return True


# ✅ NOTA: TimezoneUtils foi movido para geographic_utils.py
# para evitar importação circular (weather_utils usa geographic_utils)


class ElevationUtils:
    """
    Utilitários para cálculos dependentes de elevação (FAO-56).

    ⚠️ IMPORTANTE: Elevação precisa é CRÍTICA para acurácia do ETo!

    Impacto da elevação nos cálculos FAO-56:

    1. **Pressão Atmosférica (P)**:
       - Varia ~12% por 1000m de elevação
       - Exemplo: Nível do mar (0m) = 101.3 kPa
                  Brasília (1172m) = 87.8 kPa (-13.3%)
                  La Paz (3640m) = 65.5 kPa (-35.3%)

    2. **Constante Psicrométrica (γ)**:
       - Proporcional à pressão atmosférica
       - γ = 0.665 × 10^-3 × P
       - Afeta diretamente o termo aerodinâmico do ETo

    3. **Radiação Solar**:
       - Aumenta ~10% por 1000m (menos atmosfera)
       - Afeta componente radiativo do ETo

    📊 **Precisão da Elevação**:
    - Open-Meteo: ~7-30m (aproximado)
    - OpenTopoData: ~1m (SRTM 30m/ASTER 30m)
    - Diferença: até 30m pode causar erro de ~0.3% no ETo

    💡 **Uso Recomendado**:
    Em eto_services.py:
        1. Buscar elevação precisa: OpenTopoClient.get_elevation()
        2. Calcular fatores: ElevationUtils.get_elevation_correction_factor()
        3. Passar fatores para calculate_et0()

    Referências:
        Allen et al. (1998). FAO-56 Irrigation and Drainage Paper 56.
        Capítulo 3: Equações 7, 8 (Pressão e Gamma).
    """

    @staticmethod
    def calculate_atmospheric_pressure(elevation: float) -> float:
        """
        Calcula pressão atmosférica a partir da elevação (FAO-56 Eq. 7).

        Fórmula:
        P = 101.3 × [(293 - 0.0065 × z) / 293]^5.26

        Args:
            elevation: Elevação em metros

        Returns:
            Pressão atmosférica em kPa

        Raises:
            ValueError: Se elevação < -1000m (limite físico)

        Referência:
            Allen et al. (1998). FAO-56, Capítulo 3, Equação 7, página 31.
        """
        # Validação: limite físico (Mar Morto: -430m)
        if elevation < -1000:
            raise ValueError(
                f"Elevation too low: {elevation}m. Minimum: -1000m"
            )

        return 101.3 * ((293.0 - 0.0065 * elevation) / 293.0) ** 5.26

    @staticmethod
    def calculate_psychrometric_constant(elevation: float) -> float:
        """
        Calcula constante psicrométrica a partir da elevação (FAO-56 Eq. 8).

        Fórmula:
        γ = 0.665 × 10^-3 × P

        onde P é a pressão atmosférica (kPa) calculada da elevação.

        Args:
            elevation: Elevação em metros

        Returns:
            Constante psicrométrica (kPa/°C)
        """
        pressure = ElevationUtils.calculate_atmospheric_pressure(elevation)
        return 0.000665 * pressure

    @staticmethod
    def adjust_solar_radiation_for_elevation(
        radiation_sea_level: float,
        elevation: float,
    ) -> float:
        """
        Ajusta radiação solar para elevação.

        Radiação solar aumenta ~10% por 1000m de elevação
        devido à menor absorção atmosférica.

        Args:
            radiation_sea_level: Radiação ao nível do mar (MJ/m²/dia)
            elevation: Elevação em metros

        Returns:
            Radiação ajustada (MJ/m²/dia)

        Nota:
            Esta é uma aproximação. FAO-56 usa Ra (extraterrestre)
            que já considera elevação via latitude e dia do ano.
        """
        factor = 1.0 + (elevation / 1000.0) * 0.10
        return radiation_sea_level * factor

    @staticmethod
    def clear_sky_radiation(Ra: np.ndarray, elevation: float) -> np.ndarray:
        """
        Calcula a radiação solar em céu claro (Rso) - FAO-56 Eq. 37.

        Radiação solar que seria recebida na ausência de nuvens.
        Usado para calcular o fator de cobertura de nuvens (Rs/Rso).

        Args:
            Ra: Radiação extraterrestre (MJ/m²/dia) - array ou escalar
            elevation: Elevação do local (m)

        Returns:
            Rso: Radiação em céu claro (MJ/m²/dia) - array ou escalar
        """
        Rso = (0.75 + 2e-5 * elevation) * Ra
        return Rso

    @staticmethod
    def net_longwave_radiation(
        Rs: np.ndarray,
        Ra: np.ndarray,
        Tmax: np.ndarray,
        Tmin: np.ndarray,
        ea: np.ndarray,
        elevation: float,
    ) -> np.ndarray:
        """
        Calcula a radiação de onda longa líquida (Rnl) - FAO-56 Eq. 39.

        Radiação de onda longa emitida pela superfície e absorvida
        pela atmosfera. Inclui efeitos de temperatura, umidade,
        cobertura de nuvens e elevação.

        Args:
            Rs: Radiação solar global medida (MJ/m²/dia)
            Ra: Radiação extraterrestre (MJ/m²/dia)
            Tmax: Temperatura máxima diária (°C)
            Tmin: Temperatura mínima diária (°C)
            ea: Pressão real de vapor (kPa)
            elevation: Elevação do local (m)

        Returns:
            Rnl: Radiação de onda longa líquida (MJ/m²/dia)
        """
        # Constante de Stefan-Boltzmann [MJ K⁻⁴ m⁻² day⁻¹]
        sigma = 4.903e-9

        # Converter temperaturas para Kelvin
        Tmax_K = Tmax + 273.15
        Tmin_K = Tmin + 273.15

        # Radiação em céu claro (Rso) - FAO-56 Eq. 37
        Rso = ElevationUtils.clear_sky_radiation(Ra, elevation)

        # Fator de cobertura de nuvens (fcd) - FAO-56 Eq. 39
        # Razão Rs/Rso com proteção contra divisão por zero
        ratio = np.divide(Rs, Rso, out=np.ones_like(Rs), where=Rso > 1e-6)
        fcd = np.clip(1.35 * ratio - 0.35, 0.3, 1.0)

        # Radiação de onda longa líquida - FAO-56 Eq. 39
        Rnl = (
            sigma
            * ((Tmax_K**4 + Tmin_K**4) / 2)
            * (0.34 - 0.14 * np.sqrt(np.maximum(ea, 0.01)))
            * fcd
        )

        return Rnl

    @staticmethod
    def get_elevation_correction_factor(elevation: float) -> dict[str, float]:
        """
        Calcula todos os fatores de correção por elevação para ETo FAO-56.

        Usar elevação precisa de OpenTopoData (1m) para máxima
        acurácia. Elevações aproximadas (Open-Meteo ~7-30m) podem causar
        erros no ETo final.

        Args:
            elevation: Elevação em metros (preferencialmente de OpenTopoData)

        Returns:
            Dicionário com fatores de correção FAO-56:
            - pressure: Pressão atmosférica (kPa) - FAO-56 Eq. 7
            - gamma: Constante psicrométrica (kPa/°C) - FAO-56 Eq. 8
            - solar_factor: Fator multiplicativo para radiação solar
            - elevation: Elevação usada (m)
        """
        pressure = ElevationUtils.calculate_atmospheric_pressure(elevation)
        gamma = ElevationUtils.calculate_psychrometric_constant(elevation)
        solar_factor = 1.0 + (elevation / 1000.0) * 0.10

        return {
            "pressure": pressure,
            "gamma": gamma,
            "solar_factor": solar_factor,
            "elevation": elevation,
        }

    @staticmethod
    def compare_elevation_impact(
        elevation_precise: float,
        elevation_approx: float,
    ) -> dict[str, Any]:
        """
        Compara impacto de diferentes fontes de elevação nos fatores FAO-56.

        Use para quantificar a melhoria ao usar OpenTopoData (1m) vs
        Open-Meteo (~7-30m).

        Args:
            elevation_precise: Elevação precisa (OpenTopoData, 1m)
            elevation_approx: Elevação aproximada (Open-Meteo, ~7-30m)

        Returns:
            Dicionário com análise comparativa:
            - elevation_diff_m: Diferença absoluta (m)
            - pressure_diff_kpa: Diferença de pressão (kPa)
            - pressure_diff_pct: Diferença de pressão (%)
            - gamma_diff_pct: Diferença de gamma (%)
            - eto_impact_pct: Impacto estimado no ETo (%)

        Exemplo:
            > # OpenTopoData (preciso)
            > precise = 1172.0
            > # Open-Meteo (aproximado)
            > approx = 1150.0

            > impact = ElevationUtils.compare_elevation_impact(
                precise, approx
            )
            > print(f"Diferença elevação: {impact['elevation_diff_m']:.1f}m")
            > print(f"Impacto no ETo: {impact['eto_impact_pct']:.3f}%")
            Diferença elevação: 22.0m
            Impacto no ETo: 0.245%

        Interpretação:
            - < 10m: Impacto negligenciável (< 0.1% no ETo)
            - 10-30m: Impacto pequeno (0.1-0.3% no ETo)
            - > 30m: Impacto significativo (> 0.3% no ETo)
            - > 100m: Impacto crítico (> 1% no ETo)
        """
        factors_precise = ElevationUtils.get_elevation_correction_factor(
            elevation_precise
        )
        factors_approx = ElevationUtils.get_elevation_correction_factor(
            elevation_approx
        )

        elevation_diff = abs(elevation_precise - elevation_approx)
        pressure_diff = abs(
            factors_precise["pressure"] - factors_approx["pressure"]
        )
        pressure_diff_pct = (pressure_diff / factors_approx["pressure"]) * 100
        gamma_diff_pct = (
            abs(factors_precise["gamma"] - factors_approx["gamma"])
            / factors_approx["gamma"]
        ) * 100

        # Estimar impacto no ETo (aproximação baseada em sensibilidade)
        # ETo é ~50% sensível à pressão no termo aerodinâmico
        eto_impact_pct = pressure_diff_pct * 0.5

        return {
            "elevation_diff_m": elevation_diff,
            "elevation_precise_m": elevation_precise,
            "elevation_approx_m": elevation_approx,
            "pressure_precise_kpa": factors_precise["pressure"],
            "pressure_approx_kpa": factors_approx["pressure"],
            "pressure_diff_kpa": pressure_diff,
            "pressure_diff_pct": pressure_diff_pct,
            "gamma_diff_pct": gamma_diff_pct,
            "eto_impact_pct": eto_impact_pct,
            "recommendation": (
                "Negligenciável"
                if elevation_diff < 10
                else (
                    "Pequeno"
                    if elevation_diff < 30
                    else (
                        "Significativo" if elevation_diff < 100 else "Crítico"
                    )
                )
            ),
        }
