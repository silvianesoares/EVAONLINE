"""
NWS Forecast Daily Sync Adapter

Adapter sincrono para nws_forecast_client.py (cliente assincrono).
Converte dados horarios do NWS Forecast em dados diarios agregados.

Este adapter:
- Wraps o NWSForecastClient assincrono em interface sincrona
- Gerencia event loop automaticamente
- Converte dados horarios em agregacoes diarias usando pandas
- Mantém compatibilidade com codigo sincrono existente

Coverage: USA Continental (-125°W to -66°W, 24°N to 49°N)
Extended: Alaska/Hawaii (18°N to 71°N)

License: US Government Public Domain
API Documentation: https://www.weather.gov/documentation/services-web-api

Related Files:
- nws_forecast_client.py: Cliente assincrono (base)
- nws_stations_sync_adapter.py: Adapter para estacoes/observacoes
"""

import asyncio
from datetime import datetime
from typing import List, Optional

from loguru import logger
from pydantic import BaseModel

from .nws_forecast_client import (
    create_nws_forecast_client,
)


class NWSDailyForecastRecord(BaseModel):
    """
    Registro diário de dados NWS Forecast.

    Formato de saida do adapter para compatibilidade com
    sistemas existentes que esperam dados diarios.

    Attributes:
        date: Data no formato YYYY-MM-DD (string)
        temp_max: Temperatura maxima (°C) - oficial NWS
        temp_min: Temperatura minima (°C) - oficial NWS
        temp_mean: Temperatura media (°C)
        humidity_mean: Umidade relativa media (%)
        wind_speed_mean: Velocidade media do vento a 2m (m/s) - FAO-56
        dewpoint_mean: Ponto de orvalho medio (°C) - para ETo
        pressure_mean: Pressao atmosferica media (hPa) - para ETo
        solar_radiation: Radiacao solar (MJ/m²/dia) - USA-ASOS calibrado
        precipitation_sum: Precipitacao total (mm) - ESTIMATIVA
        precipitation_probability: Probabilidade media de precipitacao (%)
        short_forecast: Previsao textual curta
    """

    date: str
    temp_max: Optional[float] = None
    temp_min: Optional[float] = None
    temp_mean: Optional[float] = None
    humidity_mean: Optional[float] = None
    wind_speed_mean: Optional[float] = None
    dewpoint_mean: Optional[float] = None
    pressure_mean: Optional[float] = None
    solar_radiation: Optional[float] = None
    precipitation_sum: Optional[float] = None
    precipitation_probability: Optional[float] = None
    short_forecast: Optional[str] = None


