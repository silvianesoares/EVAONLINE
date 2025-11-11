"""Testar carregamento dos GeoJSON do Brasil e MATOPIBA"""

import json
import os

# Testar Brasil
brasil_path = os.path.join("data", "geojson", "BR_UF_2024.geojson")
print(f"📂 Brasil: {brasil_path}")
print(f"   Existe? {os.path.exists(brasil_path)}")

try:
    with open(brasil_path, "r", encoding="utf-8") as f:
        brasil_data = json.load(f)
    print(
        f"   ✅ Type: {brasil_data['type']}, Features: {len(brasil_data.get('features', []))}"
    )
    if brasil_data.get("features"):
        first = brasil_data["features"][0]["properties"]
        print(
            f"   Primeira: {first.get('NM_UF', 'N/A')} ({first.get('SIGLA_UF', 'N/A')})"
        )
except Exception as e:
    print(f"   ❌ Erro: {e}")

print()

# Testar MATOPIBA
matopiba_path = os.path.join("data", "geojson", "Matopiba_Perimetro.geojson")
print(f"📂 MATOPIBA: {matopiba_path}")
print(f"   Existe? {os.path.exists(matopiba_path)}")

try:
    with open(matopiba_path, "r", encoding="utf-8") as f:
        matopiba_data = json.load(f)
    print(
        f"   ✅ Type: {matopiba_data['type']}, Features: {len(matopiba_data.get('features', []))}"
    )
    if matopiba_data.get("features"):
        first = matopiba_data["features"][0]
        print(
            f"   Geometry type: {first.get('geometry', {}).get('type', 'N/A')}"
        )
except Exception as e:
    print(f"   ❌ Erro: {e}")
