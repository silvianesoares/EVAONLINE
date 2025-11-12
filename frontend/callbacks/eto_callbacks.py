"""
Callbacks para página ETo.

Integração com 6 fontes climáticas do backend:
- Open-Meteo Archive: Histórico (1990 → hoje-2d)
- Open-Meteo Forecast: Previsão/Recent (hoje-30d → hoje+5d)
- NASA POWER: Histórico global (1990 → hoje-7d)
- MET Norway: Previsão global (hoje → hoje+5d)
- NWS Forecast: Previsão USA (hoje → hoje+5d)
- NWS Stations: Observações USA (hoje-1d → agora)

Validações (api_limits.py):
- Histórico: 1990-01-01 (padrão EVA), máx 90 dias
- Real-time: 7-30 dias
- Forecast: até +5 dias
"""

import logging
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html

logger = logging.getLogger(__name__)

# Importar helper do backend para fontes disponíveis
try:
    from backend.api.services.climate_source_selector import (
        get_available_sources_for_frontend,
    )
except ImportError:
    logger.warning(
        "⚠️ Não foi possível importar get_available_sources_for_frontend"
    )
    get_available_sources_for_frontend = None


def decimal_to_dms(decimal_coord, is_latitude=True):
    """
    Converte coordenada decimal para formato DMS (Degrees-Minutes-Seconds).

    Args:
        decimal_coord: Coordenada em decimal (-90 a 90 para lat, -180 a 180 para lon)
        is_latitude: True se for latitude, False se for longitude

    Returns:
        String formatada: "45°30'15.25"N" ou "120°15'30.50"W"
    """
    direction = ""
    if is_latitude:
        direction = "N" if decimal_coord >= 0 else "S"
    else:
        direction = "E" if decimal_coord >= 0 else "W"

    abs_coord = abs(decimal_coord)
    degrees = int(abs_coord)
    minutes = int((abs_coord - degrees) * 60)
    seconds = ((abs_coord - degrees) * 60 - minutes) * 60

    return f"{degrees}°{minutes}'{seconds:.2f}\"{direction}"


@callback(
    [
        Output("location-display", "children"),
        Output("parsed-coordinates", "data"),
    ],
    Input("navigation-coordinates", "data"),
)
def update_location_from_store(coords_data):
    """
    Atualiza exibição da localização com coordenadas do Store GLOBAL.

    Recebe: {"lat": float, "lon": float} do sessionStorage
    """
    # Log para debug
    logger.info(
        f"🔍 update_location_from_store chamado com coords_data: {coords_data}"
    )

    if not coords_data:
        logger.warning("⚠️ coords_data está vazio")
        return (
            html.Div(
                [
                    html.I(
                        className="bi bi-exclamation-circle me-2",
                        style={"color": "#856404"},
                    ),
                    html.Span(
                        "Nenhuma localização selecionada. ",
                        style={"color": "#856404"},
                    ),
                    dbc.Button(
                        [
                            html.I(className="bi bi-arrow-left me-2"),
                            "Voltar ao mapa",
                        ],
                        href="/",
                        color="warning",
                        size="sm",
                        outline=True,
                        className="ms-2",
                    ),
                ],
                className="d-flex align-items-center",
            ),
            None,
        )

    try:
        lat = coords_data.get("lat")
        lon = coords_data.get("lon")

        logger.info(f"🎯 lat={lat}, lon={lon}")

        if lat and lon:
            lat_f = float(lat)
            lon_f = float(lon)

            logger.info(f"✅ Coordenadas válidas: {lat_f}, {lon_f}")

            # Converter para DMS usando helper
            lat_dms = decimal_to_dms(lat_f, is_latitude=True)
            lon_dms = decimal_to_dms(lon_f, is_latitude=False)

            display = html.Div(
                [
                    html.Div(
                        [
                            html.I(
                                className="bi bi-geo-alt-fill me-2",
                                style={"fontSize": "1.2rem"},
                            ),
                            html.Div(
                                [
                                    html.Strong(
                                        "Coordenadas Selecionadas:",
                                        className="d-block",
                                    ),
                                    html.Span(
                                        f"Lat: {lat_dms} | Lon: {lon_dms}",
                                        className="d-block text-muted small",
                                    ),
                                    html.Span(
                                        f"Decimal: {lat_f:.6f}, {lon_f:.6f}",
                                        className="text-muted small",
                                    ),
                                ],
                                className="flex-grow-1",
                            ),
                        ],
                        className="d-flex align-items-start",
                    ),
                    dbc.Button(
                        [html.I(className="bi bi-pencil me-2"), "Alterar"],
                        href="/",
                        color="secondary",
                        size="sm",
                        outline=True,
                        className="ms-auto",
                    ),
                ],
                className="d-flex align-items-center justify-content-between w-100",
            )

            # Retornar display E coordenadas no Store
            return display, {"lat": lat_f, "lon": lon_f}
        else:
            logger.warning(
                f"⚠️ Coordenadas ausentes ou inválidas: lat={lat}, lon={lon}"
            )
            return (
                html.Div(
                    [
                        html.I(
                            className="bi bi-exclamation-circle me-2",
                            style={"color": "#856404"},
                        ),
                        html.Span(
                            "Coordenadas não encontradas na URL. ",
                            style={"color": "#856404"},
                        ),
                        dbc.Button(
                            [
                                html.I(className="bi bi-arrow-left me-2"),
                                "Voltar ao mapa",
                            ],
                            href="/",
                            color="warning",
                            size="sm",
                            outline=True,
                            className="ms-2",
                        ),
                    ],
                    className="d-flex align-items-center",
                ),
                None,
            )

    except Exception as e:
        logger.error(f"❌ Erro ao parsear URL params: {e}", exc_info=True)
        return (
            html.Div(
                [
                    html.I(
                        className="bi bi-exclamation-triangle me-2",
                        style={"color": "#721c24"},
                    ),
                    html.Span(
                        f"Erro ao processar coordenadas: {str(e)}",
                        style={"color": "#721c24"},
                    ),
                    dbc.Button(
                        [
                            html.I(className="bi bi-arrow-left me-2"),
                            "Voltar ao mapa",
                        ],
                        href="/",
                        color="danger",
                        size="sm",
                        outline=True,
                        className="ms-2",
                    ),
                ],
                className="d-flex align-items-center",
            ),
            None,
        )


