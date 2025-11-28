"""
COMPLETE ETo SOURCES COMPARISON

Compares 4 ETo sources against Xavier BR-DWGD (reference):
1. NASA POWER raw only (without fusion)
2. OpenMeteo raw only (without fusion)
3. OpenMeteo ETo raw
4. EVAonline Full Pipeline (NASA + OpenMeteo with Kalman)

Outputs:
- Complete metrics in single CSV
- Comparative plots for each city
- Consolidated statistical summary
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

# Directories
DATA_DIR = PROJECT_ROOT / "data"
ORIGINAL_DATA = DATA_DIR / "original_data"
VALIDATION_DIR = DATA_DIR / "6_validation_full_pipeline" / "xavier_validation"

# ETo sources
SOURCES = {
    "NASA_ONLY": DATA_DIR / "4_eto_nasa_only",
    "OPENMETEO_ONLY": DATA_DIR / "4_eto_openmeteo_only",
    "OPENMETEO_API": ORIGINAL_DATA / "eto_open_meteo",
    "EVAONLINE_FUSION": VALIDATION_DIR / "cache",
}

# Referência Xavier
XAVIER_DIR = ORIGINAL_DATA / "eto_xavier_csv"

# Output (inside data directory, same level as other numbered folders)
OUTPUT_DIR = DATA_DIR / "7_comparison_all_sources"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_eto_data(city_name: str, source_key: str) -> Optional[pd.DataFrame]:
    """
    Load ETo data from a specific source.

    Args:
        city_name: City name (e.g., Alvorada_do_Gurgueia_PI)
        source_key: Source key (NASA_ONLY, OPENMETEO_ONLY, etc)

    Returns:
        DataFrame with columns [date, eto]
    """
    source_dir = SOURCES[source_key]

    # Naming patterns by source
    patterns = {
        "NASA_ONLY": f"{city_name}_ETo_NASA_ONLY.csv",
        "OPENMETEO_ONLY": f"{city_name}_ETo_OpenMeteo_ONLY.csv",
        "OPENMETEO_API": f"{city_name}_OpenMeteo_ETo.csv",
        "EVAONLINE_FUSION": f"{city_name}_eto_final.csv",
    }

    file_path = source_dir / patterns[source_key]

    if not file_path.exists():
        logger.warning(f"{source_key}: File not found - {file_path.name}")
        return None

    try:
        df = pd.read_csv(file_path, parse_dates=["date"])

        # Rename ETo column for standardization
        eto_col_map = {
            "NASA_ONLY": "eto_evaonline",
            "OPENMETEO_ONLY": "eto_evaonline",
            "OPENMETEO_API": "eto_openmeteo",
            "EVAONLINE_FUSION": "eto_final",
        }

        eto_col = eto_col_map[source_key]

        if eto_col not in df.columns:
            logger.error(f"{source_key}: Column '{eto_col}' not found")
            return None

        df = df[["date", eto_col]].rename(columns={eto_col: "eto"})
        logger.info(f"{source_key}: {len(df)} days")

        return df

    except Exception as e:
        logger.error(f"{source_key}: Error reading file - {e}")
        return None


def load_xavier_reference(city_name: str) -> Optional[pd.DataFrame]:
    """Load Xavier reference data."""
    file_path = XAVIER_DIR / f"{city_name}.csv"

    if not file_path.exists():
        logger.error(f"Xavier not found: {file_path.name}")
        return None

    try:
        df = pd.read_csv(file_path, parse_dates=["date"])
        df = df[["date", "eto_xavier"]].rename(columns={"eto_xavier": "eto"})
        logger.info(f"Xavier: {len(df)} days")
        return df
    except Exception as e:
        logger.error(f"Error reading Xavier: {e}")
        return None


def calculate_metrics(ref: np.ndarray, calc: np.ndarray) -> Dict[str, float]:
    """
    Calculate complete validation metrics.

    Returns:
        Dictionary with R², KGE, NSE, MAE, RMSE, PBIAS, etc.
    """

    # Force float and remove NaN (safety)
    ref = np.asarray(ref, dtype=float)
    calc = np.asarray(calc, dtype=float)
    mask = ~(np.isnan(ref) | np.isnan(calc))
    if mask.sum() < 10:  # protection against insufficient data
        return {
            k: np.nan
            for k in "r2 kge nse mae rmse bias pbias slope intercept p_value significance".split()
        }

    ref, calc = ref[mask], calc[mask]
    n = len(ref)

    # Basic metrics
    mae = float(mean_absolute_error(ref, calc))
    rmse = float(np.sqrt(mean_squared_error(ref, calc)))
    bias = float(np.mean(calc - ref))
    pbias = (
        float(100 * np.sum(calc - ref) / np.sum(ref))
        if np.sum(ref) != 0
        else np.nan
    )

    # Linear regression
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

    # R significance (correlation)
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
    Compare all ETo sources for a city.

    Returns:
        List of dictionaries with metrics by source
    """
    logger.info(f"\n{city_name}")

    # Load Xavier (reference)
    df_xavier = load_xavier_reference(city_name)
    if df_xavier is None:
        return []

    results = []
    dfs_for_plot = {"Xavier": df_xavier}

    # Load and compare each source
    for source_key in SOURCES.keys():
        df_source = load_eto_data(city_name, source_key)

        if df_source is None:
            continue

        # Merge with Xavier
        df_compare = pd.merge(
            df_xavier, df_source, on="date", suffixes=("_xavier", "_source")
        ).dropna()

        if len(df_compare) < 100:
            logger.warning(
                f"{source_key}: Insufficient data ({len(df_compare)} days)"
            )
            continue

        # Calculate metrics
        ref = df_compare["eto_xavier"].values
        calc = df_compare["eto_source"].values

        metrics = calculate_metrics(ref, calc)
        metrics["city"] = city_name
        metrics["source"] = source_key
        metrics["n_days"] = len(df_compare)

        results.append(metrics)

        # Save for plotting
        dfs_for_plot[source_key] = df_compare[["date", "eto_source"]].rename(
            columns={"eto_source": "eto"}
        )

        logger.success(
            f"{source_key:20s} | R²={metrics['r2']:.3f} | "
            f"KGE={metrics['kge']:.3f} | MAE={metrics['mae']:.3f}"
        )

    # Generate comparative plot
    if len(results) > 0:
        plot_comparison(city_name, dfs_for_plot, results)

    return results


