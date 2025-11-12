"""
Callback para contador de visitantes em tempo real.
"""

import logging
import requests
from dash import Input, Output, callback, no_update

logger = logging.getLogger(__name__)

# URL da API backend
API_BASE_URL = "http://localhost:8000/api/v1"


@callback(
    [
        Output("visitor-count", "children"),
        Output("visitor-count-hourly", "children"),
    ],
    Input("visitor-counter-interval", "n_intervals"),
)
def update_visitor_counter(n_intervals):
    """
    Atualiza o contador de visitantes a cada intervalo.

    Args:
        n_intervals: Número de intervalos passados (incrementa a cada 10s)

    Returns:
        Tuple[str, str]: (total_visitors, hourly_visitors)
    """
    try:
        # Chamar API para obter estatísticas
        response = requests.get(f"{API_BASE_URL}/visitors/stats", timeout=3)

        if response.status_code == 200:
            data = response.json()
            total = data.get("total_visitors", 0)
            hourly = data.get("current_hour_visitors", 0)

            logger.debug(f"📊 Visitantes: {total} total, {hourly} última hora")

            return f"{total:,}", f"{hourly:,}"
        else:
            logger.warning(f"⚠️ API retornou status {response.status_code}")
            return "N/A", "N/A"

    except requests.exceptions.Timeout:
        logger.warning("⏱️ Timeout ao buscar estatísticas de visitantes")
        return "...", "..."
    except requests.exceptions.ConnectionError:
        logger.warning(
            "🔌 Erro de conexão ao buscar estatísticas de visitantes"
        )
        return "offline", "offline"
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar contador de visitantes: {e}")
        return "erro", "erro"


# Callback para incrementar visitante quando página carrega
@callback(
    Output("visitor-counter-interval", "n_intervals", allow_duplicate=True),
    Input("url", "pathname"),
    prevent_initial_call=True,
)
def increment_visitor_on_page_load(pathname):
    """
    Incrementa o contador quando usuário acessa qualquer página.

    Args:
        pathname: Caminho da URL atual

    Returns:
        no_update: Não atualiza o n_intervals (apenas trigger para efeito colateral)
    """
    try:
        # Chamar API para incrementar contador
        response = requests.post(
            f"{API_BASE_URL}/visitors/increment", timeout=3
        )

        if response.status_code == 200:
            data = response.json()
            logger.info(
                f"✅ Visitante registrado: {data.get('total_visitors')} total"
            )
        else:
            logger.warning(
                f"⚠️ Falha ao registrar visitante: status {response.status_code}"
            )

    except Exception as e:
        logger.debug(f"Erro ao registrar visitante: {e}")

    return no_update


logger.info("✅ Callbacks de contador de visitantes registrados")
