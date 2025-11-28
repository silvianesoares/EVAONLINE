"""
Script de teste para NASA POWER API
Execute com: python test_nasa_power.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Adicionar diretório de scripts ao path
project_root = Path(__file__).parent.parent
scripts_path = project_root / "scripts"
sys.path.insert(0, str(scripts_path))

from api.services.nasa_power.nasa_power_sync_adapter import (
    NASAPowerSyncAdapter,
)


def test_nasa_power():
    print("=" * 70)
    print("🧪 TESTE NASA POWER API")
    print("=" * 70)

    # Criar adapter
    print("\n1️⃣ Criando adapter NASA POWER...")
    nasa_adapter = NASAPowerSyncAdapter()

    # Verificar informações
    print("\n2️⃣ Informações da API:")
    info = nasa_adapter.get_info()
    for key, value in info.items():
        print(f"   {key}: {value}")

    # Health check
    print("\n3️⃣ Health Check...")
    is_healthy = nasa_adapter.health_check_sync()
    print(f"   Status: {'✅ OK' if is_healthy else '❌ FALHOU'}")

    if not is_healthy:
        print("\n❌ API não está acessível. Teste interrompido.")
        return False

    # Baixar dados de Piracicaba/SP
    print("\n4️⃣ Baixando dados de Piracicaba/SP (ESALQ/USP)...")
    lat = -22.7089
    lon = -47.6361
    end_date = datetime.now() - timedelta(days=7)
    start_date = end_date - timedelta(
        days=7
    )  # Apenas 7 dias para teste rápido

    print(f"   📍 Localização: {lat:.4f}°, {lon:.4f}°")
    print(f"   📅 Período: {start_date.date()} até {end_date.date()}")

    try:
        nasa_data = nasa_adapter.get_daily_data_sync(
            lat=lat,
            lon=lon,
            start_date=start_date,
            end_date=end_date,
            community="AG",
        )

        print(f"\n5️⃣ Dados recebidos: {len(nasa_data)} registros")

        if nasa_data:
            # Mostrar primeiro registro
            first = nasa_data[0]
            print("\n6️⃣ Primeiro registro:")
            print(f"   Data: {first.date}")
            print(f"   Temp máx: {first.temp_max:.2f}°C")
            print(f"   Temp mín: {first.temp_min:.2f}°C")
            print(f"   Temp média: {first.temp_mean:.2f}°C")
            print(f"   Umidade: {first.humidity:.1f}%")
            print(f"   Vento: {first.wind_speed:.2f} m/s")
            print(f"   Radiação solar: {first.solar_radiation:.2f} MJ/m²")
            print(f"   Precipitação: {first.precipitation:.2f} mm")

        print("\n" + "=" * 70)
        print("✅ TESTE CONCLUÍDO COM SUCESSO!")
        print("=" * 70)
        return True

    except Exception as e:
        print(f"\n❌ Erro ao baixar dados: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_nasa_power()
    sys.exit(0 if success else 1)
