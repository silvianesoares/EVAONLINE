"""
Cliente para API NASA POWER.
Domínio Público.
POWER Daily API
Return a daily data for a region on a 0.5 x 0.5 degree grid.

Data Source:
-----------
The data was obtained from the Prediction Of Worldwide Energy Resources
(POWER) Project, funded through the NASA Earth Science Directorate
Applied Science Program.

POWER Data Reference:
--------------------
The data was obtained from the POWER Project's Daily 2.x.x version.

NASA POWER: https://power.larc.nasa.gov/
Documentation: https://power.larc.nasa.gov/docs/services/api/
Citation Guide: https://power.larc.nasa.gov/docs/referencing/

When using POWER data in publications, please reference:
"Data obtained from NASA Langley Research Center POWER Project
funded through the NASA Earth Science Directorate Applied Science Program."

Contact: larc-power-project@mail.nasa.gov

IMPORTANTE:
- Community 'ag' (agronomy): Radiação solar em MJ/m²/day (pronta para ETo)
- Sempre usar community='ag' para dados agroclimáticos

7 VARIÁVEIS DIÁRIAS DISPONÍVEIS:
1. ALLSKY_SFC_SW_DWN: CERES SYN1deg All Sky Surface Shortwave
   Downward Irradiance (MJ/m^2/day)
Spatial Resolution: 1 x 1 Degrees

2. T2M: MERRA-2 Temperature at 2 Meters (C)
Spatial Resolution: 0.5 x 0.625 Degrees

3. T2M_MAX: MERRA-2 Temperature at 2 Meters Maximum (C)
Spatial Resolution: 0.5 x 0.625 Degrees

4. T2M_MIN: MERRA-2 Temperature at 2 Meters Minimum (C)
Spatial Resolution: 0.5 x 0.625 Degrees

5. RH2M: MERRA-2 Relative Humidity at 2 Meters (%)
Spatial Resolution: 0.5 x 0.625 Degrees

6. WS2M: MERRA-2 Wind Speed at 2 Meters (m/s)
Spatial Resolution: 0.5 x 0.625 Degrees

7. PRECTOTCORR: MERRA-2 Precipitation Corrected (mm/day)
Spatial Resolution: 0.5 x 0.625 Degrees

"""

from datetime import datetime, timedelta
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field

from validation_logic_eto.api.services.geographic_utils import GeographicUtils


class NASAPowerConfig(BaseModel):
    """Configuração da API NASA POWER."""

    base_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point"
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0


class NASAPowerData(BaseModel):
    """Dados retornados pela NASA POWER."""

    date: str = Field(..., description="Data ISO 8601")
    temp_max: float | None = Field(None, description="Temp máxima (°C)")
    temp_min: float | None = Field(None, description="Temp mínima (°C)")
    temp_mean: float | None = Field(None, description="Temp média (°C)")
    humidity: float | None = Field(None, description="Umidade relativa (%)")
    wind_speed: float | None = Field(
        None, description="Velocidade vento (m/s)"
    )
    solar_radiation: float | None = Field(
        None, description="Radiação solar (MJ/m²/day)"
    )
    precipitation: float | None = Field(
        None, description="Precipitação (mm/dia)"
    )