@callback(
    Output("location-input-container", "children"),
    [
        Input("location-mode-radio", "value"),
        Input("url", "search"),
    ],
)
def render_location_input(mode, search):
    """
    Renderiza interface de entrada de coordenadas baseado no modo selecionado.

    - map: Exibe coordenadas recebidas via URL (ou alerta se não houver)
    - manual: Campos de entrada para lat/lon + botão validar
    """
    if mode == "map":
        # Modo mapa: mostra coordenadas da URL ou alerta
        if not search:
            return dbc.Alert(
                [
                    html.I(className="bi bi-info-circle me-2"),
                    html.Span(
                        "Clique no mapa da página inicial para selecionar uma localização."
                    ),
                ],
                color="info",
                className="mb-0",
            )

        # Parse URL params
        try:
            params = parse_qs(search.lstrip("?"))
            lat = float(params.get("lat", [None])[0])
            lon = float(params.get("lon", [None])[0])

            # Converter para DMS
            lat_dms = decimal_to_dms(lat, is_latitude=True)
            lon_dms = decimal_to_dms(lon, is_latitude=False)

            return html.Div(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Strong("Latitude:"),
                                    html.Br(),
                                    html.Span(f"{lat_dms} ({lat:.6f}°)"),
                                ],
                                width=6,
                            ),
                            dbc.Col(
                                [
                                    html.Strong("Longitude:"),
                                    html.Br(),
                                    html.Span(f"{lon_dms} ({lon:.6f}°)"),
                                ],
                                width=6,
                            ),
                        ],
                        className="mb-3",
                    ),
                    dbc.Button(
                        [
                            html.I(className="bi bi-arrow-left me-2"),
                            "Alterar no Mapa",
                        ],
                        href="/",
                        color="primary",
                        size="sm",
                        outline=True,
                    ),
                ],
            )
        except (ValueError, TypeError, KeyError):
            return dbc.Alert(
                [
                    html.I(className="bi bi-exclamation-triangle me-2"),
                    html.Span(
                        "Coordenadas inválidas. Clique no mapa para selecionar uma localização."
                    ),
                    html.Br(),
                    dbc.Button(
                        [
                            html.I(className="bi bi-arrow-left me-2"),
                            "Ir ao Mapa",
                        ],
                        href="/",
                        color="warning",
                        size="sm",
                        outline=True,
                        className="mt-2",
                    ),
                ],
                color="warning",
                className="mb-0",
            )

    else:  # mode == "manual"
        return html.Div(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label(
                                    "Latitude (°):",
                                    html_for="manual-lat-input",
                                ),
                                dbc.Input(
                                    id="manual-lat-input",
                                    type="number",
                                    placeholder="-90.0 a 90.0",
                                    min=-90,
                                    max=90,
                                    step=0.000001,
                                    className="mb-2",
                                ),
                                html.Small(
                                    "Valores negativos = Sul",
                                    className="text-muted",
                                ),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(
                                    "Longitude (°):",
                                    html_for="manual-lon-input",
                                ),
                                dbc.Input(
                                    id="manual-lon-input",
                                    type="number",
                                    placeholder="-180.0 a 180.0",
                                    min=-180,
                                    max=180,
                                    step=0.000001,
                                    className="mb-2",
                                ),
                                html.Small(
                                    "Valores negativos = Oeste",
                                    className="text-muted",
                                ),
                            ],
                            md=6,
                        ),
                    ],
                    className="mb-3",
                ),
                dbc.Button(
                    [
                        html.I(className="bi bi-check-circle me-2"),
                        "Validar Coordenadas",
                    ],
                    id="validate-coords-button",
                    color="success",
                    outline=True,
                    className="w-100",
                ),
                html.Div(id="coord-validation-feedback", className="mt-2"),
            ]
        )


