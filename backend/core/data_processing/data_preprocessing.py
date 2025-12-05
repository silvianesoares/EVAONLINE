import os
import pickle
from datetime import timedelta
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import redis
from celery import shared_task
from loguru import logger

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CACHE_EXPIRY_HOURS = 24  # 24 hours


def _get_validation_limits(
    region: str = "global",
) -> dict:
    """
    Retorna limites de validação para diferentes regiões.

    Args:
        region: "brazil" (Xavier et al. 2016, 2022) ou
            "global" (limites mundiais)

    Returns:
        Dict[str, Tuple[float, float, str]]: {coluna: (min, max, inclusive)}
    """
    # ─────────────────────────────────────────────────────────────
    # Limites GLOBAIS (mundo inteiro)
    # ─────────────────────────────────────────────────────────────
    global_limits = {
        # NASA POWER
        "T2M_MAX": (-90, 60, "neither"),
        "T2M_MIN": (-90, 60, "neither"),
        "T2M": (-90, 60, "neither"),
        "RH2M": (0, 100, "both"),
        "WS2M": (0, 113, "left"),
        "PRECTOTCORR": (0, 2000, "neither"),
        "ALLSKY_SFC_SW_DWN": (0, 45, "left"),
        # Open-Meteo Archive/Forecast
        "temperature_2m_max": (-90, 60, "neither"),
        "temperature_2m_min": (-90, 60, "neither"),
        "temperature_2m_mean": (-90, 60, "neither"),
        "relative_humidity_2m_max": (0, 100, "both"),
        "relative_humidity_2m_mean": (0, 100, "both"),
        "relative_humidity_2m_min": (0, 100, "both"),
        "wind_speed_10m_max": (0, 113, "left"),
        "wind_speed_10m_mean": (0, 113, "left"),
        "shortwave_radiation_sum": (0, 45, "left"),
        "daylight_duration": (0, 24, "both"),
        "sunshine_duration": (0, 24, "both"),
        "precipitation_sum": (0, 2000, "neither"),
        "et0_fao_evapotranspiration": (0, 20, "left"),
        # MET Norway
        "pressure_mean_sea_level": (800, 1150, "both"),
        "temp_celsius": (-90, 60, "neither"),
        "humidity_percent": (0, 100, "both"),
        # NWS
        "wind_speed_ms": (0, 113, "left"),
        "precipitation_mm": (0, 2000, "neither"),
    }

    # ─────────────────────────────────────────────────────────────
    # Limites BRASIL (Xavier et al. 2016, 2022)
    # "New improved Brazilian daily weather gridded data (1961–2020)"
    # ─────────────────────────────────────────────────────────────
    brazil_limits = {
        # NASA POWER
        "T2M_MAX": (-30, 50, "neither"),
        "T2M_MIN": (-30, 50, "neither"),
        "T2M": (-30, 50, "neither"),
        "RH2M": (0, 100, "both"),
        "WS2M": (0, 100, "left"),
        "PRECTOTCORR": (0, 450, "neither"),
        "ALLSKY_SFC_SW_DWN": (0, 40, "left"),
        # Open-Meteo Archive/Forecast
        "temperature_2m_max": (-30, 50, "neither"),
        "temperature_2m_min": (-30, 50, "neither"),
        "temperature_2m_mean": (-30, 50, "neither"),
        "relative_humidity_2m_max": (0, 100, "both"),
        "relative_humidity_2m_mean": (0, 100, "both"),
        "relative_humidity_2m_min": (0, 100, "both"),
        "wind_speed_10m_max": (0, 100, "left"),
        "wind_speed_10m_mean": (0, 100, "left"),
        "shortwave_radiation_sum": (0, 40, "left"),
        "daylight_duration": (0, 24, "both"),
        "sunshine_duration": (0, 24, "both"),
        "precipitation_sum": (0, 450, "neither"),
        "et0_fao_evapotranspiration": (0, 15, "left"),
        # MET Norway
        "pressure_mean_sea_level": (900, 1100, "both"),
        "temp_celsius": (-30, 50, "neither"),
        "humidity_percent": (0, 100, "both"),
        # NWS
        "wind_speed_ms": (0, 100, "left"),
        "precipitation_mm": (0, 450, "neither"),
    }

    if region.lower() == "brazil":
        logger.info("Usando limites de validação do Brasil (Xavier et al.)")
        return brazil_limits
    else:
        logger.info("Usando limites de validação globais")
        return global_limits


