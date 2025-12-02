"""
FAO-56 Penman-Monteith ETo calculation (Allen et al., 1998)
using raw data from any source (NASA POWER, Open-Meteo, etc.).

Usage:
    python 4_calculate_eto_data_from_openmeteo.py --source nasa
    python 4_calculate_eto_data_from_openmeteo.py --source openmeteo
"""

from pathlib import Path
import pandas as pd
import numpy as np
from loguru import logger
import sys

# Logger configuration
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | {message}",
)


class EToFAO56:
    """FAO-56 Penman-Monteith"""

    Gsc = 0.0820  # Solar constant [MJ m⁻² min⁻¹]
    sigma = 4.903e-9  # Stefan-Boltzmann [MJ K⁻⁴ m⁻² day⁻¹]
    albedo = 0.23  # Reference grass albedo

    @staticmethod
    def fractional_day_of_year(date_str: str) -> float:
        """
        Returns fractional day of year (1.0 to 366.0).
        Used directly in FAO-56 equations 21-25.
        """
        from datetime import datetime

        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.timetuple().tm_yday + 0.0  # 0.0 = start of day

    @staticmethod
    def atmospheric_pressure(elevation: float) -> float:
        """Eq. 7 - Atmospheric pressure (kPa)"""
        return 101.3 * ((293.0 - 0.0065 * elevation) / 293.0) ** 5.26

    @staticmethod
    def psychrometric_constant(elevation: float) -> float:
        """Eq. 8 - Psychrometric constant (kPa °C⁻¹)"""
        P = EToFAO56.atmospheric_pressure(elevation)
        return 0.000665 * P

    @staticmethod
    def wind_speed_2m(
        u_height: np.ndarray, height: float = 10.0
    ) -> np.ndarray:
        """
        Eq. 47 - Logarithmic wind speed conversion to 2m height

        Args:
            u_height: Wind speed at measurement height (m/s)
            height: Measurement height (m) - default 10m for Open-Meteo
                    NASA POWER data is already at 2m, so height=2.0

        Returns:
            Wind speed at 2m height (m/s)
        """
        if height == 2.0:
            # NASA POWER is already at 2m
            return np.maximum(u_height, 0.5)

        # FAO-56 Eq. 47 logarithmic conversion
        u2 = u_height * (4.87 / np.log(67.8 * height - 5.42))
        return np.maximum(u2, 0.5)  # Physical minimum limit

    @staticmethod
    def extraterrestrial_radiation(lat: float, doy: np.ndarray) -> np.ndarray:
        """
        Extraterrestrial radiation (Ra) — FAO-56 Eqs. 21-25
        (Allen et al., 1998)

        Args:
            lat: Latitude in decimal degrees (e.g., -15.78)
            doy: Fractional day of year
                 (1.0 = Jan 1st 00:00, 1.5 = Jan 1st 12:00)

        Returns:
            Ra in MJ m⁻² day⁻¹
        """
        phi = np.radians(lat)  # Latitude in radians
        doy = np.asarray(doy, dtype=float)

        # Eq. 23: Inverse relative Earth-Sun distance
        dr = 1.0 + 0.033 * np.cos(2.0 * np.pi * doy / 365.0)

        # Eq. 24: Solar declination (radians)
        delta = 0.409 * np.sin(2.0 * np.pi * doy / 365.0 - 1.39)

        # Sunset hour angle (ωs) — Eq. 25
        # Avoid NaN with np.clip and handle polar cases
        cos_ws = -np.tan(phi) * np.tan(delta)
        cos_ws = np.clip(cos_ws, -1.0, 1.0)  # Ensure arccos domain

        # Polar cases: sun never rises (ws=0) or never sets (ws=π)
        ws = np.zeros_like(cos_ws)
        ws = np.where(cos_ws <= -1.0, np.pi, ws)  # Sun never sets
        ws = np.where((cos_ws > -1.0) & (cos_ws < 1.0), np.arccos(cos_ws), ws)
        # cos_ws >= 1.0 → sun never rises → ws = 0 (already zero)

        # Eq. 21: Extraterrestrial radiationion
        Ra = (
            (24.0 * 60.0 / np.pi)
            * EToFAO56.Gsc
            * dr
            * (
                ws * np.sin(phi) * np.sin(delta)
                + np.cos(phi) * np.cos(delta) * np.sin(ws)
            )
        )

        return np.maximum(Ra, 0.0)  # Ensure non-negative

    @staticmethod
    def clear_sky_radiation(Ra: np.ndarray, elevation: float) -> np.ndarray:
        """Eq. 37 - Rso (MJ m⁻² day⁻¹)"""
        return (0.75 + 2e-5 * elevation) * Ra

    @staticmethod
    def net_longwave_radiation(
        Rs: np.ndarray,
        Ra: np.ndarray,
        Tmax: np.ndarray,
        Tmin: np.ndarray,
        ea: np.ndarray,
        elevation: float,
    ) -> np.ndarray:
        """Eq. 39 - Net longwave radiation (with Rso and elevation)"""
        Tmax_K = Tmax + 273.15
        Tmin_K = Tmin + 273.15

        Rso = EToFAO56.clear_sky_radiation(Ra, elevation)

        # Cloud cover factor
        ratio = np.divide(Rs, Rso, out=np.ones_like(Rs), where=Rso > 1e-6)
        fcd = np.clip(1.35 * ratio - 0.35, 0.3, 1.0)

        Rnl = (
            EToFAO56.sigma
            * ((Tmax_K**4 + Tmin_K**4) / 2)
            * (0.34 - 0.14 * np.sqrt(np.maximum(ea, 0.01)))
            * fcd
        )
        return Rnl

    @staticmethod
    def calculate_et0(
        df: pd.DataFrame,
        lat: float,
        elevation: float,
        wind_height: float = 10.0,
    ) -> pd.Series:
        """
        Complete vectorized ETo calculation (mm day⁻¹)

        Args:
            df: DataFrame with meteorological data
            lat: Latitude (decimal degrees)
            elevation: Elevation (meters)
            wind_height: Wind measurement height (m)
                        - 10.0 for Open-Meteo (WS10M)
                        - 2.0 for NASA POWER (WS2M)

        Returns:
            Series with calculated ETo (mm/day)
        """

        # 1. Input variables
        Tmax = df["T2M_MAX"].to_numpy()
        Tmin = df["T2M_MIN"].to_numpy()
        Tmean = df["T2M"].to_numpy()
        RH = df["RH2M"].to_numpy()
        Rs = np.maximum(df["ALLSKY_SFC_SW_DWN"].to_numpy(), 0.1)

        # Detect wind column (WS10M or WS2M) and determine measurement height
        if "WS10M" in df.columns:
            u_wind = df["WS10M"].to_numpy()
            wind_height = 10.0  # Open-Meteo: wind at 10m
        elif "WS2M" in df.columns:
            u_wind = df["WS2M"].to_numpy()
            wind_height = 2.0  # NASA POWER: wind already at 2m
        else:
            raise ValueError("Wind column not found (WS10M or WS2M)")

        # Fractional day of year (J) — essential for astronomical precision
        dates = pd.to_datetime(df["date"])
        doy = dates.dt.dayofyear.astype(float).to_numpy()

        # 2. Derived variables
        # Saturation vapor pressure (es)
        es_Tmax = 0.6108 * np.exp(17.27 * Tmax / (Tmax + 237.3))
        es_Tmin = 0.6108 * np.exp(17.27 * Tmin / (Tmin + 237.3))
        es = 0.5 * (es_Tmax + es_Tmin)

        # Actual vapor pressure (ea)
        ea = (RH / 100.0) * es
        VPD = np.maximum(es - ea, 0.01)  # Minimum deficit

        # Convert wind speed to 2m height (FAO-56 Eq. 47)
        u2 = EToFAO56.wind_speed_2m(u_wind, height=wind_height)

        Ra = EToFAO56.extraterrestrial_radiation(lat, doy)

        Rn_s = (1 - EToFAO56.albedo) * Rs

        Rn_l = EToFAO56.net_longwave_radiation(
            Rs, Ra, Tmax, Tmin, ea, elevation
        )
        Rn = Rn_s - Rn_l
        G = np.zeros_like(Rn)  # Soil heat flux ≈ 0 (daily period)

        # Slope of saturation vapor pressure curve
        delta = (
            4098
            * (0.6108 * np.exp(17.27 * Tmean / (Tmean + 237.3)))
            / ((Tmean + 237.3) ** 2)
        )

        # Psychrometric constant with altitude correction
        gamma = EToFAO56.psychrometric_constant(elevation)

        # 3. FAO-56 Penman-Monteith Eq. 6
        numerator = (
            0.408 * delta * (Rn - G)
            + gamma * (900 / (Tmean + 273.15)) * u2 * VPD
        )
        denominator = delta + gamma * (1 + 0.34 * u2)

        ETo = np.where(denominator > 1e-6, numerator / denominator, 0.0)
        ETo = np.maximum(ETo, 0.0)

        return pd.Series(
            np.round(ETo, 3), index=df.index, name="eto_evaonline"
        )