@callback(
    [
        Output("coord-validation-feedback", "children"),
        Output("climate-source-dropdown", "options", allow_duplicate=True),
        Output("climate-source-dropdown", "value", allow_duplicate=True),
        Output("climate-source-dropdown", "disabled", allow_duplicate=True),
        Output("source-selection-info", "children", allow_duplicate=True),
    ],
    Input("validate-coords-button", "n_clicks"),
    [
        State("manual-lat-input", "value"),
        State("manual-lon-input", "value"),
    ],
    prevent_initial_call=True,
)
def validate_manual_coordinates(n_clicks, lat, lon):
    """
    Valida coordenadas inseridas manualmente e busca fontes disponíveis.
    """
    if not n_clicks:
        return "", [], None, True, ""

    # Validar entrada
    if lat is None or lon is None:
        return (
            dbc.Alert(
                [
                    html.I(className="bi bi-exclamation-triangle me-2"),
                    "Por favor, insira latitude e longitude.",
                ],
                color="warning",
                className="mb-0",
            ),
            [],
            None,
            True,
            "",
        )

    # Validar ranges
    if not (-90 <= lat <= 90):
        return (
            dbc.Alert(
                [
                    html.I(className="bi bi-x-circle me-2"),
                    "Latitude deve estar entre -90° e 90°.",
                ],
                color="danger",
                className="mb-0",
            ),
            [],
            None,
            True,
            "",
        )

    if not (-180 <= lon <= 180):
        return (
            dbc.Alert(
                [
                    html.I(className="bi bi-x-circle me-2"),
                    "Longitude deve estar entre -180° e 180°.",
                ],
                color="danger",
                className="mb-0",
            ),
            [],
            None,
            True,
            "",
        )

    # Buscar fontes disponíveis
    if get_available_sources_for_frontend is None:
        return (
            dbc.Alert(
                [
                    html.I(className="bi bi-exclamation-triangle me-2"),
                    "Serviço de seleção de fontes indisponível.",
                ],
                color="warning",
                className="mb-0",
            ),
            [],
            None,
            True,
            "",
        )

    try:
        sources_data = get_available_sources_for_frontend(lat, lon)

        # Formatar opções do dropdown
        dropdown_options = [
            {"label": source["label"], "value": source["value"]}
            for source in sources_data["sources"]
        ]

        # Info sobre região
        region = sources_data["location_info"]["region"]
        region_icon = (
            "🇺🇸"
            if sources_data["location_info"]["in_usa"]
            else ("🇳🇴" if sources_data["location_info"]["in_nordic"] else "🌍")
        )

        info_alert = dbc.Alert(
            [
                html.I(className="bi bi-info-circle me-2"),
                html.Strong(f"{region_icon} Região: {region}"),
                html.Br(),
                html.Small(
                    f"{sources_data['total_sources']} fontes de dados disponíveis para esta localização."
                ),
            ],
            color="info",
            className="mb-0",
        )

        # Sucesso
        lat_dms = decimal_to_dms(lat, is_latitude=True)
        lon_dms = decimal_to_dms(lon, is_latitude=False)

        feedback = dbc.Alert(
            [
                html.I(className="bi bi-check-circle me-2"),
                html.Strong("Coordenadas válidas!"),
                html.Br(),
                html.Small(f"Lat: {lat_dms} ({lat:.6f}°)"),
                html.Br(),
                html.Small(f"Lon: {lon_dms} ({lon:.6f}°)"),
            ],
            color="success",
            className="mb-0",
        )

        return (
            feedback,
            dropdown_options,
            sources_data["recommended"],
            False,
            info_alert,
        )

    except Exception as e:
        logger.error(f"❌ Erro ao buscar fontes: {e}")
        return (
            dbc.Alert(
                [
                    html.I(className="bi bi-x-circle me-2"),
                    f"Erro ao buscar fontes disponíveis: {str(e)}",
                ],
                color="danger",
                className="mb-0",
            ),
            [],
            None,
            True,
            "",
        )


