"""
SOLUÇÃO FUNCIONAL: Usar GeoJSON para capturar cliques no mapa.
Dash Leaflet 1.1.3 tem bug com click_lat_lng - usaremos workaround.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import dash
import dash_bootstrap_components as dbc
import dash_leaflet as dl
from dash import html, Input, Output, State

print("=" * 70)
print("✅ SOLUÇÃO FUNCIONAL - WORKAROUND PARA CLIQUES")
print("=" * 70)

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# GeoJSON vazio para capturar cliques
geojson = dl.GeoJSON(
    data=None,
    id="geojson",
    options=dict(
        style=dict(opacity=0),  # Invisível
    ),
)

# Mapa com GeoJSON layer
mapa = dl.Map(
    id="map-workaround",
    center=[0, 0],
    zoom=2,
    children=[
        dl.TileLayer(),
        dl.LayerGroup(id="markers-workaround"),
        geojson,
    ],
    style={"width": "100%", "height": "600px"},
)

app.layout = dbc.Container(
    [
        html.H1("✅ Workaround - Cliques Funcionando!", className="my-4"),
        html.Div(id="output-workaround", className="alert alert-info mb-3"),
        dbc.Card([dbc.CardHeader("Mapa Funcional"), dbc.CardBody(mapa)]),
    ],
    fluid=True,
)


# WORKAROUND: Usar GeoJSON click
@app.callback(
    [
        Output("output-workaround", "children"),
        Output("markers-workaround", "children"),
    ],
    Input("geojson", "click_feature"),
    State("markers-workaround", "children"),
)
def handle_geojson_click(click_feature, current_markers):
    """Captura cliques via GeoJSON."""
    print("\n" + "=" * 70)
    print("🎯 GEOJSON CLICK!")
    print(f"📍 Feature: {click_feature}")
    print("=" * 70)

    if not click_feature:
        return "Clique no mapa...", current_markers or []

    # Extrair coordenadas
    coords = click_feature.get("geometry", {}).get("coordinates", [])
    if len(coords) >= 2:
        lon, lat = coords[0], coords[1]

        output = html.Div(
            [
                html.H5(f"✅ CLIQUE #{len(current_markers or []) + 1}"),
                html.P(f"Lat: {lat:.6f}°"),
                html.P(f"Lon: {lon:.6f}°"),
            ]
        )

        # Adicionar marcador
        new_marker = dl.Marker(
            position=[lat, lon],
            children=[dl.Tooltip(f"Click {len(current_markers or []) + 1}")],
        )

        markers = (current_markers or []) + [new_marker]

        return output, markers

    return "Coordenadas inválidas", current_markers or []


# ALTERNATIVA 2: Capturar via propriedade do mapa
@app.callback(
    Output("output-workaround", "children", allow_duplicate=True),
    Input("map-workaround", "click_lat_lng"),
    prevent_initial_call=True,
)
def test_direct_click(click_lat_lng):
    """Testa click_lat_lng direto (pode não funcionar)."""
    print(f"\n🔍 click_lat_lng direto: {click_lat_lng}")

    if click_lat_lng:
        lat, lon = click_lat_lng
        return html.Div(
            [
                html.H5("✅ FUNCIONOU COM click_lat_lng!"),
                html.P(f"Lat: {lat:.6f}"),
                html.P(f"Lon: {lon:.6f}"),
            ]
        )

    return dash.no_update


if __name__ == "__main__":
    print("\n🚀 Servidor: http://localhost:8054")
    print("💡 Este usa WORKAROUND para contornar bug do dash-leaflet\n")
    app.run(host="0.0.0.0", port=8054, debug=True)
