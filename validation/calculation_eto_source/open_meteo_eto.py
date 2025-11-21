"""
Calcula ETo usando SOMENTE dados Open-Meteo Archive (sem fusão)
Para comparação com Xavier, NASA POWER e EVAOnline
"""

import sys
from pathlib import Path
import pandas as pd
from loguru import logger

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from validation.config import VALIDATION_DIR
from validation_logic_eto.core.eto_calculation.eto_services import (
    calculate_eto_timeseries,
)
from validation_logic_eto.core.data_processing.data_preprocessing import (
    preprocessing,
)

# Paths
RAW_DATA_DIR = VALIDATION_DIR / "results/brasil/raw_data/open_meteo"
OUTPUT_DIR = RAW_DATA_DIR / "eto_open_meteo"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# CSV com coordenadas
CITIES_CSV = VALIDATION_DIR / "data_validation/data/info_cities.csv"


def calculate_eto_open_meteo(city_name: str) -> None:
    """Calcula ETo usando apenas Open-Meteo Archive."""

    logger.info(f"🌦️  Processando {city_name} (Open-Meteo Archive)...")

    # Buscar arquivo Open-Meteo RAW
    om_files = list(RAW_DATA_DIR.glob(f"{city_name}_*_OpenMeteo_RAW.csv"))
    if not om_files:
        logger.warning(f"❌ Arquivo Open-Meteo não encontrado: {city_name}")
        return

    om_file = om_files[0]
    logger.info(f"📂 Carregando: {om_file.name}")

    # Carregar dados brutos
    df_om = pd.read_csv(om_file)

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

    # Converter date para datetime e definir como index
    df_om["date"] = pd.to_datetime(df_om["date"])
    df_om = df_om.set_index("date")

    # Log de dados disponíveis
    logger.info(f"📊 Dados carregados: {len(df_om)} dias")
    for col in [
        "T2M_MAX",
        "T2M_MIN",
        "T2M",
        "RH2M",
        "WS2M",
        "ALLSKY_SFC_SW_DWN",
    ]:
        if col in df_om.columns:
            valid_count = df_om[col].notna().sum()
            logger.info(f"  {col}: {valid_count}/{len(df_om)} válidos")

    # Buscar coordenadas e altitude
    cities_df = pd.read_csv(CITIES_CSV)

    # Tentar buscar com nome completo primeiro, depois com prefixo
    city_info = cities_df[cities_df["city"] == city_name]
    if city_info.empty:
        # Tentar extrair prefixo (ex: Barreiras_BA_TO -> Barreiras_BA)
        city_base = "_".join(city_name.split("_")[:2])
        city_info = cities_df[cities_df["city"] == city_base]

    if city_info.empty:
        logger.warning(f"❌ Cidade {city_name} não encontrada no CSV")
        return

    lat = float(city_info["lat"].iloc[0])
    lon = float(city_info["lon"].iloc[0])
    alt = float(city_info["alt"].iloc[0])

    logger.info(f"📍 Coordenadas: {lat:.4f}, {lon:.4f}, {alt:.1f}m")

    # Preprocessing Open-Meteo (retorna tupla)
    df_prep, warnings = preprocessing(
        weather_df=df_om,
        latitude=lat,
    )

    if warnings:
        for warning in warnings:
            logger.warning(f"⚠️  {warning}")

    if df_prep.empty:
        logger.warning(f"❌ Preprocessing falhou para {city_name}")
        return

    # Calcular ETo usando FAO-56 Penman-Monteith
    df_eto = calculate_eto_timeseries(
        df=df_prep,
        latitude=lat,
        longitude=lon,
        elevation_m=alt,
    )

    if df_eto.empty or "eto_final" not in df_eto.columns:
        logger.warning(f"❌ Cálculo ETo falhou para {city_name}")
        return

    # Salvar resultado
    output_file = OUTPUT_DIR / f"{city_name}_ETo_OpenMeteo.csv"
    df_result = df_eto[["date", "eto_final"]].copy()
    df_result.columns = ["date", "eto_openmeteo"]
    df_result.to_csv(output_file, index=False)

    # Estatísticas
    mean_eto = df_result["eto_openmeteo"].mean()
    logger.success(
        f"✅ {city_name}: ETo médio = {mean_eto:.2f} mm/dia "
        f"({len(df_result)} dias) → {output_file.name}"
    )


def process_all_cities():
    """Processa todas as cidades com dados Open-Meteo Archive."""

    logger.info("=" * 80)
    logger.info("🚀 CALCULANDO ETo USANDO OPEN-METEO ARCHIVE (SEM FUSÃO)")
    logger.info("=" * 80)

    # Listar todos os arquivos Open-Meteo RAW
    om_files = list(RAW_DATA_DIR.glob("*_OpenMeteo_RAW.csv"))
    cities = [f.stem.split("_1991")[0] for f in om_files]
    cities = sorted(set(cities))

    logger.info(f"📊 {len(cities)} cidades encontradas")

    for idx, city in enumerate(cities, 1):
        logger.info(f"\n[{idx}/{len(cities)}] {city}")
        try:
            calculate_eto_open_meteo(city)
        except Exception as e:
            logger.error(f"❌ Erro em {city}: {e}")
            continue

    logger.info("\n" + "=" * 80)
    logger.success(f"✅ Processamento concluído! Arquivos em: {OUTPUT_DIR}")
    logger.info("=" * 80)


if __name__ == "__main__":
    process_all_cities()