@callback(
    [
        Output("climate-source-dropdown", "options", allow_duplicate=True),
        Output("climate-source-dropdown", "value", allow_duplicate=True),
        Output("climate-source-dropdown", "disabled", allow_duplicate=True),
        Output("source-selection-info", "children", allow_duplicate=True),
    ],
    Input("parsed-coordinates", "data"),
    prevent_initial_call="initial_duplicate",
)
def populate_sources_from_url(coords_data):
    """
    Popular dropdown de fontes quando coordenadas vêm da URL (modo mapa).
    """
    logger.info(
        f"🔍 populate_sources_from_url CHAMADO! coords_data={coords_data}"
    )

    if not coords_data:
        logger.warning("⚠️ coords_data vazio")
        return [], None, True, ""

    try:
        lat = coords_data.get("lat")
        lon = coords_data.get("lon")

        logger.info(f"📍 Coordenadas: lat={lat}, lon={lon}")

        if get_available_sources_for_frontend is None:
            logger.error("❌ get_available_sources_for_frontend = None")
            return [], None, True, ""

        logger.info("🔄 Chamando backend...")
        sources_data = get_available_sources_for_frontend(lat, lon)
        logger.info(
            f"✅ Backend retornou: {sources_data.get('total_sources')} fontes"
        )

        # Formatar opções do dropdown
        dropdown_options = [
            {"label": source["label"], "value": source["value"]}
            for source in sources_data["sources"]
        ]

        # Info sobre região
        region = sources_data["location_info"]["region"]
        region_icon = (
            "🇺🇸"
            if sources_data["location_info"]["in_usa"]
            else ("🇳🇴" if sources_data["location_info"]["in_nordic"] else "🌍")
        )

        info_alert = dbc.Alert(
            [
                html.I(className="bi bi-info-circle me-2"),
                html.Strong(f"{region_icon} Região: {region}"),
                html.Br(),
                html.Small(
                    f"{sources_data['total_sources']} fontes de dados disponíveis para esta localização."
                ),
            ],
            color="info",
            className="mb-0",
        )

        return (
            dropdown_options,
            sources_data["recommended"],
            False,
            info_alert,
        )

    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"⚠️ Erro ao processar URL para fontes: {e}")
        return [], None, True, ""


@callback(
    Output("source-description", "children"),
    Input("climate-source-dropdown", "value"),
)
def update_source_description(selected_source):
    """
    Atualiza descrição da fonte selecionada.
    """
    if not selected_source:
        return ""

    # Mapeamento de descrições
    descriptions = {
        "fusion": "🔀 Combina dados de múltiplas fontes automaticamente para melhor cobertura e precisão.",
        "openmeteo_forecast": "🌍 Dados de previsão e recentes (até 30 dias) com cobertura global.",
        "openmeteo_archive": "🌍 Dados históricos desde 1990 com cobertura global.",
        "nasa_power": "🛰️ Dados de satélite da NASA desde 1990.",
        "met_norway": "🇳🇴 Previsão meteorológica de alta qualidade para região nórdica.",
        "nws_forecast": "🇺🇸 Previsão oficial do National Weather Service (EUA).",
        "nws_stations": "🇺🇸 Observações de estações meteorológicas do NWS.",
    }

    return descriptions.get(selected_source, "")