def plot_comparison(
    city_name: str,
    dfs: Dict[str, pd.DataFrame],
    metrics: List[Dict],
):
    """
    Generate comparative plot with 4 sources vs Xavier.

    Layout: 2x2 grid
    - (A) Complete time series
    - (B) Scatter plots NASA vs OpenMeteo
    - (C) Metrics bars (R², KGE, MAE)
    - (D) Residuals box plots
    """
    fig = plt.figure(figsize=(18, 14))
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)

    fig.suptitle(
        f'{city_name.replace("_", " ")} - ETo Sources Comparison (1991-2020)',
        fontsize=16,
        fontweight="bold",
    )

    # Colors by source
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

    # (A) Time series - 2 full columns
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

        # Merge for scatter
        df_merge = pd.merge(
            df_xavier, dfs[source], on="date", suffixes=("_xavier", "_source")
        ).dropna()

        ref = df_merge["eto_xavier"].values
        calc = df_merge["eto_source"].values

        # Scatter plot plot
        ax.scatter(ref, calc, alpha=0.3, s=10, color=colors[source])

        # 1:1 line
        min_val = min(ref.min(), calc.min())
        max_val = max(ref.max(), calc.max())
        ax.plot([min_val, max_val], [min_val, max_val], "k--", lw=2, alpha=0.5)

        # Regression line
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

        # Metrics in corner
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

    # Save plots
    plot_dir = OUTPUT_DIR / "plots"
    plot_dir.mkdir(exist_ok=True)

    plot_path = plot_dir / f"{city_name}_comparison"
    plt.savefig(f"{plot_path}.png", dpi=300, bbox_inches="tight")
    plt.savefig(f"{plot_path}.pdf", dpi=300, bbox_inches="tight")
    plt.close()

    logger.info(f"  📊 Plot saved: {plot_path.name}")


