"""
Tarefa Celery para sincronização periódica de dados de visitantes.

Esta tarefa garante que os dados de contagem de visitantes sejam
persistidos do Redis para PostgreSQL regularmente.
"""

import logging
from typing import Any, Dict

from backend.core.analytics.visitor_counter_service import (
    VisitorCounterService,
)
from backend.database.connection import get_db
from backend.infrastructure.celery.celery_config import celery_app

# from config.settings import get_settings
from config.settings.app_config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(name="backend.infrastructure.celery.tasks.sync_visitor_data")
def sync_visitor_data() -> Dict[str, Any]:
    """
    Tarefa Celery para sincronizar dados de visitantes Redis → PostgreSQL.

    Executada automaticamente a cada 30 minutos pelo Celery Beat.
    Garante persistência dos dados de visitantes mesmo em caso de
    falha do Redis ou reinício do servidor.

    Returns:
        Dict com resultado da sincronização
    """
    try:
        logger.info("🔄 Iniciando sincronização de dados de visitantes")

        # Obter sessão do banco
        db = next(get_db())

        # Criar serviço de visitantes
        import redis

        redis_client = redis.from_url(settings.REDIS_URL)
        service = VisitorCounterService(redis_client, db)

        # Executar sincronização
        result = service.sync_to_database()

        if "error" in result:
            logger.error(f"❌ Erro na sincronização: {result['error']}")
            return result

        logger.info(
            f"✅ Sincronização concluída: {result['total_visitors']} visitantes"
        )
        return result

    except Exception as e:
        error_msg = f"Erro crítico na sincronização de visitantes: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {"error": error_msg}
        return {"error": error_msg}
