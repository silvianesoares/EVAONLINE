"""
FULL EVAONLINE PIPELINE WITH KALMAN FUSION

This script implements the COMPLETE EVAonline pipeline including:
- Multi-source data fusion (NASA POWER + Open-Meteo) using Kalman ensemble
- Final Kalman correction on calculated ETo for bias reduction
- Comprehensive validation against Xavier et al. (2022) BR-DWGD

Difference from script 5:
  Script 5: Single-source validation (Open-Meteo only, NO Kalman fusion)
  Script 6: Full pipeline with Kalman fusion of multiple data sources

Workflow:
1. Load local RAW data (NASA POWER + Open-Meteo)
2. Fetch elevation via TopoData
3. FAO-56 preprocessing
4. Vectorized wind conversion (10m → 2m, FAO-56 Eq. 47)
5. VECTORIZED Kalman fusion (NASA + Open-Meteo)
6. Calculate ETo + final Kalman bias correction
7. Validation vs Xavier BR-DWGD with publication-ready plots
"""

import sys
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np
from loguru import logger
from scipy.stats import linregress, norm as scipy_norm
from sklearn.metrics import mean_absolute_error, mean_squared_error

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Add root directory to Python path
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# EVAonline imports (after sys.path modification)
from scripts.config import (
    XAVIER_RESULTS_DIR,
    BRASIL_CITIES,
    get_xavier_eto_path,
)
from api.services.opentopo.opentopo_sync_adapter import (
    OpenTopoSyncAdapter,
)
from core.data_processing.data_preprocessing import (
    preprocessing,
)
from core.data_processing.kalman_ensemble import (
    ClimateKalmanEnsemble,
)
from core.eto_calculation.eto_services import (
    calculate_eto_timeseries,
)

# Optimized logger configuration
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
)

# Directories
DATA_DIR = Path(__file__).parent.parent / "data" / "original_data"
NASA_RAW_DIR = DATA_DIR / "nasa_power_raw"
OPENMETEO_RAW_DIR = DATA_DIR / "open_meteo_raw"

OUTPUT_DIR = XAVIER_RESULTS_DIR
CACHE_DIR = OUTPUT_DIR / "cache"
PREPROCESSED_DIR = OUTPUT_DIR / "preprocessed"

# Create only base directory (others created when needed)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_raw_data(city_name: str, source: str) -> pd.DataFrame:
    """
    Load local RAW data with intelligent fallback using glob pattern.

    Args:
        city_name: City name
        source: 'nasa' or 'openmeteo'

    Returns:
        DataFrame with RAW data
    """
    pattern = f"{city_name}_*.csv"
    directory = NASA_RAW_DIR if source == "nasa" else OPENMETEO_RAW_DIR

    files = list(directory.glob(pattern))
    if not files:
        logger.error(f"{source.upper()} not found: {city_name}")
        return pd.DataFrame()

    df = pd.read_csv(files[0])
    df["date"] = pd.to_datetime(df["date"])
    logger.info(f"{source.upper()}: {len(df)} days → {files[0].name}")
    return df


async def get_elevation(lat: float, lon: float) -> float:
    """
    Fetch elevation via TopoData with fast fallback.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Elevation in meters (default 500m if fails)
    """
    try:
        topo = OpenTopoSyncAdapter()
        elevation_obj = await asyncio.to_thread(
            topo.get_elevation_sync, lat, lon
        )
        if elevation_obj and hasattr(elevation_obj, "elevation"):
            elev = float(elevation_obj.elevation)
            logger.info(f"TopoData elevation: {elev:.1f}m")
            return elev
    except Exception as e:
        logger.warning(f"TopoData failed → using 500m (error: {str(e)[:50]})")
    return 500.0