def generate_summary_table(results: List[Dict]) -> pd.DataFrame:
    """
    Generate summary table with averages, std, min, max by source.
    """
    df = pd.DataFrame(results)

    # Create summary manually to avoid multi-index
    summary_data = []
    for source in df["source"].unique():
        src_df = df[df["source"] == source]
        summary_data.append(
            {
                "source": source,
                "n_cities": len(src_df),
                "n_days": int(src_df["n_days"].mean()),
                # R²
                "r2_mean": round(src_df["r2"].mean(), 4),
                "r2_std": round(src_df["r2"].std(), 4),
                "r2_min": round(src_df["r2"].min(), 4),
                "r2_max": round(src_df["r2"].max(), 4),
                # KGE
                "kge_mean": round(src_df["kge"].mean(), 4),
                "kge_std": round(src_df["kge"].std(), 4),
                "kge_min": round(src_df["kge"].min(), 4),
                "kge_max": round(src_df["kge"].max(), 4),
                # NSE
                "nse_mean": round(src_df["nse"].mean(), 4),
                "nse_std": round(src_df["nse"].std(), 4),
                "nse_min": round(src_df["nse"].min(), 4),
                "nse_max": round(src_df["nse"].max(), 4),
                # MAE
                "mae_mean": round(src_df["mae"].mean(), 4),
                "mae_std": round(src_df["mae"].std(), 4),
                "mae_min": round(src_df["mae"].min(), 4),
                "mae_max": round(src_df["mae"].max(), 4),
                # RMSE
                "rmse_mean": round(src_df["rmse"].mean(), 4),
                "rmse_std": round(src_df["rmse"].std(), 4),
                "rmse_min": round(src_df["rmse"].min(), 4),
                "rmse_max": round(src_df["rmse"].max(), 4),
                # PBIAS
                "pbias_mean": round(src_df["pbias"].mean(), 2),
                "pbias_std": round(src_df["pbias"].std(), 2),
                "pbias_min": round(src_df["pbias"].min(), 2),
                "pbias_max": round(src_df["pbias"].max(), 2),
                # Slope
                "slope_mean": round(src_df["slope"].mean(), 4),
                "slope_std": round(src_df["slope"].std(), 4),
                "slope_min": round(src_df["slope"].min(), 4),
                "slope_max": round(src_df["slope"].max(), 4),
                # Intercept
                "intercept_mean": round(src_df["intercept"].mean(), 4),
                "intercept_std": round(src_df["intercept"].std(), 4),
                "intercept_min": round(src_df["intercept"].min(), 4),
                "intercept_max": round(src_df["intercept"].max(), 4),
                # P-value (mean across cities)
                "p_value_mean": round(src_df["p_value"].mean(), 6),
                "p_value_max": round(src_df["p_value"].max(), 6),
            }
        )

    return pd.DataFrame(summary_data)


def main():
    """Main comparison pipeline."""
    logger.info("=" * 90)
    logger.info("COMPLETE COMPARISON - 4 ETo SOURCES vs Xavier BR-DWGD")
    logger.info("=" * 90)

    # City list (same as MATOPIBA)
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

    # Save complete results
    if all_results:
        df_results = pd.DataFrame(all_results)
        results_path = OUTPUT_DIR / "COMPARISON_ALL_SOURCES.csv"
        df_results.to_csv(results_path, index=False)
        logger.success(f"\n✅ Results saved: {results_path}")

        # Generate statistical summary
        summary = generate_summary_table(all_results)
        summary_path = OUTPUT_DIR / "SUMMARY_BY_SOURCE.csv"
        summary.to_csv(summary_path, index=False)
        logger.success(f"->> Summary saved: {summary_path}")

        # Display summary
        logger.info("\n" + "=" * 90)
        logger.info("->> SUMMARY BY SOURCE (mean ± std):")
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
                r2_m = src_data["r2"].mean()
                r2_s = src_data["r2"].std()
                logger.info(f"R²: {r2_m:.3f} ± {r2_s:.3f}")

                kge_m = src_data["kge"].mean()
                kge_s = src_data["kge"].std()
                logger.info(f"KGE: {kge_m:.3f} ± {kge_s:.3f}")

                nse_m = src_data["nse"].mean()
                nse_s = src_data["nse"].std()
                logger.info(f"NSE: {nse_m:.3f} ± {nse_s:.3f}")

                mae_m = src_data["mae"].mean()
                mae_s = src_data["mae"].std()
                logger.info(f"MAE: {mae_m:.3f} ± {mae_s:.3f}")

                pb_m = src_data["pbias"].mean()
                pb_s = src_data["pbias"].std()
                logger.info(f"PBIAS: {pb_m:.2f}% ± {pb_s:.2f}%")

        logger.success("\n--->> PROCESS COMPLETED SUCCESSFULLY! <<---")
    else:
        logger.error("No results generated!")


if __name__ == "__main__":
    main()
