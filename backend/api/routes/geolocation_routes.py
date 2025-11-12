"""
Rotas da API para rastreamento de geolocalização de usuários.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from backend.core.analytics.geolocation_service import GeolocationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/geolocation", tags=["Geolocation"])


class GeolocationRequest(BaseModel):
    """Schema para requisição de geolocalização."""

    visitor_id: str = Field(..., description="UUID do visitante")
    session_id: str = Field(..., description="ID da sessão")
    latitude: Optional[float] = Field(
        None, ge=-90, le=90, description="Latitude"
    )
    longitude: Optional[float] = Field(
        None, ge=-180, le=180, description="Longitude"
    )
    accuracy: Optional[float] = Field(None, description="Precisão em metros")
    country: Optional[str] = Field(None, max_length=100, description="País")
    city: Optional[str] = Field(None, max_length=100, description="Cidade")


class GeolocationResponse(BaseModel):
    """Schema para resposta de geolocalização."""

    status: str
    visitor_id: str
    visit_count: int
    message: str


@router.post("/track", response_model=GeolocationResponse)
async def track_geolocation(data: GeolocationRequest, request: Request):
    """
    Armazena geolocalização do usuário.

    **Exemplo de requisição:**
    ```json
    {
        "visitor_id": "visitor_abc123",
        "session_id": "sess_xyz789",
        "latitude": -15.7939,
        "longitude": -47.8828,
        "accuracy": 50,
        "country": "Brazil",
        "city": "Brasília"
    }
    ```

    **Resposta:**
    ```json
    {
        "status": "success",
        "visitor_id": "visitor_abc123",
        "total_visits": 1,
        "message": "Geolocalização registrada com sucesso"
    }
    ```
    """
    try:
        # Obter User-Agent e IP
        user_agent = request.headers.get("user-agent", "Unknown")
        ip_address = request.client.host if request.client else None

        # Preparar geolocalização (opcional)
        geolocation = None
        if data.latitude is not None and data.longitude is not None:
            geolocation = {
                "latitude": data.latitude,
                "longitude": data.longitude,
                "accuracy": data.accuracy,
            }

        # Criar/atualizar visitante
        service = GeolocationService()
        visitor = service.create_or_update_visitor(
            visitor_id=data.visitor_id,
            session_id=data.session_id,
            geolocation=geolocation,
            user_agent=user_agent,
            ip_address=ip_address,
            country=data.country,
            city=data.city,
        )

        return GeolocationResponse(
            status="success",
            visitor_id=visitor.visitor_id,
            visit_count=visitor.visit_count,
            message="Geolocalização registrada com sucesso",
        )

    except Exception as e:
        logger.error(f"❌ Erro ao rastrear geolocalização: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao rastrear geolocalização: {str(e)}",
        )


@router.get("/visitor/{visitor_id}")
async def get_visitor_info(visitor_id: str):
    """
    Retorna informações do visitante.

    **Resposta:**
    ```json
    {
        "visitor_id": "visitor_abc123",
        "total_visits": 5,
        "first_visit": "2025-01-01T10:00:00Z",
        "last_visit": "2025-01-15T14:30:00Z",
        "last_location": {
            "latitude": -15.7939,
            "longitude": -47.8828,
            "accuracy": 50
        },
        "device_type": "desktop",
        "browser": "chrome",
        "os": "windows"
    }
    ```
    """
    try:
        service = GeolocationService()
        visitor = service.get_visitor_by_id(visitor_id)

        if not visitor:
            raise HTTPException(
                status_code=404, detail="Visitante não encontrado"
            )

        return {
            "status": "success",
            "visitor_id": visitor.visitor_id,
            "visit_count": visitor.visit_count,
            "first_visit": visitor.first_visit.isoformat(),
            "last_visit": visitor.last_visit.isoformat(),
            "last_location": {
                "latitude": visitor.last_latitude,
                "longitude": visitor.last_longitude,
                "accuracy": visitor.geolocation_accuracy,
            },
            "country": visitor.country,
            "city": visitor.city,
            "device_type": visitor.device_type,
            "browser": visitor.browser,
            "os": visitor.os,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar visitante: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erro ao buscar visitante: {str(e)}"
        )


@router.post("/generate-ids")
async def generate_visitor_ids():
    """
    Gera novos IDs de visitante e sessão.

    **Resposta:**
    ```json
    {
        "visitor_id": "visitor_abc123def456",
        "session_id": "sess_xyz789abc123def4"
    }
    ```
    """
    service = GeolocationService()
    return {
        "visitor_id": service.generate_visitor_id(),
        "session_id": service.generate_session_id(),
    }