class NWSDailyForecastSyncAdapter:
    """
    Adapter síncrono para NWS Forecast com agregação diária.

    Wrapper síncrono para NWSForecastClient (async) que já fornece
    dados diários agregados com todas as variáveis ETo:
    - Temperaturas oficiais NWS (max/min de períodos 12h/24h)
    - Radiação solar (USA-ASOS calibrado com correção de vapor)
    - Ponto de orvalho e pressão atmosférica
    - Vento a 2m (FAO-56 convertido)
    - Precipitação (estimativa, pode superestimar)

    Este adapter:
        - Wraps NWSForecastClient (async) em interface síncrona
        - Cria/reusa event loop conforme necessário
        - Usa get_daily_forecast_data() do client (sem pandas)
        - Filtra dados por período solicitado
        - Remove timezone para compatibilidade com datas naive

    Métodos:
        - health_check_sync(): Verifica disponibilidade da API
        - get_daily_data_sync(): Obtém dados diários agregados
        - get_attribution(): Retorna informações de atribuição
        - get_info(): Informações gerais da API

    Exemplo:
        adapter = NWSDailyForecastSyncAdapter()
        if adapter.health_check_sync():
            data = adapter.get_daily_data_sync(
                39.7392, -104.9903,
                start_date, end_date
            )
            print(f"Rs = {data[0].solar_radiation} MJ/m²/day")
    """

    def __init__(self):
        """Inicializar adapter com cliente NWS assincrono."""
        self.client = create_nws_forecast_client()

    def health_check_sync(self) -> bool:
        """
        Verificar se NWS API está acessível (sincrono).

        Cria event loop se necessário e executa health check
        do cliente assincrono de forma bloqueante.

        Returns:
            bool: True se API está funcionando, False caso contrário

        Exemplo:
            adapter = NWSDailyForecastSyncAdapter()
            if adapter.health_check_sync():
                print("NWS API disponível")
        """

        async def _health_check_async():
            client = create_nws_forecast_client()
            try:
                result = await client.health_check()
                return result.get("status") == "ok"
            finally:
                await client.close()

        try:
            # Sempre criar novo event loop para evitar conflitos
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_health_check_async())
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"NWS Forecast health check failed: {e}")
            return False

    async def _get_daily_data_async(
        self, lat: float, lon: float, start_date: datetime, end_date: datetime
    ) -> List[NWSDailyForecastRecord]:
        """
        Obter dados diários agregados de forma assíncrona.

        Agora usa get_daily_forecast_data() do client que já retorna
        dados agregados com todas as variáveis ETo incluindo:
        - Temperaturas oficiais NWS (max/min de períodos 12h/24h)
        - Radiação solar estimada (método USA-ASOS calibrado)
        - Ponto de orvalho e pressão atmosférica
        - Vento a 2m (FAO-56 convertido)
        """
        # Criar novo client para este request (evita conflitos de loop)
        client = create_nws_forecast_client()
        try:
            # Client já retorna dados diários agregados!
            daily_forecast = await client.get_daily_forecast_data(lat, lon)

            if not daily_forecast:
                logger.warning(f"Nenhum dado de forecast para ({lat}, {lon})")
                return []

            # Filtrar período solicitado
            filtered_data = []
            for day in daily_forecast:
                # Remover timezone para comparação
                day_date = day.date.replace(tzinfo=None)

                if start_date.date() <= day_date.date() <= end_date.date():
                    record = NWSDailyForecastRecord(
                        date=day.date.strftime("%Y-%m-%d"),
                        temp_max=day.temp_max_celsius,
                        temp_min=day.temp_min_celsius,
                        temp_mean=day.temp_mean_celsius,
                        humidity_mean=day.humidity_mean_percent,
                        wind_speed_mean=day.wind_speed_mean_ms,
                        dewpoint_mean=day.dewpoint_mean_celsius,
                        pressure_mean=day.pressure_mean_hpa,
                        solar_radiation=day.solar_radiation_mj_m2_day,
                        precipitation_sum=day.precip_total_mm,
                        precipitation_probability=(
                            day.probability_precip_mean_percent
                        ),
                        short_forecast=day.short_forecast,
                    )
                    filtered_data.append(record)

            logger.info(
                f"NWS Forecast: {len(filtered_data)} dias no período "
                f"solicitado para ({lat}, {lon})"
            )

            return filtered_data

        except ValueError:
            # Re-raise validation errors (coverage, dates, etc)
            raise
        except Exception as e:
            logger.error(f"Erro ao processar dados NWS Forecast: {e}")
            return []
        finally:
            # Fechar client para liberar recursos
            await client.close()

    def get_daily_data_sync(
        self, lat: float, lon: float, start_date: datetime, end_date: datetime
    ) -> List[NWSDailyForecastRecord]:
        """
        Wrapper síncrono para obter dados diários agregados.
        Compatível com Celery (não-async).

        Retorna dados diários com TODAS as variáveis para ETo:
        - Temperaturas oficiais NWS (max/min/mean)
        - Umidade relativa média
        - Vento médio a 2m (FAO-56)
        - Ponto de orvalho médio
        - Pressão atmosférica média
        - Radiação solar (USA-ASOS calibrado)
        - Precipitação total (estimativa)

        Args:
            lat: Latitude do ponto
            lon: Longitude do ponto
            start_date: Data inicial
            end_date: Data final

        Returns:
            Lista de registros diários agregados com variáveis ETo
        """
        try:
            # Criar novo event loop (evita "Event loop is closed")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self._get_daily_data_async(lat, lon, start_date, end_date)
                )
                return result
            finally:
                # Garantir limpeza do loop
                loop.close()
        except Exception as e:
            logger.error(f"NWS Forecast sync wrapper failed: {e}")
            return []

    def get_attribution(self) -> str:
        """
        Retorna texto de atribuição dos dados NWS.

        Returns:
            str: Texto formatado com informações de atribuição
        """
        attr = self.client.get_attribution()
        return (
            f"{attr['source']} | "
            f"License: {attr['license']} | "
            f"API: {attr['api_docs']}"
        )

    def get_info(self) -> dict:
        """
        Get general information about the NWS Forecast API.

        Returns:
            dict: API information including name, coverage, license,
                attribution, and ETo variables
        """
        return {
            "api_name": "National Weather Service (NOAA)",
            "coverage": "USA Continental + Alaska/Hawaii",
            "coverage_details": {
                "continental": "-125°W to -66°W, 24°N to 49°N",
                "extended": "Alaska/Hawaii (18°N to 71°N)",
            },
            "license": "US Government Public Domain",
            "attribution": self.get_attribution(),
            "forecast_period": "5 days",
            "temporal_resolution": "Hourly (aggregated to daily by client)",
            "eto_variables": [
                "Temperature (official max/min from NWS)",
                "Humidity (mean)",
                "Wind speed at 2m (FAO-56 converted)",
                "Dewpoint (mean)",
                "Atmospheric pressure (estimated from elevation)",
                "Solar radiation (USA-ASOS calibrated with vapor correction)",
                "Precipitation (estimate, may be overestimated)",
            ],
            "solar_radiation_method": (
                "Ångström-Prescott (USA-ASOS a=0.20, b=0.79)"
            ),
            "solar_radiation_reference": (
                "Belcher & DeGaetano (2007) Solar Energy 81(3):329-345 "
                "DOI:10.1016/j.solener.2006.07.003"
            ),
        }
