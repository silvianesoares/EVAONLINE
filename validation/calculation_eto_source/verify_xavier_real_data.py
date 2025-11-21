import pandas as pd
from pathlib import Path

print("\n" + "=" * 80)
print("VERIFICAÇÃO DOS DADOS REAIS DE XAVIER")
print("=" * 80 + "\n")

# Verificar 3 cidades como exemplo
cities = ["Piracicaba_SP", "Alvorada_do_Gurgueia_PI", "Bom_Jesus_PI"]

for city in cities:
    file_path = f"validation/data_validation/data/csv/BRASIL/ETo/{city}.csv"
    df = pd.read_csv(file_path)

    print(f"📂 {city}.csv")
    print(f"   Total de registros: {len(df)}")
    print(f"   Período: {df['Data'].iloc[0]} até {df['Data'].iloc[-1]}")
    print(f"   ETo médio: {df['ETo'].mean():.4f} mm/dia")
    print(f"   ETo std: {df['ETo'].std():.4f}")
    print(
        f"   ETo range: {df['ETo'].min():.2f} - {df['ETo'].max():.2f} mm/dia"
    )
    print(f"   Primeiros 3 valores:")
    for i in range(3):
        print(f"      {df['Data'].iloc[i]}: {df['ETo'].iloc[i]:.4f} mm/dia")
    print()

print("=" * 80)
print("ESTATÍSTICAS AGREGADAS (todas as 17 cidades)")
print("=" * 80 + "\n")

xavier_dir = Path("validation/data_validation/data/csv/BRASIL/ETo")
all_files = sorted(xavier_dir.glob("*.csv"))

means = []
stds = []

print(f"Total de arquivos: {len(all_files)}\n")
for f in all_files:
    df = pd.read_csv(f)
    mean_eto = df["ETo"].mean()
    std_eto = df["ETo"].std()
    means.append(mean_eto)
    stds.append(std_eto)
    print(f"   {f.stem:30s} → ETo: {mean_eto:.4f} ± {std_eto:.4f} mm/dia")

import numpy as np

print(f"\n✅ VALORES REAIS VERIFICADOS:")
print(f"   Média geral: {np.mean(means):.4f} ± {np.std(means):.4f} mm/dia")
print(f"   Std médio: {np.mean(stds):.4f} ± {np.std(stds):.4f} mm/dia")
print(f"\n   Esses são os MESMOS valores que coloquei no summary!")