class NASAPowerClient:
    """
    Cliente para API NASA POWER com cache inteligente.
    """

    def __init__(
        self, config: NASAPowerConfig | None = None, cache: Any | None = None
    ):
        """
        Inicializa cliente NASA POWER.

        Args:
            config: Configuração customizada (opcional)
            cache: ClimateCacheService (opcional, injetado via DI)
        """
        self.config = config or NASAPowerConfig()
        self.client = httpx.AsyncClient(timeout=self.config.timeout)
        self.cache = cache  # Cache service opcional

    async def close(self):
        """Fecha conexão HTTP."""
        await self.client.aclose()

    async def get_daily_data(
        self,
        lat: float,
        lon: float,
        start_date: datetime,
        end_date: datetime,
        community: str = "AG",  # UPPERCASE: AG, RE, SB
    ) -> list[NASAPowerData]:
        """
        Busca dados climáticos diários para um ponto com cache inteligente.

        NOTA: Validações de range devem ser feitas em climate_validation.py
        antes de chamar este método. Este cliente assume dados já validados.

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)
            start_date: Data inicial (datetime) - DEVE estar validada
            end_date: Data final (datetime) - DEVE estar validada
            community: NASA POWER community (UPPERCASE required):
                - AG: Agronomy (agronomia - padrão)
                - RE: Renewable Energy (energia renovável)
                - SB: Sustainable Buildings (edifícios sustentáveis)

        Returns:
            Lista de NASAPowerData com dados climáticos diários
        """
        # Validações básicas - usar GeographicUtils (SINGLE SOURCE OF TRUTH)
        if not GeographicUtils.is_valid_coordinate(lat, lon):
            msg = f"Coordenadas inválidas: ({lat}, {lon})"
            raise ValueError(msg)

        if start_date > end_date:
            msg = "start_date deve ser <= end_date"
            raise ValueError(msg)

        # IMPORTANTE: Validações de range (7-30 dias) devem ser feitas
        # em climate_validation.py ANTES de chamar este método.
        # Este cliente assume dados pré-validados por climate_validation.

        # 1. Tenta buscar do cache (se disponível)
        if self.cache:
            cached_data = await self.cache.get(
                source="nasa_power",
                lat=lat,
                lon=lon,
                start=start_date,
                end=end_date,
            )
            if cached_data:
                logger.info(f"🎯 Cache HIT: NASA POWER lat={lat}, lon={lon}")
                return cached_data

        # 2. Cache MISS - busca da API
        logger.info(f"Buscando NASA API: lat={lat}, lon={lon}")

        # Formatar datas (YYYYMMDD)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        # Parâmetros de requisição
        params = {
            "parameters": ",".join(
                [
                    "T2M_MAX",  # Temp máxima 2m (°C)
                    "T2M_MIN",  # Temp mínima 2m (°C)
                    "T2M",  # Temp média 2m (°C)
                    "RH2M",  # Umidade relativa 2m (%)
                    "WS2M",  # Velocidade vento 2m (m/s)
                    "ALLSKY_SFC_SW_DWN",  # Radiação solar (MJ/m²/day)
                    "PRECTOTCORR",  # Precipitação (mm/dia)
                ]
            ),
            "community": community,
            "longitude": lon,
            "latitude": lat,
            "start": start_str,
            "end": end_str,
            "format": "JSON",
        }

        # Requisição com retry
        for attempt in range(self.config.retry_attempts):
            try:
                logger.info(
                    f"NASA POWER request: lat={lat}, lon={lon}, "
                    f"dates={start_str} to {end_str} (attempt {attempt + 1})"
                )

                response = await self.client.get(
                    self.config.base_url, params=params
                )
                response.raise_for_status()

                data = response.json()
                parsed_data = self._parse_response(data)

                # 3. Salva no cache (se disponível)
                if self.cache and parsed_data:
                    await self.cache.set(
                        source="nasa_power",
                        lat=lat,
                        lon=lon,
                        start=start_date,
                        end=end_date,
                        data=parsed_data,
                    )
                    logger.info(f"Cache SAVE: NASA POWER lat={lat}, lon={lon}")

                return parsed_data

            except httpx.HTTPError as e:
                logger.warning(
                    f"NASA POWER request failed (attempt {attempt + 1}): {e}"
                )
                if attempt == self.config.retry_attempts - 1:
                    raise
                await self._delay_retry()

        msg = "NASA POWER: Todos os attempts falharam"
        raise httpx.HTTPError(msg)

    def _parse_response(self, data: dict) -> list[NASAPowerData]:
        """
        Parseia resposta JSON da NASA POWER.

        Args:
            data: Resposta JSON

        Returns:
            List[NASAPowerData]: Dados parseados
        """
        if "properties" not in data or "parameter" not in data["properties"]:
            msg = "Resposta NASA POWER inválida (falta 'parameter')"
            raise ValueError(msg)

        parameters = data["properties"]["parameter"]

        # Extrair datas (primeira chave de qualquer parâmetro)
        first_param = next(iter(parameters.values()))
        dates = sorted(first_param.keys())

        results = []
        for date_str in dates:
            # Radiação já vem em MJ/m²/day com community=ag
            solar_mj = parameters.get("ALLSKY_SFC_SW_DWN", {}).get(date_str)

            record = NASAPowerData(
                date=self._format_date(date_str),
                temp_max=parameters.get("T2M_MAX", {}).get(date_str),
                temp_min=parameters.get("T2M_MIN", {}).get(date_str),
                temp_mean=parameters.get("T2M", {}).get(date_str),
                humidity=parameters.get("RH2M", {}).get(date_str),
                wind_speed=parameters.get("WS2M", {}).get(date_str),
                solar_radiation=solar_mj,
                precipitation=parameters.get("PRECTOTCORR", {}).get(date_str),
            )
            results.append(record)

        logger.info(f"NASA POWER: Parseados {len(results)} registros")
        return results

    def _format_date(self, date_str: str) -> str:
        """
        Converte data YYYYMMDD → ISO 8601 (YYYY-MM-DD).

        Args:
            date_str: Data no formato YYYYMMDD

        Returns:
            str: Data ISO 8601
        """
        year = date_str[:4]
        month = date_str[4:6]
        day = date_str[6:8]
        return f"{year}-{month}-{day}"

    async def _delay_retry(self):
        """Delay entre tentativas de retry."""
        import asyncio

        await asyncio.sleep(self.config.retry_delay)

    @classmethod
    def get_data_availability_info(cls) -> dict[str, Any]:
        """
        Retorna informações sobre disponibilidade de dados históricos.

        Returns:
            dict: Informações sobre cobertura temporal e limitações
        """
        start_date = datetime(1981, 1, 1).date()
        today = datetime.now().date()

        return {
            "data_start_date": start_date,
            "max_historical_years": (today - start_date).days // 365,
            "delay_days": 7,  # Typical delay
            "description": "Historical data from 1981, global coverage",
            "coverage": "Global",
            "update_frequency": "Daily (with 2-7 day delay)",
        }

    async def health_check(self) -> bool:
        """
        Verifica se API está acessível.

        Returns:
            bool: True se API responde
        """
        try:
            # Tenta buscar 7 dias (mínimo) para um ponto qualquer
            end_date = datetime.now() - timedelta(days=7)
            start_date = end_date - timedelta(days=6)  # 7 days total
            await self.get_daily_data(
                lat=0.0, lon=0.0, start_date=start_date, end_date=end_date
            )
            return True
        except Exception as e:
            logger.error(f"NASA POWER health check failed: {e}")
            return False
