"""
COMPARAÇÃO COMPLETA DE FONTES ETo

Compara 4 fontes de ETo contra Xavier BR-DWGD (referência):
1. NASA POWER raw only (sem fusão)
2. OpenMeteo raw only (sem fusão)
3. OpenMeteo ETo raw
4. EVAonline Full Pipeline (NASA + OpenMeteo com Kalman)

Saídas:
- Métricas completas em CSV único
- Gráficos comparativos para cada cidade
- Resumo estatístico consolidado
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np
from loguru import logger
from scipy.stats import linregress
from sklearn.metrics import mean_absolute_error, mean_squared_error
import matplotlib
import matplotlib.pyplot as plt

# Setup
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

matplotlib.use("Agg")
plt.style.use("seaborn-v0_8-darkgrid")
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["font.size"] = 14
plt.rcParams["figure.dpi"] = 300

logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
)

# Diretórios
DATA_DIR = PROJECT_ROOT / "data"
ORIGINAL_DATA = DATA_DIR / "original_data"
VALIDATION_DIR = (
    DATA_DIR / "validation_results_all_pipeline" / "xavier_validation"
)

# Fontes de ETo
SOURCES = {
    "NASA_ONLY": DATA_DIR / "eto_nasa_only",
    "OPENMETEO_ONLY": DATA_DIR / "eto_openmeteo_only",
    "OPENMETEO_API": ORIGINAL_DATA / "eto_open_meteo",
    "EVAONLINE_FUSION": VALIDATION_DIR / "full_pipeline" / "cache",
}

# Referência Xavier
XAVIER_DIR = ORIGINAL_DATA / "eto_xavier_csv"

# Output
OUTPUT_DIR = VALIDATION_DIR / "comparison_all_sources"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_eto_data(city_name: str, source_key: str) -> Optional[pd.DataFrame]:
    """
    Carrega dados de ETo de uma fonte específica.

    Args:
        city_name: Nome da cidade (ex: Alvorada_do_Gurgueia_PI)
        source_key: Chave da fonte (NASA_ONLY, OPENMETEO_ONLY, etc)

    Returns:
        DataFrame com colunas [date, eto]
    """
    source_dir = SOURCES[source_key]

    # Padrões de nomenclatura por fonte
    patterns = {
        "NASA_ONLY": f"{city_name}_ETo_NASA_ONLY.csv",
        "OPENMETEO_ONLY": f"{city_name}_ETo_OpenMeteo_ONLY.csv",
        "OPENMETEO_API": f"{city_name}_OpenMeteo_ETo.csv",
        "EVAONLINE_FUSION": f"{city_name}_eto_final.csv",
    }

    file_path = source_dir / patterns[source_key]

    if not file_path.exists():
        logger.warning(
            f"{source_key}: Arquivo não encontrado - {file_path.name}"
        )
        return None

    try:
        df = pd.read_csv(file_path, parse_dates=["date"])

        # Renomear coluna de ETo para padronização
        eto_col_map = {
            "NASA_ONLY": "eto_evaonline",
            "OPENMETEO_ONLY": "eto_evaonline",
            "OPENMETEO_API": "eto_openmeteo",
            "EVAONLINE_FUSION": "eto_final",
        }

        eto_col = eto_col_map[source_key]

        if eto_col not in df.columns:
            logger.error(f"{source_key}: Coluna '{eto_col}' não encontrada")
            return None

        df = df[["date", eto_col]].rename(columns={eto_col: "eto"})
        logger.info(f"{source_key}: {len(df)} dias")

        return df

    except Exception as e:
        logger.error(f"{source_key}: Erro ao ler arquivo - {e}")
        return None


def load_xavier_reference(city_name: str) -> Optional[pd.DataFrame]:
    """Carrega dados de referência Xavier."""
    file_path = XAVIER_DIR / f"{city_name}.csv"

    if not file_path.exists():
        logger.error(f"Xavier não encontrado: {file_path.name}")
        return None

    try:
        df = pd.read_csv(file_path, parse_dates=["date"])
        df = df[["date", "eto_xavier"]].rename(columns={"eto_xavier": "eto"})
        logger.info(f"Xavier: {len(df)} dias")
        return df
    except Exception as e:
        logger.error(f"Erro ao ler Xavier: {e}")
        return None


def calculate_metrics(ref: np.ndarray, calc: np.ndarray) -> Dict[str, float]:
    """
    Calcula métricas completas de validação.

    Returns:
        Dicionário com R², KGE, NSE, MAE, RMSE, PBIAS, etc.
    """

    # Forçar float e remover NaN (segurança)
    ref = np.asarray(ref, dtype=float)
    calc = np.asarray(calc, dtype=float)
    mask = ~(np.isnan(ref) | np.isnan(calc))
    if mask.sum() < 10:  # proteção contra poucos dados
        return {
            k: np.nan
            for k in "r2 kge nse mae rmse bias pbias slope intercept p_value significance".split()
        }

    ref, calc = ref[mask], calc[mask]
    n = len(ref)

    # Métricas básicas
    mae = float(mean_absolute_error(ref, calc))
    rmse = float(np.sqrt(mean_squared_error(ref, calc)))
    bias = float(np.mean(calc - ref))
    pbias = (
        float(100 * np.sum(calc - ref) / np.sum(ref))
        if np.sum(ref) != 0
        else np.nan
    )

    # Regressão linear
    slope, intercept, r_val, p_val, _ = linregress(ref, calc)
    r2 = float(r_val**2)

    # NSE (Nash-Sutcliffe Efficiency)
    nse = float(
        1 - np.sum((calc - ref) ** 2) / np.sum((ref - ref.mean()) ** 2)
    )

    # KGE 2012 (Kling-Gupta Efficiency)
    r = np.corrcoef(ref, calc)[0, 1]
    alpha = np.std(calc) / np.std(ref) if np.std(ref) > 0 else np.nan
    beta = np.mean(calc) / np.mean(ref) if np.mean(ref) > 0 else np.nan
    kge = float(1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2))

    # Significância do R (correlação)
    sig = (
        "***"
        if p_val < 0.001
        else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "ns"
    )

    return {
        "n": int(n),
        "r2": round(r2, 3),
        "kge": round(kge, 3),
        "nse": round(nse, 3),
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "bias": round(bias, 3),
        "pbias": round(pbias, 2),
        "slope": round(float(slope), 3),
        "intercept": round(float(intercept), 3),
        "p_value": round(float(p_val), 6),
        "significance": sig,
    }


def compare_city(city_name: str) -> List[Dict]:
    """
    Compara todas as fontes de ETo para uma cidade.

    Returns:
        Lista de dicionários com métricas por fonte
    """
    logger.info(f"\n{city_name}")

    # Carregar Xavier (referência)
    df_xavier = load_xavier_reference(city_name)
    if df_xavier is None:
        return []

    results = []
    dfs_for_plot = {"Xavier": df_xavier}

    # Carregar e comparar cada fonte
    for source_key in SOURCES.keys():
        df_source = load_eto_data(city_name, source_key)

        if df_source is None:
            continue

        # Merge com Xavier
        df_compare = pd.merge(
            df_xavier, df_source, on="date", suffixes=("_xavier", "_source")
        ).dropna()

        if len(df_compare) < 100:
            logger.warning(
                f"{source_key}: Dados insuficientes ({len(df_compare)} dias)"
            )
            continue

        # Calcular métricas
        ref = df_compare["eto_xavier"].values
        calc = df_compare["eto_source"].values

        metrics = calculate_metrics(ref, calc)
        metrics["city"] = city_name
        metrics["source"] = source_key
        metrics["n_days"] = len(df_compare)

        results.append(metrics)

        # Guardar para plot
        dfs_for_plot[source_key] = df_compare[["date", "eto_source"]].rename(
            columns={"eto_source": "eto"}
        )

        logger.success(
            f"{source_key:20s} | R²={metrics['r2']:.3f} | "
            f"KGE={metrics['kge']:.3f} | MAE={metrics['mae']:.3f}"
        )

    # Gerar gráfico comparativo
    if len(results) > 0:
        plot_comparison(city_name, dfs_for_plot, results)

    return results


def plot_comparison(
    city_name: str,
    dfs: Dict[str, pd.DataFrame],
    metrics: List[Dict],
):
    """
    Gera gráfico comparativo com 4 fontes vs Xavier.

    Layout: 2x2 grid
    - (A) Séries temporais completas
    - (B) Scatter plots NASA vs OpenMeteo
    - (C) Barras de métricas (R², KGE, MAE)
    - (D) Box plots de resíduos
    """
    fig = plt.figure(figsize=(18, 14))
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)

    fig.suptitle(
        f'{city_name.replace("_", " ")} - Comparação de Fontes ETo (1991-2020)',
        fontsize=16,
        fontweight="bold",
    )

    # Cores por fonte
    colors = {
        "Xavier": "#000000",
        "NASA_ONLY": "#E63946",
        "OPENMETEO_ONLY": "#2A9D8F",
        "OPENMETEO_API": "#F4A261",
        "EVAONLINE_FUSION": "#264653",
    }

    labels = {
        "Xavier": "BR-DWGD (reference)",
        "NASA_ONLY": "NASA POWER only",
        "OPENMETEO_ONLY": "OpenMeteo only",
        "OPENMETEO_API": "OpenMeteo API",
        "EVAONLINE_FUSION": "EVAonline Fusion",
    }

    # (A) Séries temporais - 2 colunas inteiras
    ax1 = fig.add_subplot(gs[0, :])

    df_xavier = dfs["Xavier"]
    ax1.plot(
        df_xavier["date"],
        df_xavier["eto"],
        label=labels["Xavier"],
        color=colors["Xavier"],
        alpha=0.8,
        lw=2,
        zorder=5,
    )

    for source in [
        "NASA_ONLY",
        "OPENMETEO_ONLY",
        "OPENMETEO_API",
        "EVAONLINE_FUSION",
    ]:
        if source in dfs:
            df = dfs[source]
            ax1.plot(
                df["date"],
                df["eto"],
                label=labels[source],
                color=colors[source],
                alpha=0.6,
                lw=1.5,
            )

    ax1.set_xlabel("Date", fontweight="bold")
    ax1.set_ylabel("ET₀ (mm day⁻¹)", fontweight="bold")
    ax1.set_title("(A) Time Series Comparison", fontweight="bold", loc="left")
    ax1.legend(loc="upper right", framealpha=0.95, ncol=3)
    ax1.grid(True, alpha=0.3)

    # (B) Scatter plots - 4 subplots
    scatter_axes = [
        fig.add_subplot(gs[1, 0]),
        fig.add_subplot(gs[1, 1]),
        fig.add_subplot(gs[2, 0]),
        fig.add_subplot(gs[2, 1]),
    ]

    source_order = [
        "NASA_ONLY",
        "OPENMETEO_ONLY",
        "OPENMETEO_API",
        "EVAONLINE_FUSION",
    ]

    for i, (ax, source) in enumerate(zip(scatter_axes, source_order)):
        if source not in dfs:
            ax.text(0.5, 0.5, "Data not available", ha="center", va="center")
            ax.set_title(
                f"({chr(66+i)}) {labels[source]}",
                fontweight="bold",
                loc="left",
            )
            continue

        # Merge para scatter
        df_merge = pd.merge(
            df_xavier, dfs[source], on="date", suffixes=("_xavier", "_source")
        ).dropna()

        ref = df_merge["eto_xavier"].values
        calc = df_merge["eto_source"].values

        # Scatter
        ax.scatter(ref, calc, alpha=0.3, s=10, color=colors[source])

        # Linha 1:1
        min_val = min(ref.min(), calc.min())
        max_val = max(ref.max(), calc.max())
        ax.plot([min_val, max_val], [min_val, max_val], "k--", lw=2, alpha=0.5)

        # Regressão
        m = [m for m in metrics if m["source"] == source][0]
        x_line = np.array([min_val, max_val])
        y_line = m["slope"] * x_line + m["intercept"]
        ax.plot(x_line, y_line, color=colors[source], lw=2, alpha=0.8)

        ax.set_xlabel("Xavier ET₀ (mm day⁻¹)", fontweight="bold")
        ax.set_ylabel(
            f"{labels[source].split()[0]} ET₀ (mm day⁻¹)", fontweight="bold"
        )
        ax.set_title(
            f"({chr(66+i)}) {labels[source]}", fontweight="bold", loc="left"
        )
        ax.grid(True, alpha=0.3)
        ax.set_aspect("equal", adjustable="box")

        # Métricas no canto
        textstr = "\n".join(
            [
                f"R² = {m['r2']:.3f} {m['significance']}",
                f"KGE = {m['kge']:.3f}",
                f"MAE = {m['mae']:.2f}",
                f"PBIAS = {m['pbias']:.1f}%",
            ]
        )
        props = {"boxstyle": "round", "facecolor": "wheat", "alpha": 0.8}
        ax.text(
            0.05,
            0.95,
            textstr,
            transform=ax.transAxes,
            fontsize=8,
            verticalalignment="top",
            bbox=props,
        )

    # Salvar
    plot_dir = OUTPUT_DIR / "plots"
    plot_dir.mkdir(exist_ok=True)

    plot_path = plot_dir / f"{city_name}_comparison"
    plt.savefig(f"{plot_path}.png", dpi=300, bbox_inches="tight")
    plt.savefig(f"{plot_path}.pdf", dpi=300, bbox_inches="tight")
    plt.close()

    logger.info(f"  📊 Gráfico salvo: {plot_path.name}")


def generate_summary_table(results: List[Dict]) -> pd.DataFrame:
    """
    Gera tabela resumo com médias por fonte (formato limpo).
    """
    df = pd.DataFrame(results)

    # Criar resumo manualmente para evitar multi-index
    summary_data = []
    for source in df["source"].unique():
        src_df = df[df["source"] == source]
        summary_data.append(
            {
                "source": source,
                "n_cities": len(src_df),
                "n_days": int(src_df["n_days"].mean()),
                "r2_mean": round(src_df["r2"].mean(), 4),
                "r2_std": round(src_df["r2"].std(), 4),
                "kge_mean": round(src_df["kge"].mean(), 4),
                "kge_std": round(src_df["kge"].std(), 4),
                "nse_mean": round(src_df["nse"].mean(), 4),
                "nse_std": round(src_df["nse"].std(), 4),
                "mae_mean": round(src_df["mae"].mean(), 4),
                "mae_std": round(src_df["mae"].std(), 4),
                "rmse_mean": round(src_df["rmse"].mean(), 4),
                "rmse_std": round(src_df["rmse"].std(), 4),
                "pbias_mean": round(src_df["pbias"].mean(), 2),
                "pbias_std": round(src_df["pbias"].std(), 2),
            }
        )

    return pd.DataFrame(summary_data)


def main():
    """Pipeline principal de comparação."""
    logger.info("=" * 90)
    logger.info("COMPARAÇÃO COMPLETA - 4 FONTES ETo vs Xavier BR-DWGD")
    logger.info("=" * 90)

    # Lista de cidades (mesmas do MATOPIBA)
    cities = [
        "Alvorada_do_Gurgueia_PI",
        "Araguaina_TO",
        "Balsas_MA",
        "Barreiras_BA",
        "Bom_Jesus_PI",
        "Campos_Lindos_TO",
        "Carolina_MA",
        "Corrente_PI",
        "Formosa_do_Rio_Preto_BA",
        "Imperatriz_MA",
        "Luiz_Eduardo_Magalhaes_BA",
        "Pedro_Afonso_TO",
        "Piracicaba_SP",
        "Porto_Nacional_TO",
        "Sao_Desiderio_BA",
        "Tasso_Fragoso_MA",
        "Urucui_PI",
    ]

    all_results = []

    for i, city in enumerate(cities, 1):
        logger.info(f"\n[{i}/{len(cities)}]")
        city_results = compare_city(city)
        all_results.extend(city_results)

    # Salvar resultados completos
    if all_results:
        df_results = pd.DataFrame(all_results)
        results_path = OUTPUT_DIR / "COMPARISON_ALL_SOURCES.csv"
        df_results.to_csv(results_path, index=False)
        logger.success(f"\n✅ Resultados salvos: {results_path}")

        # Gerar resumo estatístico
        summary = generate_summary_table(all_results)
        summary_path = OUTPUT_DIR / "SUMMARY_BY_SOURCE.csv"
        summary.to_csv(summary_path, index=False)
        logger.success(f"->> Resumo salvo: {summary_path}")

        # Exibir resumo
        logger.info("\n" + "=" * 90)
        logger.info("->> RESUMO POR FONTE (média ± std):")
        logger.info("=" * 90)

        for source in [
            "NASA_ONLY",
            "OPENMETEO_ONLY",
            "OPENMETEO_API",
            "EVAONLINE_FUSION",
        ]:
            src_data = df_results[df_results["source"] == source]
            if len(src_data) > 0:
                logger.info(f"\n{source}:")
                logger.info(
                    f"R²: {src_data['r2'].mean():.3f} ± {src_data['r2'].std():.3f}"
                )
                logger.info(
                    f"KGE: {src_data['kge'].mean():.3f} ± {src_data['kge'].std():.3f}"
                )
                logger.info(
                    f"NSE: {src_data['nse'].mean():.3f} ± {src_data['nse'].std():.3f}"
                )
                logger.info(
                    f"MAE: {src_data['mae'].mean():.3f} ± {src_data['mae'].std():.3f}"
                )
                logger.info(
                    f"PBIAS: {src_data['pbias'].mean():.2f}% ± {src_data['pbias'].std():.2f}%"
                )

        logger.success("\n--->>PROCESSO CONCLUÍDO COM SUCESSO!<<---")
    else:
        logger.error("Nenhum resultado gerado!")


if __name__ == "__main__":
    main()