@callback(
    Output("conditional-form", "children"),
    Input("data-type-radio", "value"),
)
def render_conditional_form(data_type):
    """
    Renderiza formulário condicional baseado no tipo de dados.

    - Histórico: date range (1990 → ontem)
    - Atual: últimos N dias (1-7)
    """
    if data_type == "historical":
        return html.Div(
            [
                html.Label(
                    "Período de Análise:",
                    className="fw-bold mb-3",
                    style={"fontSize": "1.1rem"},
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Label("Data Inicial:", className="mb-2"),
                                dcc.DatePickerSingle(
                                    id="start-date-historical",
                                    min_date_allowed=datetime(1990, 1, 1),
                                    max_date_allowed=datetime.now()
                                    - timedelta(days=1),
                                    initial_visible_month=datetime.now()
                                    - timedelta(days=30),
                                    date=datetime.now() - timedelta(days=30),
                                    display_format="DD/MM/YYYY",
                                    placeholder="Selecione a data",
                                    className="w-100",
                                ),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                html.Label("Data Final:", className="mb-2"),
                                dcc.DatePickerSingle(
                                    id="end-date-historical",
                                    min_date_allowed=datetime(1990, 1, 1),
                                    max_date_allowed=datetime.now()
                                    - timedelta(days=1),
                                    initial_visible_month=datetime.now(),
                                    date=datetime.now() - timedelta(days=1),
                                    display_format="DD/MM/YYYY",
                                    placeholder="Selecione a data",
                                    className="w-100",
                                ),
                            ],
                            md=6,
                        ),
                    ],
                    className="mb-3",
                ),
                html.Small(
                    "💡 Dados históricos: 01/01/1990 até ontem (padrão EVAonline)",
                    className="text-muted",
                ),
                html.Br(),
                html.Small(
                    "⚠️ Limite: 90 dias por requisição",
                    className="text-warning",
                ),
            ]
        )
    else:  # current
        return html.Div(
            [
                html.Label(
                    "Período de Análise:",
                    className="fw-bold mb-3",
                    style={"fontSize": "1.1rem"},
                ),
                # Sub-opções: Dados recentes vs Previsão
                dbc.RadioItems(
                    id="current-subtype-radio",
                    options=[
                        {
                            "label": "📊 Dados Recentes (até 30 dias atrás)",
                            "value": "recent",
                        },
                        {
                            "label": "🔮 Previsão (próximos 5 dias)",
                            "value": "forecast",
                        },
                    ],
                    value="recent",
                    className="mb-3",
                    inline=False,
                ),
                # Formulário condicional interno
                html.Div(id="current-subform"),
            ]
        )


# Callback para sub-formulário de dados atuais
@callback(
    Output("current-subform", "children"),
    Input("current-subtype-radio", "value"),
)
def render_current_subform(subtype):
    """Renderiza sub-formulário para dados atuais: recentes ou previsão."""
    if subtype == "recent":
        return html.Div(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Label("Últimos dias:", className="mb-2"),
                                dbc.Select(
                                    id="days-current",
                                    options=[
                                        {
                                            "label": "Últimos 7 dias",
                                            "value": "7",
                                        },
                                        {
                                            "label": "Últimos 14 dias",
                                            "value": "14",
                                        },
                                        {
                                            "label": "Últimos 21 dias",
                                            "value": "21",
                                        },
                                        {
                                            "label": "Últimos 30 dias",
                                            "value": "30",
                                        },
                                    ],
                                    value="7",
                                    className="w-100",
                                ),
                            ],
                            md=6,
                        ),
                    ],
                    className="mb-3",
                ),
                html.Small(
                    "💡 Dados recentes: mínimo 7 dias, máximo 30 dias",
                    className="text-muted",
                ),
                html.Br(),
                html.Small(
                    "📡 Fontes: Open-Meteo Forecast, MET Norway, NWS (se USA)",
                    className="text-info",
                ),
            ]
        )
    else:  # forecast
        return html.Div(
            [
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle me-2"),
                        html.Strong("Previsão de 5 dias"),
                        html.Br(),
                        "Será calculado ETo para os próximos 5 dias com base em dados de previsão meteorológica.",
                    ],
                    color="info",
                    className="mb-3",
                ),
                html.Small(
                    "� Período: hoje até hoje+5 dias (padrão EVAonline)",
                    className="text-muted",
                ),
                html.Br(),
                html.Small(
                    "📡 Fontes: Open-Meteo Forecast, MET Norway, NWS Forecast (se USA)",
                    className="text-info",
                ),
            ]
        )