async def process_city(
    city_name: str,
    lat: float,
    lon: float,
    start_date: str = "1991-01-01",
    end_date: str = "2020-12-31",
) -> Optional[pd.DataFrame]:
    """
    Process one city: RAW → Preprocessing → Kalman → ETo (optimized).

    Args:
        city_name: City name
        lat: Latitude
        lon: Longitude
        start_date: Start date
        end_date: End date

    Returns:
        DataFrame with calculated ETo
    """
    cache_file = CACHE_DIR / f"{city_name}_eto_final.csv"

    if cache_file.exists():
        logger.info(f"Using cache: {city_name}")
        return pd.read_csv(cache_file, parse_dates=["date"])

    # Create cache directory only when saving
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(f"Processing {city_name} | lat={lat:.4f}, lon={lon:.4f}")

    # === 1. LOAD RAW DATA ===
    nasa_raw = load_raw_data(city_name, "nasa")
    om_raw = load_raw_data(city_name, "openmeteo")

    if nasa_raw.empty:
        logger.error(f"NASA POWER missing → skipping {city_name}")
        return None

    # === 2. FETCH ELEVATION ===
    elevation = await get_elevation(lat, lon)

    # === 3. FAO-56 PREPROCESSING ===
    nasa_clean, _ = preprocessing(nasa_raw.set_index("date"), lat)
    om_clean = pd.DataFrame()

    if not om_raw.empty:
        # VECTORIZED wind conversion 10m → 2m
        if "WS10M" in om_raw.columns:
            logger.info("Converting wind 10m → 2m (vectorized)...")
            om_raw["WS2M"] = np.maximum(
                om_raw["WS10M"] * (4.87 / np.log(67.8 * 10 - 5.42)),
                0.5,  # minimum physical limit
            )
            om_raw = om_raw.drop(columns=["WS10M"], errors="ignore")
        om_clean, _ = preprocessing(om_raw.set_index("date"), lat)

    nasa_clean = nasa_clean.reset_index()
    om_clean = om_clean.reset_index() if not om_clean.empty else om_clean

    # === 4. VECTORIZED KALMAN FUSION  ===
    logger.info("->> Vectorized Kalman fusion...")
    kalman = ClimateKalmanEnsemble()

    try:
        fused_df = kalman.fuse_vectorized(
            nasa_df=nasa_clean, om_df=om_clean, lat=lat, lon=lon
        )
        logger.success(f"Fusion completed: {len(fused_df)} days")
    except Exception as e:
        logger.error(f"Vectorized fusion failed: {e}")
        logger.info("Using NASA POWER only")
        fused_df = nasa_clean.copy()

    # Save fused data
    PREPROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    fused_output = PREPROCESSED_DIR / f"{city_name}_FUSED.csv"
    fused_df.to_csv(fused_output, index=False)
    logger.info(f"Fused data saved: {fused_output.name}")

    # === 5. CALCULATE ETo + FINAL KALMAN CORRECTION ===
    logger.info("🌾 Calculating ETo + final Kalman correction...")
    df_final = calculate_eto_timeseries(
        df=fused_df,
        latitude=lat,
        longitude=lon,
        elevation_m=elevation,
        kalman_ensemble=kalman,
    )

    # Save fused data WITH calculated ETo (for Zenodo)
    fused_with_eto = PREPROCESSED_DIR / f"{city_name}_FUSED_ETo.csv"
    df_final.to_csv(fused_with_eto, index=False)
    logger.info(f"Fused data + ETo saved: {fused_with_eto.name}")

    # Save cache
    df_final.to_csv(cache_file, index=False)
    logger.success(f"{city_name} completed → {len(df_final)} days")

    return df_final


