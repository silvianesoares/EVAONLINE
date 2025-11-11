"""
Script de DIAGNÓSTICO para testar eventos do Dash Leaflet.
Versão minimalista com máximo de debug.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import dash
import dash_bootstrap_components as dbc
import dash_leaflet as dl
from dash import html, dcc, Input, Output, State

print("=" * 70)
print("🔍 DIAGNÓSTICO DO DASH LEAFLET")
print("=" * 70)
print(f"📦 Dash version: {dash.__version__}")
print(f"📦 Dash Leaflet version: {dl.__version__}")
print("=" * 70)

# Criar app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Criar mapa MINIMALISTA
mapa = dl.Map(
    id="test-map",
    center=[0, 0],
    zoom=2,
    children=[
        dl.TileLayer(url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png")
    ],
    style={"width": "100%", "height": "600px"},
)

# Layout simples
app.layout = dbc.Container(
    [
        html.H1("🔍 Diagnóstico de Cliques no Mapa", className="my-4"),
        html.Div(
            [
                html.H5("Status:", className="d-inline me-2"),
                html.Span(
                    "Aguardando clique...",
                    id="status",
                    className="badge bg-secondary",
                ),
            ],
            className="mb-3",
        ),
        html.Div(id="output", className="alert alert-info mb-3"),
        dbc.Card(
            [
                dbc.CardHeader(html.H5("Mapa de Teste")),
                dbc.CardBody(mapa),
            ]
        ),
        dcc.Store(id="click-store"),
    ],
    fluid=True,
    className="py-4",
)


# Callback MINIMALISTA
@app.callback(
    [
        Output("output", "children"),
        Output("status", "children"),
        Output("status", "className"),
        Output("click-store", "data"),
    ],
    Input("test-map", "click_lat_lng"),
    State("click-store", "data"),
)
def handle_click(click_lat_lng, previous_data):
    """Captura QUALQUER clique no mapa."""

    print("\n" + "=" * 70)
    print("🎯 CALLBACK EXECUTADO!")
    print("=" * 70)
    print(f"📍 click_lat_lng recebido: {click_lat_lng}")
    print(f"📍 Tipo: {type(click_lat_lng)}")
    print(f"📍 Dados anteriores: {previous_data}")
    print("=" * 70)

    if not click_lat_lng:
        print("⚠️  click_lat_lng está vazio/None")
        return (
            "Nenhum clique detectado ainda. Clique no mapa!",
            "Aguardando...",
            "badge bg-secondary",
            None,
        )

    try:
        lat, lon = click_lat_lng
        print(f"✅ Coordenadas extraídas: LAT={lat:.6f}, LON={lon:.6f}")

        output_message = html.Div(
            [
                html.H5(
                    "✅ CLIQUE DETECTADO COM SUCESSO!",
                    className="text-success",
                ),
                html.Hr(),
                html.P([html.Strong("Latitude: "), f"{lat:.6f}°"]),
                html.P([html.Strong("Longitude: "), f"{lon:.6f}°"]),
                html.P([html.Strong("Formato bruto: "), str(click_lat_lng)]),
                html.Hr(),
                html.Small(
                    f"Cliques anteriores: {previous_data if previous_data else 'Nenhum'}"
                ),
            ]
        )

        return (
            output_message,
            f"✅ {lat:.4f}, {lon:.4f}",
            "badge bg-success",
            {
                "lat": lat,
                "lon": lon,
                "count": (previous_data or {}).get("count", 0) + 1,
            },
        )

    except Exception as e:
        print(f"❌ ERRO ao processar: {e}")
        import traceback

        traceback.print_exc()

        return (
            html.Div(
                [
                    html.H5("❌ ERRO", className="text-danger"),
                    html.P(f"Erro: {str(e)}"),
                    html.P(f"Dados recebidos: {click_lat_lng}"),
                ]
            ),
            "❌ Erro",
            "badge bg-danger",
            None,
        )


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🚀 INICIANDO SERVIDOR DE DIAGNÓSTICO")
    print("=" * 70)
    print("📌 URL: http://localhost:8052")
    print("🎯 Clique ANYWHERE no mapa para testar!")
    print("💡 Veja os prints no terminal quando clicar")
    print("=" * 70 + "\n")

    app.run(
        host="0.0.0.0",
        port=8052,  # Porta diferente para não conflitar
        debug=True,
    )