@callback(
    Output("validation-alert", "children"),
    Input("calculate-eto-btn", "n_clicks"),
    State("url", "href"),
    State("data-type-radio", "value"),
    State("start-date-historical", "date"),
    State("end-date-historical", "date"),
    State("current-subtype-radio", "value"),
    State("days-current", "value"),
    prevent_initial_call=True,
)
def validate_calculation_inputs(
    n_clicks,
    href,
    data_type,
    start_date_hist,
    end_date_hist,
    current_subtype,
    days_current,
):
    """
    Valida inputs conforme regras do backend (api_limits.py).

    Validações:
    - Coordenadas válidas na URL
    - Histórico: 1990-01-01 → ontem, máx 90 dias
    - Atual: 7-30 dias
    - start_date < end_date
    """
    if n_clicks == 0:
        return None

    errors = []

    # Valida localização
    if not href:
        errors.append("❌ Nenhuma localização selecionada")
    else:
        try:
            parsed = urlparse(href)
            params = parse_qs(parsed.query)
            lat = params.get("lat", [None])[0]
            lon = params.get("lon", [None])[0]

            if not lat or not lon:
                errors.append("❌ Coordenadas inválidas na URL")
            else:
                lat_f = float(lat)
                lon_f = float(lon)
                if not (-90 <= lat_f <= 90) or not (-180 <= lon_f <= 180):
                    errors.append("❌ Coordenadas fora dos limites válidos")
        except Exception:
            errors.append("❌ Erro ao processar coordenadas")

    # Valida datas (histórico)
    if data_type == "historical":
        if not start_date_hist or not end_date_hist:
            errors.append("❌ Selecione as datas de início e fim")
        else:
            try:
                start = datetime.fromisoformat(
                    start_date_hist.replace("Z", "")
                )
                end = datetime.fromisoformat(end_date_hist.replace("Z", ""))
                yesterday = datetime.now() - timedelta(days=1)
                eva_start = datetime(1990, 1, 1)

                if start < eva_start:
                    errors.append(
                        "❌ Data inicial deve ser >= 01/01/1990 (padrão EVA)"
                    )

                if start >= end:
                    errors.append(
                        "❌ Data inicial deve ser anterior à data final"
                    )

                if end.date() > yesterday.date():
                    errors.append(
                        "❌ Data final não pode ser posterior a ontem"
                    )

                # Limita período a 90 dias (regra api_limits.py)
                days = (end - start).days + 1
                if days > 90:
                    errors.append(
                        f"⚠️ Período máximo: 90 dias (solicitado: {days} dias)"
                    )

            except Exception:
                errors.append("❌ Formato de data inválido")

    # Valida dias (atual - recent)
    if data_type == "current":
        if current_subtype == "recent":
            if not days_current or int(days_current) not in [7, 14, 21, 30]:
                errors.append("❌ Selecione um período válido (7-30 dias)")
        elif current_subtype == "forecast":
            # Previsão sempre válida (5 dias fixo)
            pass

    # Retorna alertas
    if errors:
        return dbc.Alert(
            [html.P(error, className="mb-1") for error in errors],
            color="danger",
            dismissable=True,
        )
    else:
        # Sucesso - backend ainda não implementado
        return dbc.Alert(
            [
                html.I(className="bi bi-check-circle me-2"),
                html.Strong("✅ Validação OK! "),
                "Todos os parâmetros estão corretos. ",
                html.Br(),
                html.Small(
                    "🔧 Backend de cálculo ETo será implementado na próxima fase."
                ),
            ],
            color="success",
            dismissable=True,
        )


