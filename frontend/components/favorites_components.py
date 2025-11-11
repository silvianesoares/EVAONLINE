"""
Componentes relacionados ao sistema de favoritos.

Contém:
- Botão Salvar Favorito
- Botão Calcular ETo
- Botão Limpar Favoritos
- Componentes da lista de favoritos
"""

import logging

import dash_bootstrap_components as dbc
from dash import html

logger = logging.getLogger(__name__)


def create_favorite_button():
    """
    Cria botão para salvar localização atual nos favoritos.
    Returns:
        dbc.Button: Botão Salvar Favorito
    """
    return dbc.Button(
        [html.I(className="bi bi-star me-2"), "⭐ Salvar Favorito"],
        id="favorite-button",
        color="primary",
        className="me-2",
        n_clicks=0,
        disabled=True,  # Inicialmente desabilitado
        title="Salvar localização atual na lista de favoritos (máx. 10)",
    )


def create_calc_eto_button():
    """
    Cria botão para calcular ETo na localização atual.
    Returns:
        dbc.Button: Botão Calcular ETo
    """
    return dbc.Button(
        [html.I(className="bi bi-calculator me-2"), "📊 Calcular ETo"],
        id="calc-eto-button",
        color="success",
        className="me-2",
        n_clicks=0,
        disabled=True,  # Inicialmente desabilitado
        title="Calcular Evapotranspiração para a localização selecionada",
    )


def create_clear_favorites_button():
    """
    Cria botão para limpar toda a lista de favoritos.
    Returns:
        dbc.Button: Botão Limpar Favoritos
    """
    return dbc.Button(
        [html.I(className="bi bi-trash me-2"), "🧹 Limpar Todos os Favoritos"],
        id="clear-favorites-button",
        color="danger",
        className="mt-2",
        n_clicks=0,
        size="sm",
        title="Remover todos os favoritos da lista",
    )


def create_favorite_item(favorite):
    """
    Cria um item individual da lista de favoritos.
    Args:
        favorite (dict): Dados do favorito
    Returns:
        html.Tr: Linha da tabela de favoritos
    """
    return html.Tr(
        [
            html.Td(
                [
                    html.Div(
                        favorite.get("lat_dms", "N/A"), className="fw-bold"
                    ),
                    html.Div(
                        favorite.get("lon_dms", "N/A"),
                        className="text-muted small",
                    ),
                    html.Div(
                        f"({favorite.get('lat', 0):.4f}, "
                        f"{favorite.get('lon', 0):.4f})",
                        className="text-muted small",
                    ),
                ]
            ),
            html.Td(
                [
                    html.Div(
                        favorite.get("timezone", "N/A"), className="fw-bold"
                    ),
                    html.Div(
                        favorite.get(
                            "location_info", "Local não identificado"
                        ),
                        className="text-muted small mt-1",
                    ),
                ]
            ),
            html.Td(
                [
                    dbc.Button(
                        "📊 Calcular ETo",
                        color="success",
                        size="sm",
                        className="me-1 mb-1",
                        id={"type": "calc-fav-eto", "index": favorite["id"]},
                    ),
                    dbc.Button(
                        "❌ Excluir",
                        color="danger",
                        size="sm",
                        className="mb-1",
                        id={
                            "type": "delete-favorite",
                            "index": favorite["id"],
                        },
                    ),
                ],
                style={"minWidth": "150px"},
            ),
        ]
    )


def create_favorites_table(favorites):
    """
    Cria a tabela completa de favoritos.
    Args:
        favorites (list): Lista de favoritos
    Returns:
        dbc.Table: Tabela de favoritos
    """
    if not favorites:
        return html.Div()
    table_header = [
        html.Thead(
            html.Tr(
                [
                    html.Th("Ponto", style={"width": "40%"}),
                    html.Th("Fuso Horário", style={"width": "30%"}),
                    html.Th("Ações Rápidas", style={"width": "30%"}),
                ]
            )
        )
    ]
    table_rows = [create_favorite_item(fav) for fav in favorites]
    table_body = [html.Tbody(table_rows)]
    return dbc.Table(
        table_header + table_body,
        bordered=True,
        striped=True,
        hover=True,
        responsive=True,
        className="mt-3",
    )


def create_empty_favorites_alert():
    """
    Cria alerta para quando a lista de favoritos está vazia.
    Returns:
        dbc.Alert: Alerta de lista vazia
    """
    return dbc.Alert(
        [
            html.I(className="bi bi-info-circle me-2"),
            "Lista de favoritos vazia. ",
            html.Strong("Adicione pontos clicando no mapa"),
            " e depois em 'Salvar Favorito'.",
        ],
        color="info",
        id="empty-favorites-alert",
        className="mt-3",
    )


logger.info("✅ Componentes de favoritos carregados com sucesso")
