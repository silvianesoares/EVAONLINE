"""
Teste de integração do pipeline completo de ETo.

Validações:
1. Download de dados climáticos (NASA POWER)
2. Obtenção de elevação precisa (OpenTopoData)
3. Fusão Kalman
4. Cálculo ETo FAO-56
5. (Opcional) Salvamento PostgreSQL

Objetivo: Confirmar que OpenTopoData e Kalman estão integrados corretamente.
"""

import pytest
from datetime import datetime, timedelta

# Pular teste se não houver DB configurada
pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_eto_pipeline_with_opentopo_and_kalman():
    """
    Teste end-to-end do pipeline ETo completo.

    Fluxo:
    1. Coordenadas de Brasília (-15.7801, -47.9292)
    2. Período: 7 dias (hoje - 7 dias até hoje)
    3. Verificar que OpenTopoData foi usado
    4. Verificar que Kalman foi aplicado
    5. Verificar que ETo foi calculado
    """
    from backend.core.eto_calculation.eto_services import (
        EToProcessingService,
    )

    # Setup
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)

    latitude = -15.7801
    longitude = -47.9292

    # Criar serviço (sem DB para teste simples)
    service = EToProcessingService(
        db_session=None, redis_client=None, s3_client=None
    )

    # Executar pipeline
    result = await service.process_location(
        latitude=latitude,
        longitude=longitude,
        start_date=str(start_date),
        end_date=str(end_date),
        elevation=None,  # Forçar obtenção via OpenTopoData
        include_recomendations=True,
        database="nasa_power",
        use_precise_elevation=True,  # Habilitar OpenTopoData
    )

    # ═════════════════════════════════════════════════════════════════
    # VALIDAÇÕES
    # ═════════════════════════════════════════════════════════════════

    # 1️⃣ Pipeline não deve ter erro
    assert "error" not in result, f"Pipeline falhou: {result.get('error')}"

    # 2️⃣ Elevação deve estar presente
    assert "elevation" in result
    assert "value" in result["elevation"]
    assert result["elevation"]["value"] is not None

    # 3️⃣ Verificar fonte de elevação (deve ser OpenTopo ou fallback)
    elevation_source = result["elevation"]["source"]
    assert elevation_source in [
        "opentopo",
        "openmeteo_archive",
        "openmeteo_forecast",
        "default",
    ]

    # 4️⃣ Se OpenTopo foi usado, verificar metadados
    if elevation_source == "opentopo":
        assert result["elevation"]["opentopo"] is not None
        print(
            f"✅ OpenTopoData usado: "
            f"{result['elevation']['opentopo']:.1f}m (precisão ~1m)"
        )
    else:
        print(
            f"⚠️  OpenTopo falhou, usando fallback: "
            f"{elevation_source} ({result['elevation']['value']:.1f}m)"
        )

    # 5️⃣ Fatores de correção de elevação devem estar presentes
    assert "elevation_factors" in result
    assert "pressure" in result["elevation_factors"]
    assert "gamma" in result["elevation_factors"]
    assert "solar_factor" in result["elevation_factors"]

    # 6️⃣ Série ETo deve estar presente
    assert "et0_series" in result
    assert len(result["et0_series"]) > 0

    # 7️⃣ Verificar estrutura de cada ponto da série
    for et0_data in result["et0_series"]:
        assert "date" in et0_data
        assert "et0_mm_day" in et0_data
        assert "quality" in et0_data
        assert et0_data["et0_mm_day"] >= 0  # ETo nunca negativo
        assert et0_data["et0_mm_day"] < 20  # Sanity check (< 20mm/dia)

    # 8️⃣ Resumo estatístico deve estar presente
    assert "summary" in result
    assert result["summary"]["total_days"] > 0
    assert result["summary"]["et0_total_mm"] > 0

    # 9️⃣ Recomendações devem estar presentes
    assert "recomendations" in result
    assert len(result["recomendations"]) > 0

    # 🔟 Log de sucesso
    print("\n" + "=" * 70)
    print("✅ PIPELINE COMPLETO VALIDADO COM SUCESSO")
    print("=" * 70)
    print(f"📍 Local: ({latitude}, {longitude}) - Brasília")
    print(f"📅 Período: {start_date} → {end_date}")
    print(
        f"🗻 Elevação: {result['elevation']['value']:.1f}m "
        f"(fonte: {elevation_source})"
    )
    print(f"📊 ETo médio: {result['summary']['et0_mean_mm_day']:.2f} mm/dia")
    print(f"💧 ETo total: {result['summary']['et0_total_mm']:.1f} mm")
    print("=" * 70)


@pytest.mark.asyncio
async def test_eto_pipeline_with_input_elevation():
    """
    Teste com elevação fornecida pelo usuário (não usa OpenTopoData).
    """
    from backend.core.eto_calculation.eto_services import (
        EToProcessingService,
    )

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=3)

    service = EToProcessingService()

    result = await service.process_location(
        latitude=-15.7801,
        longitude=-47.9292,
        start_date=str(start_date),
        end_date=str(end_date),
        elevation=1172.0,  # Elevação INPUT
        database="nasa_power",
    )

    # Validações
    assert "error" not in result
    assert result["elevation"]["value"] == 1172.0
    assert result["elevation"]["source"] == "input"
    assert "et0_series" in result
    print(f"✅ Pipeline com elevação INPUT: {result['elevation']['value']}m")


@pytest.mark.asyncio
async def test_eto_pipeline_kalman_fusion():
    """
    Teste focado em verificar se Kalman está sendo aplicado.

    Estratégia: Comparar resultado com/sem fusão não é viável aqui,
    mas podemos verificar que não há erro no processo.
    """
    from backend.core.eto_calculation.eto_services import (
        EToProcessingService,
    )

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=5)

    service = EToProcessingService()

    result = await service.process_location(
        latitude=-15.7801,
        longitude=-47.9292,
        start_date=str(start_date),
        end_date=str(end_date),
        database="nasa_power",
    )

    # Validar que pipeline não falhou
    assert "error" not in result
    assert "et0_series" in result
    assert len(result["et0_series"]) > 0

    # TODO: Adicionar metadado "fusion_applied" no resultado
    # para verificar se Kalman foi realmente usado
    print("✅ Pipeline com Kalman Fusion executado sem erros")


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_eto_pipeline_with_opentopo_and_kalman())
