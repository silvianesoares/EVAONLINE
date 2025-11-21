"""
Script para regenerar apenas os gráficos consolidados
sem reprocessar toda a validação.
"""

import pandas as pd
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from validation.batch_5cities_fusion import create_consolidated_plots

# Carregar CSV existente
csv_path = (
    Path(__file__).parent
    / "results/brasil/batch_validation/VALIDACAO_FINAL_20251120_1809.csv"
)
output_dir = csv_path.parent

df = pd.read_csv(csv_path)

# Remover duplicatas (se houver)
df = df.drop_duplicates(subset=["city"], keep="first")

print(f"📊 Gerando gráficos consolidados para {len(df)} cidades...")
create_consolidated_plots(df, output_dir)
print("✅ Gráficos consolidados gerados com sucesso!")
