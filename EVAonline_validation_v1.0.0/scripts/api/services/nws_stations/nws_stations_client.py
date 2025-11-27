"""
Cliente Async para NWS Stations (National Weather Service / NOAA).
Licença: US Government Public Domain - Uso livre.

Este cliente fornece acesso às observações meteorológicas de estações
NWS para dados históricos e em tempo real.

NWS Stations API:
- Observações de ~1800 estações nos EUA
- Dados horários históricos disponíveis
- Sem autenticação necessária
- User-Agent OBRIGATÓRIO (conforme documentação)
- Rate limit: ~5 requests/second

Coverage: USA (bbox: -125°W to -66°W, 18°N to 71°N)
Extended: Inclui Alaska, Hawaii, territórios

Endpoints utilizados:
- /points/{lat},{lon}/stations → Lista estações próximas
- /stations/{stationId}/observations → Observações históricas
- /stations/{stationId}/observations/latest → Observação mais recente
- /stations/{stationId}/observations/{time} → Observação específica

Known Issues (2025):
- Observações podem ter delay de até 20 minutos (MADIS)
- Valores nulos em temp max/min fora do CST (Central Standard Time)
- Precipitação <0.4" pode ser reportada como 0 (rounding)

Workflow Típico:
1. find_nearest_stations(lat, lon) → Estações próximas ordenadas
2. get_station_observations(station_id, start, end) → Observações
3. Agregar para diário: mean (temp/humidity/wind), sum (precip)

API Reference: https://www.weather.gov/documentation/services-web-api
General FAQs: https://weather-gov.github.io/api/general-faqs
"""

import os
from datetime import datetime, timedelta
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field

# Import para detecção regional (fonte única)
try:
    from validation_logic_eto.api.services.geographic_utils import (
        GeographicUtils,
    )
except ImportError:
    from ..geographic_utils import GeographicUtils


class NWSStationsConfig(BaseModel):
    """
    Configuração da API NWS Stations.

    Attributes:
        base_url: URL base da API NWS
        timeout: Timeout para requisições HTTP (segundos)
        retry_attempts: Número de tentativas em caso de falha
        retry_delay: Delay base para retry exponencial (segundos)
        user_agent: User-Agent header (OBRIGATÓRIO pela API NWS)
        max_stations: Máximo de estações para retornar
        observation_delay_threshold: Threshold para log de delays (minutos)
    """

    base_url: str = "https://api.weather.gov"
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0
    user_agent: str = os.getenv(
        "NWS_USER_AGENT",
        (
            "EVAonline/1.0 "
            "(https://github.com/angelacunhasoares/EVAonline_SoftwareX)"
        ),
    )
    max_stations: int = 10  # Máximo de estações para buscar
    observation_delay_threshold: int = 20  # minutos


class NWSStation(BaseModel):
    """Dados de uma estação meteorológica NWS."""

    station_id: str = Field(..., description="ID da estação (ex: KJFK)")
    name: str = Field(..., description="Nome da estação")
    latitude: float = Field(..., description="Latitude")
    longitude: float = Field(..., description="Longitude")
    elevation_m: float | None = Field(None, description="Elevação (m)")
    timezone: str | None = Field(None, description="Fuso horário")
    distance_km: float | None = Field(
        None, description="Distância da coordenada de referência (km)"
    )


class NWSObservation(BaseModel):
    """
    Observação meteorológica de uma estação NWS.

    Representa uma observação horária com parâmetros meteorológicos essenciais.
    Nem todos os parâmetros são reportados por todas as estações.

    Known Issues:
        - Delays de até 20 minutos são normais (MADIS processing)
        - Valores nulos em temp max/min fora do CST
        - Precipitação <0.4" pode ser reportada como 0 (rounding)

    Attributes:
        - station_id: ID da estação (ex: KJFK)
        - timestamp: Timestamp da observação (timezone-aware):
           para agregação diária
        - temp_celsius: Temperatura atual em °C
        - temp_max_24h: Temperatura máxima últimas 24h em °C
        - temp_min_24h: Temperatura mínima últimas 24h em °C
        - dewpoint_celsius: Ponto de orvalho em °C (backup para calcular RH)
        - humidity_percent: Umidade relativa (0-100%)
        - wind_speed_ms: Velocidade do vento a 10m (m/s) - original da API
        - wind_speed_2m_ms: Velocidade do vento a 2m (m/s):
          convertido para FAO-56 PM
        - precipitation_1h_mm: Precipitação última hora em mm
        - is_delayed: Flag indicando se observação está atrasada (>20min):
          controle de qualidade
    """

    station_id: str = Field(..., description="ID da estação")
    timestamp: datetime = Field(..., description="Timestamp da observação")
    temp_celsius: float | None = Field(None, description="Temperatura (°C)")
    temp_max_24h: float | None = Field(
        None, description="Temperatura máxima últimas 24h (°C)"
    )
    temp_min_24h: float | None = Field(
        None, description="Temperatura mínima últimas 24h (°C)"
    )
    dewpoint_celsius: float | None = Field(
        None, description="Ponto de orvalho (°C) - backup para calcular RH"
    )
    humidity_percent: float | None = Field(
        None, description="Umidade relativa (%)"
    )
    wind_speed_ms: float | None = Field(
        None, description="Velocidade vento a 10m (m/s)"
    )
    wind_speed_2m_ms: float | None = Field(
        None,
        description="Velocidade vento a 2m (m/s) - convertido para FAO-56 PM",
    )
    precipitation_1h_mm: float | None = Field(
        None, description="Precipitação última hora (mm)"
    )
    is_delayed: bool = Field(
        default=False, description="Observação atrasada (>20min)"
    )


