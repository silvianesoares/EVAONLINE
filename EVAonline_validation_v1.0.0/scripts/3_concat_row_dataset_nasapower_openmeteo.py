"""
Concatenate NASA POWER and Open-Meteo datasets

- This script reads all CSV files from NASA POWER and Open-Meteo raw data
directories, adds city and source identifiers, and concatenates them into
two unified datasets.
- Converts wind speed from 10m to 2m using FAO-56 logarithmic wind
  profile equation.

Output files:
- all_nasa_power_raw_1991_2020.csv: All NASA POWER data combined
- all_open_meteo_raw_1991_2020.csv: All Open-Meteo data combined
- all_climate_data_1991_2020.csv: Combined dataset from both sources

Usage:
    python scripts/concat_row_dataset_nasapower_openmeteo.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
from loguru import logger
import sys

logger.remove()
logger.add(sys.stdout, level="INFO", colorize=True)


def convert_wind_speed_2m(
    u_height: pd.Series, height: float = 10.0
) -> pd.Series:
    """
    Eq. 47 - FAO-56 logarithmic wind speed conversion to 2m height.

    Converts wind speed measurements from any height to the standard
    2m reference height using the logarithmic wind profile equation.
    This is the exact formula from FAO-56 Equation 47, ensuring
    consistency with ETo calculations.

    Formula: u2 = uz * [4.87 / ln(67.8*z - 5.42)]

    Args:
        u_height: Wind speed at measurement height (m/s)
        height: Measurement height (m) - default 10m for Open-Meteo
                NASA POWER data is already at 2m, so height=2.0

    Returns:
        Wind speed at 2m height (m/s), with minimum value of 0.5 m/s

    Reference:
        Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998).
        Crop evapotranspiration - Guidelines for computing crop water
        requirements. FAO Irrigation and drainage paper 56, Eq. 47.

    Example:
        >>> ws_2m = convert_wind_speed_2m(ws_10m, height=10.0)
        # Converts from 10m to 2m using logarithmic profile
    """
    if height == 2.0:
        # Already at 2m height (NASA POWER case)
        return u_height.clip(lower=0.5)

    # FAO-56 Eq. 47: u2 = uz * [4.87 / ln(67.8*z - 5.42)]
    conversion_factor = 4.87 / np.log(67.8 * height - 5.42)
    u2 = u_height * conversion_factor
    return u2.clip(lower=0.5)  # Physical minimum limit


def extract_city_name(file_path: Path) -> str:
    """
    Extract city name from filename.

    Examples:
        "Alvorada_do_Gurgueia_PI_1991-01-01_2020-12-31_NASA_RAW.csv"
        -> "Alvorada_do_Gurgueia_PI"

        "Alvorada_do_Gurgueia_PI_1991-01-01_2020-12-31_OpenMeteo_RAW.csv"
        -> "Alvorada_do_Gurgueia_PI"

    Args:
        file_path: Path to the CSV file

    Returns:
        City name with state
    """
    filename = file_path.stem
    parts = filename.split("_")
    city_parts = []

    for part in parts:
        # Stop when we find a date pattern (YYYY-MM-DD format)
        if "-" in part and len(part) == 10:
            # Check if it looks like a date
            date_parts = part.split("-")
            if (
                len(date_parts) == 3
                and len(date_parts[0]) == 4
                and date_parts[0].isdigit()
            ):
                break
        city_parts.append(part)

    return "_".join(city_parts)


def concat_nasa_power_data(data_dir: Path) -> pd.DataFrame:
    """
    Concatenate all NASA POWER raw data files.

    Args:
        data_dir: Path to data directory

    Returns:
        Combined DataFrame with all NASA POWER data
    """
    logger.info("Processing NASA POWER data...")

    nasa_dir = data_dir / "nasa_power_raw"
    all_data = []

    for file_path in sorted(nasa_dir.glob("*.csv")):
        city = extract_city_name(file_path)
        logger.info(f"Reading {file_path.name}...")

        df = pd.read_csv(file_path)

        # Remove existing city/source columns if present
        if "city" in df.columns:
            df = df.drop(columns=["city"])
        if "source" in df.columns:
            df = df.drop(columns=["source"])

        df["city"] = city
        df["source"] = "NASA_POWER"

        all_data.append(df)

    # Concatenate all dataframes
    df_combined = pd.concat(all_data, ignore_index=True)

    logger.info(
        f"NASA POWER: {len(all_data)} cities, "
        f"{len(df_combined):,} total records"
    )

    return df_combined


def concat_openmeteo_data(data_dir: Path) -> pd.DataFrame:
    """
    Concatenate all Open-Meteo raw data files.

    Converts WS10M (wind speed at 10m) to WS2M (wind speed at 2m) using
    logarithmic wind profile equation from FAO-56:

    u2 = u10 * (4.87 / ln(67.8 * 10 - 5.42))

    where:
    - u2 = wind speed at 2m height (m/s)
    - u10 = wind speed at 10m height (m/s)
    - ln = natural logarithm

    Reference: Allen et al. (1998) FAO Irrigation and Drainage Paper 56

    Args:
        data_dir: Path to data directory

    Returns:
        Combined DataFrame with all Open-Meteo data
    """
    logger.info("Processing Open-Meteo data...")

    openmeteo_dir = data_dir / "open_meteo_raw"
    all_data = []

    for file_path in sorted(openmeteo_dir.glob("*.csv")):
        city = extract_city_name(file_path)
        logger.info(f"Reading {file_path.name}...")

        df = pd.read_csv(file_path)

        # Remove existing city column if present
        if "city" in df.columns:
            df = df.drop(columns=["city"])
        if "source" in df.columns:
            df = df.drop(columns=["source"])

        # Convert WS10M to WS2M using FAO-56 Eq. 47 (logarithmic)
        if "WS10M" in df.columns:
            df["WS2M"] = convert_wind_speed_2m(df["WS10M"], height=10.0).round(
                2
            )
            logger.info(
                f"    Converted WS10M to WS2M for {city} " f"(FAO-56 Eq. 47)"
            )
            # Drop WS10M column as we now have WS2M
            df = df.drop(columns=["WS10M"])
        else:
            logger.warning(f"WS10M column not found in {city}!")
            logger.info(f"Available columns: {list(df.columns)}")

        df["city"] = city
        df["source"] = "Open_Meteo"

        all_data.append(df)

    # Concatenate all dataframes
    df_combined = pd.concat(all_data, ignore_index=True)

    # Reorder columns to match NASA POWER standard order
    standard_cols = [
        "date",
        "T2M_MAX",
        "T2M_MIN",
        "T2M",
        "RH2M",
        "WS2M",
        "ALLSKY_SFC_SW_DWN",
        "PRECTOTCORR",
        "city",
        "source",
    ]
    df_combined = df_combined[standard_cols]

    logger.info(
        f"Open-Meteo: {len(all_data)} cities, "
        f"{len(df_combined):,} total records"
    )

    return df_combined


def main():
    """Main function."""
    logger.info("=" * 80)
    logger.info("Starting dataset concatenation")
    logger.info("=" * 80)

    # Set paths
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent
    data_dir = base_dir / "data" / "original_data"
    output_dir = base_dir / "data" / "3_combined_datasets"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Concatenate NASA POWER data
    df_nasa = concat_nasa_power_data(data_dir)

    # Save NASA POWER combined data
    output_file = output_dir / "all_nasa_power_raw_1991_2020.csv"
    df_nasa.to_csv(output_file, index=False, decimal=".", sep=",")
    logger.info(f"\nNASA POWER data saved to: {output_file}")
    logger.info(f"Shape: {df_nasa.shape}")
    logger.info(f"Columns: {list(df_nasa.columns)}")
    logger.info(f"Cities: {df_nasa['city'].nunique()}")
    logger.info(
        f"Date range: {df_nasa['date'].min()} to {df_nasa['date'].max()}"
    )

    # Concatenate Open-Meteo data
    df_openmeteo = concat_openmeteo_data(data_dir)

    # Save Open-Meteo combined data
    output_file = output_dir / "all_open_meteo_raw_1991_2020.csv"
    df_openmeteo.to_csv(output_file, index=False, decimal=".", sep=",")
    logger.info(f"\nOpen-Meteo data saved to: {output_file}")
    logger.info(f"Shape: {df_openmeteo.shape}")
    logger.info(f"Columns: {list(df_openmeteo.columns)}")
    logger.info(f"Cities: {df_openmeteo['city'].nunique()}")
    logger.info(
        f"Date range: {df_openmeteo['date'].min()} to "
        f"{df_openmeteo['date'].max()}"
    )

    # Concatenate both sources into a single dataset
    logger.info("\nCombining NASA POWER and Open-Meteo into single dataset...")

    # Standardize column order for both datasets
    standard_cols = [
        "date",
        "T2M_MAX",
        "T2M_MIN",
        "T2M",
        "RH2M",
        "WS2M",
        "ALLSKY_SFC_SW_DWN",
        "PRECTOTCORR",
        "city",
        "source",
    ]

    # Reorder columns to match standard order
    df_nasa_ordered = df_nasa[standard_cols]
    df_openmeteo_ordered = df_openmeteo[standard_cols]

    logger.info(f"Standardized columns: {standard_cols}")

    # Concatenate with aligned columns
    df_all = pd.concat(
        [df_nasa_ordered, df_openmeteo_ordered], ignore_index=True
    )

    # Save combined dataset
    output_file = output_dir / "all_climate_data_1991_2020.csv"
    df_all.to_csv(output_file, index=False, decimal=".", sep=",")
    logger.info(f"\nCombined data saved to: {output_file}")
    logger.info(f"Shape: {df_all.shape}")
    logger.info(f"Sources: {df_all['source'].unique().tolist()}")
    logger.info(f"Cities: {df_all['city'].nunique()}")
    logger.info(
        f"Date range: {df_all['date'].min()} to {df_all['date'].max()}"
    )

    # Display records per source
    logger.info("\nRecords per source:")
    for source in df_all["source"].unique():
        count = len(df_all[df_all["source"] == source])
        logger.info(f"{source}: {count:,} records")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"NASA POWER: {len(df_nasa):,} records")
    logger.info(f"Open-Meteo: {len(df_openmeteo):,} records")
    logger.info(f"Combined: {len(df_all):,} records")
    logger.info("\nOutput files:")
    logger.info("1. all_nasa_power_raw_1991_2020.csv")
    logger.info("2. all_open_meteo_raw_1991_2020.csv")
    logger.info("3. all_climate_data_1991_2020.csv (NASA + Open-Meteo)")
    logger.info("=" * 80)
    logger.info("Concatenation complete!")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
