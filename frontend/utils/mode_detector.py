"""
Operation Mode Auto-Detection
Detecta automaticamente o modo operacional baseado nas datas selecionadas.

Mapeia interface do usuário → modos do backend:
- Frontend: "historical", "recent", "forecast"
- Backend: "HISTORICAL_EMAIL", "DASHBOARD_CURRENT", "DASHBOARD_FORECAST"
"""

from datetime import date, datetime, timedelta
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class OperationModeDetector:
    """Detecta e valida modos operacionais do EVAonline"""

    # Mapeamento Frontend → Backend
    MODE_MAPPING = {
        "historical": "HISTORICAL_EMAIL",
        "recent": "DASHBOARD_CURRENT",
        "forecast": "DASHBOARD_FORECAST",
    }

    # Configurações de cada modo backend
    BACKEND_MODES = {
        "HISTORICAL_EMAIL": {
            "description": "1-90 days historical data with email report",
            "min_date": date(1990, 1, 1),
            "max_date_offset": -2,  # today - 2 days
            "min_period": 1,
            "max_period": 90,
            "sources": ["nasa_power", "openmeteo_archive"],
            "requires_email": True,
        },
        "DASHBOARD_CURRENT": {
            "description": "Last 7/14/21/30 days dashboard view",
            "min_date_offset": -29,  # today - 29 days
            "max_date_offset": 0,  # today
            "allowed_periods": [7, 14, 21, 30],
            "sources": [
                "nasa_power",
                "openmeteo_archive",
                "openmeteo_forecast",
            ],
            "requires_email": False,
        },
        "DASHBOARD_FORECAST": {
            "description": "Next 6 days forecast (today → today+5)",
            "min_date_offset": 0,  # today
            "max_date_offset": 5,  # today + 5 days
            "fixed_period": 6,
            "sources": ["openmeteo_forecast", "met_norway", "nws_forecast"],
            "usa_station_option": True,  # NWS Stations available in USA
            "requires_email": False,
        },
    }

    @classmethod
    def detect_mode(
        cls,
        ui_selection: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        period_days: Optional[int] = None,
    ) -> Tuple[str, dict]:
        """
        Detecta o modo backend apropriado baseado na seleção do usuário.

        Args:
            ui_selection: Seleção da UI ("historical", "recent", "forecast")
            start_date: Data inicial (para modo historical)
            end_date: Data final (para modo historical)
            period_days: Número de dias (para modo recent)

        Returns:
            Tuple (backend_mode: str, config: dict)

        Example:
            >>> mode, config = OperationModeDetector.detect_mode(
            ...     "recent",
            ...     period_days=30
            ... )
            >>> print(mode)  # "DASHBOARD_CURRENT"
        """
        backend_mode = cls.MODE_MAPPING.get(ui_selection)

        if not backend_mode:
            logger.error(f"Invalid UI selection: {ui_selection}")
            raise ValueError(f"Unknown operation mode: {ui_selection}")

        config = cls.BACKEND_MODES[backend_mode].copy()
        config["ui_selection"] = ui_selection

        logger.info(
            f"🎯 Detected mode: {backend_mode} (from UI: {ui_selection})"
        )

        return backend_mode, config

    @classmethod
    def validate_dates(
        cls,
        mode: str,
        start_date: date,
        end_date: date,
    ) -> Tuple[bool, str]:
        """
        Valida se as datas são válidas para o modo.

        Args:
            mode: Modo backend ("HISTORICAL_EMAIL", "DASHBOARD_CURRENT", etc)
            start_date: Data inicial
            end_date: Data final

        Returns:
            Tuple (is_valid: bool, message: str)
        """
        if mode not in cls.BACKEND_MODES:
            return False, f"Invalid mode: {mode}"

        config = cls.BACKEND_MODES[mode]
        today = date.today()
        period_days = (end_date - start_date).days + 1

        if mode == "HISTORICAL_EMAIL":
            # Validar data mínima
            min_date = config["min_date"]
            if start_date < min_date:
                return False, f"Start date must be >= {min_date.isoformat()}"

            # Validar data máxima (hoje - 2 dias)
            max_date = today + timedelta(days=config["max_date_offset"])
            if end_date > max_date:
                return (
                    False,
                    f"End date must be <= {max_date.isoformat()} (today-2d)",
                )

            # Validar período
            if not (
                config["min_period"] <= period_days <= config["max_period"]
            ):
                return (
                    False,
                    f"Period must be {config['min_period']}-{config['max_period']} days",
                )

            return True, f"Valid historical period ({period_days} days)"

        elif mode == "DASHBOARD_CURRENT":
            # End date deve ser hoje
            if end_date != today:
                return (
                    False,
                    f"Dashboard current requires end_date = today ({today.isoformat()})",
                )

            # Período deve ser um dos permitidos
            if period_days not in config["allowed_periods"]:
                allowed = ", ".join(map(str, config["allowed_periods"]))
                return False, f"Period must be one of: {allowed} days"

            # Start date calculado deve estar dentro do range
            min_date = today + timedelta(days=config["min_date_offset"])
            if start_date < min_date:
                return False, f"Start date must be >= {min_date.isoformat()}"

            return (
                True,
                f"Valid dashboard period ({period_days} days ending today)",
            )

        elif mode == "DASHBOARD_FORECAST":
            # Deve começar hoje
            expected_start = today + timedelta(days=config["min_date_offset"])
            if abs((start_date - expected_start).days) > 1:
                return (
                    False,
                    f"Forecast must start today ({today.isoformat()})",
                )

            # Deve terminar em today+5
            expected_end = today + timedelta(days=config["max_date_offset"])
            if abs((end_date - expected_end).days) > 1:
                return (
                    False,
                    f"Forecast must end {expected_end.isoformat()} (today+5d)",
                )

            # Período deve ser 6 dias
            if period_days != config["fixed_period"]:
                return (
                    False,
                    f"Forecast period must be exactly {config['fixed_period']} days",
                )

            return True, "Valid 6-day forecast period"

        return False, "Unknown validation error"

    @classmethod
    def prepare_api_request(
        cls,
        ui_selection: str,
        latitude: float,
        longitude: float,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        period_days: Optional[int] = None,
        email: Optional[str] = None,
        usa_forecast_source: str = "fusion",
    ) -> dict:
        """
        Prepara payload para requisição à API do backend.

        Args:
            ui_selection: Seleção da UI
            latitude: Latitude
            longitude: Longitude
            start_date: Data inicial (para historical)
            end_date: Data final (para historical)
            period_days: Número de dias (para recent/forecast)
            email: Email do usuário (para historical)
            usa_forecast_source: "fusion" ou "stations" (para forecast nos EUA)

        Returns:
            dict com payload formatado para API
        """
        # Detectar modo
        backend_mode, config = cls.detect_mode(
            ui_selection, start_date, end_date, period_days
        )

        today = date.today()

        # Calcular datas baseado no modo
        if ui_selection == "historical":
            # Modo 1: Usar datas fornecidas
            if not (start_date and end_date):
                raise ValueError(
                    "Historical mode requires start_date and end_date"
                )
            request_start = start_date
            request_end = end_date

        elif ui_selection == "recent":
            # Modo 2: Calcular datas do período
            if not period_days:
                raise ValueError("Recent mode requires period_days")
            request_end = today
            request_start = today - timedelta(days=period_days - 1)

        elif ui_selection == "forecast":
            # Modo 3: Período fixo
            request_start = today
            request_end = today + timedelta(days=5)

            # Se USA e selecionou stations, usar modo especial
            if usa_forecast_source == "stations":
                backend_mode = "DASHBOARD_FORECAST_STATIONS"
        else:
            raise ValueError(f"Unknown UI selection: {ui_selection}")

        # Validar datas
        is_valid, message = cls.validate_dates(
            backend_mode, request_start, request_end
        )
        if not is_valid:
            raise ValueError(
                f"Invalid dates for mode {backend_mode}: {message}"
            )

        # Montar payload
        payload = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": request_start.isoformat(),
            "end_date": request_end.isoformat(),
            "mode": backend_mode,
            "email": email if config["requires_email"] else None,
        }

        logger.info(f"📦 API request payload prepared: {payload}")

        return payload

    @classmethod
    def get_mode_info(cls, backend_mode: str) -> dict:
        """
        Retorna informações sobre um modo backend.

        Args:
            backend_mode: Nome do modo backend

        Returns:
            dict com configuração do modo
        """
        return cls.BACKEND_MODES.get(backend_mode, {})

    @classmethod
    def get_available_sources(cls, backend_mode: str) -> list:
        """
        Retorna fontes de dados disponíveis para um modo.

        Args:
            backend_mode: Nome do modo backend

        Returns:
            list de fontes disponíveis
        """
        config = cls.BACKEND_MODES.get(backend_mode, {})
        return config.get("sources", [])


def format_date_for_display(date_obj: date) -> str:
    """
    Formata data para exibição na UI.

    Args:
        date_obj: Objeto date

    Returns:
        String formatada (DD/MM/YYYY)
    """
    return date_obj.strftime("%d/%m/%Y")


def parse_date_from_ui(date_str: str) -> date:
    """
    Parse data vinda da UI (formato ISO ou DD/MM/YYYY).

    Args:
        date_str: String de data

    Returns:
        Objeto date
    """
    # Tentar formato ISO primeiro (YYYY-MM-DD)
    try:
        return datetime.fromisoformat(date_str).date()
    except (ValueError, AttributeError):
        pass

    # Tentar formato brasileiro (DD/MM/YYYY)
    try:
        return datetime.strptime(date_str, "%d/%m/%Y").date()
    except ValueError:
        pass

    raise ValueError(f"Unable to parse date: {date_str}")