@callback(
    Output("eto-results-container", "children"),
    Input("calculate-eto-btn", "n_clicks"),
    [
        State("navigation-coordinates", "data"),  # ✅ LER DO STORE!
        State("climate-source-dropdown", "value"),
        State("data-type-radio", "value"),
        State("start-date-historical", "date"),
        State("end-date-historical", "date"),
    ],
    prevent_initial_call=True,
)
def calculate_eto(
    n_clicks,
    coords_data,
    selected_source,
    data_type,
    start_date_hist,
    end_date_hist,
):
    """
    Calcula ETo chamando o backend com validação completa de parâmetros.

    Validações:
    - Coordenadas válidas no Store
    - Fonte de dados selecionada
    - Datas dentro dos limites da API
    - Período não excede 90 dias para histórico
    """
    logger.info(
        f"🧮 calculate_eto CHAMADO! n_clicks={n_clicks}, data_type={data_type}, start_date={start_date_hist}, end_date={end_date_hist}"
    )

    if n_clicks is None or n_clicks == 0:
        logger.warning("⚠️ Abortando - n_clicks vazio ou zero")
        return None

    logger.info(f"✅ Prosseguindo com validação...")

    # ========================================================================
    # 1. VALIDAR COORDENADAS (do Store)
    # ========================================================================
    if not coords_data:
        logger.error("❌ coords_data vazio")
        return dbc.Alert(
            [
                html.I(className="bi bi-exclamation-triangle me-2"),
                html.Strong("Erro: "),
                "Coordenadas não encontradas. Selecione uma localização no mapa.",
            ],
            color="danger",
        )

    try:
        lat = float(coords_data.get("lat"))
        lon = float(coords_data.get("lon"))

        # Validar ranges
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            logger.error(f"❌ Coordenadas inválidas: lat={lat}, lon={lon}")
            return dbc.Alert(
                [
                    html.I(className="bi bi-exclamation-triangle me-2"),
                    html.Strong("Erro: "),
                    f"Coordenadas inválidas (lat={lat:.6f}, lon={lon:.6f}).",
                ],
                color="danger",
            )

    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"❌ Erro ao parsear coordenadas: {e}")
        return dbc.Alert(
            [
                html.I(className="bi bi-exclamation-triangle me-2"),
                html.Strong("Erro: "),
                "Falha ao processar coordenadas.",
            ],
            color="danger",
        )

    # ========================================================================
    # 2. VALIDAR FONTE DE DADOS
    # ========================================================================
    if not selected_source:
        logger.error("❌ Nenhuma fonte selecionada")
        return dbc.Alert(
            [
                html.I(className="bi bi-exclamation-triangle me-2"),
                html.Strong("Erro: "),
                "Selecione uma fonte de dados climáticos.",
            ],
            color="warning",
        )

    logger.info(f"📡 Fonte selecionada: {selected_source}")

    # ========================================================================
    # 3. VALIDAR DATAS (depende do tipo de dado)
    # ========================================================================
    from datetime import datetime, timedelta

    if data_type == "historical":
        if not start_date_hist or not end_date_hist:
            return dbc.Alert(
                [
                    html.I(className="bi bi-exclamation-triangle me-2"),
                    html.Strong("Erro: "),
                    "Informe as datas de início e fim para dados históricos.",
                ],
                color="warning",
            )

        try:
            start_dt = datetime.fromisoformat(start_date_hist)
            end_dt = datetime.fromisoformat(end_date_hist)

            # Validar ordem das datas
            if start_dt > end_dt:
                return dbc.Alert(
                    [
                        html.I(className="bi bi-exclamation-triangle me-2"),
                        html.Strong("Erro: "),
                        "Data de início deve ser anterior à data de fim.",
                    ],
                    color="warning",
                )

            # Validar limites (1990-01-01 até hoje-7 dias)
            min_date = datetime(1990, 1, 1)
            max_date = datetime.now() - timedelta(days=7)

            if start_dt < min_date:
                return dbc.Alert(
                    [
                        html.I(className="bi bi-exclamation-triangle me-2"),
                        html.Strong("Erro: "),
                        f"Data de início deve ser posterior a {min_date.strftime('%d/%m/%Y')}.",
                    ],
                    color="warning",
                )

            if end_dt > max_date:
                return dbc.Alert(
                    [
                        html.I(className="bi bi-exclamation-triangle me-2"),
                        html.Strong("Erro: "),
                        f"Data de fim deve ser anterior a {max_date.strftime('%d/%m/%Y')} (delay de 7 dias).",
                    ],
                    color="warning",
                )

            # Validar período máximo (90 dias)
            days_diff = (end_dt - start_dt).days
            if days_diff > 90:
                return dbc.Alert(
                    [
                        html.I(className="bi bi-exclamation-triangle me-2"),
                        html.Strong("Erro: "),
                        f"Período máximo: 90 dias. Você selecionou {days_diff} dias.",
                    ],
                    color="warning",
                )

        except ValueError as e:
            return dbc.Alert(
                [
                    html.I(className="bi bi-exclamation-triangle me-2"),
                    html.Strong("Erro: "),
                    f"Formato de data inválido: {str(e)}",
                ],
                color="danger",
            )

    # ========================================================================
    # 4. CHAMAR BACKEND (TODO: implementar requisição HTTP)
    # ========================================================================
    logger.info(f"✅ Validações OK - Pronto para chamar backend")
    logger.info(f"   📍 Coordenadas: lat={lat:.6f}, lon={lon:.6f}")
    logger.info(f"   📡 Fonte: {selected_source}")
    logger.info(f"   📅 Tipo: {data_type}")

    # ========================================================================
    # 4. FAZER REQUISIÇÃO HTTP PARA BACKEND
    # ========================================================================
    import requests

    try:
        logger.info("🔄 Enviando requisição para backend...")

        # Preparar payload
        payload = {
            "lat": lat,
            "lng": lon,  # Backend usa "lng" não "lon"
            "start_date": start_date_hist,
            "end_date": end_date_hist,
            "sources": selected_source,  # Ex: "fusion", "openmeteo_forecast", etc
        }

        logger.info(f"📦 Payload: {payload}")

        # Fazer requisição POST
        response = requests.post(
            "http://localhost:8000/api/v1/internal/eto/calculate",
            json=payload,
            timeout=30,  # 30 segundos
        )

        # Verificar status
        if response.status_code == 200:
            logger.info("✅ Backend respondeu com sucesso!")
            results = response.json()
            logger.info(
                f"📊 Resultados recebidos: {len(results.get('data', []))} registros"
            )

            # TODO: Criar visualização dos resultados
            return dbc.Card(
                [
                    dbc.CardHeader(
                        [
                            html.H5(
                                [
                                    html.I(
                                        className="bi bi-check-circle-fill me-2"
                                    ),
                                    "Cálculo Concluído",
                                ],
                                className="mb-0",
                            )
                        ]
                    ),
                    dbc.CardBody(
                        [
                            dbc.Alert(
                                [
                                    html.I(
                                        className="bi bi-check-circle-fill me-2"
                                    ),
                                    html.Strong(
                                        f"✅ Sucesso! {len(results.get('data', []))} dias calculados"
                                    ),
                                    html.Br(),
                                    html.Br(),
                                    html.Pre(
                                        str(results)[:500] + "..."
                                    ),  # Preview dos dados
                                ],
                                color="success",
                            ),
                        ]
                    ),
                ],
                className="mt-4",
            )
        else:
            logger.error(f"❌ Backend retornou erro {response.status_code}")
            return dbc.Alert(
                [
                    html.I(className="bi bi-exclamation-triangle me-2"),
                    html.Strong(f"Erro {response.status_code}: "),
                    response.text[:200],
                ],
                color="danger",
            )

    except requests.Timeout:
        logger.error("⏱️ Timeout na requisição ao backend")
        return dbc.Alert(
            [
                html.I(className="bi bi-clock-fill me-2"),
                html.Strong("Timeout: "),
                "O backend demorou muito para responder (>30s). Tente novamente.",
            ],
            color="warning",
        )

    except requests.ConnectionError:
        logger.error("🔌 Erro de conexão com backend")
        return dbc.Alert(
            [
                html.I(className="bi bi-plug-fill me-2"),
                html.Strong("Erro de conexão: "),
                "Não foi possível conectar ao backend. Certifique-se de que está rodando em http://localhost:8000",
            ],
            color="danger",
        )

    except Exception as e:
        logger.error(f"💥 Erro inesperado: {str(e)}")
        return dbc.Alert(
            [
                html.I(className="bi bi-exclamation-octagon-fill me-2"),
                html.Strong("Erro inesperado: "),
                str(e),
            ],
            color="danger",
        )

    # Fallback (nunca deve chegar aqui)
    return dbc.Card(
        [
            dbc.CardHeader(
                [
                    html.H5(
                        [
                            html.I(className="bi bi-check-circle-fill me-2"),
                            "Validação Concluída",
                        ],
                        className="mb-0",
                    )
                ]
            ),
            dbc.CardBody(
                [
                    dbc.Alert(
                        [
                            html.I(className="bi bi-info-circle-fill me-2"),
                            html.Strong(
                                "✅ Todos os parâmetros validados com sucesso!"
                            ),
                            html.Br(),
                            html.Br(),
                            html.Strong("Próximos passos:"),
                            html.Ul(
                                [
                                    html.Li(
                                        f"📍 Coordenadas: {lat:.6f}, {lon:.6f}"
                                    ),
                                    html.Li(f"📡 Fonte: {selected_source}"),
                                    html.Li(f"📅 Tipo: {data_type}"),
                                    html.Li(
                                        "🔄 Integrar com backend/api/routes/eto_routes.py"
                                    ),
                                    html.Li(
                                        "📊 Exibir gráficos e tabelas de resultados"
                                    ),
                                ]
                            ),
                        ],
                        color="success",
                    ),
                ]
            ),
        ],
        className="mt-4",
    )


logger.info("✅ Página ETo carregada com sucesso")
