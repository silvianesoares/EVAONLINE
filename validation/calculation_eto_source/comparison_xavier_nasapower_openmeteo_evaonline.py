"""
Comparação completa: Xavier x NASA POWER x Open-Meteo x EVAOnline
Gera tabelas e gráficos para publicação na SoftwareX
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from loguru import logger
from scipy.stats import pearsonr, linregress
from sklearn.metrics import mean_absolute_error, mean_squared_error
import matplotlib

matplotlib.use("Agg")

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from validation.config import VALIDATION_DIR, BRASIL_ETO_DIR

# Paths das 4 fontes
XAVIER_DIR = BRASIL_ETO_DIR  # validation/data_validation/data/csv/BRASIL/ETo
NASA_DIR = VALIDATION_DIR / "results/brasil/raw_data/nasa_power/eto_nasa_power"
OPENMETEO_DIR = (
    VALIDATION_DIR / "results/brasil/raw_data/open_meteo/eto_open_meteo"
)  # noqa: E501
EVAONLINE_DIR = VALIDATION_DIR / "results/brasil/raw_data/evaonline"

# Output
OUTPUT_DIR = VALIDATION_DIR / "results/brasil/comparison_4sources"
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
    bias = float(np.mean(predicted - observed))
    nse = float(
        1
        - (
            np.sum((observed - predicted) ** 2)
            / np.sum((observed - np.mean(observed)) ** 2)
        )
    )
    pbias = float(100 * np.sum(predicted - observed) / np.sum(observed))

    # Significância
    if p_value < 0.001:
        sig = "***"
    elif p_value < 0.01:
        sig = "**"
    elif p_value < 0.05:
        sig = "*"
    else:
        sig = "ns"

    return {
        "r2": r2,
        "p_value": f"{p_value:.2e}" if p_value >= 1e-300 else "< 1e-300",
        "p_value_slope": (
            f"{p_value_slope:.2e}" if p_value_slope >= 1e-300 else "< 1e-300"
        ),  # noqa: E501
        "significance": sig,
        "nse": nse,
        "mae": mae,
        "rmse": rmse,
        "bias": bias,
        "pbias": pbias,
        "slope": slope,
        "intercept": intercept,
        "n_days": len(observed),
        "mean_observed": float(np.mean(observed)),
        "mean_predicted": float(np.mean(predicted)),
    }


def compare_city(city_name: str) -> dict | None:
    """Compara as 4 fontes para uma cidade."""

    logger.info(f"🔍 Comparando {city_name}...")

    # Carregar Xavier (referência)
    xavier_file = XAVIER_DIR / f"{city_name}.csv"
    if not xavier_file.exists():
        logger.warning(f"❌ Xavier não encontrado: {city_name}")
        return None

    df_xavier = pd.read_csv(xavier_file)
    df_xavier.columns = df_xavier.columns.str.strip()
    df_xavier["Data"] = pd.to_datetime(df_xavier["Data"])
    df_xavier = df_xavier.rename(columns={"Data": "date", "ETo": "eto_xavier"})

    # Carregar NASA POWER
    nasa_file = NASA_DIR / f"{city_name}_ETo_NASA.csv"
    if not nasa_file.exists():
        logger.warning(f"⚠️  NASA não encontrado: {city_name}")
        df_nasa = None
    else:
        df_nasa = pd.read_csv(nasa_file, parse_dates=["date"])

    # Carregar Open-Meteo
    om_file = OPENMETEO_DIR / f"{city_name}_ETo_OpenMeteo.csv"
    if not om_file.exists():
        logger.warning(f"⚠️  Open-Meteo não encontrado: {city_name}")
        df_om = None
    else:
        df_om = pd.read_csv(om_file, parse_dates=["date"])

    # Carregar EVAOnline
    eva_file = EVAONLINE_DIR / f"{city_name}_ETo_EVAOnline.csv"
    if not eva_file.exists():
        logger.warning(f"⚠️  EVAOnline não encontrado: {city_name}")
        df_eva = None
    else:
        df_eva = pd.read_csv(eva_file, parse_dates=["date"])

    # Merge com Xavier
    results = {"city": city_name}

    if df_nasa is not None:
        df_merge = pd.merge(df_xavier, df_nasa, on="date", how="inner")
        if len(df_merge) > 0:
            metrics = calculate_metrics(
                np.array(df_merge["eto_xavier"].values, dtype=float),
                np.array(df_merge["eto_nasa"].values, dtype=float),
            )
            results["nasa"] = metrics
            logger.info(
                f"  NASA: R²={metrics['r2']:.4f}, " f"MAE={metrics['mae']:.4f}"
            )

    if df_om is not None:
        df_merge = pd.merge(df_xavier, df_om, on="date", how="inner")
        if len(df_merge) > 0:
            metrics = calculate_metrics(
                np.array(df_merge["eto_xavier"].values, dtype=float),
                np.array(df_merge["eto_openmeteo"].values, dtype=float),
            )
            results["openmeteo"] = metrics
            logger.info(
                f"  Open-Meteo: R²={metrics['r2']:.4f}, "
                f"MAE={metrics['mae']:.4f}"
            )

    if df_eva is not None:
        df_merge = pd.merge(df_xavier, df_eva, on="date", how="inner")
        if len(df_merge) > 0:
            metrics = calculate_metrics(
                np.array(df_merge["eto_xavier"].values, dtype=float),
                np.array(df_merge["eto_evaonline"].values, dtype=float),
            )
            results["evaonline"] = metrics
            logger.info(
                f"  EVAOnline: R²={metrics['r2']:.4f}, "
                f"MAE={metrics['mae']:.4f}"
            )

    return results


def process_all_cities():
    """Processa todas as cidades e gera relatórios."""

    logger.info("=" * 80)
    logger.info("🚀 COMPARAÇÃO: Xavier x NASA x Open-Meteo x EVAOnline")
    logger.info("=" * 80)

    # Listar cidades com Xavier
    xavier_files = list(XAVIER_DIR.glob("*.csv"))
    cities = [f.stem for f in xavier_files]
    cities = sorted(cities)

    logger.info(f"📊 {len(cities)} cidades encontradas no Xavier")

    all_results = []
    for idx, city in enumerate(cities, 1):
        logger.info(f"\n[{idx}/{len(cities)}] {city}")
        result = compare_city(city)
        if result:
            all_results.append(result)

    # Gerar tabelas
    generate_tables(all_results)

    logger.info("\n" + "=" * 80)
    logger.success(f"✅ Comparação concluída! Resultados em: {OUTPUT_DIR}")
    logger.info("=" * 80)


def generate_tables(results: list):
    """Gera tabelas CSV e LaTeX para publicação."""

    logger.info("\n📊 Gerando tabelas...")

    # Tabela 1: Métricas por cidade e fonte
    rows = []
    for result in results:
        city = result["city"]

        for source in ["nasa", "openmeteo", "evaonline"]:
            if source in result:
                metrics = result[source]
                rows.append({"city": city, "source": source, **metrics})

    df_metrics = pd.DataFrame(rows)

    # Salvar CSV
    csv_file = OUTPUT_DIR / "comparison_metrics.csv"
    df_metrics.to_csv(csv_file, index=False)
    logger.success(f"✅ Tabela de métricas: {csv_file.name}")

    # Tabela 2: Resumo estatístico por fonte
    summary_rows = []
    for source in ["nasa", "openmeteo", "evaonline"]:
        df_source = df_metrics[df_metrics["source"] == source]
        if len(df_source) > 0:
            summary_rows.append(
                {
                    "source": source,
                    "n_cities": len(df_source),
                    "r2_mean": df_source["r2"].mean(),
                    "r2_std": df_source["r2"].std(),
                    "nse_mean": df_source["nse"].mean(),
                    "nse_std": df_source["nse"].std(),
                    "mae_mean": df_source["mae"].mean(),
                    "mae_std": df_source["mae"].std(),
                    "rmse_mean": df_source["rmse"].mean(),
                    "rmse_std": df_source["rmse"].std(),
                    "pbias_mean": df_source["pbias"].mean(),
                    "pbias_std": df_source["pbias"].std(),
                }
            )

    df_summary = pd.DataFrame(summary_rows)
    summary_file = OUTPUT_DIR / "comparison_summary.csv"
    df_summary.to_csv(summary_file, index=False)
    logger.success(f"✅ Resumo estatístico: {summary_file.name}")

    # Gerar LaTeX
    generate_latex_tables(df_metrics, df_summary)


def generate_latex_tables(df_metrics: pd.DataFrame, df_summary: pd.DataFrame):
    """Gera tabelas em formato LaTeX para o artigo."""

    logger.info("📝 Gerando tabelas LaTeX...")

    # Tabela resumo para o artigo
    latex_file = OUTPUT_DIR / "tables_latex.tex"

    with open(latex_file, "w", encoding="utf-8") as f:
        f.write("% Tabela 1: Resumo das métricas por fonte\n")
        f.write("\\begin{table}[htbp]\n")
        f.write("\\centering\n")
        f.write(
            "\\caption{Performance comparison of ETo calculation "
            "methods against Xavier et al. reference dataset}\n"
        )
        f.write("\\label{tab:comparison}\n")
        f.write("\\begin{tabular}{lcccccc}\n")
        f.write("\\hline\n")
        f.write("Source & Cities & R² & NSE & MAE & RMSE & PBIAS (\\%) \\\\\n")
        f.write("\\hline\n")

        for _, row in df_summary.iterrows():
            source_name = {
                "nasa": "NASA POWER",
                "openmeteo": "Open-Meteo",
                "evaonline": "\\textbf{EVAOnline (fusion)}",
            }[row["source"]]

            f.write(
                f"{source_name} & "
                f"{int(row['n_cities'])} & "
                f"{row['r2_mean']:.3f} $\\pm$ {row['r2_std']:.3f} & "
                f"{row['nse_mean']:.3f} $\\pm$ {row['nse_std']:.3f} & "
                f"{row['mae_mean']:.3f} $\\pm$ {row['mae_std']:.3f} & "
                f"{row['rmse_mean']:.3f} $\\pm$ {row['rmse_std']:.3f} & "
                f"{row['pbias_mean']:.2f} $\\pm$ {row['pbias_std']:.2f} \\\\\n"
            )

        f.write("\\hline\n")
        f.write("\\end{tabular}\n")
        f.write("\\end{table}\n")

    logger.success(f"✅ Tabelas LaTeX: {latex_file.name}")


if __name__ == "__main__":
    process_all_cities()
