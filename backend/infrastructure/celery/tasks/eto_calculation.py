"""
Task Celery para cálculo ETo com progresso em tempo real.

Integra:
- ClimateSourceManager: Seleção de fontes por localização
- EToProcessingService: Pipeline completo de ETo
- WebSocket: Broadcasting de progresso
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import datetime
from typing import Any

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    name="backend.infrastructure.celery.tasks.calculate_eto_task",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,  # Max 10 minutos entre retries
    retry_jitter=True,
)
def calculate_eto_task(
    self,
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    sources: list[str] | None = None,
    elevation: float | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """
    Calcula ETo para localização com progresso em tempo real.

    Args:
        self: Contexto Celery (bind=True)
        lat, lon: Coordenadas
        start_date, end_date: Período (YYYY-MM-DD)
        sources: Fontes climáticas (None = auto-select)
        elevation: Elevação em metros (None = buscar via OpenTopo)
        mode: Modo de operação (None = auto-detect)

    Returns:
        Dict com resultado completo:
        {
            "summary": {...},
            "et0_series": [...],
            "quality_metrics": {...},
            "sources_used": [...],
            "task_id": "abc-123",
            "processing_time_seconds": 12.5
        }

    Raises:
        ValidationError: Se parâmetros inválidos
        APIError: Se todas as fontes falharem
    """
    import asyncio
    from backend.core.eto_calculation.eto_services import EToProcessingService
    from backend.database.connection import get_db
    from backend.api.services.climate_validation import (
        ClimateValidationService,
    )
    from backend.api.services.climate_source_manager import (
        ClimateSourceManager,
    )
    from backend.api.services.climate_source_availability import (
        OperationMode,
    )

    task_id = self.request.id
    start_time = datetime.now()

    try:
        # ========== STEP 1: VALIDAÇÃO (5%) ==========
        self.update_state(
            state="PROGRESS",
            meta={
                "progress": 5,
                "step": "validation",
                "message": "Validando parâmetros...",
            },
        )

        # Validar coordenadas
        if not ClimateValidationService.validate_coordinates(lat, lon)[0]:
            raise ValueError(f"Coordenadas inválidas: ({lat}, {lon})")

        # Converter datas
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # Auto-detectar modo se não fornecido
        if mode is None:
            detected_mode, error = (
                ClimateValidationService.detect_mode_from_dates(
                    start_date, end_date
                )
            )
            if detected_mode:
                mode = detected_mode
                logger.info(f"✅ Modo auto-detectado: {mode}")
            else:
                mode = OperationMode.DASHBOARD_CURRENT.value
                logger.warning(f"⚠️  Modo não detectado, usando padrão: {mode}")

        logger.info(
            f"📍 Task {task_id}: ETo para ({lat}, {lon}) "
            f"de {start_date} a {end_date} - Modo: {mode}"
        )

        # ========== STEP 2: SELEÇÃO DE FONTES (10%) ==========
        self.update_state(
            state="PROGRESS",
            meta={
                "progress": 10,
                "step": "source_selection",
                "message": "Selecionando melhores fontes climáticas...",
            },
        )

        manager = ClimateSourceManager()
        source_info = manager.get_sources_for_data_download(
            lat=lat,
            lon=lon,
            start_date=start_dt,
            end_date=end_dt,
            mode=mode,
            preferred_sources=sources,
        )

        selected_sources = source_info["sources"]
        region = source_info["location_info"]["region"]

        logger.info(
            f"🔍 Fontes selecionadas para {region}: {selected_sources}"
        )

        # ========== STEP 3: PROCESSAMENTO ETo (20-90%) ==========
        self.update_state(
            state="PROGRESS",
            meta={
                "progress": 20,
                "step": "eto_processing",
                "message": (
                    f"Processando dados de {len(selected_sources)} fontes..."
                ),
                "sources": selected_sources,
                "region": region,
            },
        )

        # Inicializar serviço de processamento
        db = next(get_db())
        service = EToProcessingService(db_session=db)

        # ========== STEP 4: CÁLCULO ETo (60-90%) ==========
        self.update_state(
            state="PROGRESS",
            meta={
                "progress": 60,
                "step": "eto_calculation",
                "message": "Calculando ETo (FAO-56 Penman-Monteith)...",
            },
        )

        # O process_location_with_sources já faz download +
        # processamento completo
        result = asyncio.run(
            service.process_location_with_sources(
                latitude=lat,
                longitude=lon,
                start_date=start_date,
                end_date=end_date,
                sources=selected_sources,
                elevation=elevation,
            )
        )

        # ========== STEP 5: FINALIZAÇÃO (90-100%) ==========
        self.update_state(
            state="PROGRESS",
            meta={
                "progress": 90,
                "step": "finalization",
                "message": "Preparando resultado final...",
            },
        )

        processing_time = (datetime.now() - start_time).total_seconds()

        final_result = {
            **result["data"],  # Usar apenas os dados do resultado
            "task_id": task_id,
            "processing_time_seconds": round(processing_time, 2),
            "sources_used": selected_sources,
            "location_info": source_info["location_info"],
            "mode": mode,
        }

        self.update_state(
            state="PROGRESS",
            meta={
                "progress": 100,
                "step": "completed",
                "message": "✅ Cálculo ETo concluído!",
            },
        )

        logger.info(
            f"✅ Task {task_id} completed in {processing_time:.2f}s "
            f"for ({lat}, {lon})"
        )

        return final_result

    except Exception as e:
        logger.error(f"❌ Task {task_id} failed: {e}", exc_info=True)

        # Atualizar estado de erro
        self.update_state(
            state="FAILURE",
            meta={
                "progress": 0,
                "step": "error",
                "message": f"Erro: {str(e)}",
                "error_type": type(e).__name__,
            },
        )

        # Retry automático (max 3 tentativas)
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
