"""
Gerenciador de fontes de dados climáticos.

Detecta quais fontes estão disponíveis para uma determinada localização
e gerencia a fusão de dados de múltiplas fontes.

IMPORTANTE: Este módulo NÃO faz validações de datas/período.
Validações de entrada: climate_validation.py
Disponibilidade temporal: climate_source_availability.py
Seleção inteligente: climate_source_selector.py
"""

from datetime import date, datetime, timedelta
from typing import Any

from loguru import logger

from validation_logic_eto.api.services.climate_source_availability import (
    ClimateSourceAvailability,
    OperationMode,
)
from validation_logic_eto.api.services.climate_source_selector import ClimateSourceSelector
from validation_logic_eto.api.services.geographic_utils import GeographicUtils


def normalize_operation_mode(period_type: str | None) -> OperationMode:
    """
    Normaliza period_type para OperationMode de forma consistente.

    Args:
        period_type: String representando o tipo de período

    Returns:
        OperationMode: Enum normalizado

    Exemplo:
        mode = normalize_operation_mode("historical")
        # Retorna: OperationMode.HISTORICAL_EMAIL
    """
    period_type_str = (period_type or "dashboard_current").lower()

    # Mapeamento completo de aliases
    mapping = {
        "historical": OperationMode.HISTORICAL_EMAIL,
        "historical_email": OperationMode.HISTORICAL_EMAIL,
        "dashboard": OperationMode.DASHBOARD_CURRENT,
        "dashboard_current": OperationMode.DASHBOARD_CURRENT,
        "forecast": OperationMode.DASHBOARD_FORECAST,
        "dashboard_forecast": OperationMode.DASHBOARD_FORECAST,
    }

    return mapping.get(period_type_str, OperationMode.DASHBOARD_CURRENT)


