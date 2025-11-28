#!/usr/bin/env python3
"""
Generate Descriptive Statistics for EVAonline Validation Dataset

This script calculates comprehensive descriptive statistics for all
data sources:
- Xavier (reference dataset)
- NASA POWER (MERRA-2 reanalysis)
- Open-Meteo (ERA5-Land reanalysis)

Output files:
- descriptive_stats_by_variable.csv: Variable-level statistics
- descriptive_stats_complete.csv: City-level statistics
- descriptive_stats_report.txt: Formatted text report for publication

Usage:
    python scripts/2_generate_descriptive_stats.py
"""
import sys
import pandas as pd
from pathlib import Path
from typing import Dict, Optional
from loguru import logger
from datetime import datetime

logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | {message}",
)


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
        > ws_2m = convert_wind_speed_2m(ws_10m, height=10.0)
        # Converts from 10m to 2m using logarithmic profile
    """
    if height == 2.0:
        # Already at 2m height (NASA POWER case)
        return u_height.clip(lower=0.5)

    # FAO-56 Eq. 47: u2 = uz * [4.87 / ln(67.8*z - 5.42)]
    import numpy as np

    conversion_factor = 4.87 / np.log(67.8 * height - 5.42)
    u2 = u_height * conversion_factor
    return u2.clip(lower=0.5)  # Physical minimum limit


def get_xavier_limits() -> Dict:
    """
    Get physical limits based on Xavier et al. (2016, 2022) for Brazil.

    Reference:
    - Xavier, A. C., King, C. W., & Scanlon, B. R. (2016).
      Daily gridded meteorological variables in Brazil (1980–2013).
    - Xavier, A. C., Scanlon, B. R., King, C. W., & Alves, A. I. (2022).
      New improved Brazilian daily weather gridded data (1961–2020).

    Returns:
        Dict with variable limits: {variable: (min, max, inclusive)}
    """
    return {
        # NASA POWER and Open-Meteo common variables
        "T2M_MAX": (-30, 50, "neither"),  # Temperature max (°C)
        "T2M_MIN": (-30, 50, "neither"),  # Temperature min (°C)
        "T2M": (-30, 50, "neither"),  # Temperature mean (°C)
        "RH2M": (0, 100, "both"),  # Relative humidity (%)
        "WS2M": (0, 100, "left"),  # Wind speed at 2m (m/s)
        "WS10M": (0, 100, "left"),  # Wind speed at 10m (m/s)
        "PRECTOTCORR": (0, 450, "left"),  # Precipitation (mm)
        "ALLSKY_SFC_SW_DWN": (0, 40, "left"),  # Solar radiation (MJ/m²/day)
    }


def detect_outliers_xavier_limits(
    df: pd.DataFrame, variable: str
) -> pd.DataFrame:
    """
    Detect outliers based on Xavier et al. physical limits for Brazil.

    Args:
        df: DataFrame with weather data
        variable: Variable name to check

    Returns:
        DataFrame with 'is_outlier' column added
    """
    limits = get_xavier_limits()

    if variable not in limits:
        df["is_outlier"] = False
        return df

    min_val, max_val, inclusive = limits[variable]

    # Check bounds based on inclusive parameter
    if inclusive == "both":
        df["is_outlier"] = (df[variable] < min_val) | (df[variable] > max_val)
    elif inclusive == "left":
        df["is_outlier"] = (df[variable] < min_val) | (df[variable] >= max_val)
    elif inclusive == "right":
        df["is_outlier"] = (df[variable] <= min_val) | (df[variable] > max_val)
    else:  # "neither"
        df["is_outlier"] = (df[variable] <= min_val) | (
            df[variable] >= max_val
        )

    return df


def calculate_statistics(
    data: pd.Series, variable_name: Optional[str] = None
) -> Dict:
    """
    Calculate comprehensive descriptive statistics.

    Args:
        data: Series with variable values
        variable_name: Variable name for outlier detection (optional)

    Returns:
        Dict with statistics including outlier counts
    """
    stats = {
        "count": int(data.count()),
        "mean": float(data.mean()),
        "std": float(data.std()),
        "min": float(data.min()),
        "q25": float(data.quantile(0.25)),
        "median": float(data.median()),
        "q75": float(data.quantile(0.75)),
        "max": float(data.max()),
        "cv": float(data.std() / data.mean() * 100) if data.mean() != 0 else 0,
        "missing": int(data.isna().sum()),
        "missing_pct": float(data.isna().sum() / len(data) * 100),
    }

    # Add outlier detection based on Xavier limits
    if variable_name:
        df_temp = pd.DataFrame({variable_name: data})
        df_temp = detect_outliers_xavier_limits(df_temp, variable_name)
        outlier_count = df_temp["is_outlier"].sum()
        outlier_pct = (outlier_count / len(data)) * 100 if len(data) > 0 else 0

        stats["outliers"] = int(outlier_count)
        stats["outliers_pct"] = float(outlier_pct)

    return stats


def analyze_xavier_data(data_dir: Path) -> pd.DataFrame:
    """Analyze Xavier dataset."""
    logger.info("Analyzing Xavier dataset...")

    xavier_dir = data_dir / "eto_xavier_csv"
    all_stats = []

    for file_path in xavier_dir.glob("*.csv"):
        city = file_path.stem
        df = pd.read_csv(file_path)
        df["date"] = pd.to_datetime(df["date"])

        # Filter to common period (1991-2020)
        df = df[(df["date"] >= "1991-01-01") & (df["date"] <= "2020-12-31")]

        stats = calculate_statistics(df["eto_xavier"])
        stats["source"] = "Xavier"
        stats["city"] = city
        stats["variable"] = "ETo"
        stats["period_start"] = df["date"].min().strftime("%Y-%m-%d")
        stats["period_end"] = df["date"].max().strftime("%Y-%m-%d")
        stats["n_days"] = len(df)

        all_stats.append(stats)

    logger.info(f"Processed {len(all_stats)} cities from Xavier")
    return pd.DataFrame(all_stats)


def analyze_nasa_power_data(data_dir: Path) -> pd.DataFrame:
    """Analyze NASA POWER dataset."""
    logger.info("Analyzing NASA POWER dataset...")

    nasa_dir = data_dir / "nasa_power_raw"
    all_stats = []

    # Variables in NASA POWER
    variables = [
        "T2M_MAX",
        "T2M_MIN",
        "T2M",
        "RH2M",
        "WS2M",
        "ALLSKY_SFC_SW_DWN",
        "PRECTOTCORR",
    ]

    for file_path in nasa_dir.glob("*.csv"):
        # Extract city_state from filename
        # e.g., "Alvorada_do_Gurgueia_PI" from
        # "Alvorada_do_Gurgueia_PI_1991-01-01_2020-12-31_NASA_RAW.csv"
        parts = file_path.stem.split("_")
        # Find where the date starts (format: YYYY-MM-DD)
        city_parts = []
        for part in parts:
            if (
                len(part) == 4 and part.isdigit() and int(part) >= 1900
            ):  # Year found
                break
            city_parts.append(part)
        city = "_".join(city_parts)

        df = pd.read_csv(file_path)
        df["date"] = pd.to_datetime(df["date"])

        for var in variables:
            if var in df.columns:
                stats = calculate_statistics(df[var], variable_name=var)
                stats["source"] = "NASA POWER"
                stats["city"] = city
                stats["variable"] = var
                stats["period_start"] = df["date"].min().strftime("%Y-%m-%d")
                stats["period_end"] = df["date"].max().strftime("%Y-%m-%d")
                stats["n_days"] = len(df)

                all_stats.append(stats)

    logger.info(
        f"Processed {len(all_stats)} variable-city combinations from NASA"
    )
    return pd.DataFrame(all_stats)


def analyze_openmeteo_data(data_dir: Path) -> pd.DataFrame:
    """Analyze Open-Meteo dataset."""
    logger.info("Analyzing Open-Meteo dataset...")

    openmeteo_dir = data_dir / "open_meteo_raw"
    all_stats = []

    # Variables in Open-Meteo
    # Note: Open-Meteo provides WS10M, which needs conversion to WS2M
    variables = [
        "T2M_MAX",
        "T2M_MIN",
        "T2M",
        "RH2M",
        "WS10M",  # Wind at 10m (will be converted to WS2M)
        "ALLSKY_SFC_SW_DWN",
        "PRECTOTCORR",
    ]

    for file_path in openmeteo_dir.glob("*.csv"):
        parts = file_path.stem.split("_")
        # Find where the date starts (format: YYYY-MM-DD)
        city_parts = []
        for part in parts:
            if (
                len(part) == 4 and part.isdigit() and int(part) >= 1900
            ):  # Year found
                break
            city_parts.append(part)
        city = "_".join(city_parts)

        df = pd.read_csv(file_path)
        df["date"] = pd.to_datetime(df["date"])

        # Convert WS10M to WS2M using FAO-56 Eq. 47 (logarithmic profile)
        # This ensures consistency with ETo calculation methodology
        if "WS10M" in df.columns:
            logger.debug(
                f"Converting WS10M to WS2M for {city} "
                f"(FAO-56 Eq. 47: logarithmic profile)"
            )
            df["WS2M"] = convert_wind_speed_2m(df["WS10M"], height=10.0)

        for var in variables:
            # Map WS10M to WS2M for statistics
            if var == "WS10M":
                if "WS2M" not in df.columns:
                    logger.warning(
                        f"WS10M found but WS2M conversion failed for {city}"
                    )
                    continue
                # Use converted WS2M data but report as WS2M
                var_data = df["WS2M"]
                var_name = "WS2M"  # Report as WS2M (converted)
                var_limits = "WS2M"  # Use WS2M limits for validation
            elif var in df.columns:
                var_data = df[var]
                var_name = var
                var_limits = var
            else:
                continue

            stats = calculate_statistics(var_data, variable_name=var_limits)
            stats["source"] = "Open-Meteo"
            stats["city"] = city
            stats["variable"] = var_name  # Report as WS2M if converted
            stats["period_start"] = df["date"].min().strftime("%Y-%m-%d")
            stats["period_end"] = df["date"].max().strftime("%Y-%m-%d")
            stats["n_days"] = len(df)

            all_stats.append(stats)

    logger.info(
        f"Processed {len(all_stats)} variable-city combinations "
        f"from Open-Meteo"
    )
    return pd.DataFrame(all_stats)


def generate_summary_by_source(df_all: pd.DataFrame) -> pd.DataFrame:
    """Generate summary statistics grouped by data source."""
    logger.info("Generating source-level summary...")

    # Group by source and variable
    summary = (
        df_all.groupby(["source", "variable"])
        .agg(
            {
                "count": "sum",
                "mean": "mean",
                "std": "mean",
                "min": "min",
                "median": "mean",
                "max": "max",
                "cv": "mean",
                "missing_pct": "mean",
                "n_days": "sum",
            }
        )
        .reset_index()
    )

    return summary


def generate_summary_by_city_meteo(df_all: pd.DataFrame) -> pd.DataFrame:
    """Generate summary statistics for meteorological variables by city."""
    logger.info("Generating city-level summary for meteo variables...")

    # Filter only meteorological variables (exclude ETo)
    df_meteo = df_all[df_all["variable"] != "ETo"]

    # Create a simplified table: city, source, variable, mean
    summary = (
        df_meteo[["city", "source", "variable", "mean"]]
        .pivot_table(
            index="city",
            columns=["source", "variable"],
            values="mean",
            aggfunc="first",
        )
        .reset_index()
    )

    # Flatten column names
    summary.columns = [
        f"{col[1]}_{col[0]}" if col[0] != "" else col[1]
        for col in summary.columns
    ]

    return summary


def generate_summary_by_city_eto(df_all: pd.DataFrame) -> pd.DataFrame:
    """Generate summary statistics for ETo by city (Xavier only)."""
    logger.info("Generating city-level summary for ETo (Xavier)...")

    # Filter only ETo from Xavier
    df_eto = df_all[
        (df_all["variable"] == "ETo") & (df_all["source"] == "Xavier")
    ]

    # Simple table with city and ETo mean
    summary = df_eto[["city", "mean"]].copy()
    summary = summary.rename(columns={"mean": "ETo_mean_daily_mm"})
    summary = summary.sort_values("city").reset_index(drop=True)

    return summary


def generate_text_report(df_all: pd.DataFrame, output_dir: Path):
    """Generate formatted text report for publication."""
    logger.info("Generating publication-ready text report...")

    report_path = output_dir / "descriptive_stats_report.txt"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("DESCRIPTIVE STATISTICS REPORT\n")
        f.write("EVAonline Validation Dataset (1991-2020)\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")

        # 1. Overall Summary
        f.write("1. DATA SOURCES OVERVIEW\n")
        f.write("-" * 80 + "\n\n")

        sources = df_all["source"].unique()
        for source in sorted(sources):
            df_source = df_all[df_all["source"] == source]
            n_cities = df_source["city"].nunique()
            n_vars = df_source["variable"].nunique()
            total_obs = df_source["count"].sum()

            f.write(f"{source}:\n")
            f.write(f"Cities: {n_cities}\n")
            f.write(f"Variables: {n_vars}\n")
            f.write(f"Total observations: {total_obs:,}\n")
            f.write(
                f"Missing data: {df_source['missing_pct'].mean():.2f}%\n\n"
            )

        # 2. ETo Statistics by Source
        f.write("\n2. REFERENCE EVAPOTRANSPIRATION (ETo) STATISTICS\n")
        f.write("-" * 80 + "\n\n")

        df_eto = df_all[df_all["variable"] == "ETo"]

        f.write(
            "Table 1. ETo descriptive statistics by data source (mm/day)\n\n"
        )
        f.write(
            f"{'Source':<15} {'N':>8} {'Mean':>8} {'SD':>8} {'Min':>8} "
            f"{'Q25':>8} {'Median':>8} {'Q75':>8} {'Max':>8} {'CV%':>8}\n"
        )
        f.write("-" * 80 + "\n")

        for source in sorted(df_eto["source"].unique()):
            df_src = df_eto[df_eto["source"] == source]

            f.write(
                f"{source:<15} "
                f"{int(df_src['count'].sum()):>8,} "
                f"{df_src['mean'].mean():>8.2f} "
                f"{df_src['std'].mean():>8.2f} "
                f"{df_src['min'].min():>8.2f} "
                f"{df_src['q25'].mean():>8.2f} "
                f"{df_src['median'].mean():>8.2f} "
                f"{df_src['q75'].mean():>8.2f} "
                f"{df_src['max'].max():>8.2f} "
                f"{df_src['cv'].mean():>8.2f}\n"
            )

        # 3. Meteorological Variables (NASA POWER and Open-Meteo)
        f.write("\n\n3. METEOROLOGICAL VARIABLES STATISTICS\n")
        f.write("-" * 80 + "\n\n")

        var_names = {
            "T2M": "Temperature Mean (°C)",
            "T2M_MAX": "Temperature Maximum (°C)",
            "T2M_MIN": "Temperature Minimum (°C)",
            "RH2M": "Relative Humidity (%)",
            "WS2M": "Wind Speed at 2m (m/s)",
            "WS10M": "Wind Speed at 10m (m/s)",
            "ALLSKY_SFC_SW_DWN": "Solar Radiation (MJ/m²/day)",
            "PRECTOTCORR": "Precipitation (mm/day)",
        }

        for var in [
            "T2M",
            "T2M_MAX",
            "T2M_MIN",
            "RH2M",
            "WS2M",
            "WS10M",
            "ALLSKY_SFC_SW_DWN",
            "PRECTOTCORR",
        ]:
            df_var = df_all[df_all["variable"] == var]

            if not df_var.empty:
                f.write(f"\n{var_names.get(var, var)}\n")
                f.write(
                    f"{'Source':<15} {'Mean':>8} {'SD':>8} {'Min':>8} "
                    f"{'Max':>8} {'CV%':>8}\n"
                )
                f.write("-" * 60 + "\n")

                for source in sorted(df_var["source"].unique()):
                    df_src = df_var[df_var["source"] == source]
                    f.write(
                        f"{source:<15} "
                        f"{df_src['mean'].mean():>8.2f} "
                        f"{df_src['std'].mean():>8.2f} "
                        f"{df_src['min'].min():>8.2f} "
                        f"{df_src['max'].max():>8.2f} "
                        f"{df_src['cv'].mean():>8.2f}\n"
                    )

        # 3. Data Quality Summary
        f.write("\n\n3. DATA QUALITY ASSESSMENT\n")
        f.write("-" * 80 + "\n\n")

        for source in sorted(df_all["source"].unique()):
            df_source = df_all[df_all["source"] == source]

            f.write(f"{source}:\n")
            complete_pct = 100 - df_source["missing_pct"].mean()
            f.write(f"  Complete data: {complete_pct:.2f}%\n")
            f.write(
                f"  Missing data: {df_source['missing_pct'].mean():.2f}%\n"
            )

            # Add outlier statistics if available
            if "outliers_pct" in df_source.columns:
                total_outliers = int(df_source["outliers"].sum())
                # Calculate percentage based on total observations
                total_obs = df_source["count"].sum()
                outliers_pct = (
                    (total_outliers / total_obs * 100) if total_obs > 0 else 0
                )
                valid_data_pct = (
                    100 - df_source["missing_pct"].mean() - outliers_pct
                )

                # Use more decimals for very small percentages
                if outliers_pct < 0.01 and outliers_pct > 0:
                    outliers_str = f"{outliers_pct:.6f}%"
                else:
                    outliers_str = f"{outliers_pct:.2f}%"

                f.write(
                    f"  Outliers detected: {total_outliers:,} "
                    f"({outliers_str})\n"
                )
                f.write(f"  Valid data after QC: {valid_data_pct:.2f}%\n")

            f.write(
                f"  Temporal coverage: {df_source['period_start'].iloc[0]} to "
                f"{df_source['period_end'].iloc[0]}\n"
            )
            f.write(f"  Total days: {df_source['n_days'].iloc[0]:,}\n\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write("End of Report\n")
        f.write("=" * 80 + "\n")

    logger.info(f"Text report saved to: {report_path}")


def main():
    """Main function."""
    logger.info("=" * 80)
    logger.info("Starting Descriptive Statistics Generation")
    logger.info("=" * 80)

    # Set paths
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent
    data_dir = base_dir / "data" / "original_data"
    output_dir = base_dir / "data" / "2_statistics_raw_dataset"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validate required directories exist
    required_dirs = [
        data_dir / "eto_xavier_csv",
        data_dir / "nasa_power_raw",
        data_dir / "open_meteo_raw",
    ]

    for dir_path in required_dirs:
        if not dir_path.exists():
            logger.error(f"ERROR: Required directory not found: {dir_path}")
            logger.error(
                "Please ensure you're running this script from the "
                "EVAonline_validation_v1.0.0/scripts/ directory."
            )
            sys.exit(1)

    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Output directory: {output_dir}")

    # Analyze each data source (raw data - no ETo calculation)
    df_xavier = analyze_xavier_data(data_dir)
    df_nasa = analyze_nasa_power_data(data_dir)
    df_openmeteo = analyze_openmeteo_data(data_dir)

    # Combine all statistics
    df_all = pd.concat([df_xavier, df_nasa, df_openmeteo], ignore_index=True)

    # Generate summaries
    df_summary_source = generate_summary_by_source(df_all)

    # Save outputs
    logger.info("\nSaving output files...")

    # Complete statistics
    output_file = output_dir / "descriptive_stats_complete.csv"
    df_all.to_csv(output_file, index=False, float_format="%.4f")
    logger.info(f"Complete statistics: {output_file}")

    # Summary by source and variable
    output_file = output_dir / "descriptive_stats_by_variable.csv"
    df_summary_source.to_csv(output_file, index=False, float_format="%.4f")
    logger.info(f"Summary by variable: {output_file}")

    # Generate text report
    generate_text_report(df_all, output_dir)

    # Display summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"\nTotal records analyzed: {len(df_all):,}")
    logger.info(f"Data sources: {df_all['source'].nunique()}")
    logger.info(f"Cities: {df_all['city'].nunique()}")
    logger.info(f"Variables: {df_all['variable'].nunique()}")

    logger.info("\nMeteorological Variables by Source:")
    for source in sorted(df_all["source"].unique()):
        df_src = df_all[df_all["source"] == source]
        vars_list = sorted(df_src["variable"].unique())
        logger.info(f"  {source}: {', '.join(vars_list)}")

    logger.info("\n" + "=" * 80)
    logger.info("Descriptive statistics generation complete!")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
