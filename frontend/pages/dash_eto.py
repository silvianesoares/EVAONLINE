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
                                    "📊 Calculadora ETo",
                                    className="text-center mb-3",
                                    style={
                                        "color": "#2c3e50",
                                        "fontWeight": "bold",
                                    },
                                ),
                                html.P(
                                    "Calcule a Evapotranspiração de Referência (ET₀) usando o método FAO-56 Penman-Monteith",
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
                                                    "📍 Localização",
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
                                                            "label": "🗺️ Usar coordenadas do mapa",
                                                            "value": "map",
                                                        },
                                                        {
                                                            "label": "✍️ Inserir coordenadas manualmente",
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
                                                    "🌐 Fonte de Dados Climáticos",
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
                                                    placeholder="Selecione a fonte de dados...",
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
                                                    "⚙️ Configurações do Cálculo",
                                                    className="mb-0",
                                                )
                                            ]
                                        ),
                                        dbc.CardBody(
                                            [
                                                # Radio buttons: Dados Históricos vs Dados Atuais
                                                html.Label(
                                                    "Tipo de Dados:",
                                                    className="fw-bold mb-3",
                                                    style={
                                                        "fontSize": "1.1rem"
                                                    },
                                                ),
                                                dbc.RadioItems(
                                                    id="data-type-radio",
                                                    options=[
                                                        {
                                                            "label": "📅 Dados Históricos (1940 - hoje)",
                                                            "value": "historical",
                                                        },
                                                        {
                                                            "label": "🌤️ Dados Atuais (últimos 7 dias)",
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
                                                        "CALCULAR ETO",
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
                                                    "🔬 Método FAO-56",
                                                    className="mb-0",
                                                )
                                            ]
                                        ),
                                        dbc.CardBody(
                                            [
                                                html.P(
                                                    "O método Penman-Monteith FAO-56 é o padrão internacional "
                                                    "para cálculo de evapotranspiração de referência (ET₀).",
                                                    className="small",
                                                ),
                                                html.P(
                                                    [
                                                        html.Strong(
                                                            "Parâmetros necessários:"
                                                        ),
                                                        html.Br(),
                                                        "• Temperatura do ar",
                                                        html.Br(),
                                                        "• Umidade relativa",
                                                        html.Br(),
                                                        "• Velocidade do vento",
                                                        html.Br(),
                                                        "• Radiação solar",
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
                                                    "📡 Fontes de Dados",
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
                                                        "Dados globais de alta resolução (recomendado)",
                                                    ],
                                                    className="small mb-2",
                                                ),
                                                html.P(
                                                    [
                                                        html.Strong(
                                                            "NASA POWER: "
                                                        ),
                                                        "Dados históricos globais desde 1940",
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

logger.info("✅ Página ETo carregada com sucesso")


# Funções auxiliares para a página ETo
def create_period_validation_alert(is_valid, message):
    """
    Cria alerta de validação do período selecionado.
    Args:
        is_valid (bool): Se o período é válido
        message (str): Mensagem de validação
    Returns:
        dbc.Alert: Alerta de validação
    """
    color = "success" if is_valid else "danger"
    icon = "bi bi-check-circle" if is_valid else "bi bi-exclamation-triangle"
    return dbc.Alert(
        [
            html.I(className=f"{icon} me-2"),
            html.Strong(
                "Período " + ("válido" if is_valid else "inválido") + ": "
            ),
            message,
        ],
        color=color,
        className="py-2",
    )


def create_eto_results_card(results_data):
    """
    Cria card com os resultados do cálculo ETo.
    Args:
        results_data (dict): Dados dos resultados
    Returns:
        dbc.Card: Card com resultados
    """
    if not results_data:
        return dbc.Alert(
            "Nenhum resultado disponível. Execute o cálculo primeiro.",
            color="warning",
        )
    return dbc.Card(
        [
            dbc.CardHeader(
                [html.H6("📊 Resultados do Cálculo ETo", className="mb-0")]
            ),
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.P(
                                        [
                                            html.Strong("ETo Média: "),
                                            html.Span(
                                                f"{results_data.get('eto_mean', 0):.2f} mm/dia",
                                                className="text-success fw-bold",
                                            ),
                                        ]
                                    ),
                                    html.P(
                                        [
                                            html.Strong("ETo Máxima: "),
                                            f"{results_data.get('eto_max', 0):.2f} mm/dia",
                                        ]
                                    ),
                                    html.P(
                                        [
                                            html.Strong("ETo Mínima: "),
                                            f"{results_data.get('eto_min', 0):.2f} mm/dia",
                                        ]
                                    ),
                                ],
                                md=6,
                            ),
                            dbc.Col(
                                [
                                    html.P(
                                        [
                                            html.Strong("Período: "),
                                            f"{results_data.get('start_date', 'N/A')} a "
                                            f"{results_data.get('end_date', 'N/A')}",
                                        ]
                                    ),
                                    html.P(
                                        [
                                            html.Strong("Dias calculados: "),
                                            str(
                                                results_data.get(
                                                    "days_count", 0
                                                )
                                            ),
                                        ]
                                    ),
                                    html.P(
                                        [
                                            html.Strong("Fonte: "),
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
                                "Estes valores representam a evapotranspiração de "
                                "referência (ETo) calculada usando o método "
                                "Penman-Monteith padrão FAO-56.",
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
    Cria alerta de erro no cálculo.
    Args:
        error_message (str): Mensagem de erro
    Returns:
        dbc.Alert: Alerta de erro
    """
    return dbc.Alert(
        [
            html.I(className="bi bi-exclamation-triangle me-2"),
            html.Strong("Erro no cálculo: "),
            error_message,
            html.Br(),
            html.Small(
                "Verifique a localização selecionada e tente novamente.",
                className="text-muted",
            ),
        ],
        color="danger",
        className="my-3",
    )


logger.info("✅ Página ETo carregada com sucesso")
