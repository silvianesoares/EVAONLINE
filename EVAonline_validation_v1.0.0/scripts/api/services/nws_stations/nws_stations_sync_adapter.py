"""
Adapter síncrono para NWS Stations Client (National Weather Service).

Este adapter permite usar o cliente assíncrono NWS Stations em código síncrono,
facilitando a integração com data_download.py que usa Celery (síncrono).

Padrão seguido: NASAPowerSyncAdapter

Features:
- Conversão de dados horários NWS em agregações diárias (pandas)
- Monitoramento de known issues (delays, nulls, rounding)
- Filtragem de observações atrasadas (opcional)
- Logging detalhado de qualidade dos dados
- Cache Redis integrado (opcional)

Known Issues Tratados:
- Observações atrasadas (>20min MADIS delay) - filtradas opcionalmente
- Valores nulos em temperaturas (max/min fora CST) - skipados
- Precipitação <0.4" rounding down - mantida com warning

Usage:
    >>> adapter = NWSStationsSyncAdapter()
    >>> data = adapter.get_daily_data_sync(
    ...     lat=40.7128,  # NYC
    ...     lon=-74.0060,
    ...     start_date=datetime(2024, 10, 1),
    ...     end_date=datetime(2024, 10, 7)
    ... )
    >>> print(f"Obtidos {len(data)} registros de NWS")
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from loguru import logger

from .nws_stations_client import NWSStationsClient, NWSStationsConfig


class DailyNWSData:
    """Dados diários agregados de NWS (convertidos de dados horários)."""

    def __init__(
        self,
        date: datetime,
        temp_min: float | None = None,
        temp_max: float | None = None,
        temp_mean: float | None = None,
        humidity: float | None = None,
        wind_speed: float | None = None,
        solar_radiation: float | None = None,
        precipitation: float | None = None,
    ):
        self.date = date
        self.temp_min = temp_min
        self.temp_max = temp_max
        self.temp_mean = temp_mean
        self.humidity = humidity
        self.wind_speed = wind_speed
        self.solar_radiation = solar_radiation
        self.precipitation = precipitation


class NWSStationsSyncAdapter:
    """
    Adapter síncrono para NWSStationsClient assíncrono.

    Converte chamadas síncronas em assíncronas usando asyncio.run(),
    mantendo compatibilidade com código legacy (Celery tasks).

    Responsabilidades:
    - Interface síncrona simples
    - Conversão de dados horários NWS em agregações diárias (pandas)
    - Mapeamento de campos NWS → padrão EVAonline
    - Filtragem de observações atrasadas (opcional)
    - Logging detalhado de qualidade dos dados
    - Tratamento de erros gracioso

    NWS API Detalhes:
    - Retorna dados HORÁRIOS de estações meteorológicas
    - Precisamos agregar em DIÁRIOS usando pandas
    - Cobertura: USA Extended (incluindo Alaska, Hawaii)
    - Sem autenticação necessária
    - Known issues: delays (MADIS), nulls (CST), rounding (<0.4")

    Args:
        config: Configuração NWS Stations (opcional)
        cache: Cache service (opcional)
        filter_delayed: Filtrar observações atrasadas >20min (padrão: False)
    """

    def __init__(
        self,
        config: NWSStationsConfig | None = None,
        cache: Any | None = None,
        filter_delayed: bool = False,
    ):
        """
        Inicializa adapter.

        Args:
            config: Configuração NWS Stations (opcional)
            cache: Cache service (opcional)
            filter_delayed: Se True, remove observações com delay >20min
        """
        self.config = config or NWSStationsConfig()
        self.cache = cache
        self.filter_delayed = filter_delayed
        logger.info(
            f"NWSStationsSyncAdapter initialized "
            f"(filter_delayed={filter_delayed})"
        )

    def get_daily_data_sync(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
    ) -> list[DailyNWSData]:
        """
        Busca dados diários de forma síncrona.

        Internamente:
        1. Chama NWS API (retorna dados horários)
        2. Agrupa por dia
        3. Calcula min, max, média
        4. Retorna como DailyNWSData

        Args:
            lat: Latitude (-90 a 90, deve estar na cobertura USA)
            lon: Longitude (-180 a 180, deve estar na cobertura USA)
            start_date: Data inicial
            end_date: Data final

        Returns:
            List[DailyNWSData]: Dados diários

        Raises:
            ValueError: Se coordenadas fora de USA
            Exception: Se requisição falhar
        """
        logger.debug(
            f"NWS Sync request: lat={lat}, lon={lon}, "
            f"dates={start_date.date()} to {end_date.date()}"
        )

        # Executa função assíncrona de forma síncrona
        return asyncio.run(
            self._async_get_daily_data(
                lat=lat,
                lon=lon,
                start_date=start_date,
                end_date=end_date,
            )
        )

    async def _async_get_daily_data(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
    ) -> list[DailyNWSData]:
        """
        Método assíncrono interno.

        Fluxo:
        1. Cria cliente NWS Stations
        2. Valida cobertura
        3. Busca estação mais próxima
        4. Busca observações da estação
        5. Agrupa por dia
        6. Calcula agregações (min, max, média)
        7. Retorna como DailyNWSData
        """
        client = NWSStationsClient(config=self.config, cache=self.cache)

        try:
            # 1. Validar cobertura USA
            if not client.is_in_coverage(lat=lat, lon=lon):
                logger.warning(
                    f"⚠️  Coordenadas ({lat}, {lon}) "
                    f"fora da cobertura NWS (USA)"
                )
                msg = (
                    f"NWS: Coordenadas ({lat}, {lon}) "
                    f"fora da cobertura USA"
                )
                raise ValueError(msg)

            # 2. Buscar estações próximas
            logger.info(f"� Buscando estações NWS próximas: ({lat}, {lon})")
            stations = await client.find_nearest_stations(
                lat=lat, lon=lon, limit=1
            )

            if not stations:
                logger.warning("❌ Nenhuma estação NWS encontrada")
                return []

            station = stations[0]
            logger.info(
                f"📡 Usando estação: {station.station_id} " f"({station.name})"
            )

            # 3. Buscar observações da estação
            observations = await client.get_station_observations(
                station_id=station.station_id,
                start_date=start_date,
                end_date=end_date,
            )

            if not observations:
                logger.warning("❌ NWS retornou dados vazios")
                return []

            logger.info(f"✅ NWS: {len(observations)} observações horárias")

            # Filtrar observações atrasadas (se configurado)
            if self.filter_delayed:
                original_count = len(observations)
                observations = [
                    obs for obs in observations if not obs.is_delayed
                ]
                filtered_count = original_count - len(observations)
                if filtered_count > 0:
                    threshold = self.config.observation_delay_threshold
                    logger.warning(
                        f"⚠️  Filtradas {filtered_count} observações "
                        f"atrasadas (>{threshold}min)"
                    )

            # Log data quality
            temps = [
                o.temp_celsius
                for o in observations
                if o.temp_celsius is not None
            ]
            if len(observations) > 0:
                completeness = len(temps) / len(observations) * 100
                logger.info(
                    f"📊 Qualidade: {len(temps)}/{len(observations)} "
                    f"({completeness:.1f}%) "
                    f"temperaturas válidas"
                )
            else:
                logger.warning(
                    "⚠️  Nenhuma observação disponível após filtragem"
                )
                return []

            # 4. Agregar observações em diários usando pandas
            daily_data = self._aggregate_hourly_to_daily_pandas(observations)

            logger.info(
                f"✅ NWS sync: {len(daily_data)} dias agregados "
                f"(de {len(observations)} observações)"
            )

            return daily_data

        except Exception as e:
            logger.error(f"❌ Erro ao buscar dados NWS: {e}")
            raise

        finally:
            await client.close()

    def _aggregate_hourly_to_daily_pandas(
        self, hourly_data: list
    ) -> list[DailyNWSData]:
        """
        Agrupa observações horárias em diários usando pandas.

        Usa DataFrame.resample('D') para agregação eficiente.

        Calcula:
        - temp_min: mínimo do dia
        - temp_max: máximo do dia
        - temp_mean: média aritmética
        - humidity: média
        - wind_speed: média a 2m (convertido para FAO-56 PM)
        - solar_radiation: 0 (NWS não fornece)
        - precipitation: soma do dia

        Args:
            hourly_data: Lista de NWSObservation

        Returns:
            List[DailyNWSData]: Dados agregados por dia
        """
        if not hourly_data:
            return []

        # Converter para DataFrame pandas
        df_data = []
        for obs in hourly_data:
            df_data.append(
                {
                    "timestamp": obs.timestamp,
                    "temp_celsius": obs.temp_celsius,
                    "humidity_percent": obs.humidity_percent,
                    "wind_speed_2m_ms": obs.wind_speed_2m_ms,
                    "precipitation_1h_mm": obs.precipitation_1h_mm or 0.0,
                }
            )

        df = pd.DataFrame(df_data)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)

        # Agregar por dia usando resample
        daily = df.resample("D").agg(
            {
                "temp_celsius": ["min", "max", "mean"],
                "humidity_percent": "mean",
                "wind_speed_2m_ms": "mean",
                "precipitation_1h_mm": "sum",
            }
        )

        # Flatten multi-index columns
        daily.columns = [
            "_".join(col).strip("_") if col[1] else col[0]
            for col in daily.columns
        ]

        # Converter para DailyNWSData
        daily_results = []
        for date_idx, row in daily.iterrows():
            # Converter índice para datetime python
            # type: ignore - pandas retorna Timestamp que tem to_pydatetime()
            date_dt = date_idx.to_pydatetime()  # type: ignore[attr-defined]

            daily_record = DailyNWSData(
                date=date_dt,
                temp_min=row.get("temp_celsius_min"),
                temp_max=row.get("temp_celsius_max"),
                temp_mean=row.get("temp_celsius_mean"),
                humidity=row.get("humidity_percent"),
                wind_speed=row.get("wind_speed_2m_ms"),
                solar_radiation=0.0,  # NWS não fornece radiação solar
                precipitation=(
                    row.get("precipitation_1h_mm")
                    if row.get("precipitation_1h_mm", 0) > 0
                    else None
                ),
            )
            daily_results.append(daily_record)

        logger.debug(f"Agregados {len(daily_results)} dias usando pandas")
        return daily_results

    def _aggregate_hourly_to_daily(
        self, hourly_data: list
    ) -> list[DailyNWSData]:
        """
        Agrupa observações horárias em diários.

        Calcula:
        - temp_min: mínimo do dia
        - temp_max: máximo do dia
        - temp_mean: média aritmética
        - humidity: média
        - wind_speed: média
        - solar_radiation: 0 (NWS não fornece)
        - precipitation: soma do dia

        Args:
            hourly_data: Lista de NWSObservation

        Returns:
            List[DailyNWSData]: Dados agregados por dia
        """
        if not hourly_data:
            return []

        # Agrupar por dia
        daily_groups = {}

        for record in hourly_data:
            try:
                # Parse timestamp (ISO 8601)
                if isinstance(record.timestamp, str):
                    dt = datetime.fromisoformat(
                        record.timestamp.replace("Z", "+00:00")
                    )
                else:
                    dt = record.timestamp

                date_key = dt.date()

                if date_key not in daily_groups:
                    daily_groups[date_key] = {
                        "temps": [],
                        "humidities": [],
                        "wind_speeds": [],
                        "precip_sum": 0.0,
                        "date": dt,
                    }

                # Coletar valores (se não None)
                if record.temp_celsius is not None:
                    daily_groups[date_key]["temps"].append(record.temp_celsius)

                if record.humidity_percent is not None:
                    daily_groups[date_key]["humidities"].append(
                        record.humidity_percent
                    )

                # Usar vento a 2m (convertido para FAO-56 PM)
                if record.wind_speed_2m_ms is not None:
                    daily_groups[date_key]["wind_speeds"].append(
                        record.wind_speed_2m_ms
                    )

                if record.precipitation_1h_mm is not None:
                    daily_groups[date_key][
                        "precip_sum"
                    ] += record.precipitation_1h_mm

            except Exception as e:
                logger.warning(f"⚠️  Erro ao processar registro horário: {e}")
                continue

        # Calcular agregações
        daily_results = []

        for date_key in sorted(daily_groups.keys()):
            group = daily_groups[date_key]

            # Calcular stats
            temps = group["temps"]
            humidities = group["humidities"]
            wind_speeds = group["wind_speeds"]
            precip = group["precip_sum"]

            temp_min = min(temps) if temps else None
            temp_max = max(temps) if temps else None
            temp_mean = sum(temps) / len(temps) if temps else None
            humidity_mean = (
                sum(humidities) / len(humidities) if humidities else None
            )
            wind_mean = (
                sum(wind_speeds) / len(wind_speeds) if wind_speeds else None
            )

            daily_record = DailyNWSData(
                date=date_key,
                temp_min=temp_min,
                temp_max=temp_max,
                temp_mean=temp_mean,
                humidity=humidity_mean,
                wind_speed=wind_mean,
                solar_radiation=0.0,  # NWS não fornece radiação solar
                precipitation=precip if precip > 0 else None,
            )

            daily_results.append(daily_record)

        logger.debug(f"Agregados {len(daily_groups)} dias de dados NWS")

        return daily_results

    def health_check_sync(self) -> bool:
        """
        Health check síncrono.

        Testa conectividade com NWS API.

        Returns:
            bool: True se API está acessível
        """
        return asyncio.run(self._async_health_check())

    async def _async_health_check(self) -> bool:
        """
        Health check assíncrono interno.

        Testa com coordenadas padrão (NYC).
        """
        client = NWSStationsClient(config=self.config, cache=self.cache)

        try:
            # Teste com NYC (sempre em cobertura)
            stations = await client.find_nearest_stations(
                lat=40.7128, lon=-74.0060, limit=1
            )

            is_healthy = len(stations) > 0
            status_icon = "✅ OK" if is_healthy else "❌ FAIL"
            logger.info(f"🏥 NWS health check: {status_icon}")
            return is_healthy

        except Exception as e:
            logger.error(f"🏥 NWS health check failed: {e}")
            return False

        finally:
            await client.close()


# Exemplo de uso
def example_sync_usage():
    """Demonstra uso síncrono do adapter."""
    adapter = NWSStationsSyncAdapter()

    try:
        # Buscar dados para NYC (código síncrono!)
        data = adapter.get_daily_data_sync(
            lat=40.7128,
            lon=-74.0060,
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=5),
        )

        print(f"✅ NWS: {len(data)} dias obtidos")
        for record in data[:3]:  # Primeiros 3 dias
            print(
                f"  {record.date}: "
                f"T={record.temp_mean}°C "
                f"(min={record.temp_min}, max={record.temp_max}), "
                f"RH={record.humidity}%, "
                f"Wind={record.wind_speed}m/s"
            )
    except Exception as e:
        print(f"❌ Erro: {e}")


if __name__ == "__main__":
    example_sync_usage()
