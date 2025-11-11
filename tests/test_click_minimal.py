"""
Teste MINIMALISTA para descobrir formato exato do clickData
"""

import dash
import dash_leaflet as dl
from dash import html, Output, Input

app = dash.Dash(__name__)

app.layout = html.Div(
    [
        html.H1("Teste Minimal de Cliques"),
        html.Pre(
            id="output", style={"background": "#f0f0f0", "padding": "20px"}
        ),
        dl.MapContainer(
            id="map",
            center=[0, 0],
            zoom=2,
            children=[dl.TileLayer()],
            style={"height": "500px", "width": "100%"},
        ),
    ]
)


@app.callback(
    Output("output", "children"),
    Input("map", "clickData"),
)
def show_click(click_data):
    """Mostrar EXATAMENTE o que vem no clickData."""
    if not click_data:
        return "Nenhum clique ainda. Clique no mapa!"

    import json

    return f"clickData recebido:\n\n{json.dumps(click_data, indent=2)}"


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🔬 TESTE MINIMAL - Descobrir formato do clickData")
    print("=" * 60)
    print("📌 URL: http://localhost:8055")
    print("🎯 Clique no mapa e veja o formato EXATO dos dados")
    print("=" * 60 + "\n")

    app.run(host="0.0.0.0", port=8055, debug=True)
