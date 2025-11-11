import logging
import requests

from geopy.geocoders import Nominatim

# Initialize services
geolocator = Nominatim(user_agent="eto_calculator")

# Configurar logger específico para este módulo
logger = logging.getLogger(__name__)


def get_timezone_from_coordinates(lat, lon):
    """
    Obtém timezone a partir de coordenadas usando OpenTopoData API.

    API: https://www.opentopodata.org/

    Args:
        lat (float): Latitude
        lon (float): Longitude

    Returns:
        str: Timezone (ex: 'America/Sao_Paulo') ou 'UTC' se falhar
    """
    try:
        # OpenTopoData timezone API
        url = f"https://api.opentopodata.org/v1/timezone?locations={lat},{lon}"
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get("results") and len(data["results"]) > 0:
                timezone = data["results"][0].get("timezone")
                if timezone:
                    logger.info(
                        f"Timezone encontrado: {timezone} para ({lat}, {lon})"
                    )
                    return timezone

        logger.warning(
            f"Timezone não encontrado via OpenTopoData para ({lat}, {lon})"
        )
        return "UTC"

    except Exception as e:
        logger.error(f"Erro ao buscar timezone: {e}")
        return "UTC"


def get_timezone(lat, lon):
    """
    Get timezone for given coordinates usando OpenTopoData API.

    Args:
        lat (float): Latitude
        lon (float): Longitude

    Returns:
        str: Timezone ou 'UTC' se falhar
    """
    return get_timezone_from_coordinates(lat, lon)


def get_location_info(lat, lon):
    """
    Get location information using geopy.

    Args:
        lat (float): Latitude
        lon (float): Longitude

    Returns:
        str: Endereço completo ou mensagem de erro
    """
    try:
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        if location:
            return location.address
        return "Localização não encontrada"
    except Exception as e:
        logger.error(
            f"Erro ao obter localização para ({lat:.4f}, {lon:.4f}): {e}"
        )
        return "Localização não disponível"


def format_coordinates(lat, lon):
    """Format coordinates to degrees, minutes, seconds"""

    def to_dms(coord, is_lat):
        if is_lat:
            direction = "N" if coord >= 0 else "S"
        else:
            direction = "E" if coord >= 0 else "O"
        coord = abs(coord)
        degrees = int(coord)
        minutes = int((coord - degrees) * 60)
        seconds = (coord - degrees - minutes / 60) * 3600
        return f"{degrees}°{minutes}′{seconds:.0f}″ {direction}"

    lat_dms = to_dms(lat, True)
    lon_dms = to_dms(lon, False)
    logger.debug(f"🧭 Coordenadas formatadas: {lat_dms}, {lon_dms}")
    return lat_dms, lon_dms


# Log de inicialização bem-sucedida
logger.info("✅ Utilitários de timezone carregados com sucesso")
