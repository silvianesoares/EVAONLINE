"""
Callbacks - Lógica de interação do Dash.
"""

from .cache_callbacks import register_cache_callbacks
from .favorites_callbacks import register_favorites_callbacks
from .home_callbacks import register_home_callbacks
from .location_sync_callbacks import register_location_sync_callbacks
from .navigation_callbacks import register_navigation_callbacks
from .selection_info_callbacks import register_selection_info_callbacks

__all__ = [
    "register_home_callbacks",
    "register_cache_callbacks",
    "register_location_sync_callbacks",
    "register_selection_info_callbacks",
    "register_favorites_callbacks",
    "register_navigation_callbacks",
]
