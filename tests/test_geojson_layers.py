"""Teste de carregamento das camadas GeoJSON"""

import sys

sys.path.insert(0, ".")

from frontend.components.world_map_leaflet import (
    load_brasil_geojson,
    load_matopiba_geojson,
    load_matopiba_cities_markers,
    load_piracicaba_marker,
)

print("\n🔄 Testando carregamento das camadas...")
print("=" * 60)

brasil = load_brasil_geojson()
print(f"1. Brasil: {'✅ OK' if brasil else '❌ FALHOU'}")

matopiba = load_matopiba_geojson()
print(f"2. MATOPIBA: {'✅ OK' if matopiba else '❌ FALHOU'}")

cidades = load_matopiba_cities_markers()
print(f"3. Cidades: {'✅ OK' if cidades else '❌ FALHOU'}")

piracicaba = load_piracicaba_marker()
print(f"4. Piracicaba: {'✅ OK' if piracicaba else '❌ FALHOU'}")

print("=" * 60)

if brasil:
    print(f"\n📊 Brasil: {type(brasil)} - ID: {brasil.id}")
if matopiba:
    print(f"📊 MATOPIBA: {type(matopiba)} - ID: {matopiba.id}")
if cidades:
    print(f"📊 Cidades: {type(cidades)} - ID: {cidades.id}")
if piracicaba:
    print(f"📊 Piracicaba: {type(piracicaba)}")
