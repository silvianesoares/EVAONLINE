"""
Módulo de componentes reutilizáveis para o aplicativo EVAOnline.
"""

from .favorites_components import (
    create_calc_eto_button,
    create_clear_favorites_button,
    create_empty_favorites_alert,
    create_favorite_button,
    create_favorite_item,
    create_favorites_table,
)
from .footer import create_footer
from .navbar import create_navbar
from .world_map_leaflet import create_world_map

# Exportar os componentes
__all__ = [
    "create_navbar",
    "create_footer",
    "create_favorite_button",
    "create_calc_eto_button",
    "create_clear_favorites_button",
    "create_favorite_item",
    "create_favorites_table",
    "create_empty_favorites_alert",
    "create_world_map",
]
