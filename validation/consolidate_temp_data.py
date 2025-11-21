"""
Consolidar Dados de temp/ para Cache
Organiza os arquivos baixados em temp/ para a estrutura de cache
"""

from pathlib import Path
import pandas as pd
from loguru import logger


BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR.parent / "temp"  # temp/ na raiz do projeto
CACHE_DIR = BASE_DIR / "results/brasil/cache"
INFO_CITIES = BASE_DIR / "data_validation/data/info_cities.csv"

CACHE_DIR.mkdir(parents=True, exist_ok=True)


def consolidate_city_data(city_name: str, lat: float, lon: float):
    """
    Consolida dados anuais de temp/ em um único arquivo consolidado.
    """
    logger.info(f"🔄 Consolidando {city_name}...")

    # Buscar arquivos no formato: historical_final_{year}_{lat}_{lon}.csv
    # Usar busca mais flexível porque float pode ter muitas casas decimais
    all_files = list(TEMP_DIR.glob("historical_final_*.csv"))

    # Filtrar arquivos que correspondem às coordenadas (com tolerância)
    files = []
    for file in all_files:
        parts = file.stem.split("_")
        # Formato: historical_final_YEAR_LAT_LON
        if len(parts) >= 5:
            try:
                file_lat = float(parts[3])  # Índice 3 é LAT
                file_lon = float(parts[4])  # Índice 4 é LON
                # Verificar se coordenadas batem (tolerância de 0.0001 graus)
                if (
                    abs(file_lat - lat) < 0.0001
                    and abs(file_lon - lon) < 0.0001
                ):
                    files.append(file)
            except (ValueError, IndexError):
                continue

    files = sorted(files)

    if not files:
        logger.warning(f"  ⚠️  Nenhum arquivo encontrado para {city_name}")
        return None

    logger.info(f"  📁 Encontrados {len(files)} arquivos")

    all_data = []
    years_found = []

    for file in files:
        try:
            # Extrair ano do nome do arquivo
            # Formato: historical_final_YYYY_lat_lon.csv
            parts = file.stem.split("_")
            year = parts[2]  # "historical_final_YYYY_..."

            df = pd.read_csv(file)

            # Verificar se tem coluna date
            if "date" not in df.columns:
                logger.warning(f"  ⚠️  Sem coluna 'date' em {file.name}")
                continue

            df["date"] = pd.to_datetime(df["date"])
            all_data.append(df)
            years_found.append(year)

            logger.info(f"  ✅ {year}: {len(df)} dias")

        except Exception as e:
            logger.error(f"  ❌ Erro em {file.name}: {e}")
            continue

    if not all_data:
        logger.error(f"  ❌ Nenhum dado válido para {city_name}")
        return None

    # Concatenar e ordenar
    df_complete = pd.concat(all_data, ignore_index=True)
    df_complete = df_complete.sort_values("date").drop_duplicates(
        subset=["date"]
    )

    # Determinar período
    years_found.sort()
    start_year = years_found[0]
    end_year = years_found[-1]

    # Salvar consolidado
    output_file = CACHE_DIR / f"{city_name}_{start_year}_{end_year}.csv"
    df_complete.to_csv(output_file, index=False)

    logger.info(
        f"  💾 Salvo: {output_file.name} "
        f"({len(df_complete)} dias, {start_year}-{end_year})"
    )

    return df_complete


def main():
    """
    Processa todas as cidades do info_cities.csv.
    """
    df_cities = pd.read_csv(INFO_CITIES)

    logger.info(f"🚀 Consolidando dados de {len(df_cities)} cidades")
    logger.info(f"   Origem: {TEMP_DIR}")
    logger.info(f"   Destino: {CACHE_DIR}\n")

    success = 0
    failed = 0

    for idx, row in df_cities.iterrows():
        city = row["city"]
        lat = row["lat"]
        lon = row["lon"]

        result = consolidate_city_data(city, lat, lon)

        if result is not None:
            success += 1
        else:
            failed += 1

    logger.info(f"\n{'='*70}")
    logger.info(f"✅ Consolidação completa!")
    logger.info(f"   Sucesso: {success} cidades")
    logger.info(f"   Falhas: {failed} cidades")
    logger.info(f"{'='*70}")


if __name__ == "__main__":
    main()