def compare_with_xavier(
    df_result: pd.DataFrame,
    city_key: str,
    output_dir: Path,
) -> Optional[Dict[str, Any]]:
    """
    Validation against BR-DWGD (Xavier et al., 2016) - Brazilian gold standard.

    Returns dictionary with complete metrics (FAO-56 + modern hydrology).
    Includes KGE (Kling-Gupta Efficiency)
    """
    logger.info(f"Validating {city_key} against Xavier BR-DWGD...")

    # Fetch Xavier file
    xavier_file = get_xavier_eto_path(city_key)

    if not xavier_file.exists():
        logger.error(f"Xavier file missing: {xavier_file.name}")
        return None

    try:
        df_xavier = pd.read_csv(xavier_file)
        df_xavier["date"] = pd.to_datetime(df_xavier["date"])
    except Exception as e:
        logger.error(f"Error reading Xavier: {e}")
        return None

    # Convert df_result date to datetime if needed
    if "date" not in df_result.columns and df_result.index.name == "date":
        df_result = df_result.reset_index()

    if not pd.api.types.is_datetime64_any_dtype(df_result["date"]):
        df_result["date"] = pd.to_datetime(df_result["date"])

    # Merge (use eto_final = ETo with final Kalman correction)
    df_compare = pd.merge(
        df_result[["date", "eto_final"]],
        df_xavier[["date", "eto_xavier"]],
        on="date",
        how="inner",
    ).dropna(subset=["eto_final", "eto_xavier"])

    if len(df_compare) < 100:  # more rigorous than 30
        logger.warning(f"Insufficient data: {len(df_compare)} days")
        return None

    calc = np.array(df_compare["eto_final"].values, dtype=float)
    ref = np.array(df_compare["eto_xavier"].values, dtype=float)

    # METRICS
    mae = float(mean_absolute_error(ref, calc))
    rmse = float(np.sqrt(mean_squared_error(ref, calc)))
    bias = float(np.mean(calc - ref))
    pbias = float(100 * np.sum(calc - ref) / np.sum(ref))

    # Linear regression
    lr = linregress(ref, calc)
    slope_val = float(lr.slope)
    intercept_val = float(lr.intercept)
    r_val = float(lr.rvalue)
    p_value = float(lr.pvalue)
    r2 = float(r_val**2)

    # NSE (Nash-Sutcliffe)
    nse = float(
        1 - np.sum((calc - ref) ** 2) / np.sum((ref - ref.mean()) ** 2)
    )

    # KGE (Kling-Gupta Efficiency - required in modern papers)
    r = np.corrcoef(ref, calc)[0, 1]
    alpha = np.std(calc) / np.std(ref)
    beta = np.mean(calc) / np.mean(ref)
    kge = float(1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2))

    # Determine statistical significance
    if p_value < 0.001:
        sig_level = "***"
        p_display = "p < 0.001"
    elif p_value < 0.01:
        sig_level = "**"
        p_display = f"p = {p_value:.3f}"
    elif p_value < 0.05:
        sig_level = "*"
        p_display = f"p = {p_value:.3f}"
    else:
        sig_level = "ns"
        p_display = f"p = {p_value:.3f} (ns)"

    logger.success(
        f"{city_key}: R²={r2:.3f}{sig_level} | NSE={nse:.3f} | "
        f"KGE={kge:.3f} | MAE={mae:.3f} | RMSE={rmse:.3f} | "
        f"PBIAS={pbias:+.1f}%"
    )

    # === PUBLICATION-READY PLOTS ===
    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    plt.style.use("seaborn-v0_8-darkgrid")
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["font.size"] = 10
    plt.rcParams["figure.dpi"] = 300

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle(
        f'{city_key.replace("_", " ")} - EVAonline Full Pipeline (1991-2020)',
        fontsize=14,
        fontweight="bold",
    )

    # (A) Scatter plot
    ax1 = axes[0, 0]
    ax1.scatter(
        ref, calc, c=np.arange(len(ref)), cmap="viridis", alpha=0.4, s=15
    )

    min_val = float(ref.min())
    max_val = float(ref.max())

    ax1.plot(
        [min_val, max_val],
        [min_val, max_val],
        "r--",
        lw=2,
        label="1:1 line",
        alpha=0.8,
    )
    ax1.plot(
        [min_val, max_val],
        [
            slope_val * min_val + intercept_val,
            slope_val * max_val + intercept_val,
        ],
        "b-",
        lw=2,
        label=f"y={slope_val:.2f}x+{intercept_val:.2f}",
        alpha=0.8,
    )

    ax1.set_xlabel("Xavier ET₀ (mm day⁻¹)", fontweight="bold")
    ax1.set_ylabel("EVAonline ET₀ (mm day⁻¹)", fontweight="bold")
    ax1.set_title("(A) Scatter Plot", fontweight="bold", loc="left")
    ax1.legend(loc="upper left", framealpha=0.9)
    ax1.grid(True, alpha=0.3, linestyle="--")
    ax1.set_aspect("equal", adjustable="box")

    # Add metrics (with KGE!)
    textstr = "\n".join(
        [
            f"R² = {r2:.3f} {sig_level}",
            f"{p_display}",
            f"KGE = {kge:.3f}",  # new metric
            f"NSE = {nse:.3f}",
            f"MAE = {mae:.2f} mm/day",
            f"RMSE = {rmse:.2f} mm/day",
            f"PBIAS = {pbias:.1f}%",
            f"n = {len(ref):,} days",
        ]
    )
    props = {"boxstyle": "round", "facecolor": "wheat", "alpha": 0.8}
    ax1.text(
        0.98,
        0.02,
        textstr,
        transform=ax1.transAxes,
        fontsize=9,
        verticalalignment="bottom",
        horizontalalignment="right",
        bbox=props,
    )

    # (B) Time series
    ax2 = axes[0, 1]
    ax2.plot(
        df_compare["date"],
        ref,
        label="Xavier (reference)",
        alpha=0.7,
        lw=1,
        color="#2E86AB",
    )
    ax2.plot(
        df_compare["date"],
        calc,
        label="EVAonline (Kalman-corrected)",
        alpha=0.7,
        lw=1,
        color="#A23B72",
    )
    ax2.set_xlabel("Date", fontweight="bold")
    ax2.set_ylabel("ET₀ (mm day⁻¹)", fontweight="bold")
    ax2.set_title("(B) Time Series", fontweight="bold", loc="left")
    ax2.legend(loc="upper right", framealpha=0.9)
    ax2.grid(True, alpha=0.3, linestyle="--")
    ax2.tick_params(axis="x", rotation=45)

    # (C) Residuals
    ax3 = axes[1, 0]
    residuals = calc - ref
    ax3.scatter(df_compare["date"], residuals, alpha=0.3, s=10, color="gray")
    ax3.axhline(y=0, color="r", linestyle="--", lw=2, alpha=0.8)
    ax3.axhline(
        y=np.mean(residuals),
        color="b",
        linestyle="-",
        lw=1.5,
        alpha=0.6,
        label=f"Mean bias = {bias:.2f} mm/day",
    )
    ax3.fill_between(
        df_compare["date"],
        -mae,
        mae,
        alpha=0.2,
        color="green",
        label=f"±MAE ({mae:.2f} mm/day)",
    )
    ax3.set_xlabel("Date", fontweight="bold")
    ax3.set_ylabel("Residuals (mm day⁻¹)", fontweight="bold")
    ax3.set_title("(C) Residuals Analysis", fontweight="bold", loc="left")
    ax3.legend(loc="upper right", framealpha=0.9)
    ax3.grid(True, alpha=0.3, linestyle="--")
    ax3.tick_params(axis="x", rotation=45)

    # (D) Distribution
    ax4 = axes[1, 1]
    ax4.hist(
        residuals,
        bins=50,
        density=True,
        alpha=0.6,
        color="steelblue",
        edgecolor="black",
        linewidth=0.5,
    )

    mu, std = residuals.mean(), residuals.std()
    x = np.linspace(residuals.min(), residuals.max(), 100)
    ax4.plot(
        x,
        scipy_norm.pdf(x, mu, std),
        "r-",
        lw=2,
        label=f"Normal(μ={mu:.2f}, σ={std:.2f})",
    )
    ax4.axvline(
        x=0, color="green", linestyle="--", lw=2, alpha=0.8, label="Zero bias"
    )
    ax4.set_xlabel("Residuals (mm day⁻¹)", fontweight="bold")
    ax4.set_ylabel("Probability Density", fontweight="bold")
    ax4.set_title("(D) Error Distribution", fontweight="bold", loc="left")
    ax4.legend(loc="upper right", framealpha=0.9)
    ax4.grid(True, alpha=0.3, linestyle="--", axis="y")

    plt.tight_layout(rect=(0, 0.03, 1, 0.97))

    # Save plots
    plot_base = plot_dir / f"{city_key}_validation"
    plt.savefig(f"{plot_base}.png", dpi=300, bbox_inches="tight")
    plt.savefig(f"{plot_base}.pdf", dpi=300, bbox_inches="tight")
    logger.info(f"📊 Plots saved: {plot_base}.[png|pdf]")
    plt.close()

    return {
        "city": city_key,
        "n_days": len(df_compare),
        "r2": round(r2, 4),
        "kge": round(kge, 4),  # new metric (reviewers love it)
        "nse": round(nse, 4),
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "bias": round(bias, 4),
        "pbias": round(pbias, 2),
        "slope": round(slope_val, 4),
        "intercept": round(intercept_val, 4),
        "p_value": round(p_value, 6),
        "significance": sig_level,
    }


