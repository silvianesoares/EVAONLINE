"""
Calcula ETo usando FUSÃO KALMAN (EVAOnline) dos dados brutos
Segue o pipeline completo: TopoData → Preprocessing → Fusão Kalman → ETo
Para comparação com Xavier, NASA POWER e Open-Meteo
"""

import sys
from pathlib import Path
import pandas as pd
from loguru import logger

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from validation.config import VALIDATION_DIR
from validation_logic_eto.api.services.opentopo.opentopo_sync_adapter import (
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

# Paths
NASA_DIR = VALIDATION_DIR / "results/brasil/raw_data/nasa_power"
OPENMETEO_DIR = VALIDATION_DIR / "results/brasil/raw_data/open_meteo"
OUTPUT_DIR = VALIDATION_DIR / "results/brasil/raw_data/evaonline"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# CSV com coordenadas
CITIES_CSV = VALIDATION_DIR / "data_validation/data/info_cities.csv"


def calculate_eto_evaonline(city_name: str) -> None:
    """Calcula ETo usando fusão Kalman (EVAOnline)."""

    logger.info(f"⚡ Processando {city_name} (EVAOnline - Fusão Kalman)...")

    # Buscar arquivos NASA e Open-Meteo RAW
    nasa_files = list(NASA_DIR.glob(f"{city_name}_*_NASA_RAW.csv"))
    om_files = list(OPENMETEO_DIR.glob(f"{city_name}_*_OpenMeteo_RAW.csv"))

    if not nasa_files:
        logger.warning(f"❌ Arquivo NASA não encontrado: {city_name}")
        return

    if not om_files:
        logger.warning(f"❌ Arquivo Open-Meteo não encontrado: {city_name}")
        return

    nasa_file = nasa_files[0]
    om_file = om_files[0]
    logger.info(f"📂 NASA: {nasa_file.name}")
    logger.info(f"📂 Open-Meteo: {om_file.name}")

    # Carregar dados brutos
    df_nasa = pd.read_csv(nasa_file, parse_dates=["date"], index_col="date")
    df_om = pd.read_csv(om_file, parse_dates=["date"], index_col="date")

    # Converter vento de 10m para 2m se necessário (usando perfil logarítmico)
    if "wind_speed_10m_mean" in df_om.columns:
        logger.info(
            "🌪️  Convertendo vento de 10m para 2m (perfil logarítmico)..."
        )
        # Fórmula FAO-56: u2 = u_z * (4.87 / ln(67.8*z - 5.42))
        # Para z=10m: u2 = u10 * (4.87 / ln(672.8)) = u10 * 0.748
        df_om["wind_speed_2m_mean"] = df_om["wind_speed_10m_mean"] * 0.748
        df_om = df_om.drop(columns=["wind_speed_10m_mean"])

    # Renomear colunas Open-Meteo para padrão NASA/preprocessing
    column_mapping = {
        "temperature_2m_max": "T2M_MAX",
        "temperature_2m_min": "T2M_MIN",
        "temperature_2m_mean": "T2M",
        "relative_humidity_2m_mean": "RH2M",
        "wind_speed_2m_mean": "WS2M",
        "shortwave_radiation_sum": "ALLSKY_SFC_SW_DWN",
        "precipitation_sum": "PRECTOTCORR",
    }
    df_om = df_om.rename(columns=column_mapping)

    # Buscar coordenadas e altitude
    cities_df = pd.read_csv(CITIES_CSV)
    city_info = cities_df[cities_df["city"] == city_name]

    if city_info.empty:
        logger.warning(f"❌ Cidade {city_name} não encontrada no CSV")
        return

    lat = float(city_info["lat"].iloc[0])
    lon = float(city_info["lon"].iloc[0])

    logger.info(f"📍 Coordenadas: {lat:.4f}, {lon:.4f}")

    # === 1. Buscar elevação via TopoData ===
    topo = OpenTopoSyncAdapter()
    try:
        altitude_result = topo.get_elevation_sync(lat, lon)
        if hasattr(altitude_result, "elevation"):
            altitude = float(altitude_result.elevation)
        elif isinstance(altitude_result, (int, float)):
            altitude = float(altitude_result)
        else:
            altitude = float(city_info["alt"].iloc[0])
        logger.info(f"🏔️  Elevação TopoData: {altitude:.1f}m")
    except Exception as e:
        logger.warning(f"⚠️  TopoData falhou: {e}, usando altitude do CSV")
        altitude = float(city_info["alt"].iloc[0])

    # === 2. Preprocessing ===
    logger.info(
        "🔧 Preprocessing NASA POWER (limites Brasil - Xavier et al.)..."
    )
    nasa_clean, _ = preprocessing(df_nasa, lat, region="brazil")

    logger.info(
        "🔧 Preprocessing Open-Meteo (limites Brasil - Xavier et al.)..."
    )
    om_clean, _ = preprocessing(df_om, lat, region="brazil")

    if nasa_clean.empty or om_clean.empty:
        logger.warning(f"❌ Preprocessing falhou para {city_name}")
        return

    # Reset index para fusão
    nasa_clean = nasa_clean.reset_index()
    om_clean = om_clean.reset_index()

    # === 3. Fusão Kalman (método correto: auto_fuse_sync) ===
    logger.info("🔀 Aplicando Fusão Kalman...")
    kalman = ClimateKalmanEnsemble()

    fused_records = []
    start_date = pd.to_datetime("1991-01-01")
    end_date = pd.to_datetime("2020-12-31")
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

        # Adiciona Open-Meteo (com sufixo 1)
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
                        measurements[f"{var}1"] = row[var].iloc[0]

        if measurements:
            fused_day = kalman.auto_fuse_sync(
                latitude=lat,
                longitude=lon,
                measurements=measurements,
                date=current_date,
            )
            record = {"date": current_date}
            record.update(fused_day["fused"])
            fused_records.append(record)

    if not fused_records:
        logger.warning(f"❌ Nenhum dado fusionado para {city_name}")
        return

    fused_df = pd.DataFrame(fused_records)
    fused_df = fused_df.set_index("date")

    # === 4. Cálculo ETo com Kalman final ===
    logger.info("📊 Calculando ETo com Kalman final...")
    df_eto = calculate_eto_timeseries(
        df=fused_df,
        latitude=lat,
        longitude=lon,
        elevation_m=altitude,
        kalman_ensemble=kalman,
    )

    if df_eto.empty or "eto_final" not in df_eto.columns:
        logger.warning(f"❌ Cálculo ETo falhou para {city_name}")
        return

    # Salvar resultado
    output_file = OUTPUT_DIR / f"{city_name}_ETo_EVAOnline.csv"
    df_result = df_eto[["date", "eto_final"]].copy()
    df_result.columns = ["date", "eto_evaonline"]
    df_result.to_csv(output_file, index=False)

    # Estatísticas
    mean_eto = df_result["eto_evaonline"].mean()
    logger.success(
        f"✅ {city_name}: ETo médio = {mean_eto:.2f} mm/dia "
        f"({len(df_result)} dias) → {output_file.name}"
    )


def process_all_cities():
    """Processa todas as cidades com fusão Kalman."""

    logger.info("=" * 80)
    logger.info("🚀 CALCULANDO ETo COM FUSÃO KALMAN (EVAONLINE)")
    logger.info("=" * 80)

    # Listar cidades que têm AMBOS os arquivos (NASA + Open-Meteo)
    nasa_files = list(NASA_DIR.glob("*_NASA_RAW.csv"))
    om_files = list(OPENMETEO_DIR.glob("*_OpenMeteo_RAW.csv"))

    nasa_cities = {f.stem.split("_1991")[0] for f in nasa_files}
    om_cities = {f.stem.split("_1991")[0] for f in om_files}

    # Intersecção: cidades com ambas as fontes
    cities = sorted(nasa_cities & om_cities)

    logger.info(f"📊 {len(cities)} cidades com NASA + Open-Meteo")

    for idx, city in enumerate(cities, 1):
        logger.info(f"\n[{idx}/{len(cities)}] {city}")
        try:
            calculate_eto_evaonline(city)
        except Exception as e:
            logger.error(f"❌ Erro em {city}: {e}")
            continue

    logger.info("\n" + "=" * 80)
    logger.success(f"✅ Processamento concluído! Arquivos em: {OUTPUT_DIR}")
    logger.info("=" * 80)


if __name__ == "__main__":
    process_all_cities()
