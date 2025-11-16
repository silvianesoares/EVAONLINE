"""
Serviço de validação centralizado para dados climáticos.

Responsabilidades:
1. Valida coordenadas (-90 a 90, -180 a 180)
2. Valida formato de datas (YYYY-MM-DD)
3. Valida período (7, 14, 21 ou 30 dias) para dashboard online tempo real
4. Valida período (1-90 dias) para requisições históricas enviadas por email
5. Valida período fixo (6 dias: hoje→hoje+5d) para previsão dashboard
6. Valida variáveis climáticas
7. Valida nome de fonte (string)
"""

from datetime import date, timedelta
from typing import Any

from loguru import logger

from .climate_source_availability import OperationMode


class ClimateValidationService:
    """Centraliza validações de coordenadas e datas climáticas."""

    # Constantes de validação
    LAT_MIN, LAT_MAX = -90.0, 90.0
    LON_MIN, LON_MAX = -180.0, 180.0

    # Data mínima suportada pelas APIs (NASA POWER, OpenMeteo Archive)
    MIN_HISTORICAL_DATE = date(1990, 1, 1)

    # Variáveis válidas (padronizadas para todas as APIs)
    # Set para lookup O(1)
    VALID_CLIMATE_VARIABLES: set[str] = {
        # Temperatura
        "temperature_2m",
        "temperature_2m_max",
        "temperature_2m_min",
        "temperature_2m_mean",
        # Umidade
        "relative_humidity_2m",
        "relative_humidity_2m_max",
        "relative_humidity_2m_min",
        "relative_humidity_2m_mean",
        # Vento (IMPORTANTE: todas as APIs fornecem a 2m após conversão)
        "wind_speed_2m",
        "wind_speed_2m_mean",
        "wind_speed_2m_ms",
        # Precipitação
        "precipitation",
        "precipitation_sum",
        # Radiação solar
        "solar_radiation",
        "shortwave_radiation_sum",
        # Evapotranspiração
        "evapotranspiration",
        "et0_fao_evapotranspiration",
    }

    # Fontes válidas (todas as 6 APIs implementadas)
    # Set para lookup O(1)
    VALID_SOURCES: set[str] = {
        # Global - Dados Históricos
        "openmeteo_archive",  # Histórico (1990-01-01 → hoje-2d)
        "nasa_power",  # Histórico (1990-01-01 → hoje)
        # Global - Previsão/Recent
        "openmeteo_forecast",  # Recent+Forecast (hoje-30d → hoje+5d)
        "met_norway",  # Previsão (hoje → hoje+5d)
        # USA Continental - Previsão
        "nws_forecast",  # Previsão (hoje → hoje+5d)
        "nws_stations",  # Observações tempo real (apenas dia atual)
    }

    @staticmethod
    def _parse_date(date_str: str) -> date:
        """Parser privado para datas (YYYY-MM-DD)."""
        try:
            return date.fromisoformat(
                date_str
            )  # Mais robusto e eficiente que strptime
        except ValueError as e:
            logger.bind(date_str=date_str).error(
                f"Formato de data inválido: {e}"
            )
            raise ValueError(
                f"Data inválida '{date_str}': use YYYY-MM-DD"
            ) from e

    @staticmethod
    def validate_request_mode(
        mode: str,
        start_date: str,
        end_date: str,
        period_days: int | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Valida modo de operação e suas restrições específicas.

        Args:
            mode: Modo de operação:
                'historical_email', 'dashboard_current', 'dashboard_forecast'
            start_date: Data inicial (YYYY-MM-DD)
            end_date: Data final (YYYY-MM-DD)
            period_days: Número de dias (opcional, será calculado se omitido)

        Returns:
            Tupla (válido, detalhes)
        """
        valid_modes = [
            OperationMode.HISTORICAL_EMAIL.value,
            OperationMode.DASHBOARD_CURRENT.value,
            OperationMode.DASHBOARD_FORECAST.value,
        ]
        if mode not in valid_modes:
            return False, {
                "error": f"Modo inválido '{mode}'. Válidos: {valid_modes}"
            }

        # Parser validado
        try:
            start = ClimateValidationService._parse_date(start_date)
            end = ClimateValidationService._parse_date(end_date)
        except ValueError as e:
            return False, {"error": str(e)}

        if period_days is None:
            period_days = (end - start).days + 1

        today = date.today()  # Consistente com date.today()
        errors: list[str] = []

        # MODO 1: HISTORICAL_EMAIL (dados antigos, envio por email)
        if mode == OperationMode.HISTORICAL_EMAIL.value:
            # Período: 1-90 dias
            if not (1 <= period_days <= 90):
                errors.append(
                    f"Período histórico deve ser 1-90 dias, "
                    f"obtido {period_days}"
                )
            # Constraint: end_date ≤ hoje - 30 dias
            max_end = today - timedelta(days=30)
            if end > max_end:
                errors.append(
                    f"end_date histórico deve ser ≤ {max_end} "
                    f"(hoje - 30 dias), obtido {end_date}"
                )
            # Constraint: start_date >= 1990-01-01
            if start < ClimateValidationService.MIN_HISTORICAL_DATE:
                errors.append(
                    f"start_date histórico deve ser >= "
                    f"{ClimateValidationService.MIN_HISTORICAL_DATE} "
                    f"(mínimo suportado), obtido {start_date}"
                )

        # MODO 2: DASHBOARD_CURRENT (dados recentes, web tempo real)
        elif mode == OperationMode.DASHBOARD_CURRENT.value:
            # Período: exatamente 7, 14, 21 ou 30 dias (dropdown)
            if period_days not in [7, 14, 21, 30]:
                errors.append(
                    f"Período dashboard deve ser [7, 14, 21, 30] dias, "
                    f"obtido {period_days}"
                )
            # Constraint: end_date = hoje (fixo)
            if end != today:
                errors.append(
                    f"end_date dashboard deve ser hoje ({today}), "
                    f"obtido {end_date}"
                )
            # Constraint: start_date não pode ser anterior a 1990-01-01
            if start < ClimateValidationService.MIN_HISTORICAL_DATE:
                errors.append(
                    f"start_date dashboard deve ser >= "
                    f"{ClimateValidationService.MIN_HISTORICAL_DATE}, "
                    f"obtido {start_date}"
                )

        # MODO 3: DASHBOARD_FORECAST (previsão 5 dias, web)
        elif mode == OperationMode.DASHBOARD_FORECAST.value:
            # Período: hoje → hoje+5d = 6 dias (com tolerância para timezone)
            if period_days not in [5, 6, 7]:  # Tolerância ±1 dia
                errors.append(
                    f"Período forecast deve ser 5-7 dias "
                    f"(hoje → hoje+5d com tolerância), obtido {period_days}"
                )
            # Constraint: start_date ≈ hoje (tolerância ±1 dia para timezone)
            if abs((start - today).days) > 1:
                errors.append(
                    f"start_date forecast deve ser hoje±1d "
                    f"({today}), obtido {start_date}"
                )
            # Constraint: end_date ≈ hoje + 5 dias (tolerância ±1 dia)
            expected_end = today + timedelta(days=5)
            if abs((end - expected_end).days) > 1:
                errors.append(
                    f"end_date forecast deve ser {expected_end}±1d "
                    f"(hoje+5d), obtido {end_date}"
                )

        if errors:
            logger.bind(
                mode=mode, start=start_date, end=end_date, period=period_days
            ).warning(f"Validação de modo falhou: {errors}")
            return False, {"errors": errors, "mode": mode}

        logger.bind(mode=mode, start=start, end=end, period=period_days).debug(
            "Modo validado com sucesso"
        )
        return True, {
            "mode": mode,
            "start": start,
            "end": end,
            "period_days": period_days,
            "valid": True,
        }

    @staticmethod
    def validate_coordinates(
        lat: float, lon: float, location_name: str = "Localização"
    ) -> tuple[bool, dict[str, Any]]:
        """
        Valida coordenadas geográficas.

        Args:
            lat: Latitude
            lon: Longitude
            location_name: Nome do local (para mensagens de erro)

        Returns:
            Tupla (válido, detalhes)
        """
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            return False, {
                "error": (
                    f"Formato de coordenadas inválido " f"para {location_name}"
                )
            }

        errors: list[str] = []

        lat_min = ClimateValidationService.LAT_MIN
        lat_max = ClimateValidationService.LAT_MAX
        lon_min = ClimateValidationService.LON_MIN
        lon_max = ClimateValidationService.LON_MAX

        if not lat_min <= lat <= lat_max:
            errors.append(
                f"Latitude {lat} fora do intervalo ({lat_min} a {lat_max})"
            )

        if not lon_min <= lon <= lon_max:
            errors.append(
                f"Longitude {lon} fora do intervalo ({lon_min} a {lon_max})"
            )

        if errors:
            logger.bind(location=location_name, lat=lat, lon=lon).warning(
                f"Validação de coordenadas falhou: {errors}"
            )
            return False, {"errors": errors}

        logger.bind(location=location_name, lat=lat, lon=lon).debug(
            "Coordenadas validadas"
        )
        return True, {"lat": lat, "lon": lon, "valid": True}

    @staticmethod
    def validate_date_range(
        start_date: str,
        end_date: str,
        allow_future: bool = False,
        max_future_days: int = 0,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Valida FORMATO de datas e limites de futuro.

        NOTA: NÃO valida período em dias (min/max).
        Cada modo valida seu período específico em validate_request_mode().
        Cada API valida limites temporais próprios em
        climate_source_availability.py.

        Args:
            start_date: Data inicial (YYYY-MM-DD)
            end_date: Data final (YYYY-MM-DD)
            allow_future: Se permite datas futuras no range
            max_future_days: Máximo de dias no futuro permitido
                (0 = até hoje, 5 = até hoje+5d para forecast)

        Returns:
            Tupla (válido, detalhes)
        """
        # Parser validado
        try:
            start = ClimateValidationService._parse_date(start_date)
            end = ClimateValidationService._parse_date(end_date)
        except ValueError as e:
            return False, {"error": str(e)}

        errors: list[str] = []
        today = date.today()
        max_allowed_date = today + timedelta(days=max_future_days)

        # Validação 1: start <= end
        if start > end:
            errors.append(f"start_date {start} > end_date {end}")

        # Validação 2: Limites de futuro
        if allow_future:
            # Quando permite futuro, validar contra max_future_days
            if end > max_allowed_date:
                errors.append(
                    f"end_date {end} excede máximo "
                    f"({max_allowed_date}, hoje+{max_future_days}d)"
                )
        else:
            # Quando NÃO permite futuro, apenas end_date deve ser <= today
            # (start_date pode ser hoje para dashboard_current)
            if end > today:
                errors.append(
                    f"end_date {end} não pode ser no futuro (hoje é {today})"
                )

        # Validação 3: Data mínima histórica (aplicada universalmente)
        if start < ClimateValidationService.MIN_HISTORICAL_DATE:
            errors.append(
                f"start_date {start} é anterior à data mínima suportada "
                f"({ClimateValidationService.MIN_HISTORICAL_DATE})"
            )

        if errors:
            logger.bind(start=start_date, end=end_date).warning(
                f"Validação de intervalo de datas falhou: {errors}"
            )
            return False, {"errors": errors}

        period_days = (end - start).days + 1
        logger.bind(start=start, end=end, period=period_days).debug(
            "Intervalo de datas validado"
        )
        return True, {
            "start": start,
            "end": end,
            "period_days": period_days,
            "valid": True,
        }

    @staticmethod
    def validate_variables(
        variables: list[str],
    ) -> tuple[bool, dict[str, Any]]:
        """
        Valida lista de variáveis climáticas.

        Args:
            variables: Lista de variáveis desejadas

        Returns:
            Tupla (válido, detalhes)
        """
        if not variables:
            return False, {"error": "Pelo menos uma variável é obrigatória"}

        invalid_vars = (
            set(variables) - ClimateValidationService.VALID_CLIMATE_VARIABLES
        )

        if invalid_vars:
            logger.bind(invalid=list(invalid_vars)).warning(
                "Variáveis climáticas inválidas detectadas"
            )
            return False, {
                "error": f"Variáveis inválidas: {invalid_vars}",
                "valid_options": sorted(
                    ClimateValidationService.VALID_CLIMATE_VARIABLES
                ),
            }

        logger.bind(variables=variables).debug("Variáveis validadas")
        return True, {"variables": variables, "valid": True}

    @staticmethod
    def validate_source(source: str) -> tuple[bool, dict[str, Any]]:
        """
        Valida fonte de dados.

        Args:
            source: Nome da fonte

        Returns:
            Tupla (válido, detalhes)
        """
        if source not in ClimateValidationService.VALID_SOURCES:
            logger.bind(source=source).warning("Fonte inválida")
            return False, {
                "error": f"Fonte inválida: {source}",
                "valid_options": sorted(
                    ClimateValidationService.VALID_SOURCES
                ),
            }

        logger.bind(source=source).debug("Fonte validada")
        return True, {"source": source, "valid": True}

    @staticmethod
    def detect_mode_from_dates(
        start_date: str, end_date: str
    ) -> tuple[str | None, str | None]:
        """
        Auto-detecta modo de operação baseado nas datas.
        NOTA: Interface tem botões, mas detector útil para validação.

        Lógica:
        1. Se start ≈ hoje E end ≈ hoje+5d → DASHBOARD_FORECAST
        2. Se end = hoje E period in [7,14,21,30] → DASHBOARD_CURRENT
        3. Se end ≤ hoje-30d E period ≤ 90 → HISTORICAL_EMAIL
        4. Caso contrário → None (modo não identificável)

        Args:
            start_date: Data inicial (YYYY-MM-DD)
            end_date: Data final (YYYY-MM-DD)

        Returns:
            Tupla (modo detectado ou None, mensagem de erro)
        """
        # Parser validado
        try:
            start = ClimateValidationService._parse_date(start_date)
            end = ClimateValidationService._parse_date(end_date)
        except ValueError as e:
            return None, str(e)

        today = date.today()
        period_days = (end - start).days + 1

        # Regra 1: DASHBOARD_FORECAST (com tolerância de ±1 dia para timezone)
        expected_forecast_end = today + timedelta(days=5)
        is_start_today = abs((start - today).days) <= 1
        is_end_forecast = abs((end - expected_forecast_end).days) <= 1

        if is_start_today and is_end_forecast and period_days in [5, 6, 7]:
            return OperationMode.DASHBOARD_FORECAST.value, None

        # Regra 2: DASHBOARD_CURRENT
        if end == today and period_days in [7, 14, 21, 30]:
            return OperationMode.DASHBOARD_CURRENT.value, None

        # Regra 3: HISTORICAL_EMAIL
        if end <= today - timedelta(days=30) and 1 <= period_days <= 90:
            return OperationMode.HISTORICAL_EMAIL.value, None

        # Caso contrário: ambíguo
        error_msg = (
            f"Não foi possível detectar modo das datas "
            f"{start_date} a {end_date}. "
            f"Período: {period_days} dias. "
            f"Especifique o modo explicitamente."
        )
        logger.bind(
            start=start_date, end=end_date, period=period_days
        ).warning(error_msg)
        return None, error_msg

    @staticmethod
    def validate_all(
        lat: float,
        lon: float,
        start_date: str,
        end_date: str,
        variables: list[str],
        source: str = "openmeteo_forecast",
        allow_future: bool = False,
        mode: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Valida todos os parâmetros de uma vez.

        Args:
            lat, lon: Coordenadas
            start_date, end_date: Intervalo de datas
            variables: Variáveis climáticas
            source: Fonte de dados
            allow_future: Permite datas futuras
            mode: Modo de operação (None = auto-detect)

        Returns:
            Tupla (válido, detalhes)
        """
        # Auto-detectar modo se não fornecido
        if mode is None:
            detected_mode, error = (
                ClimateValidationService.detect_mode_from_dates(
                    start_date, end_date
                )
            )
            if detected_mode:
                mode = detected_mode
                logger.bind(mode=mode).info("Modo auto-detectado")
            else:
                logger.bind(error=error).warning(
                    "Falha na auto-detecção de modo"
                )
                # Continua sem modo (para compatibilidade)

        validations = [
            (
                "coordinates",
                ClimateValidationService.validate_coordinates(lat, lon),
            ),
        ]

        # Determinar max_future_days e allow_future baseado no modo
        max_future_days = 0
        effective_allow_future = allow_future

        if mode == OperationMode.DASHBOARD_FORECAST.value:
            max_future_days = 5
            effective_allow_future = True  # Forecast SEMPRE permite futuro
        elif mode == OperationMode.DASHBOARD_CURRENT.value:
            max_future_days = 0
            effective_allow_future = False  # Current termina hoje
        elif mode == OperationMode.HISTORICAL_EMAIL.value:
            max_future_days = 0
            effective_allow_future = False  # Historical é passado

        validations.append(
            (
                "date_range",
                ClimateValidationService.validate_date_range(
                    start_date,
                    end_date,
                    allow_future=effective_allow_future,
                    max_future_days=max_future_days,
                ),
            )
        )

        validations.extend(
            [
                (
                    "variables",
                    ClimateValidationService.validate_variables(variables),
                ),
                ("source", ClimateValidationService.validate_source(source)),
            ]
        )

        # Adicionar validação de modo se detectado/fornecido
        if mode:
            validations.append(
                (
                    "mode",
                    ClimateValidationService.validate_request_mode(
                        mode, start_date, end_date
                    ),
                )
            )

        errors: dict[str, Any] = {}
        details: dict[str, Any] = {}

        for name, (valid, detail) in validations:
            if not valid:
                errors[name] = detail
            else:
                details[name] = detail

        if errors:
            logger.bind(errors=list(errors.keys())).warning(
                "Erros de validação encontrados"
            )
            return False, {"errors": errors, "details": details}

        logger.bind(lat=lat, lon=lon, mode=mode).info(
            "Todas as validações passaram"
        )
        return True, {"all_valid": True, "details": details}


# Removido singleton desnecessário: classe é stateless, use diretamente
