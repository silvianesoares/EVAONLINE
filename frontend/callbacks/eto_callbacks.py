"""
Callbacks para página ETo.
"""

import dash_bootstrap_components as dbc
import logging
from dash import Input, Output, State
from dash import html
from frontend.services.api_client import APIClient

logger = logging.getLogger(__name__)


def register_eto_callbacks(app):
    """Registra callbacks ETo."""

    @app.callback(
        Output("eto-location-info", "children"),
        Input("current-location", "data"),
        State("url", "pathname"),
    )
    def update_eto_location_info(current_location, pathname):
        """
        Exibe informações da localização selecionada na página ETo.
        """
        if (
            pathname != "/eto-calculator"
            or not current_location
            or not current_location.get("lat")
        ):
            return dbc.Alert(
                [
                    html.I(className="bi bi-exclamation-triangle me-2"),
                    "Nenhuma localização selecionada. ",
                    html.A("Volte para a página inicial", href="/"),
                    " e selecione um ponto no mapa.",
                ],
                color="warning",
                className="my-3",
            )
        # Criar card informativo para a página ETo
        lat_dms = current_location.get("lat_dms", "N/A")
        lon_dms = current_location.get("lon_dms", "N/A")
        lat = current_location.get("lat", 0)
        lon = current_location.get("lon", 0)
        timezone = current_location.get("timezone", "N/A")
        location_info = current_location.get(
            "location_info", "Local não identificado"
        )
        return dbc.Card(
            [
                dbc.CardHeader("📍 Localização para Cálculo ETo"),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.H6(
                                            "Coordenadas:",
                                            className="fw-bold",
                                        ),
                                        html.P(f"Latitude: {lat_dms}"),
                                        html.P(f"Longitude: {lon_dms}"),
                                        html.P(
                                            f"Decimal: ({lat:.6f}, {lon:.6f})",
                                            className="text-muted small",
                                        ),
                                    ],
                                    width=4,
                                ),
                                dbc.Col(
                                    [
                                        html.H6(
                                            "Fuso Horário:",
                                            className="fw-bold",
                                        ),
                                        html.P(
                                            timezone,
                                            className="text-primary fw-bold",
                                        ),
                                    ],
                                    width=4,
                                ),
                                dbc.Col(
                                    [
                                        html.H6(
                                            "Localização:",
                                            className="fw-bold",
                                        ),
                                        html.P(
                                            location_info,
                                            className="small",
                                        ),
                                    ],
                                    width=4,
                                ),
                            ]
                        )
                    ]
                ),
            ],
            color="info",
            outline=True,
        )

    # Callback assíncrono para calcular ETo
    @app.callback(
        Output("eto-result", "children"),
        Input("calculate-eto-btn", "n_clicks"),
        State("current-location", "data"),
        prevent_initial_call=True,
    )
    async def calculate_eto(n_clicks, current_location):
        """
        Calcula ETo para a localização selecionada.
        """
        if not n_clicks or not current_location:
            return dbc.Alert(
                "Selecione uma localização primeiro", color="warning"
            )

        try:
            # Instanciar cliente API localmente
            api_client = APIClient()

            # Preparar dados para API
            location_data = {
                "lat": current_location.get("lat"),
                "lon": current_location.get("lon"),
                "timezone": current_location.get("timezone"),
                "start_date": "2024-01-01",  # Data padrão, pode ser configurável
                "end_date": "2024-01-31",
            }

            # Chamar API backend
            logger.info("📊 Calculando ETo via API...")
            result = await api_client.calculate_eto(location_data)

            # Processar resultado
            eto_value = result.get("eto", 0)
            unit = result.get("unit", "mm/day")

            return dbc.Card(
                [
                    dbc.CardHeader("✅ Resultado do Cálculo ETo"),
                    dbc.CardBody(
                        html.H4(
                            f"{eto_value} {unit}",
                            className="text-center text-success",
                        )
                    ),
                ],
                className="mt-3",
            )

        except Exception as e:
            logger.error(f"❌ Erro no cálculo ETo: {e}")
            return dbc.Alert(f"Erro ao calcular ETo: {str(e)}", color="danger")

    # Final do callback update_eto_location_info
    logger.info("✅ Callbacks ETo registrados")
