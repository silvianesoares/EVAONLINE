"""
Script de teste para executar apenas o frontend Dash.
Útil para testar componentes visuais sem depender do backend.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set standalone mode
import os

os.environ["EVA_FRONTEND_STANDALONE"] = "1"

# Import and run
from frontend.app import app

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 INICIANDO FRONTEND DASH (MODO STANDALONE)")
    print("=" * 60)
    print("📌 URL: http://localhost:8050")
    print("⚠️  Backend não está integrado neste modo")
    print("=" * 60)

    # Run standalone (Dash 3.x usa app.run ao invés de app.run_server)
    app.run(
        host="0.0.0.0",
        port=8050,
        debug=True,
    )