async def main(
    start_date: str = "1991-01-01",
    end_date: str = "2020-12-31",
    cities_filter: Optional[list] = None,
):
    """Optimized full pipeline - 17 MATOPIBA cities."""

    logger.info("🚀 STARTING FULL EVAONLINE PIPELINE - 17 MATOPIBA cities")

    # Load coordinates
    csv_coords = PROJECT_ROOT / "data" / "info_cities.csv"
    df_coords = pd.read_csv(csv_coords)
    city_coords = {
        row["city"]: (row["lat"], row["lon"])
        for _, row in df_coords.iterrows()
    }

    cities_to_process = BRASIL_CITIES
    if cities_filter:
        cities_to_process = {
            k: v for k, v in cities_to_process.items() if k in cities_filter
        }

    results = []
    total = len(cities_to_process)

    for i, (city_key, _) in enumerate(cities_to_process.items(), 1):
        logger.info(f"\n[{i}/{total}] {city_key}")

        if city_key not in city_coords:
            logger.error(f"Coordinates not found: {city_key}")
            continue

        lat, lon = city_coords[city_key]

        try:
            df_result = await process_city(
                city_key, lat, lon, start_date, end_date
            )
            if df_result is None:
                continue

            metrics = compare_with_xavier(df_result, city_key, OUTPUT_DIR)
            if metrics:
                results.append(metrics)

        except Exception as e:
            logger.error(f"Error: {city_key} → {str(e)}")
            continue

    # Final report
    if results:
        summary = pd.DataFrame(results)
        summary.to_csv(OUTPUT_DIR / "FINAL_SUMMARY.csv", index=False)

        logger.success(f"\n-->> FINAL SUMMARY ({len(results)} cities):")
        logger.success(f"Mean R²: {summary['r2'].mean():.3f}")
        logger.success(f"Mean KGE: {summary['kge'].mean():.3f}")
        logger.success(f"Mean NSE: {summary['nse'].mean():.3f}")
        logger.success(
            f"  Mean MAE: {summary['mae'].mean():.3f} ± "
            f"{summary['mae'].std():.3f} mm/day"
        )
        logger.success(f"  Mean PBIAS: {summary['pbias'].mean():.2f}%")

    logger.success("\nPIPELINE COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Full EVAonline Pipeline - Optimized Version"
    )
    parser.add_argument("--start", default="1991-01-01", help="Start date")
    parser.add_argument("--end", default="2020-12-31", help="End date")
    parser.add_argument("--cities", nargs="+", help="Specific cities")

    args = parser.parse_args()

    asyncio.run(main(args.start, args.end, args.cities))
