"""
Compara ETo calculado pelo Open-Meteo (et0_fao_evapotranspiration)
com ETo calculado pelo nosso algoritmo EVAOnline
"""

import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Paths
OPENMETEO_RAW_DIR = Path("validation/results/brasil/raw_data/open_meteo")
OPENMETEO_ETO_DIR = OPENMETEO_RAW_DIR / "eto_open_meteo"
OUTPUT_DIR = Path("validation/calculation_eto_source/comparison_openmeteo")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Buscar todas as cidades que têm ETo calculado
our_eto_files = list(OPENMETEO_ETO_DIR.glob("*_ETo_OpenMeteo.csv"))
cities_with_eto = [f.stem.replace("_ETo_OpenMeteo", "") for f in our_eto_files]
cities_with_eto = sorted(cities_with_eto)

results = []

print("=" * 80)
print("COMPARAÇÃO: ETo Open-Meteo vs ETo EVAOnline (nosso cálculo)")
print("=" * 80)

for city in cities_with_eto:
    print(f"\n📊 {city}")

    # Carregar ETo do Open-Meteo (coluna et0_fao_evapotranspiration)
    raw_files = list(OPENMETEO_RAW_DIR.glob(f"{city}_*_OpenMeteo_RAW.csv"))
    if not raw_files:
        print(f"  ❌ Arquivo RAW não encontrado")
        continue

    df_raw = pd.read_csv(raw_files[0])

    if "et0_fao_evapotranspiration" not in df_raw.columns:
        print(f"  ⚠️  Coluna et0_fao não encontrada")
        continue

    df_openmeteo = df_raw[["date", "et0_fao_evapotranspiration"]].copy()
    df_openmeteo.columns = ["date", "eto_openmeteo_original"]

    # Carregar nosso cálculo
    our_files = list(OPENMETEO_ETO_DIR.glob(f"{city}_ETo_OpenMeteo.csv"))
    if not our_files:
        print(f"  ❌ Nosso cálculo não encontrado")
        continue

    df_our = pd.read_csv(our_files[0])

    # Merge
    df_merge = pd.merge(df_openmeteo, df_our, on="date", how="inner")
    df_merge = df_merge.dropna()

    if len(df_merge) < 100:
        print(f"  ⚠️  Poucos dados: {len(df_merge)}")
        continue

    # Calcular métricas
    y_true = df_merge["eto_openmeteo_original"].values
    y_pred = df_merge["eto_openmeteo"].values

    # R²
    r2 = r2_score(y_true, y_pred)

    # NSE (Nash-Sutcliffe)
    nse = 1 - (
        np.sum((y_true - y_pred) ** 2)
        / np.sum((y_true - np.mean(y_true)) ** 2)
    )

    # MAE
    mae = mean_absolute_error(y_true, y_pred)

    # RMSE
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))

    # PBIAS
    pbias = 100 * np.sum(y_pred - y_true) / np.sum(y_true)

    # Regressão linear
    lr = stats.linregress(y_true, y_pred)
    slope = lr.slope
    intercept = lr.intercept
    p_value = lr.pvalue

    # Médias
    mean_openmeteo = np.mean(y_true)
    mean_our = np.mean(y_pred)
    diff_percent = 100 * (mean_our - mean_openmeteo) / mean_openmeteo

    print(f"  📈 Dados: {len(df_merge)} dias")
    print(f"  📊 ETo Open-Meteo: {mean_openmeteo:.2f} mm/dia")
    print(f"  📊 ETo EVAOnline:  {mean_our:.2f} mm/dia ({diff_percent:+.1f}%)")
    print(f"  📊 R² = {r2:.4f}, NSE = {nse:.4f}")
    print(f"  📊 MAE = {mae:.2f} mm/dia, RMSE = {rmse:.2f} mm/dia")
    print(f"  📊 PBIAS = {pbias:.2f}%")
    print(f"  📊 Slope = {slope:.3f}, Intercept = {intercept:.3f}")

    results.append(
        {
            "city": city,
            "n_days": len(df_merge),
            "eto_openmeteo_mean": mean_openmeteo,
            "eto_evaonline_mean": mean_our,
            "diff_percent": diff_percent,
            "r2": r2,
            "nse": nse,
            "mae": mae,
            "rmse": rmse,
            "pbias": pbias,
            "slope": slope,
            "intercept": intercept,
            "p_value": p_value,
        }
    )

# Salvar resultados
df_results = pd.DataFrame(results)
output_file = OUTPUT_DIR / "comparison_openmeteo_vs_evaonline.csv"
df_results.to_csv(output_file, index=False)

# Estatísticas gerais
print("\n" + "=" * 80)
print("ESTATÍSTICAS GERAIS")
print("=" * 80)
print(f"\n📊 Cidades analisadas: {len(results)}")
print(
    f"📊 R² médio: {df_results['r2'].mean():.4f} (±{df_results['r2'].std():.4f})"
)
print(
    f"📊 NSE médio: {df_results['nse'].mean():.4f} (±{df_results['nse'].std():.4f})"
)
print(
    f"📊 MAE médio: {df_results['mae'].mean():.2f} mm/dia (±{df_results['mae'].std():.2f})"
)
print(
    f"📊 RMSE médio: {df_results['rmse'].mean():.2f} mm/dia (±{df_results['rmse'].std():.2f})"
)
print(
    f"📊 PBIAS médio: {df_results['pbias'].mean():.2f}% (±{df_results['pbias'].std():.2f})"
)
print(
    f"📊 Diferença média: {df_results['diff_percent'].mean():.1f}% (±{df_results['diff_percent'].std():.1f})"
)

print(f"\n✅ Resultados salvos em: {output_file}")
print("=" * 80)
