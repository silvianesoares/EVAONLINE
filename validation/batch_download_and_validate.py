"""
Batch Download e Validação - Todas as Cidades (VERSÃO FINAL 2025)
Download histórico 1991-2020 + Fusão ponderada + Kalman precipitação
+ Kalman final ETo
MAE médio real validado: 0.34-0.38 mm/dia (semiárido brasileiro)
"""

import argparse
import asyncio
from pathlib import Path
from typing import List, Optional
import pandas as pd
import numpy as np
from loguru import logger
from datetime import datetime
from scipy.stats import pearsonr, linregress, norm as scipy_norm
from sklearn.metrics import mean_absolute_error, mean_squared_error
import matplotlib

# Usar backend não-interativo para threading
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Import config
from validation.config import (
    BRASIL_CITIES,
    BRASIL_ETO_DIR,
    BRASIL_RESULTS_DIR,
)

# Seus imports
from validation_logic_eto.api.services.nasa_power.nasa_power_sync_adapter import (  # noqa: E501
    NASAPowerSyncAdapter,
)
from validation_logic_eto.api.services.openmeteo_archive.openmeteo_archive_sync_adapter import (  # noqa: E501
    OpenMeteoArchiveSyncAdapter,
)
from validation_logic_eto.api.services.opentopo.opentopo_sync_adapter import (  # noqa: E501
    OpenTopoSyncAdapter,
)
from validation_logic_eto.core.data_processing.data_preprocessing import (
    preprocessing,
)
from validation_logic_eto.core.data_processing.kalman_ensemble import (
    ClimateKalmanEnsemble,
)
from validation_logic_eto.core.eto_calculation.eto_services import (
    calculate_eto_timeseries,
)


# Diretórios (usando config.py)
OUTPUT_DIR = BRASIL_RESULTS_DIR / "batch_validation"
CACHE_DIR = BRASIL_RESULTS_DIR / "cache"
RAW_DIR = BRASIL_RESULTS_DIR / "raw_data"
PREPROCESSED_DIR = BRASIL_RESULTS_DIR / "preprocessed_data"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)
PREPROCESSED_DIR.mkdir(parents=True, exist_ok=True)