def calculate_eto_from_source(source: str = "openmeteo"):
    """
    Calculate ETo from any RAW data source.

    Args:
        source: 'nasa' for NASA POWER or 'openmeteo' for Open-Meteo
    """
    logger.info("=" * 90)
    logger.info(f"ETo CALCULATION (FAO-56) - SOURCE: {source.upper()}")
    logger.info("=" * 90)

    script_dir = Path(__file__).parent
    base_dir = script_dir.parent
    data_dir = base_dir / "data" / "original_data"

    # Configure input directories based on source
    if source.lower() == "nasa":
        input_dir = data_dir / "nasa_power_raw"
        file_pattern = "*_NASA_RAW.csv"
        wind_height = 2.0  # NASA POWER wind at 2m
        output_suffix = "NASA_ONLY"
    elif source.lower() == "openmeteo":
        input_dir = data_dir / "open_meteo_raw"
        file_pattern = "*_OpenMeteo_RAW.csv"
        wind_height = 10.0  # Open-Meteo wind at 10m
        output_suffix = "OpenMeteo_ONLY"
    else:
        logger.error(f"Unknown source: {source}")
        return

    output_dir = base_dir / "data" / f"4_eto_{source.lower()}_only"
    cities_csv = base_dir / "data" / "info_cities.csv"

    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        logger.error(f"Directory not found: {input_dir}")
        return

    logger.info(f"Reading from: {input_dir}")
    logger.info(f"Saving to: {output_dir}")

    # 1. Load city metadata
    logger.info("Loading info_cities.csv...")
    df_cities = pd.read_csv(cities_csv)
    logger.success(f"{len(df_cities)} cities loaded")

    city_info = df_cities.set_index("city")[["lat", "alt"]].to_dict(
        orient="index"
    )

    # 2. Process files
    csv_files = sorted(input_dir.glob(file_pattern))
    logger.info(f"{len(csv_files)} files found")

    all_results = []

    for file_path in csv_files:
        # Extract city name
        # Format: CityName_1991-01-01_2020-12-31_SOURCE_RAW.csv
        filename = file_path.stem
        parts = filename.split("_")
        city_name = None

        # Find where date starts (YYYY-MM-DD)
        for i, part in enumerate(parts):
            if "-" in part and len(part) == 10:
                city_name = "_".join(parts[:i])
                break

        if city_name is None or city_name not in city_info:
            logger.warning(f"City not identified: {filename}")
            continue

        lat = city_info[city_name]["lat"]
        elevation = city_info[city_name]["alt"]

        logger.info(
            f"{city_name} (lat={lat:.2f}, elev={elevation}m, "
            f"wind_h={wind_height}m)"
        )

        df = pd.read_csv(file_path, parse_dates=["date"])

        # Vectorized calculation with correct wind height
        # Wind height is auto-detected based on available column (WS10M or WS2M)
        df["eto_evaonline"] = EToFAO56.calculate_et0(df, lat, elevation)

        # Statistics
        valid = df["eto_evaonline"].notna().sum()
        mean_eto = df["eto_evaonline"].mean()
        logger.success(
            f"{valid:,}/{len(df):,} days | "
            f"Mean ETo = {mean_eto:.3f} mm/day"
        )

        # Save individual file
        output_file = output_dir / f"{city_name}_ETo_{output_suffix}.csv"

        # Basic columns + wind (detect WS2M or WS10M)
        wind_col = "WS2M" if "WS2M" in df.columns else "WS10M"
        cols = [
            "date",
            "T2M_MAX",
            "T2M_MIN",
            "T2M",
            "RH2M",
            wind_col,
            "ALLSKY_SFC_SW_DWN",
            "eto_evaonline",
        ]
        df[cols].to_csv(output_file, index=False, float_format="%.3f")

        all_results.append(
            df[cols].assign(city=city_name, lat=lat, elevation=elevation)
        )

    # 3. Consolidated output
    if not all_results:
        logger.error("No data processed!")
        return

    df_final = pd.concat(all_results, ignore_index=True)
    consolidated_path = (
        output_dir / f"ALL_CITIES_ETo_{output_suffix}_1991_2020.csv"
    )
    df_final.to_csv(consolidated_path, index=False, float_format="%.3f")

    logger.success(f"\nConsolidated file saved: {consolidated_path}")
    logger.success(
        f"Overall mean ETo ({source.upper()}): "
        f"{df_final['eto_evaonline'].mean():.3f} mm/day"
    )
    logger.success(f"PROCESS COMPLETED - {len(csv_files)} cities processed!")


def main():
    """
    Main function with command line argument support.

    Examples:
        # Calculate ETo with NASA POWER
        python 4_calculate_eto_data_from_openmeteo_or_nasapower.py --source nasa

        # Calculate ETo with Open-Meteo
        python 4_calculate_eto_data_from_openmeteo_or_nasapower.py --source openmeteo

        # If no argument, uses Open-Meteo (default)
        python 4_calculate_eto_data_from_openmeteo_or_nasapower.py
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Calculate FAO-56 ETo from RAW data sources "
        "(NASA POWER or Open-Meteo)"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="openmeteo",
        choices=["nasa", "openmeteo"],
        help="Data source: 'nasa' or 'openmeteo' (default: openmeteo)",
    )

    args = parser.parse_args()

    calculate_eto_from_source(source=args.source)


if __name__ == "__main__":
    main()
