"""
Teste ALTERNATIVO usando clickData ao invés de click_lat_lng
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import dash
import dash_bootstrap_components as dbc
import dash_leaflet as dl
from dash import html, Input, Output

print("=" * 70)
print("🔧 TESTE COM CLICKDATA (ALTERNATIVO)")
print("=" * 70)
print(f"📦 Dash Leaflet version: {dl.__version__}")
print("=" * 70)

# Criar app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Criar mapa com configuração EXPLÍCITA de eventos
mapa = dl.Map(
    id="test-map-alt",
    center=[0, 0],
    zoom=2,
    children=[
        dl.TileLayer(),
        dl.LayerGroup(id="markers"),
    ],
    style={"width": "100%", "height": "600px"},
    # Tentar ambas as propriedades
)

# Layout
app.layout = dbc.Container(
    [
        html.H1("🔧 Teste ALTERNATIVO - clickData", className="my-4"),
        html.Div(id="output-alt", className="alert alert-info mb-3"),
        dbc.Card([dbc.CardHeader("Mapa"), dbc.CardBody(mapa)]),
    ],
    fluid=True,
)


# Testar com clickData
@app.callback(
    Output("output-alt", "children"),
    Input("test-map-alt", "clickData"),
)
def test_clickdata(click_data):
    """Testa usando clickData ao invés de click_lat_lng."""
    print("\n" + "=" * 70)
    print("🎯 CALLBACK CLICKDATA EXECUTADO!")
    print(f"📍 clickData: {click_data}")
    print(f"📍 Tipo: {type(click_data)}")
    print("=" * 70)

    if not click_data:
        return "Aguardando clique com clickData..."

    return html.Div(
        [
            html.H5("✅ clickData recebido!"),
            html.Pre(str(click_data)),
        ]
    )


# Testar com click_lat_lng SEM prevent_initial_call
@app.callback(
    Output("markers", "children"),
    Input("test-map-alt", "click_lat_lng"),
    prevent_initial_call=False,  # Explicitamente False
)
def test_click_lat_lng(click_lat_lng):
    """Testa click_lat_lng sem prevent_initial_call."""
    print("\n" + "=" * 70)
    print("🎯 CALLBACK CLICK_LAT_LNG EXECUTADO!")
    print(f"📍 click_lat_lng: {click_lat_lng}")
    print("=" * 70)

    if not click_lat_lng:
        return []

    lat, lon = click_lat_lng
    print(f"✅ Marcador em: {lat}, {lon}")

    return [dl.Marker(position=[lat, lon])]


if __name__ == "__main__":
    print("\n🚀 Servidor na porta 8053")
    print("📌 http://localhost:8053\n")
    app.run(host="0.0.0.0", port=8053, debug=True)
