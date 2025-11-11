"""
Script de teste SIMPLES para o mapa Leaflet.
Sem dependência do backend.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, ALL
from frontend.components.world_map_leaflet import create_world_map
from frontend.callbacks.home_callbacks import (
    create_selection_info_card,
)
from frontend.components.world_map_leaflet import create_map_marker

# Criar app Dash
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css",
    ],
    suppress_callback_exceptions=True,
)

# Layout completo com favoritos
app.layout = html.Div(
    [
        dbc.Container(
            [
                # Título
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.H1(
                                    "🗺️ Teste do Mapa Mundial - EVAonline",
                                    className="text-center my-4",
                                ),
                                html.P(
                                    "Clique no mapa para selecionar e adicionar favoritos",
                                    className="text-center text-muted mb-4",
                                ),
                            ],
                            width=12,
                        )
                    ]
                ),
                # Lista de Favoritos
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Card(
                                    [
                                        dbc.CardHeader(
                                            [
                                                html.Div(
                                                    [
                                                        html.H5(
                                                            "⭐ Lista de Favoritos",
                                                            className="mb-0 d-inline",
                                                        ),
                                                        dbc.Badge(
                                                            "0/5",
                                                            color="info",
                                                            className="ms-2",
                                                            id="favorites-count-badge",
                                                        ),
                                                    ],
                                                    className="d-flex align-items-center",
                                                )
                                            ]
                                        ),
                                        dbc.CardBody(
                                            [
                                                html.Div(
                                                    id="favorites-list-container",
                                                    className="mb-3",
                                                ),
                                                html.Div(
                                                    [
                                                        dbc.Button(
                                                            [
                                                                html.I(
                                                                    className="bi bi-trash me-2"
                                                                ),
                                                                "Limpar Todos",
                                                            ],
                                                            id="clear-favorites-button",
                                                            color="warning",
                                                            size="sm",
                                                            className="mt-2",
                                                        ),
                                                        dbc.Alert(
                                                            "Lista vazia. Clique no mapa e depois em 'Adicionar Favorito'.",
                                                            color="info",
                                                            id="empty-favorites-alert",
                                                            className="mt-3",
                                                        ),
                                                    ]
                                                ),
                                            ]
                                        ),
                                    ],
                                    className="shadow-sm",
                                )
                            ],
                            width=12,
                        )
                    ],
                    className="mb-4",
                ),
                # Mapa
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Card(
                                    [
                                        dbc.CardHeader(
                                            html.H5(
                                                "🗺️ Mapa Mundial Interativo"
                                            )
                                        ),
                                        dbc.CardBody(
                                            [
                                                create_world_map(),
                                                html.Div(
                                                    id="current-selection-info",
                                                    className="mt-3",
                                                ),
                                            ]
                                        ),
                                    ],
                                    className="shadow-sm",
                                )
                            ],
                            width=12,
                        )
                    ],
                    className="mb-5",
                ),
                # Stores
                dcc.Store(id="favorites-store", storage_type="local", data=[]),
                dcc.Store(id="map-click-data", data=None),
                dcc.Store(id="selected-location-data", data=None),
            ],
            fluid=True,
            className="pb-5",
            style={"minHeight": "100vh"},  # Garante altura mínima
        )
    ],
    style={
        "minHeight": "100vh",
        "paddingBottom": "200px",  # Espaço extra no final
        "overflowY": "auto",  # Permite scroll
    },
)


# Callback para capturar cliques no mapa
@app.callback(
    [
        Output("map-click-data", "data"),
        Output("selected-location-data", "data"),
        Output("marker-layer", "children"),
        Output("current-selection-info", "children"),
    ],
    Input("world-map", "clickData"),
    prevent_initial_call=True,
)
def handle_map_click(click_data):
    """Captura clique no mapa e atualiza informações."""
    if not click_data:
        return None, None, [], None

    try:
        latlng = click_data.get("latlng")
        if not latlng:
            print("⚠️ latlng não encontrado")
            return None, None, [], None

        lat = latlng["lat"]
        lon = latlng["lng"]

        print(f"✅ Clique: LAT={lat:.6f}, LON={lon:.6f}")

        location_data = {"lat": lat, "lon": lon}
        marker = create_map_marker(
            lat, lon, label=f"Lat: {lat:.4f}°, Lon: {lon:.4f}°"
        )
        info_card = create_selection_info_card(location_data)

        return (
            {"lat": lat, "lon": lon},
            location_data,
            [marker],
            info_card,
        )

    except Exception as e:
        print(f"❌ Erro: {e}")
        error_alert = dbc.Alert(
            [
                html.I(className="bi bi-exclamation-triangle me-2"),
                f"Erro ao obter informações: {str(e)}",
            ],
            color="warning",
        )
        return None, None, [], error_alert


# Callbacks de Favoritos
@app.callback(
    [
        Output("favorites-store", "data"),
        Output("favorites-count-badge", "children"),
        Output("add-favorite-btn", "disabled"),
    ],
    Input("add-favorite-btn", "n_clicks"),
    [
        State("selected-location-data", "data"),
        State("favorites-store", "data"),
    ],
    prevent_initial_call=True,
)
def add_to_favorites(n_clicks, location_data, current_favorites):
    """Adiciona localização aos favoritos."""
    if not location_data or not n_clicks:
        favorites_count = len(current_favorites) if current_favorites else 0
        is_disabled = favorites_count >= 5
        return current_favorites, f"{favorites_count}/5", is_disabled

    if current_favorites is None:
        current_favorites = []

    if len(current_favorites) >= 5:
        print("⚠️ Limite de 5 favoritos atingido")
        return current_favorites, "5/5", True

    lat = location_data.get("lat")
    lon = location_data.get("lon")

    # Verificar duplicatas
    for fav in current_favorites:
        if abs(fav["lat"] - lat) < 0.0001 and abs(fav["lon"] - lon) < 0.0001:
            print(f"📍 Localização já existe: {lat}, {lon}")
            favorites_count = len(current_favorites)
            is_disabled = favorites_count >= 5
            return current_favorites, f"{favorites_count}/5", is_disabled

    # Adicionar novo favorito
    new_favorite = {
        "lat": lat,
        "lon": lon,
        "label": f"Lat: {lat:.4f}°, Lon: {lon:.4f}°",
    }
    current_favorites.append(new_favorite)
    print(f"⭐ Favorito adicionado: {new_favorite['label']}")

    favorites_count = len(current_favorites)
    is_disabled = favorites_count >= 5

    return current_favorites, f"{favorites_count}/5", is_disabled


@app.callback(
    [
        Output("favorites-list-container", "children"),
        Output("empty-favorites-alert", "style"),
        Output("clear-favorites-button", "disabled"),
    ],
    Input("favorites-store", "data"),
)
def update_favorites_display(favorites):
    """Atualiza lista de favoritos."""
    if not favorites or len(favorites) == 0:
        return [], {"display": "block"}, True

    favorites_items = []
    for idx, fav in enumerate(favorites):
        item = dbc.ListGroupItem(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.I(
                                    className="bi bi-geo-alt-fill me-2 text-primary"
                                ),
                                html.Strong(fav["label"]),
                            ],
                            className="flex-grow-1",
                        ),
                        html.Div(
                            [
                                dbc.Button(
                                    [html.I(className="bi bi-calculator")],
                                    id={
                                        "type": "calc-eto-favorite",
                                        "index": idx,
                                    },
                                    color="success",
                                    size="sm",
                                    className="me-2",
                                    title="Calcular ETo",
                                ),
                                dbc.Button(
                                    [html.I(className="bi bi-trash")],
                                    id={
                                        "type": "remove-favorite",
                                        "index": idx,
                                    },
                                    color="danger",
                                    size="sm",
                                    title="Remover",
                                ),
                            ],
                            className="d-flex gap-1",
                        ),
                    ],
                    className="d-flex align-items-center justify-content-between",
                )
            ],
            className="mb-2",
        )
        favorites_items.append(item)

    return (
        dbc.ListGroup(favorites_items, flush=True),
        {"display": "none"},
        False,
    )


@app.callback(
    Output("favorites-store", "data", allow_duplicate=True),
    Input("clear-favorites-button", "n_clicks"),
    prevent_initial_call=True,
)
def clear_all_favorites(n_clicks):
    """Limpa todos os favoritos."""
    if n_clicks:
        print("🗑️ Todos os favoritos foram removidos")
        return []
    return []


@app.callback(
    Output("favorites-store", "data", allow_duplicate=True),
    Input({"type": "remove-favorite", "index": ALL}, "n_clicks"),
    State("favorites-store", "data"),
    prevent_initial_call=True,
)
def remove_favorite(n_clicks_list, current_favorites):
    """Remove um favorito específico."""
    if not current_favorites or not any(n_clicks_list):
        return current_favorites

    for idx, n_clicks in enumerate(n_clicks_list):
        if n_clicks:
            removed = current_favorites.pop(idx)
            print(f"🗑️ Favorito removido: {removed['label']}")
            break

    return current_favorites


if __name__ == "__main__":
    print("=" * 60)
    print("🗺️  TESTE DO MAPA LEAFLET")
    print("=" * 60)
    print("📌 URL: http://localhost:8051")
    print("🎯 Clique no mapa para testar!")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=8051,
        debug=True,
    )