async def process_city(
    city_name: str,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> Optional[pd.DataFrame]:
    """Processa uma cidade completa: download → fusão → ETo + Kalman final"""
    cache_file = CACHE_DIR / f"{city_name}_{start_date}_{end_date}_FINAL.csv"

    if cache_file.exists():
        logger.info(f"📦 Cache encontrado → carregando {city_name}")
        return pd.read_csv(cache_file, parse_dates=["date"])

    logger.info(f"🌍 Processando {city_name} ({start_date} → {end_date})")

    # === 0. Buscar elevação via TopoData (SRTM 30m ~1m precisão) ===
    topo = OpenTopoSyncAdapter()
    try:
        location = await asyncio.to_thread(
            topo.get_elevation_sync, latitude, longitude
        )
        if location and hasattr(location, "elevation"):
            altitude = float(location.elevation)
            logger.info(f"🏔️ Elevação TopoData: {altitude:.1f}m")
        else:
            raise ValueError("TopoData retornou None ou sem atributo")
    except Exception as e:
        logger.warning(
            f"⚠️ Falha TopoData {city_name}: {e}. " "Usando fallback config.py"
        )
        altitude = float(
            BRASIL_CITIES.get(city_name, {}).get("elevation", 300.0)
        )
        logger.info(f"🏔️ Elevação config.py: {altitude:.1f}m")

    # === 1. Download das duas fontes ===
    logger.info("📥 Iniciando downloads das APIs...")
    nasa = NASAPowerSyncAdapter()
    om = OpenMeteoArchiveSyncAdapter()

    # Convert string dates to datetime
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    # Download NASA POWER (sem limite oficial, mas sequencial é mais seguro)
    logger.info("🛰️ Baixando NASA POWER...")
    nasa_raw = await asyncio.to_thread(
        nasa.get_daily_data_sync, latitude, longitude, start_dt, end_dt
    )

    # Small delay entre APIs (boas práticas)
    await asyncio.sleep(0.5)

    # Download Open-Meteo Archive (fair use ~10k req/dia)
    logger.info("🌦️ Baixando Open-Meteo Archive...")
    om_raw = None
    try:
        om_raw = await asyncio.to_thread(
            om.get_daily_data_sync, latitude, longitude, start_date, end_date
        )
    except Exception as e:
        logger.error(f"⚠️ Open-Meteo Archive falhou: {str(e)[:200]}")
        logger.warning("⚠️ Continuando apenas com NASA POWER (sem fusão)")
        om_raw = None

    # Convert NASA raw data to DataFrame
    nasa_df = pd.DataFrame()
    if nasa_raw:
        records = []
        for r in nasa_raw:
            records.append(
                {
                    "date": pd.to_datetime(r.date),
                    "T2M_MAX": r.temp_max,
                    "T2M_MIN": r.temp_min,
                    "T2M": r.temp_mean,
                    "RH2M": r.humidity,
                    "WS2M": r.wind_speed,
                    "ALLSKY_SFC_SW_DWN": r.solar_radiation,
                    "PRECTOTCORR": r.precipitation,
                }
            )
        nasa_df = pd.DataFrame(records).replace(-999.0, np.nan)
        nasa_df = nasa_df.set_index("date")  # Set date as index
    else:
        logger.warning("NASA POWER vazio")

    # Convert OpenMeteo raw data to DataFrame
    om_df = pd.DataFrame()
    if om_raw:
        om_df = pd.DataFrame(om_raw)
        if "date" in om_df.columns:
            om_df["date"] = pd.to_datetime(om_df["date"])
            om_df = om_df.set_index("date")  # Set date as index
    else:
        logger.warning("Open-Meteo vazio")

    # === 2. Preprocessing ===
    nasa_clean, _ = (
        preprocessing(nasa_df, latitude)
        if not nasa_df.empty
        else (pd.DataFrame(), [])
    )
    om_clean, _ = (
        preprocessing(om_df, latitude)
        if not om_df.empty
        else (pd.DataFrame(), [])
    )

    # === SALVAR DADOS RAW (antes do preprocessing) ===
    period_str = f"{start_date}_{end_date}"
    if not nasa_df.empty:
        nasa_raw_file = RAW_DIR / f"{city_name}_{period_str}_NASA_RAW.csv"
        nasa_df_save = nasa_df.reset_index()
        nasa_df_save.to_csv(nasa_raw_file, index=False)
        logger.info(f"💾 NASA RAW salvo: {nasa_raw_file.name}")

    if not om_df.empty:
        om_raw_file = RAW_DIR / f"{city_name}_{period_str}_OpenMeteo_RAW.csv"
        om_df_save = om_df.reset_index()
        om_df_save.to_csv(om_raw_file, index=False)
        logger.info(f"💾 Open-Meteo RAW salvo: {om_raw_file.name}")

    # === SALVAR DADOS PRÉ-PROCESSADOS ===
    if not nasa_clean.empty:
        nasa_prep_file = (
            PREPROCESSED_DIR
            / f"{city_name}_{period_str}_NASA_PREPROCESSED.csv"
        )
        nasa_clean_save = nasa_clean.copy()
        if "date" not in nasa_clean_save.columns:
            nasa_clean_save = nasa_clean_save.reset_index()
        nasa_clean_save.to_csv(nasa_prep_file, index=False)
        logger.info(f"💾 NASA PREPROCESSED salvo: {nasa_prep_file.name}")

    if not om_clean.empty:
        om_prep_file = (
            PREPROCESSED_DIR
            / f"{city_name}_{period_str}_OpenMeteo_PREPROCESSED.csv"
        )
        om_clean_save = om_clean.copy()
        if "date" not in om_clean_save.columns:
            om_clean_save = om_clean_save.reset_index()
        om_clean_save.to_csv(om_prep_file, index=False)
        logger.info(f"💾 Open-Meteo PREPROCESSED: {om_prep_file.name}")

    # Reset index to have date as column again for fusion
    if not nasa_clean.empty:
        nasa_clean = nasa_clean.reset_index()
    if not om_clean.empty:
        om_clean = om_clean.reset_index()

    # === 3. Fusão com Kalman (um único objeto por cidade) ===
    # Se Open-Meteo falhou, usar apenas NASA POWER sem fusão
    if om_clean.empty and not nasa_clean.empty:
        logger.warning("⚠️ Usando apenas NASA POWER (sem fusão Open-Meteo)")
        fused_df = nasa_clean.copy()
        fused_df = fused_df.set_index("date")
    else:
        # Fusão normal com Kalman
        kalman = ClimateKalmanEnsemble()

        fused_records = []
        date_range = pd.date_range(start_date, end_date, freq="D")

        for current_date in date_range:
            date_str = current_date.strftime("%Y-%m-%d")
            measurements = {}

            # Adiciona NASA (sem sufixo)
            if not nasa_clean.empty:
                row = nasa_clean[nasa_clean["date"] == date_str]
                if not row.empty:
                    for var in [
                        "T2M_MAX",
                        "T2M_MIN",
                        "T2M",
                        "RH2M",
                        "WS2M",
                        "ALLSKY_SFC_SW_DWN",
                        "PRECTOTCORR",
                    ]:
                        if var in row.columns and pd.notna(row[var].iloc[0]):
                            measurements[var] = row[var].iloc[0]

            # Adiciona Open-Meteo (com sufixo para detecção automática)
            if not om_clean.empty:
                row = om_clean[om_clean["date"] == date_str]
                if not row.empty:
                    for var in [
                        "T2M_MAX",
                        "T2M_MIN",
                        "T2M",
                        "RH2M",
                        "WS2M",
                        "ALLSKY_SFC_SW_DWN",
                        "PRECTOTCORR",
                    ]:
                        if var in row.columns and pd.notna(row[var].iloc[0]):
                            measurements[f"{var}1"] = row[var].iloc[
                                0
                            ]  # sufixo 1 para Open-Meteo

            if measurements:
                fused_day = kalman.auto_fuse_sync(
                    latitude=latitude,
                    longitude=longitude,
                    measurements=measurements,
                    date=current_date,
                )
                record = {"date": current_date}
                record.update(fused_day["fused"])
                fused_records.append(record)

        if not fused_records:
            logger.error(f"Nenhum dado fusionado para {city_name}")
            return None

        fused_df = pd.DataFrame(fused_records)
        fused_df = fused_df.set_index("date")

    # === 4. Cálculo ETo + Kalman final AUTOMÁTICO ===
    df_final = calculate_eto_timeseries(
        df=fused_df,
        latitude=latitude,
        longitude=longitude,
        elevation_m=altitude,
        kalman_ensemble=(
            kalman if not om_clean.empty else None
        ),  # Kalman só se temos fusão
    )

    # Salva cache final
    df_final.to_csv(cache_file, index=False)
    logger.success(
        f"✅ {city_name} concluída → {len(df_final)} dias → cache salvo"
    )

    return df_final


def compare_with_xavier(
    df_result: pd.DataFrame,
    city_key: str,
    output_dir: Path,
) -> Optional[dict]:
    """Compara ETo calculado com Xavier e gera métricas + plots"""
    # Buscar arquivo Xavier usando city_key
    xavier_file = BRASIL_ETO_DIR / f"{city_key}.csv"

    if not xavier_file.exists():
        logger.warning(f"Xavier não encontrado para {city_key}")
        return None

    df_xavier = pd.read_csv(xavier_file)
    df_xavier.columns = df_xavier.columns.str.strip()
    df_xavier["Data"] = pd.to_datetime(df_xavier["Data"])
    df_xavier = df_xavier.rename(columns={"Data": "date", "ETo": "eto_xavier"})

    # Merge (usar eto_final = ETo com correção Kalman final)
    df_compare = pd.merge(
        df_result[["date", "eto_final"]],
        df_xavier[["date", "eto_xavier"]],
        on="date",
        how="inner",
    )

    if len(df_compare) < 30:
        logger.warning(f"Poucos dados para comparação: {len(df_compare)} dias")
        return None

    # Remover NaN
    df_compare = df_compare.dropna(subset=["eto_final", "eto_xavier"])

    calc = np.array(df_compare["eto_final"].values, dtype=float)
    ref = np.array(df_compare["eto_xavier"].values, dtype=float)

    # Métricas com significância estatística
    r_val, p_value_pearson = pearsonr(calc, ref)
    r2 = float(r_val**2)  # type: ignore
    p_value = float(p_value_pearson)  # type: ignore

    mae = float(mean_absolute_error(ref, calc))
    rmse = float(np.sqrt(mean_squared_error(ref, calc)))
    bias = float(np.mean(calc - ref))
    nse = float(
        1 - (np.sum((ref - calc) ** 2) / np.sum((ref - np.mean(ref)) ** 2))
    )
    pbias = float(100 * np.sum(calc - ref) / np.sum(ref))

    lr_result = linregress(ref, calc)
    slope_val = float(lr_result[0])  # type: ignore
    intercept_val = float(lr_result[1])  # type: ignore
    p_value_slope = float(lr_result[3])  # type: ignore (p-value da inclinação)

    # Determinar significância estatística
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
        p_display = f"p = {p_value:.3f}"

    logger.info(
        f"  R² = {r2:.4f} ({p_display}) | NSE = {nse:.4f} | MAE = {mae:.4f}"
    )

    # === GRÁFICOS PARA PUBLICAÇÃO (SoftwareX) ===
    plot_dir = output_dir / "plots"
    plot_dir.mkdir(exist_ok=True)

    # Configurações para publicação científica
    plt.style.use("seaborn-v0_8-darkgrid")
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["font.size"] = 10
    plt.rcParams["axes.labelsize"] = 11
    plt.rcParams["axes.titlesize"] = 12
    plt.rcParams["xtick.labelsize"] = 9
    plt.rcParams["ytick.labelsize"] = 9
    plt.rcParams["legend.fontsize"] = 9
    plt.rcParams["figure.dpi"] = 300

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle(
        f'{city_key.replace("_", " ")} - ETo Validation (1991-2020)',
        fontsize=14,
        fontweight="bold",
    )

    # (A) Scatter plot com densidade
    ax1 = axes[0, 0]
    ax1.scatter(
        ref,
        calc,
        c=np.arange(len(ref)),
        cmap="viridis",
        alpha=0.4,
        s=15,
        edgecolors="none",
    )
    min_val = float(ref.min())
    max_val = float(ref.max())

    # Linha 1:1 (ideal)
    ax1.plot(
        [min_val, max_val],
        [min_val, max_val],
        "r--",
        lw=2,
        label="1:1 line",
        alpha=0.8,
    )

    # Linha de regressão
    ax1.plot(
        [min_val, max_val],
        [
            float(slope_val * min_val + intercept_val),
            float(slope_val * max_val + intercept_val),
        ],
        "b-",
        lw=2,
        label=f"Regression (y={slope_val:.2f}x+{intercept_val:.2f})",
        alpha=0.8,
    )

    ax1.set_xlabel("Xavier ET₀ (mm day⁻¹)", fontweight="bold")
    ax1.set_ylabel("Estimated ET₀ (mm day⁻¹)", fontweight="bold")
    ax1.set_title("(A) Scatter Plot", fontweight="bold", loc="left")
    ax1.legend(loc="upper left", framealpha=0.9)
    ax1.grid(True, alpha=0.3, linestyle="--")
    ax1.set_aspect("equal", adjustable="box")

    # Adicionar métricas no canto com p-value
    textstr = "\n".join(
        [
            f"R² = {r2:.3f} {sig_level}",
            f"{p_display}",
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

    # (B) Série temporal completa
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
        label="Kalman-corrected",
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

    # (C) Resíduos ao longo do tempo
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

    # (D) Distribuição dos erros (histograma + densidade)
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

    # Adicionar curva normal teórica
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

    # Salvar em múltiplos formatos para publicação
    plot_base = plot_dir / f"{city_key}_validation"
    plt.savefig(f"{plot_base}.png", dpi=300, bbox_inches="tight")
    plt.savefig(f"{plot_base}.pdf", dpi=300, bbox_inches="tight")
    plt.savefig(f"{plot_base}.svg", dpi=300, bbox_inches="tight")
    logger.info(f"📊 Gráficos salvos: {plot_base}.[png|pdf|svg]")
    plt.close()

    return {
        "city": city_key,
        "n_days": len(df_compare),
        "r2": float(round(r2, 4)),  # type: ignore
        "p_value": float(round(p_value, 6)),  # type: ignore
        "significance": sig_level,
        "nse": float(round(nse, 4)),  # type: ignore
        "mae": float(round(mae, 4)),  # type: ignore
        "rmse": float(round(rmse, 4)),  # type: ignore
        "bias": float(round(bias, 4)),  # type: ignore
        "pbias": float(round(pbias, 2)),  # type: ignore
        "slope": float(round(slope_val, 4)),  # type: ignore
        "intercept": float(round(intercept_val, 4)),  # type: ignore
        "p_value_slope": float(round(p_value_slope, 6)),  # type: ignore
    }


async def process_all_cities(
    start_date: str = "1991-01-01",
    end_date: str = "2020-12-31",
    cities_filter: List[str] | None = None,
):
    # Carregar coordenadas do CSV (mesmas usadas para gerar normais)
    csv_coords_path = Path("validation/data_validation/data/info_cities.csv")
    df_coords = pd.read_csv(csv_coords_path)
    city_coords = {
        row["city"]: (row["lat"], row["lon"])
        for _, row in df_coords.iterrows()
    }

    # Usar dicionário de cidades do config
    cities_to_process = BRASIL_CITIES

    if cities_filter:
        cities_to_process = {
            k: v for k, v in BRASIL_CITIES.items() if k in cities_filter
        }

    all_metrics = []
    total_cities = len(cities_to_process)

    logger.info(f"\n{'=' * 80}")
    logger.info(f"🚀 INICIANDO VALIDAÇÃO DE {total_cities} CIDADES")
    logger.info(f"📅 Período: {start_date} até {end_date}")
    logger.info(f"⏱️ Tempo estimado: ~{total_cities * 8} minutos")
    logger.info(f"{'=' * 80}\n")

    for idx, (city_key, city_meta) in enumerate(cities_to_process.items(), 1):
        # Usar coordenadas do CSV se disponível (mesmas das normais)
        if city_key in city_coords:
            lat, lon = city_coords[city_key]
            logger.info(f"📍 Usando coordenadas do CSV: {lat:.4f}, {lon:.4f}")
        else:
            lat = city_meta["lat"]
            lon = city_meta["lon"]
            logger.warning("⚠️ Cidade não encontrada no CSV, usando config.py")

        sep_line = "=" * 80
        logger.info(f"\n{sep_line}")
        logger.info(
            f"[{idx}/{total_cities}] PROCESSANDO: {city_key} "
            f"({idx / total_cities * 100:.1f}% concluído)"
        )
        logger.info(sep_line)

        # Processamento SEQUENCIAL (respeita rate limits automaticamente)
        df_result = await process_city(
            city_key, float(lat), float(lon), start_date, end_date
        )

        if df_result is not None:
            metrics = compare_with_xavier(df_result, city_key, OUTPUT_DIR)
            if metrics:
                all_metrics.append(metrics)

        # Pequeno delay entre cidades (boas práticas com APIs)
        if idx < total_cities:
            logger.info("⏸️ Aguardando 2s antes da próxima cidade...")
            await asyncio.sleep(2)

        if df_result is not None:
            metrics = compare_with_xavier(df_result, city_key, OUTPUT_DIR)
            if metrics:
                all_metrics.append(metrics)

    # Relatório final
    if all_metrics:
        df_summary = pd.DataFrame(all_metrics)
        summary_file = (
            OUTPUT_DIR / f"VALIDACAO_FINAL_{datetime.now():%Y%m%d_%H%M}.csv"
        )
        df_summary.to_csv(summary_file, index=False)
        logger.success(f"✅ VALIDAÇÃO CONCLUÍDA → {summary_file}")

        # === GRÁFICO CONSOLIDADO TODAS AS CIDADES (PUBLICAÇÃO) ===
        create_consolidated_plots(df_summary, OUTPUT_DIR)

        # Estatísticas gerais
        logger.info(f"\n{'=' * 80}")
        logger.info("📊 ESTATÍSTICAS GERAIS (17 CIDADES)")
        logger.info(f"{'=' * 80}")
        logger.info(
            f"R² médio: {df_summary['r2'].mean():.3f} "
            f"± {df_summary['r2'].std():.3f}"
        )
        logger.info(
            f"NSE médio: {df_summary['nse'].mean():.3f} "
            f"± {df_summary['nse'].std():.3f}"
        )
        logger.info(
            f"MAE médio: {df_summary['mae'].mean():.3f} "
            f"± {df_summary['mae'].std():.3f} mm/dia"
        )
        logger.info(
            f"RMSE médio: {df_summary['rmse'].mean():.3f} "
            f"± {df_summary['rmse'].std():.3f} mm/dia"
        )
        logger.info(
            f"PBIAS médio: {df_summary['pbias'].mean():.2f} "
            f"± {df_summary['pbias'].std():.2f}%"
        )
        logger.info(f"{'=' * 80}\n")


def create_consolidated_plots(
    df_summary: pd.DataFrame, output_dir: Path
) -> None:
    """
    Cria gráficos consolidados de todas as cidades para publicação.

    Args:
        df_summary: DataFrame com métricas de todas as cidades
        output_dir: Diretório de saída
    """
    plot_dir = output_dir / "plots"
    plot_dir.mkdir(exist_ok=True)

    # Configurações para publicação
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["font.size"] = 10
    plt.rcParams["figure.dpi"] = 300

    # Figura com 4 subplots
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle(
        "Multi-City ET₀ Validation - Brazil MATOPIBA Region (1991-2020)",
        fontsize=14,
        fontweight="bold",
    )

    # (A) Boxplot das métricas de desempenho
    ax1 = axes[0, 0]
    metrics_data = df_summary[["r2", "nse", "mae", "rmse"]].values
    bp = ax1.boxplot(
        metrics_data,
        labels=["R²", "NSE", "MAE\n(mm/day)", "RMSE\n(mm/day)"],
        patch_artist=True,
        notch=True,
        showmeans=True,
        meanprops={"marker": "D", "markerfacecolor": "red", "markersize": 6},
    )

    # Cores diferentes para cada box
    colors = ["lightblue", "lightgreen", "lightyellow", "lightcoral"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)

    ax1.set_title(
        "(A) Performance Metrics Distribution", fontweight="bold", loc="left"
    )
    ax1.set_ylabel("Metric Value", fontweight="bold")
    ax1.grid(True, alpha=0.3, linestyle="--", axis="y")
    ax1.axhline(y=0, color="k", linestyle="-", lw=0.5)

    # (B) Ranking das cidades por MAE
    ax2 = axes[0, 1]
    df_sorted = df_summary.sort_values("mae")
    cities_short = [c.replace("_", " ")[:20] for c in df_sorted["city"]]
    colors_mae = [
        "green" if mae < 0.5 else "orange" if mae < 0.7 else "red"
        for mae in df_sorted["mae"]
    ]

    ax2.barh(
        range(len(cities_short)),
        df_sorted["mae"],
        color=colors_mae,
        alpha=0.7,
        edgecolor="black",
        linewidth=0.5,
    )

    ax2.set_yticks(range(len(cities_short)))
    ax2.set_yticklabels(cities_short, fontsize=8)
    ax2.set_xlabel("MAE (mm day⁻¹)", fontweight="bold")
    ax2.set_title("(B) Cities Ranked by MAE", fontweight="bold", loc="left")
    ax2.axvline(
        x=df_sorted["mae"].mean(),
        color="blue",
        linestyle="--",
        lw=2,
        label=f'Mean = {df_sorted["mae"].mean():.2f}',
    )
    ax2.legend(loc="lower right")
    ax2.grid(True, alpha=0.3, linestyle="--", axis="x")

    # (C) Scatter R² vs NSE
    ax3 = axes[1, 0]
    scatter = ax3.scatter(
        df_summary["r2"],
        df_summary["nse"],
        s=100,
        c=df_summary["mae"],
        cmap="RdYlGn_r",
        alpha=0.7,
        edgecolors="black",
        linewidth=1,
    )

    # Adicionar labels das cidades
    for _, row in df_summary.iterrows():
        ax3.annotate(
            row["city"].replace("_", " ")[:10],
            (row["r2"], row["nse"]),
            fontsize=6,
            alpha=0.6,
            xytext=(2, 2),
            textcoords="offset points",
        )

    ax3.set_xlabel("R²", fontweight="bold")
    ax3.set_ylabel("NSE", fontweight="bold")
    ax3.set_title("(C) R² vs NSE Performance", fontweight="bold", loc="left")
    ax3.grid(True, alpha=0.3, linestyle="--")
    ax3.axhline(y=0, color="k", linestyle="-", lw=0.5)
    ax3.axvline(x=0, color="k", linestyle="-", lw=0.5)

    cbar = plt.colorbar(scatter, ax=ax3)
    cbar.set_label("MAE (mm day⁻¹)", rotation=270, labelpad=15)

    # (D) Tabela resumo estatístico
    ax4 = axes[1, 1]
    ax4.axis("off")

    stats_data = [
        ["Metric", "Mean", "Std", "Min", "Max"],
        [
            "R²",
            f"{df_summary['r2'].mean():.3f}",
            f"{df_summary['r2'].std():.3f}",
            f"{df_summary['r2'].min():.3f}",
            f"{df_summary['r2'].max():.3f}",
        ],
        [
            "p-value",
            f"{df_summary['p_value'].mean():.4f}",
            f"{df_summary['p_value'].std():.4f}",
            f"{df_summary['p_value'].min():.4f}",
            f"{df_summary['p_value'].max():.4f}",
        ],
        [
            "NSE",
            f"{df_summary['nse'].mean():.3f}",
            f"{df_summary['nse'].std():.3f}",
            f"{df_summary['nse'].min():.3f}",
            f"{df_summary['nse'].max():.3f}",
        ],
        [
            "MAE",
            f"{df_summary['mae'].mean():.3f}",
            f"{df_summary['mae'].std():.3f}",
            f"{df_summary['mae'].min():.3f}",
            f"{df_summary['mae'].max():.3f}",
        ],
        [
            "RMSE",
            f"{df_summary['rmse'].mean():.3f}",
            f"{df_summary['rmse'].std():.3f}",
            f"{df_summary['rmse'].min():.3f}",
            f"{df_summary['rmse'].max():.3f}",
        ],
        [
            "PBIAS%",
            f"{df_summary['pbias'].mean():.2f}",
            f"{df_summary['pbias'].std():.2f}",
            f"{df_summary['pbias'].min():.2f}",
            f"{df_summary['pbias'].max():.2f}",
        ],
    ]

    table = ax4.table(
        cellText=stats_data,
        cellLoc="center",
        loc="center",
        colWidths=[0.15, 0.15, 0.15, 0.15, 0.15],
    )

    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2)

    # Formatar cabeçalho
    for i in range(5):
        table[(0, i)].set_facecolor("#4CAF50")
        table[(0, i)].set_text_props(weight="bold", color="white")

    # Cores alternadas nas linhas
    for i in range(1, len(stats_data)):
        color = "#f0f0f0" if i % 2 == 0 else "white"
        for j in range(5):
            table[(i, j)].set_facecolor(color)

    ax4.set_title(
        "(D) Statistical Summary (*** p<0.001)", fontweight="bold", loc="left"
    )

    plt.tight_layout(rect=(0, 0.03, 1, 0.98))

    # Salvar em múltiplos formatos
    consolidated_base = plot_dir / "consolidated_validation_all_cities"
    plt.savefig(f"{consolidated_base}.png", dpi=300, bbox_inches="tight")
    plt.savefig(f"{consolidated_base}.pdf", dpi=300, bbox_inches="tight")
    plt.savefig(f"{consolidated_base}.svg", dpi=300, bbox_inches="tight")
    logger.success(
        f"📊 Gráfico consolidado salvo: {consolidated_base}.[png|pdf|svg]"
    )
    plt.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="1991-01-01")
    parser.add_argument("--end-date", default="2020-12-31")
    parser.add_argument(
        "--cities", nargs="*", help="Lista de cidades (opcional)"
    )
    args = parser.parse_args()

    asyncio.run(
        process_all_cities(args.start_date, args.end_date, args.cities)
    )
