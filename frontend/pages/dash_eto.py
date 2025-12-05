"""
Página de cálculo ETo do ETO Calculator.

Features:
- Recebe coordenadas da home via URL params
- Radio buttons "Dados Históricos" vs "Dados Atuais"
- Formulário condicional (campos mudam conforme escolha)
- Validações de data (min/max)
- Botão "CALCULAR ETO" (ainda sem backend)
"""

import logging

import dash_bootstrap_components as dbc
from dash import dcc, html

logger = logging.getLogger(__name__)

# Layout da página ETo
eto_layout = html.Div(
    [
        dbc.Container(
            [
                # Cabeçalho da página
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.H1(
                                    "📊 ETo Calculator",
                                    className="text-center mb-3",
                                    style={
                                        "color": "#2c3e50",
                                        "fontWeight": "bold",
                                    },
                                ),
                                html.P(
                                    "Calculate Reference Evapotranspiration (ET₀) using the FAO-56 Penman-Monteith method",
                                    className="text-center lead text-muted mb-4",
                                ),
                            ],
                            width=12,
                        )
                    ]
                ),
                # Card de Localização com opções: Mapa ou Manual
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Card(
                                    [
                                        dbc.CardHeader(
                                            [
                                                html.H6(
                                                    "📍 Location",
                                                    className="mb-0",
                                                )
                                            ]
                                        ),
                                        dbc.CardBody(
                                            [
                                                # Radio: Mapa vs Manual
                                                dbc.RadioItems(
                                                    id="location-mode-radio",
                                                    options=[
                                                        {
                                                            "label": "🗺️ Use map coordinates",
                                                            "value": "map",
                                                        },
                                                        {
                                                            "label": "✍️ Enter coordinates manually",
                                                            "value": "manual",
                                                        },
                                                    ],
                                                    value="map",
                                                    className="mb-3",
                                                    inline=False,
                                                ),
                                                # Display textual das coordenadas (atualizado por callbacks)
                                                html.Div(
                                                    id="location-display",
                                                    className="mb-3",
                                                ),
                                                # Container condicional (formulário mapa vs manual)
                                                html.Div(
                                                    id="location-input-container"
                                                ),
                                            ]
                                        ),
                                    ],
                                    className="mb-4",
                                    style={"borderLeft": "4px solid #00695c"},
                                ),
                            ],
                            width=12,
                        )
                    ]
                ),
                # Card de Seleção de Fonte de Dados
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Card(
                                    [
                                        dbc.CardHeader(
                                            [
                                                html.H6(
                                                    "🌐 Climate Data Source",
                                                    className="mb-0",
                                                )
                                            ]
                                        ),
                                        dbc.CardBody(
                                            [
                                                html.Div(
                                                    id="source-selection-info",
                                                    className="mb-3",
                                                ),
                                                dbc.Select(
                                                    id="climate-source-dropdown",
                                                    placeholder="Select the data source...",
                                                    disabled=True,
                                                    className="mb-2",
                                                ),
                                                html.Small(
                                                    id="source-description",
                                                    className="text-muted",
                                                ),
                                            ]
                                        ),
                                    ],
                                    className="mb-4",
                                    style={"borderLeft": "4px solid #1976d2"},
                                ),
                            ],
                            width=12,
                        )
                    ]
                ),
                # Card principal de configuração e cálculo
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Card(
                                    [
                                        dbc.CardHeader(
                                            [
                                                html.H5(
                                                    "⚙️ Calculation Settings",
                                                    className="mb-0",
                                                )
                                            ]
                                        ),
                                        dbc.CardBody(
                                            [
                                                # Radio buttons: Dados Históricos vs Dados Atuais
                                                html.Label(
                                                    "Data Type:",
                                                    className="fw-bold mb-3",
                                                    style={
                                                        "fontSize": "1.1rem"
                                                    },
                                                ),
                                                dbc.RadioItems(
                                                    id="data-type-radio",
                                                    options=[
                                                        {
                                                            "label": "📅 Historical Data (1990 - today)",
                                                            "value": "historical",
                                                        },
                                                        {
                                                            "label": "🌤️ Current Data (last 7 days)",
                                                            "value": "current",
                                                        },
                                                    ],
                                                    value="historical",
                                                    className="mb-4",
                                                    inline=False,
                                                ),
                                                html.Hr(className="my-4"),
                                                # Formulário condicional (muda conforme seleção)
                                                html.Div(
                                                    id="conditional-form"
                                                ),
                                                html.Hr(className="my-4"),
                                                # Botão de cálculo
                                                dbc.Button(
                                                    [
                                                        html.I(
                                                            className="bi bi-calculator me-2"
                                                        ),
                                                        "CALCULATE ETO",
                                                    ],
                                                    id="calculate-eto-btn",
                                                    color="success",
                                                    size="lg",
                                                    className="w-100",
                                                    style={
                                                        "fontWeight": "600",
                                                        "fontSize": "1.1rem",
                                                        "padding": "12px",
                                                    },
                                                    n_clicks=0,
                                                ),
                                                # Alert de validação
                                                html.Div(
                                                    id="validation-alert",
                                                    className="mt-3",
                                                ),
                                                # Operation mode indicator
                                                html.Div(
                                                    id="operation-mode-indicator",
                                                    className="mt-2",
                                                ),
                                            ]
                                        ),
                                    ],
                                    className="mb-4 shadow-sm",
                                ),
                            ],
                            md=8,
                        ),
                        # Coluna lateral com informações
                        dbc.Col(
                            [
                                # Card: Sobre o método
                                dbc.Card(
                                    [
                                        dbc.CardHeader(
                                            [
                                                html.H6(
                                                    "🔬 FAO-56 Method",
                                                    className="mb-0",
                                                )
                                            ]
                                        ),
                                        dbc.CardBody(
                                            [
                                                html.P(
                                                    "The FAO-56 Penman-Monteith method is the international standard for calculating reference evapotranspiration (ET₀).",
                                                    className="small",
                                                ),
                                                html.P(
                                                    [
                                                        html.Strong(
                                                            "Required parameters:"
                                                        ),
                                                        html.Br(),
                                                        "• Air temperature",
                                                        html.Br(),
                                                        "• Relative humidity",
                                                        html.Br(),
                                                        "• Wind speed",
                                                        html.Br(),
                                                        "• Solar radiation",
                                                    ],
                                                    className="small mb-0",
                                                ),
                                            ]
                                        ),
                                    ],
                                    className="mb-3",
                                ),
                                # Card: Fontes de dados
                                dbc.Card(
                                    [
                                        dbc.CardHeader(
                                            [
                                                html.H6(
                                                    "📡 Data Sources",
                                                    className="mb-0",
                                                )
                                            ]
                                        ),
                                        dbc.CardBody(
                                            [
                                                html.P(
                                                    [
                                                        html.Strong(
                                                            "Open-Meteo: "
                                                        ),
                                                        "High-resolution global data (recommended)",
                                                    ],
                                                    className="small mb-2",
                                                ),
                                                html.P(
                                                    [
                                                        html.Strong(
                                                            "NASA POWER: "
                                                        ),
                                                        "Global historical data since 1990",
                                                    ],
                                                    className="small mb-0",
                                                ),
                                            ]
                                        ),
                                    ],
                                    className="mb-3",
                                ),
                            ],
                            md=4,
                        ),
                    ]
                ),
                # Card de resultados (aparece após cálculo)
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Div(id="eto-results-container"),
                            ],
                            width=12,
                        )
                    ]
                ),
                # Store para coordenadas parseadas da URL
                dcc.Store(id="parsed-coordinates", data=None),
            ],
            fluid=False,
            className="py-4",
        ),
    ]
)

