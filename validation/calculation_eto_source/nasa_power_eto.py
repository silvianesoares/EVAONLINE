"""
Calcula ETo usando SOMENTE dados NASA POWER (sem fusão)
Para comparação com Xavier, Open-Meteo e EVAOnline
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
# validation/results/brasil/raw_data/nasa_power
RAW_DATA_DIR = VALIDATION_DIR / "results/brasil/raw_data/nasa_power"
# validation\results\brasil\raw_data\nasa_power\eto_nasa_power
OUTPUT_DIR = RAW_DATA_DIR / "eto_nasa_power"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# CSV com coordenadas
CITIES_CSV = VALIDATION_DIR / "data_validation/data/info_cities.csv"


def calculate_eto_nasa_power(city_name: str) -> None:
    """Calcula ETo usando apenas NASA POWER."""

    logger.info(f"🛰️  Processando {city_name} (NASA POWER)...")

    # Buscar arquivo NASA RAW
    nasa_files = list(RAW_DATA_DIR.glob(f"{city_name}_*_NASA_RAW.csv"))
    if not nasa_files:
        logger.warning(f"❌ Arquivo NASA não encontrado: {city_name}")
        return

    nasa_file = nasa_files[0]
    logger.info(f"📂 Carregando: {nasa_file.name}")

    # Carregar dados brutos
    df_nasa = pd.read_csv(nasa_file)

    # Converter date para datetime e definir como index
    df_nasa["date"] = pd.to_datetime(df_nasa["date"])
    df_nasa = df_nasa.set_index("date")

    # Buscar coordenadas e altitude
    cities_df = pd.read_csv(CITIES_CSV)
    city_info = cities_df[cities_df["city"] == city_name]

    if city_info.empty:
        logger.warning(f"❌ Cidade {city_name} não encontrada no CSV")
        return

    lat = float(city_info["lat"].iloc[0])
    lon = float(city_info["lon"].iloc[0])
    alt = float(city_info["alt"].iloc[0])

    logger.info(f"📍 Coordenadas: {lat:.4f}, {lon:.4f}, {alt:.1f}m")

    # Preprocessing NASA POWER (retorna tupla)
    df_prep, warnings = preprocessing(
        weather_df=df_nasa,
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
    output_file = OUTPUT_DIR / f"{city_name}_ETo_NASA.csv"
    df_result = df_eto[["date", "eto_final"]].copy()
    df_result.columns = ["date", "eto_nasa"]
    df_result.to_csv(output_file, index=False)

    # Estatísticas
    mean_eto = df_result["eto_nasa"].mean()
    logger.success(
        f"✅ {city_name}: ETo médio = {mean_eto:.2f} mm/dia "
        f"({len(df_result)} dias) → {output_file.name}"
    )


def process_all_cities():
    """Processa todas as cidades com dados NASA POWER."""

    logger.info("=" * 80)
    logger.info("🚀 CALCULANDO ETo USANDO NASA POWER (SEM FUSÃO)")
    logger.info("=" * 80)

    # Listar todos os arquivos NASA RAW
    nasa_files = list(RAW_DATA_DIR.glob("*_NASA_RAW.csv"))
    cities = [f.stem.split("_1991")[0] for f in nasa_files]
    cities = sorted(set(cities))

    logger.info(f"📊 {len(cities)} cidades encontradas")

    for idx, city in enumerate(cities, 1):
        logger.info(f"\n[{idx}/{len(cities)}] {city}")
        try:
            calculate_eto_nasa_power(city)
        except Exception as e:
            logger.error(f"❌ Erro em {city}: {e}")
            continue

    logger.info("\n" + "=" * 80)
    logger.success(f"✅ Processamento concluído! Arquivos em: {OUTPUT_DIR}")
    logger.info("=" * 80)


if __name__ == "__main__":
    process_all_cities()
