"""
Verifica qual região de validação está sendo usada no cálculo do EVAOnline
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.core.data_processing.data_preprocessing import (
    _get_validation_limits,
)

print("\n" + "=" * 80)
print("VERIFICAÇÃO: LIMITES DE VALIDAÇÃO NO EVAONLINE")
print("=" * 80 + "\n")

# Verificar qual região está sendo usada
print("📍 VERIFICANDO CÓDIGO evaonline_eto.py:")
print("-" * 80)

with open(
    Path(__file__).parent / "evaonline_eto.py", "r", encoding="utf-8"
) as f:
    code = f.read()

# Procurar chamadas de preprocessing
import re

preprocessing_calls = re.findall(r"preprocessing\([^)]+\)", code)

print("\n🔍 Chamadas encontradas de preprocessing():\n")
for i, call in enumerate(preprocessing_calls, 1):
    print(f"{i}. {call}")
    if "region=" in call:
        region_match = re.search(r'region=["\']([^"\']+)["\']', call)
        if region_match:
            print(f"   ✅ Usa região: {region_match.group(1)}")
    else:
        print("   ⚠️  PROBLEMA: Não especifica parâmetro 'region'")
        print("   ⚠️  Usando padrão: 'global' (limites mundiais)")

print("\n" + "=" * 80)
print("COMPARAÇÃO: LIMITES BRASIL vs GLOBAL")
print("=" * 80 + "\n")

# Obter limites das duas regiões
global_limits = _get_validation_limits("global")
brazil_limits = _get_validation_limits("brazil")

# Variáveis relevantes para ETo
relevant_vars = [
    "T2M_MAX",
    "T2M_MIN",
    "T2M",
    "RH2M",
    "WS2M",
    "ALLSKY_SFC_SW_DWN",
    "PRECTOTCORR",
    "temperature_2m_max",
    "temperature_2m_min",
    "shortwave_radiation_sum",
    "precipitation_sum",
]

print(
    "Variável                      | Brasil (Xavier)    | Global (Mundial)   | Diferença"
)
print("-" * 95)

for var in relevant_vars:
    if var in brazil_limits and var in global_limits:
        b_min, b_max, _ = brazil_limits[var]
        g_min, g_max, _ = global_limits[var]

        diff = ""
        if b_min != g_min or b_max != g_max:
            diff = "⚠️ DIFERENTE"
        else:
            diff = "✅ Igual"

        print(
            f"{var:30s}| [{b_min:6.1f}, {b_max:6.1f}] | [{g_min:6.1f}, {g_max:6.1f}] | {diff}"
        )

print("\n" + "=" * 80)
print("ANÁLISE DO PROBLEMA")
print("=" * 80 + "\n")

print("❌ PROBLEMA IDENTIFICADO:\n")
print(
    "   O código evaonline_eto.py NÃO está especificando o parâmetro 'region'"
)
print(
    "   nas chamadas de preprocessing(), então está usando o padrão 'global'.\n"
)

print("   Código atual:")
print("   ─────────────")
print("   nasa_clean, _ = preprocessing(df_nasa, lat)")
print("   om_clean, _ = preprocessing(df_om, lat)\n")

print("   Deveria ser:")
print("   ────────────")
print("   nasa_clean, _ = preprocessing(df_nasa, lat, region='brazil')")
print("   om_clean, _ = preprocessing(df_om, lat, region='brazil')\n")

print("🔬 IMPACTO:\n")
print("   • Temperatura: Brasil [-30, 50]°C vs Global [-90, 60]°C")
print("   • Precipitação: Brasil [0, 450]mm vs Global [0, 2000]mm")
print("   • Radiação solar: Brasil [0, 40]MJ/m² vs Global [0, 45]MJ/m²")
print("   • Vento: Brasil [0, 100]m/s vs Global [0, 113]m/s")
print("   • ETo: Brasil [0, 15]mm/dia vs Global [0, 20]mm/dia\n")

print("   Os limites globais são MAIS PERMISSIVOS, permitindo outliers")
print("   que deveriam ser removidos segundo Xavier et al. (2016, 2022)\n")

print("💡 RECOMENDAÇÃO:\n")
print("   Atualizar evaonline_eto.py para usar region='brazil' nas")
print("   validações, já que estamos comparando com dados do Brasil.\n")

print("=" * 80)
