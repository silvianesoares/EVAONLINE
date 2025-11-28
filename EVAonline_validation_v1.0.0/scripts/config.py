"""
This module defines paths, city metadata, validation parameters,
and metrics configuration for the validation pipeline.
"""

from pathlib import Path
from typing import Dict, List, Any

# ============================================================================
# PATHS CONFIGURATION
# ============================================================================

# Root directories
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "original_data"
VALIDATION_DIR = PROJECT_ROOT / "data" / "6_validation_full_pipeline"

# Input data paths
XAVIER_ETO_DIR = DATA_DIR / "eto_xavier_csv"  # Reference ETo (Xavier BR-DWGD)
OPENMETEO_ETO_DIR = DATA_DIR / "eto_open_meteo"  # OpenMeteo calculated ETo

# Output paths
RESULTS_DIR = VALIDATION_DIR
XAVIER_RESULTS_DIR = RESULTS_DIR / "xavier_validation"
OPENMETEO_RESULTS_DIR = RESULTS_DIR / "openmeteo_validation"
CONSOLIDATED_DIR = RESULTS_DIR / "consolidated"


# ============================================================================
# CITY METADATA
# ============================================================================

# Metadados complementares (coordenadas vêm do info_cities.csv)
BRASIL_CITIES = {
    "Alvorada_do_Gurgueia_PI": {
        "name": "Alvorada do Gurgueia",
        "country": "Brazil",
        "state": "PI",
        "lat": -8.443,
        "lon": -43.863,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Araguaina_TO": {
        "name": "Araguaína",
        "country": "Brazil",
        "state": "TO",
        "lat": -7.191,
        "lon": -48.208,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Balsas_MA": {
        "name": "Balsas",
        "country": "Brazil",
        "state": "MA",
        "lat": -7.531,
        "lon": -48.038,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Barreiras_BA": {
        "name": "Barreiras",
        "country": "Brazil",
        "state": "BA",
        "lat": -12.144,
        "lon": -45.004,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Bom_Jesus_PI": {
        "name": "Bom Jesus",
        "country": "Brazil",
        "state": "PI",
        "lat": -9.070,
        "lon": -44.360,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Campos_Lindos_TO": {
        "name": "Campos Lindos",
        "country": "Brazil",
        "state": "TO",
        "lat": -7.971,
        "lon": -46.801,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Carolina_MA": {
        "name": "Carolina",
        "country": "Brazil",
        "state": "MA",
        "lat": -7.331,
        "lon": -47.470,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Corrente_PI": {
        "name": "Corrente",
        "country": "Brazil",
        "state": "PI",
        "lat": -10.441,
        "lon": -45.163,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Formosa_do_Rio_Preto_BA": {
        "name": "Formosa do Rio Preto",
        "country": "Brazil",
        "state": "BA",
        "lat": -11.047,
        "lon": -45.191,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Imperatriz_MA": {
        "name": "Imperatriz",
        "country": "Brazil",
        "state": "MA",
        "lat": -5.526,
        "lon": -47.479,
        "climate": "Tropical monsoon (Am)",
        "region": "MATOPIBA",
    },
    "Luiz_Eduardo_Magalhaes_BA": {
        "name": "Luiz Eduardo Magalhães",
        "country": "Brazil",
        "state": "BA",
        "lat": -12.078,
        "lon": -45.800,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Pedro_Afonso_TO": {
        "name": "Pedro Afonso",
        "country": "Brazil",
        "state": "TO",
        "lat": -8.964,
        "lon": -48.177,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Piracicaba_SP": {
        "name": "Piracicaba",
        "country": "Brazil",
        "lat": -22.725,
        "lon": -47.647,
        "state": "SP",
        "climate": "Humid subtropical (Cfa)",
        "region": "Southeast",
    },
    "Porto_Nacional_TO": {
        "name": "Porto Nacional",
        "country": "Brazil",
        "state": "TO",
        "lat": -10.708,
        "lon": -48.412,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Sao_Desiderio_BA": {
        "name": "São Desidério",
        "country": "Brazil",
        "state": "BA",
        "lat": -12.360,
        "lon": -44.974,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Tasso_Fragoso_MA": {
        "name": "Tasso Fragoso",
        "country": "Brazil",
        "state": "MA",
        "lat": -8.479,
        "lon": -45.744,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Urucui_PI": {
        "name": "Uruçuí",
        "country": "Brazil",
        "state": "PI",
        "lat": -7.229,
        "lon": -44.560,
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
}

MUNDO_CITIES = {
    "Addis_Ababa_Ethiopia": {
        "name": "Addis Ababa",
        "country": "Ethiopia",
        "lat": 9.03,
        "lon": 38.74,
        "climate": "Tropical highland (Cwb)",
        "continent": "Africa",
    },
    "Des_Moines_IA": {
        "name": "Des Moines",
        "country": "USA",
        "lat": 41.59,
        "lon": -93.62,
        "climate": "Humid continental (Dfa)",
        "continent": "North America",
    },
    "Fresno_CA": {
        "name": "Fresno",
        "country": "USA",
        "lat": 36.75,
        "lon": -119.77,
        "climate": "Mediterranean hot (Csa)",
        "continent": "North America",
    },
    "Hanoi_Vietnam": {
        "name": "Hanoi",
        "country": "Vietnam",
        "lat": 21.03,
        "lon": 105.85,
        "climate": "Humid subtropical (Cwa)",
        "continent": "Asia",
    },
    "Krasnodar_Russia": {
        "name": "Krasnodar",
        "country": "Russia",
        "lat": 45.04,
        "lon": 38.98,
        "climate": "Humid subtropical (Cfa)",
        "continent": "Europe",
    },
    "Ludhiana_Punjab": {
        "name": "Ludhiana",
        "country": "India",
        "lat": 30.90,
        "lon": 75.85,
        "climate": "Semi-arid (BSh)",
        "continent": "Asia",
    },
    "Mendoza_Argentina": {
        "name": "Mendoza",
        "country": "Argentina",
        "lat": -32.89,
        "lon": -68.83,
        "climate": "Arid cold (BWk)",
        "continent": "South America",
    },
    "Polokwane_Limpopo": {
        "name": "Polokwane",
        "country": "South Africa",
        "lat": -23.90,
        "lon": 29.47,
        "climate": "Semi-arid (BSh)",
        "continent": "Africa",
    },
    "Seville_Spain": {
        "name": "Seville",
        "country": "Spain",
        "lat": 37.39,
        "lon": -5.98,
        "climate": "Mediterranean (Csa)",
        "continent": "Europe",
    },
    "Wagga_Wagga_Australia": {
        "name": "Wagga Wagga",
        "country": "Australia",
        "lat": -35.12,
        "lon": 147.37,
        "climate": "Semi-arid (BSk)",
        "continent": "Oceania",
    },
}


# ============================================================================
# VALIDATION PARAMETERS
# ============================================================================

# Date ranges for validation
VALIDATION_PERIOD = {
    "brasil": {"start": "1991-01-01", "end": "2020-12-31"},
    "mundo": {"start": "1991-01-01", "end": "2020-12-31"},
}

# Metrics to calculate
VALIDATION_METRICS = [
    "mae",  # Mean Absolute Error (mm/day)
    "rmse",  # Root Mean Square Error (mm/day)
    "mbe",  # Mean Bias Error (mm/day)
    "mape",  # Mean Absolute Percentage Error (%)
    "r",  # Pearson correlation coefficient
    "r2",  # Coefficient of determination
    "nse",  # Nash-Sutcliffe Efficiency
    "d",  # Willmott's Index of Agreement
    "kge",  # Kling-Gupta Efficiency
    "pbias",  # Percent Bias (%)
]

# Thresholds for quality assessment
QUALITY_THRESHOLDS = {
    "excellent": {
        "mae": 0.30,
        "rmse": 0.40,
        "r2": 0.90,
        "nse": 0.85,
        "d": 0.95,
    },
    "good": {"mae": 0.50, "rmse": 0.70, "r2": 0.80, "nse": 0.75, "d": 0.90},
    "acceptable": {
        "mae": 0.80,
        "rmse": 1.00,
        "r2": 0.70,
        "nse": 0.60,
        "d": 0.80,
    },
}

# Statistical significance level
SIGNIFICANCE_LEVEL = 0.05


# ============================================================================
# VISUALIZATION SETTINGS
# ============================================================================

PLOT_CONFIG = {
    "figure_size": (12, 8),
    "dpi": 300,
    "font_size": 12,
    "title_size": 14,
    "label_size": 12,
    "legend_size": 10,
    "color_palette": "Set2",
    "grid": True,
    "grid_alpha": 0.3,
}

# Colors for different regions/continents
REGION_COLORS = {
    "MATOPIBA": "#1f77b4",
    "Southeast": "#ff7f0e",
    "Africa": "#2ca02c",
    "Asia": "#d62728",
    "Europe": "#9467bd",
    "North America": "#8c564b",
    "South America": "#e377c2",
    "Oceania": "#7f7f7f",
}


# ============================================================================
# ETO CALCULATION PARAMETERS
# ============================================================================

# FAO-56 Penman-Monteith constants
FAO56_CONSTANTS = {
    "stefan_boltzmann": 4.903e-9,  # MJ K⁻⁴ m⁻² day⁻¹ (Eq. 39)
    "specific_heat": 1.013e-3,  # MJ kg⁻¹ °C⁻¹ (Eq. 8)
    "latent_heat": 2.45,  # MJ kg⁻¹ (Eq. 8)
    "psychrometric_coeff": 6.65e-4,  # kPa °C⁻¹ (Eq. 8) → γ = coeff × P
    "albedo": 0.23,  # dimensionless
    "crop_height": 0.12,  # m (grass reference)
    "surface_resistance": 70.0,  # s m⁻¹ (grass reference)
    "solar_constant": 0.0820,  # MJ m⁻² min⁻¹ (Eq. 21)
}

# Wind speed measurement height adjustment
WIND_HEIGHT = {
    "measurement": 10.0,  # Standard measurement height (m)
    "reference": 2.0,  # Reference height for ETo calculation (m)
}


# ============================================================================
# DATA QUALITY FILTERS
# ============================================================================

# Physical ranges for data validation (based on WMO/NOAA extremes)
PHYSICAL_RANGES = {
    "temperature_max": {"min": -90, "max": 60},  # °C
    "temperature_min": {"min": -90, "max": 60},  # °C
    "humidity": {"min": 0, "max": 100},  # %
    "wind_speed": {"min": 0, "max": 120},  # m/s
    "precipitation": {"min": 0, "max": 2000},  # mm/day
    "solar_radiation": {"min": 0, "max": 35},  # MJ/m²/day
}

# Statistical outlier detection parameters
OUTLIER_DETECTION = {
    "method": "iqr",  # Inter-Quartile Range method
    "iqr_factor": 1.5,  # Standard IQR multiplier
    "zscore_threshold": 3.0,  # Z-score threshold for extreme outliers
}


# ============================================================================
# REPORTING CONFIGURATION
# ============================================================================

# Report sections to generate
REPORT_SECTIONS = [
    "executive_summary",
    "methodology",
    "brasil_validation",
    "global_validation",
    "regional_analysis",
    "seasonal_analysis",
    "error_analysis",
    "recommendations",
    "references",
]

# Export formats
EXPORT_FORMATS = {
    "tables": ["csv", "xlsx", "latex"],
    "plots": ["png", "pdf", "svg"],
    "reports": ["pdf", "html", "docx"],
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_city_metadata(city_key: str) -> Dict[str, Any]:
    """
    Retrieve metadata for a specific city.

    Args:
        city_key: City identifier (e.g., 'Barreiras_BA')

    Returns:
        Dictionary with city metadata
    """
    return BRASIL_CITIES.get(city_key, {})


def get_all_cities() -> List[str]:
    """
    Get list of all city identifiers.

    Returns:
        List of city keys
    """
    return list(BRASIL_CITIES.keys())


def get_xavier_eto_path(city_key: str) -> Path:
    """
    Get path to Xavier reference ETo CSV file.

    Args:
        city_key: City identifier (e.g., 'Barreiras_BA')

    Returns:
        Path object to Xavier ETo CSV file
    """
    return XAVIER_ETO_DIR / f"{city_key}.csv"


def get_openmeteo_eto_path(city_key: str) -> Path:
    """
    Get path to OpenMeteo calculated ETo CSV file.

    Args:
        city_key: City identifier (e.g., 'Barreiras_BA')

    Returns:
        Path object to OpenMeteo ETo CSV file
    """
    return OPENMETEO_ETO_DIR / f"{city_key}_OpenMeteo_ETo.csv"


def get_output_path(
    city_key: str, validation_type: str, output_type: str, filename: str
) -> Path:
    """
    Get standardized output path for validation results.

    Args:
        city_key: City identifier
        validation_type: 'xavier' or 'openmeteo'
        output_type: 'metrics', 'plots', or 'timeseries'
        filename: Output filename

    Returns:
        Path object to output file
    """
    base_dir = (
        XAVIER_RESULTS_DIR
        if validation_type == "xavier"
        else OPENMETEO_RESULTS_DIR
    )
    output_dir = base_dir / output_type
    return output_dir / filename


if __name__ == "__main__":
    # Test configuration
    print("EVAonline Validation Configuration")
    print("=" * 50)
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Data Directory: {DATA_DIR}")
    print(f"Xavier ETo Directory: {XAVIER_ETO_DIR}")
    print(f"OpenMeteo ETo Directory: {OPENMETEO_ETO_DIR}")
    print(f"Results Directory: {RESULTS_DIR}")
    print(f"\nBrazil Cities: {len(BRASIL_CITIES)}")
    print(f"Total Cities: {len(get_all_cities())}")
    print(f"\nValidation Metrics: {', '.join(VALIDATION_METRICS)}")
    print(f"\nSample Xavier ETo: {get_xavier_eto_path('Piracicaba_SP')}")
    print(f"Sample OpenMeteo ETo: {get_openmeteo_eto_path('Piracicaba_SP')}")
