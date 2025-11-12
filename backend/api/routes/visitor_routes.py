"""
Rotas para contador de visitantes em tempo real
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import redis

from backend.database.connection import get_db
from backend.database.redis_pool import get_redis_client
from backend.core.analytics.visitor_counter_service import (
    VisitorCounterService,
)

router = APIRouter(prefix="/visitors", tags=["Visitors"])


@router.post("/increment")
async def increment_visitor_count(
    redis_client: redis.Redis = Depends(get_redis_client),
    db: Session = Depends(get_db),
):
    """
    Incrementa contador de visitantes.
    Chamado quando um usuário acessa a aplicação.

    Returns:
        Dict com estatísticas atualizadas
    """
    service = VisitorCounterService(redis_client, db)
    return service.increment_visitor()


@router.get("/stats")
async def get_visitor_stats(
    redis_client: redis.Redis = Depends(get_redis_client),
    db: Session = Depends(get_db),
):
    """
    Retorna estatísticas de visitantes em tempo real.

    Returns:
        Dict com:
        - total_visitors: Total de visitas
        - current_hour_visitors: Visitas na hora atual
        - current_hour: Hora atual (formato HH:00)
        - timestamp: Timestamp UTC
    """
    service = VisitorCounterService(redis_client, db)
    return service.get_stats()


@router.post("/sync")
async def sync_visitor_stats(
    redis_client: redis.Redis = Depends(get_redis_client),
    db: Session = Depends(get_db),
):
    """
    Sincroniza estatísticas do Redis para PostgreSQL.
    Útil para backup e análises de longo prazo.

    Returns:
        Dict com status da sincronização
    """
    service = VisitorCounterService(redis_client, db)
    return service.sync_to_database()


@router.get("/stats/database")
async def get_database_visitor_stats(db: Session = Depends(get_db)):
    """
    Retorna estatísticas persistidas no PostgreSQL.

    Returns:
        Dict com estatísticas do banco de dados
    """
    service = VisitorCounterService(None, db)  # Redis não necessário aqui
    return service.get_database_stats()
