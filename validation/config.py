"""
Central configuration for EVAonline validation framework.

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
DATA_DIR = PROJECT_ROOT / "data" / "csv"
VALIDATION_DIR = PROJECT_ROOT / "validation"

# Input data paths
BRASIL_DIR = DATA_DIR / "BRASIL"
MUNDO_DIR = DATA_DIR / "MUNDO"

BRASIL_ETO_DIR = BRASIL_DIR / "ETo"
BRASIL_PR_DIR = BRASIL_DIR / "pr"

MUNDO_ETO_DIR = MUNDO_DIR / "ETo"
MUNDO_PR_DIR = MUNDO_DIR / "pr"

# Output paths
RESULTS_DIR = VALIDATION_DIR / "results"
BRASIL_RESULTS_DIR = RESULTS_DIR / "brasil"
MUNDO_RESULTS_DIR = RESULTS_DIR / "mundo"
CONSOLIDATED_DIR = RESULTS_DIR / "consolidated"

# Create subdirectories
for region in [BRASIL_RESULTS_DIR, MUNDO_RESULTS_DIR]:
    (region / "metrics").mkdir(parents=True, exist_ok=True)
    (region / "plots").mkdir(parents=True, exist_ok=True)
    (region / "timeseries").mkdir(parents=True, exist_ok=True)

CONSOLIDATED_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# CITY METADATA
# ============================================================================

# Metadados complementares (coordenadas vêm do info_cities.csv)
# Elevação obtida via TopoData em tempo real (SRTM 30m)
BRASIL_CITIES = {
    "Alvorada_do_Gurgueia_PI": {
        "name": "Alvorada do Gurgueia",
        "state": "PI",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Araguaina_TO": {
        "name": "Araguaína",
        "state": "TO",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Balsas_MA": {
        "name": "Balsas",
        "state": "MA",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Barreiras_BA": {
        "name": "Barreiras",
        "state": "BA",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Bom_Jesus_PI": {
        "name": "Bom Jesus",
        "state": "PI",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Campos_Lindos_TO": {
        "name": "Campos Lindos",
        "state": "TO",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Carolina_MA": {
        "name": "Carolina",
        "state": "MA",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Corrente_PI": {
        "name": "Corrente",
        "state": "PI",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Formosa_do_Rio_Preto_BA": {
        "name": "Formosa do Rio Preto",
        "state": "BA",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Imperatriz_MA": {
        "name": "Imperatriz",
        "state": "MA",
        "climate": "Tropical monsoon (Am)",
        "region": "MATOPIBA",
    },
    "Luiz_Eduardo_Magalhaes_BA": {
        "name": "Luiz Eduardo Magalhães",
        "state": "BA",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Pedro_Afonso_TO": {
        "name": "Pedro Afonso",
        "state": "TO",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Piracicaba_SP": {
        "name": "Piracicaba",
        "state": "SP",
        "climate": "Humid subtropical (Cfa)",
        "region": "Southeast",
    },
    "Porto_Nacional_TO": {
        "name": "Porto Nacional",
        "state": "TO",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Sao_Desiderio_BA": {
        "name": "São Desidério",
        "state": "BA",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Tasso_Fragoso_MA": {
        "name": "Tasso Fragoso",
        "state": "MA",
        "climate": "Tropical savanna (Aw)",
        "region": "MATOPIBA",
    },
    "Urucui_PI": {
        "name": "Uruçuí",
        "state": "PI",
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
        "elevation": 2355,
        "climate": "Tropical highland (Cwb)",
        "continent": "Africa",
    },
    "Des_Moines_IA": {
        "name": "Des Moines",
        "country": "USA",
        "lat": 41.59,
        "lon": -93.62,
        "elevation": 292,
        "climate": "Humid continental (Dfa)",
        "continent": "North America",
    },
    "Fresno_CA": {
        "name": "Fresno",
        "country": "USA",
        "lat": 36.75,
        "lon": -119.77,
        "elevation": 94,
        "climate": "Mediterranean hot (Csa)",
        "continent": "North America",
    },
    "Hanoi_Vietnam": {
        "name": "Hanoi",
        "country": "Vietnam",
        "lat": 21.03,
        "lon": 105.85,
        "elevation": 16,
        "climate": "Humid subtropical (Cwa)",
        "continent": "Asia",
    },
    "Krasnodar_Russia": {
        "name": "Krasnodar",
        "country": "Russia",
        "lat": 45.04,
        "lon": 38.98,
        "elevation": 28,
        "climate": "Humid subtropical (Cfa)",
        "continent": "Europe",
    },
    "Ludhiana_Punjab": {
        "name": "Ludhiana",
        "country": "India",
        "lat": 30.90,
        "lon": 75.85,
        "elevation": 247,
        "climate": "Semi-arid (BSh)",
        "continent": "Asia",
    },
    "Mendoza_Argentina": {
        "name": "Mendoza",
        "country": "Argentina",
        "lat": -32.89,
        "lon": -68.83,
        "elevation": 827,
        "climate": "Arid cold (BWk)",
        "continent": "South America",
    },
    "Polokwane_Limpopo": {
        "name": "Polokwane",
        "country": "South Africa",
        "lat": -23.90,
        "lon": 29.47,
        "elevation": 1310,
        "climate": "Semi-arid (BSh)",
        "continent": "Africa",
    },
    "Seville_Spain": {
        "name": "Seville",
        "country": "Spain",
        "lat": 37.39,
        "lon": -5.98,
        "elevation": 11,
        "climate": "Mediterranean (Csa)",
        "continent": "Europe",
    },
    "Wagga_Wagga_Australia": {
        "name": "Wagga Wagga",
        "country": "Australia",
        "lat": -35.12,
        "lon": 147.37,
        "elevation": 212,
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
    "mundo": {"start": "2015-01-01", "end": "2024-12-31"},
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
    "stefan_boltzmann": 4.903e-9,  # Stefan-Boltzmann constant (MJ K⁻⁴ m⁻² day⁻¹)
    "specific_heat": 0.001013,  # Specific heat at constant pressure (MJ kg⁻¹ °C⁻¹)
    "latent_heat": 2.45,  # Latent heat of vaporization (MJ kg⁻¹)
    "psychrometric": 0.000665,  # Psychrometric constant coefficient (kPa °C⁻¹)
    "albedo": 0.23,  # Reference crop albedo
    "crop_height": 0.12,  # Reference crop height (m)
    "surface_resistance": 70,  # Surface resistance (s m⁻¹)
    "gsc": 0.0820,  # Solar constant (MJ m⁻² min⁻¹)
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
    "rolling_window": 30,  # Rolling window for temporal outlier detection (days)
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


def get_city_metadata(city_key: str, region: str = "brasil") -> Dict[str, Any]:
    """
    Retrieve metadata for a specific city.

    Args:
        city_key: City identifier (e.g., 'Barreiras_BA')
        region: 'brasil' or 'mundo'

    Returns:
        Dictionary with city metadata
    """
    cities = BRASIL_CITIES if region == "brasil" else MUNDO_CITIES
    return cities.get(city_key, {})


def get_all_cities(region: str = "both") -> List[str]:
    """
    Get list of all city identifiers.

    Args:
        region: 'brasil', 'mundo', or 'both'

    Returns:
        List of city keys
    """
    if region == "brasil":
        return list(BRASIL_CITIES.keys())
    elif region == "mundo":
        return list(MUNDO_CITIES.keys())
    else:  # both
        return list(BRASIL_CITIES.keys()) + list(MUNDO_CITIES.keys())


def get_eto_file_path(city_key: str, region: str = "brasil") -> Path:
    """
    Get path to reference ETo CSV file.

    Args:
        city_key: City identifier
        region: 'brasil' or 'mundo'

    Returns:
        Path object to ETo CSV file
    """
    if region == "brasil":
        return BRASIL_ETO_DIR / f"{city_key}.csv"
    else:
        return MUNDO_ETO_DIR / f"{city_key}.csv"


def get_pr_file_path(city_key: str, region: str = "brasil") -> Path:
    """
    Get path to precipitation CSV file.

    Args:
        city_key: City identifier
        region: 'brasil' or 'mundo'

    Returns:
        Path object to precipitation CSV file
    """
    if region == "brasil":
        return BRASIL_PR_DIR / f"{city_key}.csv"
    else:
        return MUNDO_PR_DIR / f"{city_key}.csv"


def get_output_path(
    city_key: str, region: str, output_type: str, filename: str
) -> Path:
    """
    Get standardized output path for validation results.

    Args:
        city_key: City identifier
        region: 'brasil' or 'mundo'
        output_type: 'metrics', 'plots', or 'timeseries'
        filename: Output filename

    Returns:
        Path object to output file
    """
    base_dir = BRASIL_RESULTS_DIR if region == "brasil" else MUNDO_RESULTS_DIR
    output_dir = base_dir / output_type
    return output_dir / filename


if __name__ == "__main__":
    # Test configuration
    print("EVAonline Validation Configuration")
    print("=" * 50)
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Data Directory: {DATA_DIR}")
    print(f"Results Directory: {RESULTS_DIR}")
    print(f"\nBrazil Cities: {len(BRASIL_CITIES)}")
    print(f"Global Cities: {len(MUNDO_CITIES)}")
    print(f"Total Cities: {len(get_all_cities('both'))}")
    print(f"\nValidation Metrics: {', '.join(VALIDATION_METRICS)}")
