"""
ETo Calculation Routes
"""

import time
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database.connection import get_db
from backend.database.models.user_favorites import UserFavorites

eto_router = APIRouter(prefix="/internal/eto", tags=["ETo"])


# ============================================================================
# SCHEMAS
# ============================================================================


class EToCalculationRequest(BaseModel):
    """Request para cálculo ETo."""

    lat: float
    lng: float
    start_date: str
    end_date: str
    sources: Optional[str] = "auto"
    elevation: Optional[float] = None
    estado: Optional[str] = None
    cidade: Optional[str] = None


class LocationInfoRequest(BaseModel):
    """Request para informações de localização."""

    lat: float
    lng: float


class FavoriteRequest(BaseModel):
    """Request para favoritos."""

    user_id: str = "default"
    name: str
    lat: float
    lng: float
    cidade: Optional[str] = None
    estado: Optional[str] = None


# ============================================================================
# ENDPOINTS ESSENCIAIS (5)
# ============================================================================


@eto_router.post("/calculate")
async def calculate_eto(
    request: EToCalculationRequest, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    ✅ Cálculo ETo principal (configurável).

    Suporta:
    - Múltiplas fontes de dados
    - Auto-detecção de melhor fonte
    - Fusão de dados (Kalman)
    - Cache automático
    """
    try:
        from backend.core.eto_calculation.eto_services import (
            EToProcessingService,
        )
        from backend.api.services.climate_source_selector import (
            get_available_sources_for_frontend,
        )

        # 1. Validar fonte de dados
        if request.sources == "auto" or not request.sources:
            # Auto-detectar melhor fonte
            sources_info = get_available_sources_for_frontend(
                request.lat, request.lng
            )
            selected_source = sources_info["recommended"]
        else:
            selected_source = request.sources

        # 2. Mapear fonte para formato esperado pelo serviço
        source_mapping = {
            "fusion": "kalman",
            "openmeteo_forecast": "openmeteo_forecast",
            "openmeteo_archive": "openmeteo_archive",
            "nasa_power": "nasa_power",
            "met_norway": "met_norway",
            "nws_forecast": "nws_forecast",
            "nws_stations": "nws_stations",
        }

        database = source_mapping.get(
            str(selected_source), "openmeteo_forecast"
        )

        # 3. Obter elevação (se não fornecida)
        elevation = request.elevation
        if elevation is None:
            # TODO: Buscar elevação via API (Open-Elevation ou similar)
            elevation = 0.0  # Padrão ao nível do mar

        # 4. Executar cálculo ETo
        service = EToProcessingService(db_session=db)
        result = await service.process_location(
            latitude=request.lat,
            longitude=request.lng,
            start_date=request.start_date,
            end_date=request.end_date,
            elevation=elevation,
            include_recomendations=False,
            database=database,
        )

        # 5. Retornar resultados
        return {
            "status": "success",
            "data": result.get("eto_data", []),
            "statistics": result.get("statistics", {}),
            "source": selected_source,
            "database_used": database,
            "warnings": result.get("warnings", []),
            "location": {
                "lat": request.lat,
                "lng": request.lng,
                "elevation_m": elevation,
            },
            "period": {
                "start": request.start_date,
                "end": request.end_date,
            },
            "timestamp": time.time(),
        }

    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"ETo calculation failed: {str(e)}"
        )


@eto_router.post("/location-info")
async def get_location_info(request: LocationInfoRequest) -> Dict[str, Any]:
    """
    ✅ Informações de localização (timezone, elevação).
    """
    try:
        # TODO: Implementar busca real de timezone e elevação
        # Por enquanto, retorna estrutura básica
        return {
            "status": "success",
            "location": {
                "lat": request.lat,
                "lng": request.lng,
                "timezone": "America/Sao_Paulo",  # Placeholder
                "elevation_m": None,  # Placeholder
            },
            "timestamp": time.time(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get location info: {str(e)}"
        )


@eto_router.post("/favorites/add")
async def add_favorite(
    request: FavoriteRequest, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    ✅ Adicionar favorito.
    """
    try:
        # Verificar duplicata
        existing = (
            db.query(UserFavorites)
            .filter_by(
                user_id=request.user_id, lat=request.lat, lng=request.lng
            )
            .first()
        )

        if existing:
            return {
                "status": "exists",
                "message": "Favorito já existe",
                "favorite_id": existing.id,
            }

        # Criar novo favorito
        favorite = UserFavorites(
            user_id=request.user_id,
            name=request.name,
            lat=request.lat,
            lng=request.lng,
            cidade=request.cidade,
            estado=request.estado,
        )
        db.add(favorite)
        db.commit()
        db.refresh(favorite)

        return {
            "status": "success",
            "message": "Favorito adicionado",
            "favorite_id": favorite.id,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to add favorite: {str(e)}"
        )


@eto_router.get("/favorites/list")
async def list_favorites(
    user_id: str = "default", db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    ✅ Listar favoritos do usuário.
    """
    try:
        favorites = (
            db.query(UserFavorites)
            .filter_by(user_id=user_id)
            .order_by(UserFavorites.created_at.desc())
            .all()
        )

        return {
            "status": "success",
            "total": len(favorites),
            "favorites": [
                {
                    "id": f.id,
                    "name": f.name,
                    "lat": f.lat,
                    "lng": f.lng,
                    "cidade": f.cidade,
                    "estado": f.estado,
                    "created_at": f.created_at.isoformat(),
                }
                for f in favorites
            ],
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list favorites: {str(e)}"
        )


@eto_router.delete("/favorites/remove/{favorite_id}")
async def remove_favorite(
    favorite_id: int, user_id: str = "default", db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    ✅ Remover favorito.
    """
    try:
        favorite = (
            db.query(UserFavorites)
            .filter_by(id=favorite_id, user_id=user_id)
            .first()
        )

        if not favorite:
            raise HTTPException(
                status_code=404, detail="Favorito não encontrado"
            )

        db.delete(favorite)
        db.commit()

        return {
            "status": "success",
            "message": "Favorito removido",
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to remove favorite: {str(e)}"
        )
