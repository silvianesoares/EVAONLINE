"""
===========================================
DATA PROCESSING MODULE - EVAonline
===========================================
Módulo de processamento de dados climáticos.

Este módulo contém todas as funcionalidades de processamento de dados:
- Download de dados climáticos de múltiplas APIs
- Pré-processamento e validação de dados
- Detecção de outliers e imputação
- Fusão de dados via Kalman Ensemble
- Localização de estações meteorológicas

IMPORTANTE: Este módulo usa imports lazy para evitar dependências circulares.
Todos os imports são feitos apenas quando necessário.
"""

import importlib
from typing import Any


def __getattr__(name: str) -> Any:
    """
    Lazy loading de módulos para evitar imports circulares.

    Args:
        name: Nome do módulo/função a ser importado

    Returns:
        Módulo ou função importada dinamicamente
    """
    lazy_imports = {
        # Data download
        "download_weather_data": (
            "backend.api.services.data_download",
            "download_weather_data",
        ),
        # Data preprocessing
        "data_initial_validate": (
            "backend.core.data_processing.data_preprocessing",
            "data_initial_validate",
        ),
        "detect_outliers_iqr": (
            "backend.core.data_processing.data_preprocessing",
            "detect_outliers_iqr",
        ),
        "data_impute": (
            "backend.core.data_processing.data_preprocessing",
            "data_impute",
        ),
        "preprocessing": (
            "backend.core.data_processing.data_preprocessing",
            "preprocessing",
        ),
        # Kalman ensemble
        "KalmanEnsembleStrategy": (
            "backend.core.data_processing.kalman_ensemble",
            "KalmanEnsembleStrategy",
        ),
        "ClimateKalmanFusion": (
            "backend.core.data_processing.kalman_ensemble",
            "ClimateKalmanFusion",
        ),
        "SimpleKalmanFilter": (
            "backend.core.data_processing.kalman_ensemble",
            "SimpleKalmanFilter",
        ),
        "AdaptiveKalmanFilter": (
            "backend.core.data_processing.kalman_ensemble",
            "AdaptiveKalmanFilter",
        ),
        # Station finder
        "StationFinder": (
            "backend.core.data_processing.station_finder",
            "StationFinder",
        ),
        "find_studied_city_sync": (
            "backend.core.data_processing.station_finder",
            "find_studied_city_sync",
        ),
    }

    if name in lazy_imports:
        module_name, attr_name = lazy_imports[name]
        try:
            module = importlib.import_module(module_name)
            return getattr(module, attr_name)
        except (ImportError, AttributeError) as e:
            raise ImportError(
                f"Could not import {name} from {module_name}: {e}"
            )

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ===========================================
# VERSÃO E METADADOS
# ===========================================

__version__ = "1.2.0"  # Atualizado após correções em kalman_ensemble
__author__ = "EVAonline Team"
__description__ = (
    "Data processing module for climate data analysis and ETo calculation. "
    "Includes optimized preprocessing pipeline with physical validation, "
    "IQR outlier detection, and linear imputation following FAO-56 guidelines. "
    "Enhanced Kalman ensemble filters with improved NaN handling, "
    "input validations, and timestamp support "
    "for accurate data fusion."
)