@shared_task
def data_initial_validate(
    weather_df: pd.DataFrame, latitude: float, region: str = "global"
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Validates weather data based on physical limits.

    Physical limits follow scientific literature:
    - **Brazil** (Xavier et al. 2016, 2022):
      - 0 mm < precipitation < 450 mm
      - 0.03Ra ≤ solar_radiation < Ra
      - 0 m/s ≤ wind_speed < 100 m/s
      - -30°C < temperature_max
      - temperature_min < 50°C
    - **Global** (conservative world limits):
      - More relaxed ranges based on world records

    Args:
        weather_df (pd.DataFrame): Weather data with index as datetime and
            columns T2M_MAX, T2M_MIN, T2M, RH2M, WS2M, ALLSKY_SFC_SW_DWN,
            PRECTOTCORR.
        latitude (float): Latitude for calculating extraterrestrial radiation
            (Ra), between -90 and 90.
        region (str): "brazil" for Xavier et al. limits or "global" for
            conservative world limits. Defaults to "global".

    Returns:
        Tuple[pd.DataFrame, List[str]]: Validated DataFrame and list of
            warnings with metrics.

    """
    logger.info("Validating weather data")
    warnings = []

    # Validate latitude
    if not (-90 <= latitude <= 90):
        warnings.append("Latitude must be between -90 and 90.")
        logger.error(warnings[-1])
        raise ValueError(warnings[-1])

    # Validate index
    if not pd.api.types.is_datetime64_any_dtype(weather_df.index):
        msg = "DataFrame index must be in datetime format (YYYY-MM-DD)."
        warnings.append(msg)
        logger.error(msg)
        raise ValueError(msg)

    weather_df = weather_df.copy()
    if isinstance(weather_df.index, pd.DatetimeIndex):
        weather_df["day_of_year"] = weather_df.index.dayofyear.astype(float)
    else:
        raise ValueError("DataFrame index must be DatetimeIndex")

    # Calculate extraterrestrial radiation (Ra) - FAO-56 Eqs. 21-25
    # (Allen et al., 1998) - Optimized with vectorization
    Gsc = 0.0820  # Solar constant [MJ m^-2 min^-1]
    phi = np.radians(latitude)  # Latitude in radians

    unique_days = weather_df["day_of_year"].unique()
    doy_unique = unique_days.astype(float)

    # Eq. 23: Inverse relative distance Earth-Sun
    dr = 1.0 + 0.033 * np.cos(2.0 * np.pi * doy_unique / 365.0)

    # Eq. 24: Solar declination (radians)
    delta = 0.409 * np.sin(2.0 * np.pi * doy_unique / 365.0 - 1.39)

    # Eq. 25: Sunset hour angle (omega_s) with polar case handling
    cos_ws = -np.tan(phi) * np.tan(delta)
    cos_ws = np.clip(cos_ws, -1.0, 1.0)  # Ensure arccos domain

    # Polar cases: sun never sets (ws=pi) or never rises (ws=0)
    omega_s = np.zeros_like(cos_ws)
    omega_s = np.where(cos_ws <= -1.0, np.pi, omega_s)  # Never sets
    omega_s = np.where(
        (cos_ws > -1.0) & (cos_ws < 1.0), np.arccos(cos_ws), omega_s
    )
    # cos_ws >= 1.0 -> sun never rises -> ws = 0 (already zero)

    # Eq. 21: Extraterrestrial radiation
    Ra_unique = (
        (24.0 * 60.0 / np.pi)
        * Gsc
        * dr
        * (
            omega_s * np.sin(phi) * np.sin(delta)
            + np.cos(phi) * np.cos(delta) * np.sin(omega_s)
        )
    )
    Ra_unique = np.maximum(Ra_unique, 0.0)  # Ensure non-negative

    # Create mapping from day_of_year to calculated values
    ra_mapping = dict(zip(unique_days, Ra_unique))
    dr_mapping = dict(zip(unique_days, dr))
    delta_mapping = dict(zip(unique_days, delta))
    omega_s_mapping = dict(zip(unique_days, omega_s))

    # Apply values to DataFrame
    weather_df["Ra"] = weather_df["day_of_year"].map(ra_mapping)
    weather_df["dr"] = weather_df["day_of_year"].map(dr_mapping)
    weather_df["delta"] = weather_df["day_of_year"].map(delta_mapping)
    weather_df["omega_s"] = weather_df["day_of_year"].map(omega_s_mapping)

    # Validate Ra values
    if not (weather_df["Ra"] > 0).all():
        warnings.append("Invalid Ra values detected.")
        logger.error(warnings[-1])

    # Apply physical limits based on region
    # Suporta TODAS as variáveis retornadas pelas 7 fontes de dados para ETo:
    # NASA POWER, Open-Meteo Archive/Forecast,
    # MET Norway Locationforecast/FROST, NWS Forecast/Stations
    limits = _get_validation_limits(region)

    # Validate numeric columns
    for col, (min_val, max_val, inclusive) in limits.items():
        if col in weather_df.columns:
            # Cast inclusive to the correct type for pandas.between()
            inclusive_type = inclusive  # type: ignore
            invalid_mask = ~weather_df[col].between(
                min_val, max_val, inclusive=inclusive_type
            )
            invalid_count = invalid_mask.sum()
            if invalid_count > 0:
                percent_invalid = (invalid_count / len(weather_df)) * 100
                warnings.append(
                    f"Invalid values in {col}: {invalid_count} records "
                    f"({percent_invalid:.2f}%) replaced with NaN."
                )
                logger.warning(warnings[-1])
            weather_df[col] = weather_df[col].where(~invalid_mask, np.nan)

    # Validate solar radiation (NASA: ALLSKY_SFC_SW_DWN MJ/m²/day,
    # Open-Meteo/MET Norway: shortwave_radiation_sum may be in J/m²/day)
    radiation_cols = ["ALLSKY_SFC_SW_DWN"]
    for rad_col in radiation_cols:
        if rad_col in weather_df.columns:
            # Validate against physical limits (0.03*Ra to Ra)
            invalid_rad_mask = ~weather_df[rad_col].between(
                0.03 * weather_df["Ra"], weather_df["Ra"], inclusive="left"
            )
            invalid_count = invalid_rad_mask.sum()
            if invalid_count > 0:
                percent_invalid = (invalid_count / len(weather_df)) * 100
                warnings.append(
                    f"Invalid values in {rad_col}: {invalid_count} records "
                    f"({percent_invalid:.2f}%) replaced with NaN."
                )
                logger.warning(warnings[-1])
            weather_df[rad_col] = weather_df[rad_col].where(
                ~invalid_rad_mask, np.nan
            )

    # Metric: Total invalid values
    invalid_rows = weather_df[weather_df.isna().any(axis=1)]
    if not invalid_rows.empty:
        total_invalid = invalid_rows.isna().sum().sum()
        percent_invalid = (
            total_invalid / (len(weather_df) * len(weather_df.columns))
        ) * 100
        warnings.append(
            f"Total invalid values replaced with NaN: {total_invalid} "
            f"({percent_invalid:.2f}% of data)."
        )
        logger.info(warnings[-1])

    return weather_df, warnings


@shared_task
def detect_outliers_iqr(
    weather_df: pd.DataFrame,
    iqr_factor: float = 1.5,
    max_outlier_percent: float = 5.0,
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Detect outliers using IQR method with adaptive factors for short-term data.

    - Excludes variables with strict physical limits already validated
    - Uses global IQR detection for climate data (optimized for 7-30 days)
    - Applies adaptive IQR factors based on variable type
    - Limits maximum percentage of outliers removed
    - Validates data quality before outlier detection

    Args:
        weather_df (pd.DataFrame): Weather data with datetime index.
        iqr_factor (float): Base factor for IQR bounds (default: 1.5).
        max_outlier_percent (float): Maximum percentage of outliers allowed
            per variable (default: 5.0%).

    Returns:
        Tuple[pd.DataFrame, List[str]]: DataFrame with outliers replaced by NaN
        and list of warnings with metrics.
    """
    logger.info("Detecting outliers with IQR method (optimized for 7-30 days)")
    warnings = []

    weather_df = weather_df.copy()

    # Validate data range for this application version
    if len(weather_df) < 7 or len(weather_df) > 30:
        warnings.append(
            f"WARNING: Data length ({len(weather_df)} days) "
            f"outside supported range (7-30 days). "
            f"Results may be unreliable."
        )
        logger.warning(warnings[-1])

    # Exclude columns that already have strict physical validation
    # These variables have well-defined physical limits, so IQR is redundant
    excluded_cols = {
        "Ra",
        "dr",
        "delta",
        "omega_s",  # Calculated parameters
        # Temperature variables (already validated with physical limits)
        "T2M_MAX",
        "T2M_MIN",
        "T2M",
        "temperature_2m_max",
        "temperature_2m_min",
        "temperature_2m_mean",
        "temp_celsius",
        # Humidity variables (already validated 0-100%)
        "RH2M",
        "relative_humidity_2m_max",
        "relative_humidity_2m_mean",
        "relative_humidity_2m_min",
        "humidity_percent",
        # Wind variables (already validated 0-100 m/s)
        "WS2M",
        "wind_speed_10m_max",
        "wind_speed_10m_mean",
        "wind_speed_ms",
        # Precipitation variables (already validated 0-450 mm)
        "PRECTOTCORR",
        "precipitation_sum",
        "precipitation_mm",
        # Radiation variables (validated with Ra)
        "ALLSKY_SFC_SW_DWN",
        "shortwave_radiation_sum",
        # Duration variables (validated 0-24h)
        "daylight_duration",
        "sunshine_duration",
        # Pressure variables (validated 900-1100 hPa)
        "pressure_mean_sea_level",
        # ETo variables (validated 0-15 mm/day)
        "et0_fao_evapotranspiration",
    }

    # Get numeric columns excluding already validated ones
    numeric_cols = [
        col
        for col in weather_df.columns
        if col not in excluded_cols
        and weather_df[col].dtype
        in [np.float64, np.int64, np.float32, np.int32]
    ]

    if not numeric_cols:
        warnings.append(
            "No numeric columns available for outlier detection "
            "(all variables already have physical validation)."
        )
        logger.info(warnings[-1])
        return weather_df, warnings

    # Adaptive IQR factors based on variable characteristics
    adaptive_factors = {
        # Variables that might have natural variability - use stricter IQR
        "default": iqr_factor,  # 1.5
        # Variables with high natural variability - use more lenient IQR
        "lenient": iqr_factor * 1.5,  # 2.25
        # Variables with low variability - use stricter IQR
        "strict": iqr_factor * 0.8,  # 1.2
    }

    # Determine IQR factor for each variable
    def get_iqr_factor(col_name: str) -> float:
        """Get adaptive IQR factor based on variable name."""
        col_lower = col_name.lower()

        # Strict factors for variables with low expected variability
        if any(
            term in col_lower for term in ["pressure", "duration", "sunshine"]
        ):
            return adaptive_factors["strict"]

        # Lenient factors for variables with high natural variability
        elif any(term in col_lower for term in ["evapotranspiration", "eto"]):
            return adaptive_factors["lenient"]

        # Default factor for others
        else:
            return adaptive_factors["default"]

    total_outliers_removed = 0

    for col in numeric_cols:
        col_data = weather_df[col].dropna()

        # Skip if insufficient data for reliable IQR calculation
        if len(col_data) < 5:  # Minimum for quartile calculation
            warnings.append(
                f"Skipping outlier detection for {col}: "
                f"insufficient data ({len(col_data)} values)."
            )
            continue

        # Check data quality before outlier detection
        if col_data.std() == 0:
            warnings.append(
                f"Skipping outlier detection for {col}: "
                "no variance in data."
            )
            continue

        iqr_factor_adaptive = get_iqr_factor(col)

        # Global IQR detection for short-term data (7-30 days)
        Q1 = col_data.quantile(0.25)
        Q3 = col_data.quantile(0.75)
        IQR = Q3 - Q1

        if IQR > 0:
            lower_bound = Q1 - iqr_factor_adaptive * IQR
            upper_bound = Q3 + iqr_factor_adaptive * IQR
            outlier_mask = (weather_df[col] < lower_bound) | (
                weather_df[col] > upper_bound
            )
            outlier_count = outlier_mask.sum()

            weather_df[col] = weather_df[col].where(~outlier_mask, np.nan)
        else:
            outlier_count = 0

        # Check if outlier percentage exceeds maximum allowed
        if outlier_count > 0:
            percent_outliers = (outlier_count / len(weather_df)) * 100

            if percent_outliers > max_outlier_percent:
                warnings.append(
                    f"WARNING: High outlier percentage in {col}: "
                    f"{outlier_count} outliers ({percent_outliers:.2f}%) "
                    f"exceeds limit of {max_outlier_percent}%. "
                    f"Consider reviewing data quality."
                )
                logger.warning(warnings[-1])

            warnings.append(
                f"Detected {outlier_count} outliers in {col} "
                f"({percent_outliers:.2f}%) using global IQR "
                f"(factor: {iqr_factor_adaptive:.2f})."
            )
            logger.info(warnings[-1])

            total_outliers_removed += outlier_count

    if total_outliers_removed > 0:
        total_percent = (
            total_outliers_removed / (len(weather_df) * len(numeric_cols))
        ) * 100
        warnings.append(
            f"Total outliers removed: {total_outliers_removed} "
            f"({total_percent:.2f}% of remaining data)."
        )
        logger.info(warnings[-1])
    else:
        warnings.append("No outliers detected with IQR method.")
        logger.info(warnings[-1])

    return weather_df, warnings


@shared_task
def data_impute(weather_df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """
    Impute missing weather data using linear interpolation
    (FAO-56 recommendation).

    Args:
        weather_df (pd.DataFrame): Weather data with missing values.

    Returns:
        Tuple[pd.DataFrame, List[str]]: Imputed DataFrame and list of
        warnings with metrics.
    """
    logger.info("Imputing missing weather data")
    warnings = []

    # Validate input DataFrame
    if weather_df.empty:
        warnings.append("Input DataFrame is empty.")
        logger.warning(warnings[-1])
        return weather_df, warnings

    if not pd.api.types.is_datetime64_any_dtype(weather_df.index):
        warnings.append("DataFrame index must be in datetime format.")
        logger.warning(warnings[-1])
        return weather_df, warnings

    weather_df = weather_df.copy()
    numeric_cols = [
        col
        for col in weather_df.columns
        if col not in ["Ra", "dr", "delta", "omega_s"]
        and weather_df[col].dtype
        in [np.float64, np.int64, np.float32, np.int32]
    ]

    for col in numeric_cols:
        missing_count = weather_df[col].isna().sum()
        if missing_count > 0:
            percent_missing = (missing_count / len(weather_df)) * 100
            weather_df[col] = weather_df[col].interpolate(
                method="linear", limit_direction="both"
            )
            warnings.append(
                f"Imputed {missing_count} missing values in {col} "
                f"({percent_missing:.2f}%) using linear interpolation."
            )
            logger.info(warnings[-1])

    # Check for remaining NaNs and apply fallback
    remaining_nans = weather_df[numeric_cols].isna().sum().sum()
    if remaining_nans > 0:
        percent_remaining = (
            remaining_nans / (len(weather_df) * len(numeric_cols))
        ) * 100
        warnings.append(
            f"Warning: {remaining_nans} missing values "
            f"({percent_remaining:.2f}%) could not be imputed "
            f"with interpolation."
        )
        logger.warning(warnings[-1])
        # Fallback: Forward-fill, then backward-fill, then mean
        for col in numeric_cols:
            if weather_df[col].isna().any():
                # Try forward-fill first
                weather_df[col] = weather_df[col].ffill()
                # Then backward-fill for remaining NaNs
                weather_df[col] = weather_df[col].bfill()
                # Finally, use mean for any remaining NaNs
                if weather_df[col].isna().any():
                    weather_df[col] = weather_df[col].fillna(
                        weather_df[col].mean()
                    )
                    warnings.append(
                        f"Filled remaining NaNs in {col} with "
                        f"mean value after forward/backward fill."
                    )
                    logger.info(warnings[-1])

    return weather_df, warnings


@shared_task
def preprocessing(
    weather_df: pd.DataFrame,
    latitude: float,
    cache_key: Optional[str] = None,
    region: str = "global",
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Preprocessing pipeline: validation, outlier detection, and imputation.

    This function implements the complete preprocessing pipeline for climate
    data used in ETo calculations. Input data should already be spatially
    interpolated (e.g., via IDW/ADW methods as described in Xavier et al.
    2022). The pipeline follows FAO-56 recommendations for temporal
    imputation.

    Args:
        weather_df (pd.DataFrame): Weather data with datetime index.
        latitude (float): Latitude for Ra calculation, between -90 and 90.
        cache_key (Optional[str]): Key for caching results in Redis.
        region (str): "brazil" (Xavier et al. 2016, 2022) or "global"
            (conservative world limits). Defaults to "global".

    Returns:
        Tuple[pd.DataFrame, List[str]]: Preprocessed DataFrame and list of
        warnings with metrics.

    """

    logger.info("Starting preprocessing pipeline")
    warnings = []

    # Validate input DataFrame
    if weather_df.empty:
        warnings.append("Input DataFrame is empty.")
        logger.error(warnings[-1])
        raise ValueError(warnings[-1])

    if not pd.api.types.is_datetime64_any_dtype(weather_df.index):
        msg = "DataFrame index must be in datetime format (YYYY-MM-DD)."
        warnings.append(msg)
        logger.error(msg)
        raise ValueError(msg)

    # Validate latitude
    if not (-90 <= latitude <= 90):
        warnings.append("Latitude must be between -90 and 90.")
        logger.error(warnings[-1])
        raise ValueError(warnings[-1])

    # Initialize Redis client
    redis_client = None
    if cache_key:
        try:
            redis_client = redis.Redis.from_url(
                REDIS_URL, decode_responses=False
            )
            redis_client.ping()  # Test connection
            cached_data = redis_client.get(cache_key)
            if cached_data:
                try:
                    df = pickle.loads(cached_data)
                    logger.info(
                        f"Loaded preprocessed data from Redis cache: "
                        f"{cache_key}"
                    )
                    return df, ["Loaded from cache"]
                except (pickle.UnpicklingError, EOFError) as e:
                    warnings.append(f"Failed to unpickle cached data: {e}")
                    logger.warning(warnings[-1])
                    # Continue with processing if cache is corrupted
        except redis.ConnectionError as e:
            warnings.append(f"Redis connection failed: {e}")
            logger.warning(warnings[-1])
        except redis.RedisError as e:
            warnings.append(f"Redis error: {e}")
            logger.warning(warnings[-1])
        except Exception as e:
            warnings.append(f"Unexpected cache error: {e}")
            logger.error(warnings[-1])

    # Step 1: Initial validation
    weather_df, validate_warnings = data_initial_validate(
        weather_df, latitude, region
    )
    warnings.extend(validate_warnings)

    # Step 2: Outlier detection with IQR
    weather_df, outlier_warnings = detect_outliers_iqr(
        weather_df, iqr_factor=1.5
    )
    warnings.extend(outlier_warnings)

    # Step 3: Imputation
    weather_df, impute_warnings = data_impute(weather_df)
    warnings.extend(impute_warnings)

    # Save to cache
    if redis_client and cache_key:
        try:
            redis_client.setex(
                cache_key,
                timedelta(hours=CACHE_EXPIRY_HOURS),
                pickle.dumps(weather_df),
            )
            logger.info(f"Saved preprocessed data to Redis cache: {cache_key}")
        except redis.ConnectionError as e:
            warnings.append(f"Redis connection failed during save: {e}")
            logger.warning(warnings[-1])
        except (pickle.PicklingError, TypeError) as e:
            warnings.append(f"Failed to pickle data for cache: {e}")
            logger.warning(warnings[-1])
        except redis.RedisError as e:
            warnings.append(f"Redis save error: {e}")
            logger.warning(warnings[-1])
        except Exception as e:
            warnings.append(f"Unexpected cache save error: {e}")
            logger.error(warnings[-1])

    # Final summary: Count total operations performed
    total_invalid = sum(
        1
        for w in warnings
        if "Invalid values" in w and any(char.isdigit() for char in w)
    )
    total_outliers = sum(
        1
        for w in warnings
        if "outliers" in w and any(char.isdigit() for char in w)
    )
    total_imputed = sum(
        1
        for w in warnings
        if "missing values" in w and any(char.isdigit() for char in w)
    )

    warnings.append(
        f"Preprocessing summary: {total_invalid} validation "
        f"corrections, {total_outliers} outlier removals, "
        f"{total_imputed} imputations performed."
    )
    logger.info(warnings[-1])

    return weather_df, warnings
