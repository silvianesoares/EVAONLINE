import pandas as pd
import numpy as np
from pathlib import Path

# Calcular estatísticas do Xavier para adicionar ao summary
xavier_dir = Path("validation/data_validation/data/csv/BRASIL/ETo")
files = sorted(xavier_dir.glob("*.csv"))

print(f"\n📊 Calculando estatísticas de Xavier (referência)...")
print(f"   Encontrados: {len(files)} arquivos\n")

means = []
stds = []

for f in files:
    df = pd.read_csv(f)
    means.append(df["ETo"].mean())
    stds.append(df["ETo"].std())
    print(
        f"   {f.stem}: ETo médio = {df['ETo'].mean():.4f} mm/dia, std = {df['ETo'].std():.4f}"
    )

print(f"\n📈 ESTATÍSTICAS AGREGADAS (Xavier et al.):")
print(
    f"   Média entre cidades: {np.mean(means):.4f} ± {np.std(means):.4f} mm/dia"
)
print(f"   Std médio: {np.mean(stds):.4f} ± {np.std(stds):.4f} mm/dia")

# Adicionar ao arquivo summary
summary_file = Path(
    "validation/results/brasil/comparison_4sources_original_openmeteo/comparison_summary_original_openmeteo.csv"
)
df_summary = pd.read_csv(summary_file)

# Criar linha Xavier (R²=1.0 pois é a referência, MAE=0, RMSE=0, PBIAS=0)
xavier_row = pd.DataFrame(
    {
        "source": ["Xavier (referência)"],
        "n_cities": [len(files)],
        "r2_mean": [1.0],
        "r2_std": [0.0],
        "mae_mean": [0.0],
        "mae_std": [0.0],
        "rmse_mean": [0.0],
        "rmse_std": [0.0],
        "pbias_mean": [0.0],
        "pbias_std": [0.0],
    }
)

# Adicionar Xavier no início
df_final = pd.concat([xavier_row, df_summary], ignore_index=True)

# Salvar
df_final.to_csv(summary_file, index=False)

print(f"\n✅ Arquivo atualizado: {summary_file}")
print(f"\n📋 SUMMARY COMPLETO:")
print(df_final.to_string(index=False))