class ClimateSourceManager:
    """Gerencia disponibilidade e seleção de fontes climáticas.

    Estratégia de Resolução Temporal:
    ------------------------------------
    Todas as fontes: DIÁRIA
        * Uso para mapa mundial dash (qualquer ponto)
        * Dados diários com 3 modos de operação:
          - Historical_email: 1-90 dias (end ≤ hoje-30d, entrega email)
          - Dashboard_current: [7,14,21,30] dias (end = hoje, web)
          - Dashboard_forecast: 6 dias fixo (hoje → hoje+5d, web)
        * Sob demanda (clique do usuário)
        * Fusão de múltiplas fontes disponível

    Fontes Configuradas (6 fontes):
    -------------------------------
    Global:
    - Open-Meteo Archive: Histórico (1990 → Today-2d), CC-BY-4.0
    - Open-Meteo Forecast: Previsão (Today-30d → Today+5d), CC-BY-4.0
    - NASA POWER: Histórico (1990 → Today-2-7d), Public Domain
    - MET Norway: Previsão global (Today → Today+5d), CC-BY-4.0

    🇺🇸 USA Continental:
    - NWS Forecast: Previsão (Today → Today+5d), Public Domain
    - NWS Stations: Observações (Today-1d → Now), Public Domain

    IMPORTANTE: Bounding boxes centralizados em GeographicUtils
    """

    # Configuração de fontes de dados disponíveis
    SOURCES_CONFIG: dict[str, dict[str, Any]] = {
        "openmeteo_archive": {
            "id": "openmeteo_archive",
            "name": "Open-Meteo Archive",
            "coverage": "global",
            "temporal": "daily",
            "bbox": None,
            "license": "CC-BY-4.0",
            "realtime": False,
            "priority": 1,
            "url": "https://archive-api.open-meteo.com/v1/archive",
            "variables": [
                "temperature_2m_max",
                "temperature_2m_mean",
                "temperature_2m_min",
                "relative_humidity_2m_max",
                "relative_humidity_2m_mean",
                "relative_humidity_2m_min",
                "wind_speed_10m_mean",
                "shortwave_radiation_sum",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
            ],
            "delay_hours": 48,
            "update_frequency": "daily",
            "historical_start": "1990-01-01",
            "restrictions": {"attribution_required": True},
            "use_case": (
                "Global historical ETo validation. "
                "Aligned with MIN_HISTORICAL_DATE (1990-01-01)"
            ),
        },
        "openmeteo_forecast": {
            "id": "openmeteo_forecast",
            "name": "Open-Meteo Forecast",
            "coverage": "global",
            "temporal": "daily",
            "bbox": None,
            "license": "CC-BY-4.0",
            "realtime": True,
            "priority": 1,
            "url": "https://api.open-meteo.com/v1/forecast",
            "variables": [
                "temperature_2m_max",
                "temperature_2m_mean",
                "temperature_2m_min",
                "relative_humidity_2m_max",
                "relative_humidity_2m_mean",
                "relative_humidity_2m_min",
                "wind_speed_10m_mean",
                "shortwave_radiation_sum",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
            ],
            "delay_hours": 1,
            "update_frequency": "daily",
            "historical_start": None,
            "forecast_horizon_days": 5,
            "restrictions": {"attribution_required": True},
            "use_case": "Global forecast ETo calculations",
        },
        "nasa_power": {
            "id": "nasa_power",
            "name": "NASA POWER",
            "coverage": "global",
            "temporal": "daily",
            "bbox": None,
            "license": "public_domain",
            "realtime": False,
            "priority": 2,
            "url": "https://power.larc.nasa.gov/api/temporal/daily/point",
            "variables": [
                "T2M_MAX",
                "T2M_MIN",
                "T2M",
                "RH2M",
                "WS2M",
                "ALLSKY_SFC_SW_DWN",
                "PRECTOTCORR",
            ],
            "delay_hours": 72,
            "update_frequency": "daily",
            "historical_start": "1990-01-01",
            "restrictions": {"limit_requests": 1000},
            "use_case": (
                "Global daily ETo, data fusion. "
                "Aligned with MIN_HISTORICAL_DATE (1990-01-01)"
            ),
        },
        "nws_forecast": {
            "id": "nws_forecast",
            "name": "NWS Forecast",
            "coverage": "usa",
            "temporal": "hourly",
            "bbox": GeographicUtils.USA_BBOX,
            "license": "public_domain",
            "realtime": True,
            "priority": 3,
            "url": "https://api.weather.gov/",
            "variables": [
                "temperature",
                "relativeHumidity",
                "windSpeed",
                "windDirection",
                "skyCover",
                "quantitativePrecipitation",
            ],
            "delay_hours": 1,
            "update_frequency": "hourly",
            "forecast_horizon_days": 5,
            "restrictions": {
                "attribution_required": True,
                "user_agent_required": True,
            },
            "use_case": "USA hourly ETo forecasts",
        },
        "nws_stations": {
            "id": "nws_stations",
            "name": "NWS Stations",
            "coverage": "usa",
            "temporal": "hourly",
            "bbox": GeographicUtils.USA_BBOX,
            "license": "public_domain",
            "realtime": True,
            "priority": 3,
            "url": "https://api.weather.gov/",
            "variables": [
                "temperature",
                "relativeHumidity",
                "windSpeed",
                "windDirection",
                "skyCover",
                "quantitativePrecipitation",
            ],
            "delay_hours": 1,
            "update_frequency": "hourly",
            "historical_start": None,
            "restrictions": {
                "attribution_required": True,
                "user_agent_required": True,
                "data_window_days": 30,
            },
            "use_case": "USA station observations",
        },
        "met_norway": {
            "id": "met_norway",
            "name": "MET Norway Locationforecast",
            "coverage": "global",
            "temporal": "daily",
            "bbox": None,
            "license": "NLOD-2.0+CC-BY-4.0",
            "realtime": True,
            "priority": 4,
            "url": (
                "https://api.met.no/weatherapi/" "locationforecast/2.0/compact"
            ),
            "variables": [
                "air_temperature_max",
                "air_temperature_min",
                "air_temperature_mean",
                "relative_humidity_mean",
                "precipitation_sum",
            ],
            "delay_hours": 1,
            "update_frequency": "daily",
            "forecast_horizon_days": 5,
            "restrictions": {
                "attribution_required": True,
                "user_agent_required": True,
                "limit_requests": "20 req/s",
            },
            "use_case": (
                "Regional quality strategy: Nordic (NO/SE/FI/DK) = "
                "high-quality precipitation (1km + radar). "
                "Global = temperature/humidity only "
                "(skip precipitation, use Open-Meteo)"
            ),
            "regional_strategy": {
                "nordic": {
                    "bbox": GeographicUtils.NORDIC_BBOX,
                    "resolution": "1km (MET Nordic)",
                    "model": "MEPS 2.5km + downscaling",
                    "updates": "Hourly",
                    "post_processing": (
                        "Radar + Netatmo crowdsourced bias correction"
                    ),
                    "variables": [
                        "air_temperature_max",
                        "air_temperature_min",
                        "air_temperature_mean",
                        "relative_humidity_mean",
                        "precipitation_sum",
                    ],
                    "precipitation_quality": "✅ HIGH (use MET Norway)",
                },
                "global": {
                    "resolution": "9km (ECMWF IFS)",
                    "model": "ECMWF IFS HRES",
                    "updates": "4x daily (00/06/12/18 UTC)",
                    "post_processing": "Minimal",
                    "variables": [
                        "air_temperature_max",
                        "air_temperature_min",
                        "air_temperature_mean",
                        "relative_humidity_mean",
                    ],
                    "precipitation_quality": (
                        "⚠️ LOW (use Open-Meteo multi-model instead)"
                    ),
                },
            },
        },
    }

    # Validação de datasets (offline, apenas documentação)
    VALIDATION_DATASETS = {
        "xavier_brazil": {
            "name": "Xavier et al. Daily Weather Gridded Data",
            "period": "1961-01-01 to 2024-03-20",
            "resolution": "0.25° x 0.25°",
            "coverage": "brazil",
            # Truncado no original; assumindo lista vazia ou exemplo
            "cities": [
                {"name": "Brasília", "lat": -15.7939, "lon": -47.8828},
                {"name": "São Paulo", "lat": -23.5505, "lon": -46.6333},
            ],
            "reference": "https://doi.org/10.1002/joc.5325",
            "validation_metric": "ETo_FAO56",
        },
        "openmeteo_global": {
            "name": "Open-Meteo ETo (FAO-56 Penman-Monteith)",
            "period": "1990-01-01 to present (forecast)",
            "resolution": "Variable (depends on model)",
            "coverage": "global",
            "license": "CC-BY-4.0",
            "delay": "~1-2 days (forecast), ~2 days (archive)",
            "use_case": "Global ETo validation and comparison",
            "reference": "https://open-meteo.com/en/docs",
            "validation_metric": "et0_fao_evapotranspiration",
            "note": (
                "Open-Meteo provides pre-calculated ETo using FAO-56 "
                "Penman-Monteith method. Perfect for validating our "
                "application's ETo calculations against a reliable "
                "reference. Available through both Archive API "
                "(historical) and Forecast API (recent/current)."
            ),
            "api_endpoints": {
                "archive": "https://archive-api.open-meteo.com/v1/archive",
                "forecast": "https://api.open-meteo.com/v1/forecast",
            },
            "variable": "et0_fao_evapotranspiration",
        },
    }

    def __init__(self) -> None:
        """Inicializa o gerenciador de fontes."""
        self.enabled_sources: dict[str, dict[str, Any]] = dict(
            self.SOURCES_CONFIG
        )
        logger.info(
            "ClimateSourceManager initialized with %d sources",
            len(self.enabled_sources),
        )

    def get_available_sources(
        self, lat: float, lon: float
    ) -> list[dict[str, Any]]:
        """
        Retorna lista simples de fontes disponíveis (para compatibilidade).

        Versão simplificada que retorna lista de dicts com info básica.
        Para metadados completos, usar get_available_sources_for_location().

        Args:
            lat: Latitude (-90 a 90)
            lon: Longitude (-180 a 180)

        Returns:
            List[Dict]: Lista de fontes disponíveis
        """
        result_dict = self.get_available_sources_for_location(lat, lon)
        available = [
            {
                "id": source_id,
                "name": metadata["name"],
                "coverage": metadata["coverage"],
                "temporal": metadata["temporal"],
                "realtime": metadata["realtime"],
                "priority": metadata["priority"],
                "delay_hours": metadata.get("delay_hours", 0),
                "variables": metadata.get("variables", []),
            }
            for source_id, metadata in result_dict.items()
            if metadata["available"]
        ]
        available.sort(key=lambda x: x["priority"])
        return available

    def get_best_source_for_location(
        self, lat: float, lon: float
    ) -> str | None:
        """
        Retorna MELHOR fonte para uma localização.

        USA ClimateSourceSelector para seleção inteligente baseada em:
        1. Cobertura geográfica (USA → NWS, Nordic → MET Norway)
        2. Qualidade regional (prioridade por região)
        3. Disponibilidade temporal

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            str: ID da melhor fonte, ou None se nenhuma disponível
        """
        # Usar ClimateSourceSelector para seleção inteligente
        best_source = ClimateSourceSelector.select_source(lat, lon)

        logger.bind(lat=lat, lon=lon, source=best_source).debug(
            "Melhor fonte selecionada"
        )
        return best_source

    def get_available_sources_by_mode(
        self, lat: float, lon: float, mode: OperationMode | str
    ) -> list[str]:
        """
        Retorna fontes compatíveis com modo de operação E localização.

        Combina:
        1. Filtro geográfico (USA, Nordic, Global)
        2. Filtro temporal (Historical, Current, Forecast)
        3. Disponibilidade da API

        Args:
            lat: Latitude
            lon: Longitude
            mode: Modo de operação (OperationMode enum ou string)

        Returns:
            List[str]: IDs de fontes compatíveis, ordenados por prioridade
        """
        # Converter string para enum se necessário
        if isinstance(mode, str):
            try:
                mode = OperationMode(mode)
            except ValueError:
                logger.bind(mode=mode).error("Modo inválido")
                return []

        # Passo 1: Obter TODAS as fontes disponíveis na localização
        available_sources = ClimateSourceSelector.get_all_sources(lat, lon)

        # Passo 2: Filtrar por capacidade temporal do modo
        # Usar limites temporais típicos de cada modo para validação
        today = date.today()

        # Definir período representativo de cada modo
        if mode == OperationMode.HISTORICAL_EMAIL:
            # Historical: end ≤ hoje-30d, período 1-90d
            test_start = today - timedelta(days=60)  # 60 dias atrás
            test_end = today - timedelta(days=30)  # hoje-30d
        elif mode == OperationMode.DASHBOARD_CURRENT:
            # Current: end = hoje, período 7-30d
            test_start = today - timedelta(days=30)  # 30 dias atrás
            test_end = today  # hoje
        elif mode == OperationMode.DASHBOARD_FORECAST:
            # Forecast: start ≈ hoje, end = hoje+5d
            test_start = today
            test_end = today + timedelta(days=5)
        else:
            # Fallback
            test_start = today
            test_end = today

        compatible_sources = []

        for source_id in available_sources:
            # Verificar se fonte suporta o modo com período representativo
            is_available = ClimateSourceAvailability.is_source_available(
                source_id, mode, test_start, test_end
            )
            if is_available:
                compatible_sources.append(source_id)

        # Ordenar por prioridade
        compatible_sources.sort(
            key=lambda s: self.SOURCES_CONFIG[s]["priority"]
        )

        logger.bind(
            mode=mode.value, lat=lat, lon=lon, sources=compatible_sources
        ).debug("Fontes compatíveis por modo obtidas")
        return compatible_sources

    def get_sources_for_data_download(
        self,
        lat: float,
        lon: float,
        start_date: date | datetime,
        end_date: date | datetime,
        mode: OperationMode | str | None = None,
        preferred_sources: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        MÉTODO PRINCIPAL para data_download.py.

        Retorna fontes otimizadas para download de dados, considerando:
        1. Localização geográfica (USA, Nordic, Global)
        2. Modo de operação (Historical, Current, Forecast)
        3. Disponibilidade temporal das APIs
        4. Preferências do usuário

        Args:
            lat: Latitude
            lon: Longitude
            start_date: Data inicial
            end_date: Data final
            mode: Modo de operação (auto-detectado se None)
            preferred_sources: Fontes preferidas pelo usuário

        Returns:
            Dict com estrutura:
            {
                "sources": ["openmeteo_forecast", "met_norway"],
                "mode": "dashboard_forecast",
                "location_info": {
                    "lat": 59.9139,
                    "lon": 10.7522,
                    "in_usa": False,
                    "in_nordic": True,
                    "region": "Nordic Region"
                },
                "temporal_coverage": {
                    "start": "2024-01-15",
                    "end": "2024-01-20",
                    "period_days": 6
                },
                "warnings": []
            }
        """
        # Converter datetime para date se necessário
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()

        warnings: list[str] = []

        # Auto-detectar modo se não fornecido
        if mode is None:
            from validation_logic_eto.api.services.climate_validation import (
                ClimateValidationService,
            )

            detected_mode, error = (
                ClimateValidationService.detect_mode_from_dates(
                    start_date.isoformat(), end_date.isoformat()
                )
            )
            if detected_mode:
                mode = OperationMode(detected_mode)
                logger.bind(mode=mode.value).info("Modo auto-detectado")
            else:
                warnings.append(f"Falha na auto-detecção de modo: {error}")
                mode = OperationMode.DASHBOARD_CURRENT  # Default

        # Converter string para enum se necessário
        if isinstance(mode, str):
            mode = OperationMode(mode)

        # Validar limites temporais do modo (garante conformidade)
        today = date.today()
        period_days = (end_date - start_date).days + 1

        if mode == OperationMode.HISTORICAL_EMAIL:
            # Validar: end ≤ hoje-30d, período 1-90d, start ≥ 1990-01-01
            min_date = date(1990, 1, 1)
            max_end = today - timedelta(days=30)

            if start_date < min_date:
                warnings.append(
                    f"start_date histórico {start_date} < 1990-01-01. "
                    f"Ajustado para mínimo."
                )
                start_date = min_date

            if end_date > max_end:
                warnings.append(
                    f"end_date histórico {end_date} > {max_end} "
                    f"(hoje-30d). Dados podem ser incompletos."
                )

            if not (1 <= period_days <= 90):
                warnings.append(
                    f"Período histórico {period_days}d fora de 1-90d"
                )

        elif mode == OperationMode.DASHBOARD_CURRENT:
            # Validar: end = hoje, período [7,14,21,30]d, start ≥ 1990-01-01
            min_date = date(1990, 1, 1)

            if start_date < min_date:
                warnings.append(
                    f"start_date dashboard {start_date} < 1990-01-01. "
                    f"Ajustado para mínimo."
                )
                start_date = min_date

            if end_date != today:
                warnings.append(
                    f"end_date dashboard deve ser hoje ({today}), "
                    f"obtido {end_date}"
                )

            if period_days not in [7, 14, 21, 30]:
                warnings.append(
                    f"Período dashboard {period_days}d não em [7,14,21,30]d"
                )

        elif mode == OperationMode.DASHBOARD_FORECAST:
            # Validar: start ≈ hoje±1d, end ≈ hoje+5d±1d, período 5-7d
            if abs((start_date - today).days) > 1:
                warnings.append(
                    f"start_date forecast {start_date} != hoje±1d ({today})"
                )

            expected_end = today + timedelta(days=5)
            if abs((end_date - expected_end).days) > 1:
                warnings.append(
                    f"end_date forecast {end_date} != hoje+5d±1d "
                    f"({expected_end})"
                )

            if period_days not in [5, 6, 7]:
                warnings.append(
                    f"Período forecast {period_days}d fora de 5-7d"
                )

        # Detectar região
        in_usa = GeographicUtils.is_in_usa(lat, lon)
        in_nordic = GeographicUtils.is_in_nordic(lat, lon)
        region = (
            "USA Continental"
            if in_usa
            else ("Região Nórdica" if in_nordic else "Global")
        )

        # Obter fontes disponíveis para modo e localização
        available_sources = self.get_available_sources_by_mode(lat, lon, mode)

        # Filtrar por fontes preferidas se especificadas
        if preferred_sources:
            # Validar que fontes preferidas estão disponíveis
            valid_preferred = [
                src for src in preferred_sources if src in available_sources
            ]
            if not valid_preferred:
                warnings.append(
                    f"Fontes preferidas {preferred_sources} indisponíveis. "
                    f"Usando todas disponíveis: {available_sources}"
                )
                selected_sources = available_sources
            else:
                selected_sources = valid_preferred
                if len(valid_preferred) < len(preferred_sources):
                    invalid = set(preferred_sources) - set(valid_preferred)
                    warnings.append(
                        f"Algumas fontes preferidas indisponíveis: {invalid}"
                    )
        else:
            selected_sources = available_sources

        if not selected_sources:
            raise ValueError(
                f"Nenhuma fonte disponível para {mode.value} em "
                f"({lat}, {lon}) de {start_date} a {end_date}"
            )

        logger.bind(
            mode=mode.value,
            lat=lat,
            lon=lon,
            sources=selected_sources,
            warnings=len(warnings),
        ).info("Fontes selecionadas para download")
        return {
            "sources": selected_sources,
            "mode": mode.value,
            "location_info": {
                "lat": lat,
                "lon": lon,
                "in_usa": in_usa,
                "in_nordic": in_nordic,
                "region": region,
            },
            "temporal_coverage": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "period_days": period_days,
            },
            "warnings": warnings,
        }

    def get_available_sources_for_location(
        self, lat: float, lon: float
    ) -> dict[str, dict[str, Any]]:
        """
        Retorna fontes disponíveis para uma localização específica.

        Retorna metadados completos sobre cada fonte (disponibilidade,
        cobertura geográfica, licença, prioridade, etc).

        Args:
            lat: Latitude (-90 a 90)
            lon: Longitude (-180 a 180)

        Returns:
            Dict[str, Dict]: Dicionário com metadados de cada fonte
        """
        result: dict[str, dict[str, Any]] = {}

        for source_id, metadata in self.enabled_sources.items():
            # Verificar cobertura geográfica
            is_covered = self._is_point_covered(lat, lon, metadata)

            # Verificar restrições de fusão e download
            restrictions = metadata.get("restrictions", {})
            can_fuse = not restrictions.get("no_data_fusion", False)
            can_download = not restrictions.get("no_download", False)
            license_type = metadata.get("license", "")

            result[source_id] = {
                "available": is_covered,
                "name": metadata["name"],
                "coverage": metadata["coverage"],
                "bbox": metadata.get("bbox"),
                "bbox_str": self._format_bbox(metadata.get("bbox")),
                "license": license_type,
                "priority": metadata["priority"],
                "can_fuse": can_fuse,
                "can_download": can_download,
                "realtime": metadata.get("realtime", False),
                "temporal": metadata.get("temporal", "daily"),
                "variables": metadata.get("variables", []),
                "attribution_required": restrictions.get(
                    "attribution_required", False
                ),
            }

        # Log das fontes disponíveis
        available_ids = [
            sid for sid, meta in result.items() if meta["available"]
        ]
        logger.bind(
            lat=lat,
            lon=lon,
            available=len(available_ids),
            sources=", ".join(available_ids),
        ).info("Fontes disponíveis para localização")

        return result

    def get_fusion_weights(
        self, sources: list[str], lat: float, lon: float
    ) -> dict[str, float]:
        """
        Calcula pesos para fusão de dados baseado em qualidade regional.

        Estratégia:
        1. Nordic + MET Norway → peso maior (1km + radar)
        2. USA + NWS → peso maior (alta qualidade regional)
        3. Global → pesos baseados em prioridade

        Args:
            sources: Lista de IDs de fontes selecionadas
            lat: Latitude
            lon: Longitude

        Returns:
            Dict[str, float]: Pesos normalizados para cada fonte

        Raises:
            ValueError: Se fonte com licença não-comercial for incluída
        """
        # Validação de licenciamento
        non_commercial_sources = []
        for source_id in sources:
            if source_id in self.SOURCES_CONFIG:
                config = self.SOURCES_CONFIG[source_id]
                license_type = config.get("license", "")

                if license_type == "non_commercial":
                    non_commercial_sources.append(
                        {
                            "id": source_id,
                            "name": config["name"],
                            "license": license_type,
                            "use_case": config.get("use_case", ""),
                        }
                    )

        if non_commercial_sources:
            source_names = ", ".join(
                [s["name"] for s in non_commercial_sources]
            )
            error_msg = (
                f"Violação de licença: {source_names} não podem ser "
                f"usadas em fusão de dados devido a restrições de "
                f"licença não-comercial. Restritas a: "
                f"{non_commercial_sources[0]['use_case']}"
            )
            logger.bind(sources=non_commercial_sources).error(error_msg)
            raise ValueError(error_msg)

        # Detectar região para pesos ajustados
        in_nordic = GeographicUtils.is_in_nordic(lat, lon)
        in_usa = GeographicUtils.is_in_usa(lat, lon)

        weights: dict[str, float] = {}
        total_weight = 0.0

        for source_id in sources:
            if source_id in self.SOURCES_CONFIG:
                config = self.SOURCES_CONFIG[source_id]
                base_priority = config["priority"]

                # Ajustar peso por qualidade regional
                if source_id == "met_norway" and in_nordic:
                    # MET Norway na região Nordic: maior peso (1km + radar)
                    weight = 2.0 / base_priority
                elif source_id.startswith("nws_") and in_usa:
                    # NWS nos USA: maior peso (alta qualidade)
                    weight = 1.5 / base_priority
                else:
                    # Peso padrão baseado em prioridade
                    weight = 1.0 / base_priority

                weights[source_id] = weight
                total_weight += weight

        # Normalizar pesos (soma = 1.0)
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}

        logger.bind(sources=sources, lat=lat, lon=lon, weights=weights).debug(
            "Pesos de fusão calculados"
        )
        return weights

    def _format_bbox(self, bbox: tuple | None) -> str:
        """
        Formata bbox para exibição legível.

        Args:
            bbox: Tupla (west, south, east, north) ou None

        Returns:
            str: Bbox formatado (ex: "Europe: 35°N-72°N, 25°W-45°E")
        """
        if bbox is None:
            return "Cobertura global"

        west, south, east, north = bbox

        def format_coord(value: float, is_latitude: bool) -> str:
            """Formata coordenada com direção cardinal."""
            direction = ""
            if is_latitude:
                direction = "N" if value >= 0 else "S"
            else:
                direction = "E" if value >= 0 else "W"
            return f"{abs(value):.0f}°{direction}"

        lat_range = f"{format_coord(south, True)}-{format_coord(north, True)}"
        lon_range = f"{format_coord(west, False)}-{format_coord(east, False)}"

        return f"{lat_range}, {lon_range}"

    def _is_point_covered(
        self, lat: float, lon: float, metadata: dict[str, Any]
    ) -> bool:
        """
        Verifica se um ponto está coberto pela fonte usando GeographicUtils.

        Args:
            lat: Latitude
            lon: Longitude
            metadata: Metadados da fonte

        Returns:
            bool: True se ponto está coberto
        """
        bbox = metadata.get("bbox")

        # Cobertura global
        if bbox is None:
            return GeographicUtils.is_valid_coordinate(lat, lon)

        # Usar GeographicUtils para validação consistente de bbox
        return GeographicUtils.is_in_bbox(lat, lon, bbox)