logger.info("✅ ETo page loaded successfully")


# Helper functions for the ETo page
def create_period_validation_alert(is_valid, message):
    """
    Creates validation alert for selected period.
    Args:
        is_valid (bool): Whether the period is valid
        message (str): Validation message
    Returns:
        dbc.Alert: Validation alert
    """
    color = "success" if is_valid else "danger"
    icon = "bi bi-check-circle" if is_valid else "bi bi-exclamation-triangle"
    return dbc.Alert(
        [
            html.I(className=f"{icon} me-2"),
            html.Strong(
                ("Valid period: " if is_valid else "Invalid period: ")
            ),
            message,
        ],
        color=color,
        className="py-2",
    )


def create_eto_results_card(results_data):
    """
    Creates card with ETo calculation results.
    Args:
        results_data (dict): Results data
    Returns:
        dbc.Card: Card with results
    """
    if not results_data:
        return dbc.Alert(
            "No results available. Please run the calculation first.",
            color="warning",
        )
    return dbc.Card(
        [
            dbc.CardHeader(
                [html.H6("📊 ETo Calculation Results", className="mb-0")]
            ),
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.P(
                                        [
                                            html.Strong("Average ETo: "),
                                            html.Span(
                                                f"{results_data.get('eto_mean', 0):.2f} mm/day",
                                                className="text-success fw-bold",
                                            ),
                                        ]
                                    ),
                                    html.P(
                                        [
                                            html.Strong("Maximum ETo: "),
                                            f"{results_data.get('eto_max', 0):.2f} mm/day",
                                        ]
                                    ),
                                    html.P(
                                        [
                                            html.Strong("Minimum ETo: "),
                                            f"{results_data.get('eto_min', 0):.2f} mm/day",
                                        ]
                                    ),
                                ],
                                md=6,
                            ),
                            dbc.Col(
                                [
                                    html.P(
                                        [
                                            html.Strong("Period: "),
                                            f"{results_data.get('start_date', 'N/A')} to "
                                            f"{results_data.get('end_date', 'N/A')}",
                                        ]
                                    ),
                                    html.P(
                                        [
                                            html.Strong("Calculated days: "),
                                            str(
                                                results_data.get(
                                                    "days_count", 0
                                                )
                                            ),
                                        ]
                                    ),
                                    html.P(
                                        [
                                            html.Strong("Source: "),
                                            results_data.get(
                                                "data_source", "N/A"
                                            ),
                                        ]
                                    ),
                                ],
                                md=6,
                            ),
                        ]
                    ),
                    html.Hr(),
                    html.P(
                        [
                            html.Small(
                                "These values represent the reference evapotranspiration (ETo) calculated using the standard FAO-56 Penman-Monteith method.",
                                className="text-muted",
                            )
                        ]
                    ),
                ]
            ),
        ]
    )


def create_calculation_error_alert(error_message):
    """
    Creates an error alert for calculation.
    Args:
        error_message (str): Error message
    Returns:
        dbc.Alert: Error alert
    """
    return dbc.Alert(
        [
            html.I(className="bi bi-exclamation-triangle me-2"),
            html.Strong("Calculation error: "),
            error_message,
            html.Br(),
            html.Small(
                "Please check the selected location and try again.",
                className="text-muted",
            ),
        ],
        color="danger",
        className="my-3",
    )


logger.info("✅ ETo page loaded successfully")