class NWSStationsClient:
    """
    Cliente assíncrono para NWS Stations API.

    Features:
    - Busca estações meteorológicas próximas
    - Observações históricas e em tempo real
    - Dados horários de alta qualidade
    - Domínio Público (sem restrições)
    - Cache Redis integrado (opcional)
    - Logs de known issues (delays, nulls, rounding)

    Coverage:
    - USA (incluindo Alaska, Hawaii, territórios)
    - Longitude: -125°W a -66°W
    - Latitude: 18°N a 71°N (extended bbox)

    Known Issues Monitorados:
    - Delays de até 20 minutos (MADIS processing)
    - Valores nulos em temp max/min fora do CST (Central Standard Time)
    - Precipitação <0.4" pode ser reportada como 0

    Workflow típico:
    1. find_nearest_stations(lat, lon) → Estações próximas ordenadas
    2. get_station_observations(station_id, start, end) → Observações
    3. Agregar para diário: mean (temp/humidity/wind), sum (precip)

    API Reference: https://www.weather.gov/documentation/services-web-api
    General FAQs: https://weather-gov.github.io/api/general-faqs
    """

    def __init__(
        self,
        config: NWSStationsConfig | None = None,
        cache: Any | None = None,
    ):
        """
        Inicializa cliente NWS Stations.

        Args:
            config: Configuração customizada (opcional)
            cache: ClimateCacheService (opcional, DI)
        """
        self.config = config or NWSStationsConfig()

        # Headers recomendados NWS
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/geo+json",
        }

        self.client = httpx.AsyncClient(
            timeout=self.config.timeout,
            headers=headers,
            follow_redirects=True,
        )
        self.cache = cache
        logger.info("✅ NWSStationsClient initialized")

    async def close(self):
        """Fecha conexão HTTP."""
        await self.client.aclose()
        logger.debug("NWSStationsClient connection closed")

    def is_in_coverage(self, lat: float, lon: float) -> bool:
        """
        Verifica se coordenadas estão na cobertura USA Continental.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            bool: True se dentro do bbox USA
        """
        in_bbox = GeographicUtils.is_in_usa(lat, lon)

        if not in_bbox:
            logger.warning(
                f"⚠️  Coordenadas ({lat}, {lon}) fora cobertura NWS USA"
            )

        return in_bbox

    async def find_nearest_stations(
        self, lat: float, lon: float, limit: int | None = None
    ) -> list[NWSStation]:
        """
        Busca estações meteorológicas próximas.

        Args:
            lat: Latitude
            lon: Longitude
            limit: Número máximo de estações (padrão: config.max_stations)

        Returns:
            Lista de estações ordenadas por proximidade

        Raises:
            ValueError: Se coordenadas fora de cobertura
            httpx.HTTPError: Erro de comunicação com API
        """
        if not self.is_in_coverage(lat, lon):
            msg = f"Coordenadas ({lat}, {lon}) fora de cobertura NWS"
            raise ValueError(msg)

        limit = limit or self.config.max_stations

        logger.info(f"🔍 Buscando estações NWS próximas a ({lat}, {lon})")

        try:
            # Endpoint para buscar estações próximas
            url = f"{self.config.base_url}/points/{lat:.4f},{lon:.4f}/stations"

            response = await self.client.get(url)
            response.raise_for_status()

            data = response.json()
            features = data.get("features", [])

            stations = []
            for feature in features[:limit]:
                props = feature.get("properties", {})
                geom = feature.get("geometry", {})
                coords = geom.get("coordinates", [None, None])

                station = NWSStation(
                    station_id=props.get("stationIdentifier", ""),
                    name=props.get("name", "Unknown"),
                    latitude=coords[1] if len(coords) > 1 else lat,
                    longitude=coords[0] if len(coords) > 0 else lon,
                    elevation_m=props.get("elevation", {}).get("value"),
                    timezone=props.get("timeZone"),
                    distance_km=None,  # Calculado depois se necessário
                )
                stations.append(station)

            logger.info(f"✅ Encontradas {len(stations)} estações NWS")
            return stations

        except httpx.HTTPError as e:
            logger.error(f"❌ Erro ao buscar estações NWS: {e}")
            raise

    async def get_station_observations(
        self,
        station_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[NWSObservation]:
        """
        Busca observações de uma estação NWS.

        IMPORTANTE: Este cliente ASSUME que:
        - Coordenadas validadas em climate_validation.py
        - Cobertura USA validada em climate_source_selector.py
        - Period validado em climate_source_availability.py
        Este cliente APENAS busca dados, sem re-validar.

        Args:
            station_id: ID da estação (ex: "KJFK")
            start_date: Data inicial (opcional, padrão: últimas 24h)
            end_date: Data final (opcional, padrão: agora)

        Returns:
            Lista de observações horárias

        Raises:
            httpx.HTTPError: Erro de comunicação com API
        """
        # Defaults: últimas 24 horas
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=1)

        logger.info(
            f"📊 Buscando observações NWS: {station_id} "
            f"({start_date.date()} a {end_date.date()})"
        )

        try:
            # Endpoint de observações
            url = f"{self.config.base_url}/stations/{station_id}/observations"

            # Parâmetros de query (remover microsegundos para API NWS)
            params = {
                "start": start_date.replace(microsecond=0).isoformat() + "Z",
                "end": end_date.replace(microsecond=0).isoformat() + "Z",
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            features = data.get("features", [])

            observations = []
            for feature in features:
                props = feature.get("properties", {})

                # Parse timestamp
                timestamp_str = props.get("timestamp", "")
                try:
                    timestamp = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    logger.warning(f"Invalid timestamp: {timestamp_str}")
                    continue

                # Check for observation delay (known issue: up to 20min)
                now = datetime.now(timestamp.tzinfo)
                delay_minutes = (now - timestamp).total_seconds() / 60
                is_delayed = (
                    delay_minutes > self.config.observation_delay_threshold
                )

                if is_delayed:
                    logger.warning(
                        f"⚠️  Observação atrasada: {delay_minutes:.1f} min "
                        f"(MADIS processing delay)"
                    )

                # Extrair valores com unidades
                temp = self._extract_value(props.get("temperature"))
                temp_max_24h = self._extract_value(
                    props.get("maxTemperatureLast24Hours")
                )
                temp_min_24h = self._extract_value(
                    props.get("minTemperatureLast24Hours")
                )
                dewpoint = self._extract_value(props.get("dewpoint"))
                humidity = self._extract_value(props.get("relativeHumidity"))

                # Log null values (known issue: max/min outside CST)
                if temp is None:
                    logger.warning(
                        "⚠️  Temperatura nula - possível issue "
                        "max/min fora CST"
                    )

                if temp_max_24h is None or temp_min_24h is None:
                    logger.debug(
                        "⚠️  Temp max/min 24h nulas - issue conhecido fora CST"
                    )

                # Precipitação com log de rounding issue
                precip = self._extract_value(
                    props.get("precipitationLastHour")
                )
                if precip is not None and 0 < precip < 10:
                    logger.warning(
                        f"⚠️  Precipitação {precip}mm pode ter rounding down "
                        f'(<0.4" issue)'
                    )

                # Extrair e converter vento de 10m para 2m
                wind_10m = self._extract_value(props.get("windSpeed"))
                wind_2m = self.convert_wind_10m_to_2m(wind_10m)

                obs = NWSObservation(
                    station_id=station_id,
                    timestamp=timestamp,
                    temp_celsius=temp,
                    temp_max_24h=temp_max_24h,
                    temp_min_24h=temp_min_24h,
                    dewpoint_celsius=dewpoint,
                    humidity_percent=humidity,
                    wind_speed_ms=wind_10m,
                    wind_speed_2m_ms=wind_2m,
                    precipitation_1h_mm=precip,
                    is_delayed=is_delayed,
                )
                observations.append(obs)

            logger.info(f"✅ Obtidas {len(observations)} observações NWS")
            return observations

        except httpx.HTTPError as e:
            logger.error(
                f"❌ Erro ao buscar observações NWS {station_id}: {e}"
            )
            raise

    async def get_latest_observation(
        self, station_id: str
    ) -> NWSObservation | None:
        """
        Busca observação mais recente de uma estação.

        Inclui checks para known issues (delays, nulls, rounding).

        Args:
            station_id: ID da estação

        Returns:
            Observação mais recente ou None se não disponível
        """
        logger.info(f"📡 Buscando observação mais recente: {station_id}")

        try:
            url = (
                f"{self.config.base_url}/stations/"
                f"{station_id}/observations/latest"
            )

            response = await self.client.get(url)
            response.raise_for_status()

            data = response.json()
            props = data.get("properties", {})

            # Parse timestamp
            timestamp_str = props.get("timestamp", "")
            timestamp = datetime.fromisoformat(
                timestamp_str.replace("Z", "+00:00")
            )

            # Check for delay
            now = datetime.now(timestamp.tzinfo)
            delay_minutes = (now - timestamp).total_seconds() / 60
            is_delayed = (
                delay_minutes > self.config.observation_delay_threshold
            )

            if is_delayed:
                logger.warning(
                    f"⚠️  Observação atrasada: {delay_minutes:.1f} min"
                )

            # Extract with checks
            temp = self._extract_value(props.get("temperature"))
            temp_max_24h = self._extract_value(
                props.get("maxTemperatureLast24Hours")
            )
            temp_min_24h = self._extract_value(
                props.get("minTemperatureLast24Hours")
            )

            if temp is None:
                logger.warning(
                    "⚠️  Temp nula - possível issue max/min fora CST"
                )

            precip = self._extract_value(props.get("precipitationLastHour"))
            if precip is not None and 0 < precip < 10:
                logger.warning(f"⚠️  Precip {precip}mm - possível rounding")

            # Extrair e converter vento de 10m para 2m
            wind_10m = self._extract_value(props.get("windSpeed"))
            wind_2m = self.convert_wind_10m_to_2m(wind_10m)

            obs = NWSObservation(
                station_id=station_id,
                timestamp=timestamp,
                temp_celsius=temp,
                temp_max_24h=temp_max_24h,
                temp_min_24h=temp_min_24h,
                dewpoint_celsius=self._extract_value(props.get("dewpoint")),
                humidity_percent=self._extract_value(
                    props.get("relativeHumidity")
                ),
                wind_speed_ms=wind_10m,
                wind_speed_2m_ms=wind_2m,
                precipitation_1h_mm=precip,
                is_delayed=is_delayed,
            )

            logger.info("✅ Observação mais recente obtida")
            return obs

        except httpx.HTTPError as e:
            logger.warning(
                f"⚠️  Não foi possível obter observação de {station_id}: {e}"
            )
            return None

    async def get_observation_by_time(
        self, station_id: str, observation_time: datetime
    ) -> NWSObservation | None:
        """
        Busca observação de um timestamp específico.

        Útil para obter dados históricos de dias específicos.

        Args:
            station_id: ID da estação
            observation_time: Timestamp específico (datetime)

        Returns:
            Observação do timestamp ou None se não disponível
        """
        logger.info(
            f"📊 Buscando observação: {station_id} "
            f"em {observation_time.isoformat()}"
        )

        try:
            # Format time for API
            time_str = observation_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            url = (
                f"{self.config.base_url}/stations/"
                f"{station_id}/observations/{time_str}"
            )

            response = await self.client.get(url)
            response.raise_for_status()

            data = response.json()
            props = data.get("properties", {})

            # Parse timestamp
            timestamp_str = props.get("timestamp", "")
            timestamp = datetime.fromisoformat(
                timestamp_str.replace("Z", "+00:00")
            )

            # Check delay
            now = datetime.now(timestamp.tzinfo)
            delay_minutes = (now - timestamp).total_seconds() / 60
            is_delayed = (
                delay_minutes > self.config.observation_delay_threshold
            )

            # Extract with checks
            temp = self._extract_value(props.get("temperature"))
            temp_max_24h = self._extract_value(
                props.get("maxTemperatureLast24Hours")
            )
            temp_min_24h = self._extract_value(
                props.get("minTemperatureLast24Hours")
            )
            precip = self._extract_value(props.get("precipitationLastHour"))

            # Extrair e converter vento de 10m para 2m
            wind_10m = self._extract_value(props.get("windSpeed"))
            wind_2m = self.convert_wind_10m_to_2m(wind_10m)

            obs = NWSObservation(
                station_id=station_id,
                timestamp=timestamp,
                temp_celsius=temp,
                temp_max_24h=temp_max_24h,
                temp_min_24h=temp_min_24h,
                dewpoint_celsius=self._extract_value(props.get("dewpoint")),
                humidity_percent=self._extract_value(
                    props.get("relativeHumidity")
                ),
                wind_speed_ms=wind_10m,
                wind_speed_2m_ms=wind_2m,
                precipitation_1h_mm=precip,
                is_delayed=is_delayed,
            )

            logger.info("✅ Observação obtida")
            return obs

        except httpx.HTTPError as e:
            logger.warning(f"⚠️  Observação não disponível: {e}")
            return None

    def _extract_value(self, data: dict | None) -> float | None:
        """
        Extrai valor numérico de objeto com unidade NWS.

        NWS retorna valores como: {"value": 20.5, "unitCode": "unit:degC"}

        Args:
            data: Dicionário com value e unitCode

        Returns:
            Valor numérico ou None
        """
        if data is None:
            return None

        value = data.get("value")
        if value is None:
            return None

        # Converter para float se necessário
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def convert_wind_10m_to_2m(wind_10m: float | None) -> float | None:
        """
        Converte velocidade do vento de 10m para 2m usando perfil logarítmico.

        Fórmula FAO-56 (Allen et al., 1998):
        u2 = uz × (4.87) / ln(67.8 × z - 5.42)

        onde:
        - u2 = velocidade do vento a 2m (m/s)
        - uz = velocidade do vento na altura z (m/s)
        - z = altura de medição (10m)
        - ln = logaritmo natural

        Para z=10m:
        u2 = u10 × 4.87 / ln(67.8×10 - 5.42)
        u2 = u10 × 4.87 / ln(672.58)
        u2 = u10 × 4.87 / 6.511
        u2 ≈ u10 × 0.748

        Referência: FAO Irrigation and Drainage Paper 56
        Chapter 3, Equation 47

        Args:
            wind_10m: Velocidade do vento a 10m (m/s)

        Returns:
            Velocidade do vento a 2m (m/s) ou None
        """
        if wind_10m is None:
            return None

        # Conversão direta usando fator 0.748 (pré-calculado)
        return wind_10m * 0.748

    async def health_check(self) -> bool:
        """
        Verifica se API NWS Stations está acessível.

        Returns:
            True se API responde, False caso contrário
        """
        try:
            # Testar com uma estação conhecida (JFK Airport)
            url = f"{self.config.base_url}/stations/KJFK"
            response = await self.client.get(url)
            response.raise_for_status()

            logger.info("✅ NWS Stations API: Healthy")
            return True

        except Exception as e:
            logger.error(f"❌ NWS Stations API health check failed: {e}")
            return False

    @staticmethod
    def get_data_availability_info() -> dict[str, Any]:
        """
        Retorna informações sobre disponibilidade de dados.

        Inclui known issues documentados.

        Returns:
            Dict com informações de cobertura, limites e issues
        """
        return {
            "source": "NWS Stations (NOAA)",
            "coverage": "USA (incluindo Alaska, Hawaii, territórios)",
            "stations": "~1800 estações ativas",
            "data_type": "Hourly observations",
            "bbox": {
                "lon_min": -180.0,
                "lon_max": -66.0,
                "lat_min": 18.0,
                "lat_max": 71.5,
            },
            "temporal_resolution": "Hourly",
            "update_frequency": "Real-time (continuous)",
            "typical_delay": "Up to 20 minutes (MADIS processing)",
            "license": "US Government Public Domain",
            "attribution": "National Weather Service / NOAA",
            "api_docs": (
                "https://www.weather.gov/documentation/services-web-api"
            ),
            "known_issues": {
                "observation_delay": "Up to 20 minutes normal (MADIS)",
                "null_temps": (
                    "Max/min temps may be null outside CST timezone"
                ),
                "precip_rounding": (
                    "Precipitation <0.4 inches may round down to 0"
                ),
                "station_variability": (
                    "Not all stations report all parameters"
                ),
            },
        }


# Factory function para compatibilidade
def create_nws_stations_client(
    config: NWSStationsConfig | None = None, cache: Any | None = None
) -> NWSStationsClient:
    """
    Factory function para criar NWSStationsClient.

    Args:
        config: Configuração customizada
        cache: Cache service

    Returns:
        NWSStationsClient configurado
    """
    return NWSStationsClient(config=config, cache=cache)
