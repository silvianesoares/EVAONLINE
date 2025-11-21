"""
Comparação: Xavier x NASA POWER x Open-Meteo ORIGINAL x EVAOnline
Usa a ETo original do Open-Meteo (et0_fao_evapotranspiration) ao invés da calculada
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from loguru import logger
from scipy.stats import pearsonr, linregress
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from validation.config import VALIDATION_DIR, BRASIL_ETO_DIR

# Paths das 4 fontes
XAVIER_DIR = BRASIL_ETO_DIR  # validation/data_validation/data/csv/BRASIL/ETo
NASA_DIR = VALIDATION_DIR / "results/brasil/raw_data/nasa_power/eto_nasa_power"
OPENMETEO_RAW_DIR = (
    VALIDATION_DIR / "results/brasil/raw_data/open_meteo"
)  # Dados RAW com ETo original
EVAONLINE_DIR = VALIDATION_DIR / "results/brasil/raw_data/evaonline"

# Output
OUTPUT_DIR = (
    VALIDATION_DIR / "results/brasil/comparison_4sources_original_openmeteo"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def calculate_metrics(observed: np.ndarray, predicted: np.ndarray) -> dict:
    """Calcula todas as métricas estatísticas."""

    # R² e p-value
    r_val, p_value = pearsonr(predicted, observed)
    r2 = float(r_val**2)  # type: ignore

    # Regressão linear
    lr = linregress(observed, predicted)
    slope = float(lr.slope)  # type: ignore
    intercept = float(lr.intercept)  # type: ignore
    p_value_slope = float(lr.pvalue)  # type: ignore

    # Métricas de erro
    mae = float(mean_absolute_error(observed, predicted))
    rmse = float(np.sqrt(mean_squared_error(observed, predicted)))

    # NSE (Nash-Sutcliffe Efficiency)
    nse = float(
        1
        - (
            np.sum((observed - predicted) ** 2)
            / np.sum((observed - np.mean(observed)) ** 2)
        )
    )

    # PBIAS (Percent Bias)
    pbias = float(100 * np.sum(predicted - observed) / np.sum(observed))

    return {
        "r2": r2,
        "nse": nse,
        "mae": mae,
        "rmse": rmse,
        "pbias": pbias,
        "slope": slope,
        "intercept": intercept,
        "p_value": p_value_slope,
    }


def compare_city(city_name: str) -> dict:
    """Compara as 4 fontes para uma cidade."""

    logger.info(f"🔍 Comparando {city_name}...")

    # 1. Xavier (referência)
    xavier_file = XAVIER_DIR / f"{city_name}.csv"
    if not xavier_file.exists():
        logger.warning(f"❌ Xavier não encontrado: {city_name}")
        return {}

    df_xavier = pd.read_csv(xavier_file)
    df_xavier["Data"] = pd.to_datetime(df_xavier["Data"])

    # Filtrar 1991-2020
    df_xavier = df_xavier[
        (df_xavier["Data"] >= "1991-01-01")
        & (df_xavier["Data"] <= "2020-12-31")
    ]

    # 2. NASA POWER
    nasa_file = NASA_DIR / f"{city_name}_ETo_NASA.csv"
    if not nasa_file.exists():
        logger.warning(f"⚠️  NASA não encontrado: {city_name}")
        nasa_metrics = {}
    else:
        df_nasa = pd.read_csv(nasa_file)
        df_nasa["date"] = pd.to_datetime(df_nasa["date"])

        # Merge com Xavier
        df_merged = df_xavier.merge(
            df_nasa, left_on="Data", right_on="date", how="inner"
        )

        if len(df_merged) > 0:
            nasa_metrics = calculate_metrics(
                df_merged["ETo"].values, df_merged["eto_nasa"].values
            )
            logger.info(
                f"  NASA: R²={nasa_metrics['r2']:.4f}, MAE={nasa_metrics['mae']:.4f}"
            )
        else:
            nasa_metrics = {}

    # 3. Open-Meteo ORIGINAL (et0_fao_evapotranspiration dos dados RAW)
    openmeteo_raw_file = list(
        OPENMETEO_RAW_DIR.glob(f"{city_name}_*_OpenMeteo_RAW.csv")
    )
    if not openmeteo_raw_file:
        logger.warning(f"⚠️  Open-Meteo RAW não encontrado: {city_name}")
        openmeteo_metrics = {}
    else:
        df_om = pd.read_csv(openmeteo_raw_file[0])
        df_om["date"] = pd.to_datetime(df_om["date"])

        # Verificar se tem coluna ETo original
        if "et0_fao_evapotranspiration" not in df_om.columns:
            logger.warning(f"⚠️  Open-Meteo sem ETo original: {city_name}")
            openmeteo_metrics = {}
        else:
            # Merge com Xavier
            df_merged = df_xavier.merge(
                df_om[["date", "et0_fao_evapotranspiration"]],
                left_on="Data",
                right_on="date",
                how="inner",
            )

            if len(df_merged) > 0:
                openmeteo_metrics = calculate_metrics(
                    df_merged["ETo"].values,
                    df_merged["et0_fao_evapotranspiration"].values,
                )
                logger.info(
                    f"  Open-Meteo Original: R²={openmeteo_metrics['r2']:.4f}, "
                    f"MAE={openmeteo_metrics['mae']:.4f}"
                )
            else:
                openmeteo_metrics = {}

    # 4. EVAOnline (Kalman)
    evaonline_file = EVAONLINE_DIR / f"{city_name}_ETo_EVAOnline.csv"
    if not evaonline_file.exists():
        logger.warning(f"⚠️  EVAOnline não encontrado: {city_name}")
        evaonline_metrics = {}
    else:
        df_eva = pd.read_csv(evaonline_file)
        df_eva["date"] = pd.to_datetime(df_eva["date"])

        # Merge com Xavier
        df_merged = df_xavier.merge(
            df_eva, left_on="Data", right_on="date", how="inner"
        )

        if len(df_merged) > 0:
            evaonline_metrics = calculate_metrics(
                df_merged["ETo"].values, df_merged["eto_evaonline"].values
            )
            logger.info(
                f"  EVAOnline: R²={evaonline_metrics['r2']:.4f}, "
                f"MAE={evaonline_metrics['mae']:.4f}"
            )
        else:
            evaonline_metrics = {}

    return {
        "city": city_name,
        "nasa": nasa_metrics,
        "openmeteo_original": openmeteo_metrics,
        "evaonline": evaonline_metrics,
    }


def process_all_cities():
    """Processa todas as cidades."""

    logger.info("=" * 80)
    logger.info(
        "🚀 COMPARAÇÃO: Xavier x NASA x Open-Meteo ORIGINAL x EVAOnline"
    )
    logger.info("=" * 80)

    # Listar cidades do Xavier
    xavier_files = sorted(XAVIER_DIR.glob("*.csv"))
    cities = [f.stem for f in xavier_files]

    logger.info(f"📊 {len(cities)} cidades encontradas no Xavier")

    results = []
    for i, city in enumerate(cities, 1):
        logger.info(f"\n[{i}/{len(cities)}] {city}")
        result = compare_city(city)
        if result:
            results.append(result)

    # Gerar tabelas
    generate_tables(results)

    logger.info("\n" + "=" * 80)
    logger.info(f"✅ Comparação concluída! Resultados em: {OUTPUT_DIR}")
    logger.info("=" * 80)


def generate_tables(results: list):
    """Gera tabelas de comparação."""

    logger.info("\n📊 Gerando tabelas...")

    # Tabela de métricas detalhadas
    rows = []
    for r in results:
        city = r["city"]

        # NASA
        if r["nasa"]:
            rows.append({"city": city, "source": "NASA POWER", **r["nasa"]})

        # Open-Meteo Original
        if r["openmeteo_original"]:
            rows.append(
                {
                    "city": city,
                    "source": "Open-Meteo Original",
                    **r["openmeteo_original"],
                }
            )

        # EVAOnline
        if r["evaonline"]:
            rows.append(
                {"city": city, "source": "EVAOnline", **r["evaonline"]}
            )

    df_metrics = pd.DataFrame(rows)
    metrics_file = OUTPUT_DIR / "comparison_metrics_original_openmeteo.csv"
    df_metrics.to_csv(metrics_file, index=False)
    logger.success(f"✅ Tabela de métricas: {metrics_file.name}")

    # Resumo estatístico por fonte
    summary_rows = []
    for source in ["NASA POWER", "Open-Meteo Original", "EVAOnline"]:
        df_source = df_metrics[df_metrics["source"] == source]

        if len(df_source) > 0:
            summary_rows.append(
                {
                    "source": source,
                    "n_cities": len(df_source),
                    "r2_mean": df_source["r2"].mean(),
                    "r2_std": df_source["r2"].std(),
                    "mae_mean": df_source["mae"].mean(),
                    "mae_std": df_source["mae"].std(),
                    "rmse_mean": df_source["rmse"].mean(),
                    "rmse_std": df_source["rmse"].std(),
                    "pbias_mean": df_source["pbias"].mean(),
                    "pbias_std": df_source["pbias"].std(),
                }
            )

    df_summary = pd.DataFrame(summary_rows)
    summary_file = OUTPUT_DIR / "comparison_summary_original_openmeteo.csv"
    df_summary.to_csv(summary_file, index=False)
    logger.success(f"✅ Resumo estatístico: {summary_file.name}")

    # Tabela LaTeX
    generate_latex_tables(df_metrics, df_summary)


def generate_latex_tables(df_metrics: pd.DataFrame, df_summary: pd.DataFrame):
    """Gera tabelas formatadas em LaTeX."""

    logger.info("📝 Gerando tabelas LaTeX...")

    latex_file = OUTPUT_DIR / "tables_latex_original_openmeteo.tex"

    with open(latex_file, "w", encoding="utf-8") as f:
        f.write("% Tabela 1: Resumo estatístico por fonte\n")
        f.write("\\begin{table}[ht]\n")
        f.write("\\centering\n")
        f.write(
            "\\caption{Comparação Xavier vs NASA vs Open-Meteo Original vs EVAOnline (1991-2020)}\n"
        )
        f.write("\\begin{tabular}{lcccc}\n")
        f.write("\\hline\n")
        f.write(
            "Fonte & R² & MAE (mm/dia) & RMSE (mm/dia) & PBIAS (\\%) \\\\\n"
        )
        f.write("\\hline\n")

        for _, row in df_summary.iterrows():
            f.write(
                f"{row['source']} & "
                f"{row['r2_mean']:.3f} $\\pm$ {row['r2_std']:.3f} & "
                f"{row['mae_mean']:.2f} $\\pm$ {row['mae_std']:.2f} & "
                f"{row['rmse_mean']:.2f} $\\pm$ {row['rmse_std']:.2f} & "
                f"{row['pbias_mean']:.1f} $\\pm$ {row['pbias_std']:.1f} \\\\\n"
            )

        f.write("\\hline\n")
        f.write("\\end{tabular}\n")
        f.write("\\end{table}\n\n")

    logger.success(f"✅ Tabelas LaTeX: {latex_file.name}")


if __name__ == "__main__":
    process_all_cities()
