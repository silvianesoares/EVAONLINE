"""
RESUMO: Correção dos Limites de Validação no EVAOnline
========================================================

PROBLEMA IDENTIFICADO:
---------------------
O cálculo do EVAOnline (evaonline_eto.py) estava usando limites de validação
GLOBAIS (mundiais) ao invés dos limites específicos do BRASIL definidos por
Xavier et al. (2016, 2022).

CÓDIGO ANTERIOR (INCORRETO):
----------------------------
nasa_clean, _ = preprocessing(df_nasa, lat)
om_clean, _ = preprocessing(df_om, lat)

→ Usava padrão region='global' (não especificado)

CÓDIGO CORRIGIDO:
----------------
nasa_clean, _ = preprocessing(df_nasa, lat, region='brazil')
om_clean, _ = preprocessing(df_om, lat, region='brazil')

→ Agora usa explicitamente region='brazil'


IMPACTO DA CORREÇÃO:
-------------------

Variável          | Antes (Global)      | Depois (Brasil)    | Impacto
------------------|---------------------|--------------------|---------
Temperatura       | [-90, 60]°C         | [-30, 50]°C        | Mais restritivo
Precipitação      | [0, 2000]mm         | [0, 450]mm         | Muito mais restritivo
Radiação Solar    | [0, 45]MJ/m²        | [0, 40]MJ/m²       | Mais restritivo
Vento             | [0, 113]m/s         | [0, 100]m/s        | Mais restritivo
ETo               | [0, 20]mm/dia       | [0, 15]mm/dia      | Mais restritivo


BENEFÍCIOS DA CORREÇÃO:
----------------------
1. ✅ Remove outliers que não são fisicamente plausíveis para o Brasil
2. ✅ Segue as recomendações de Xavier et al. (2016, 2022)
3. ✅ Melhora qualidade dos dados antes da fusão Kalman
4. ✅ Validação consistente com a referência (Xavier)
5. ✅ Reduz ruído e valores extremos irreais


EXEMPLOS DE VALORES AFETADOS:
-----------------------------
Antes (Global):    Depois (Brasil):
─────────────────  ─────────────────
• Precipitação: 600mm/dia → REMOVIDO (max Brasil = 450mm)
• Temperatura: -50°C → REMOVIDO (min Brasil = -30°C)
• Radiação: 42 MJ/m² → REMOVIDO (max Brasil = 40 MJ/m²)
• Vento: 110 m/s → REMOVIDO (max Brasil = 100 m/s)


PRÓXIMOS PASSOS:
---------------
1. ✅ CORRIGIDO: evaonline_eto.py agora usa region='brazil'
2. ⏳ REPROCESSAR: Recalcular EVAOnline com limites corretos
3. ⏳ COMPARAR: Verificar impacto nos resultados finais
4. ⏳ VALIDAR: Confirmar melhoria nas métricas vs Xavier


EXPECTATIVAS:
------------
Com limites mais restritivos do Brasil:
• MAE deve MELHORAR (menos outliers)
• PBIAS deve MELHORAR (menos valores extremos)
• R² pode MELHORAR (dados mais limpos)
• Resultados mais confiáveis para agricultura brasileira


REFERÊNCIAS:
-----------
Xavier, A. C., King, C. W., & Scanlon, B. R. (2016). Daily gridded
meteorological variables in Brazil (1980–2013). International Journal
of Climatology, 36(6), 2644-2659.

Xavier, A. C., Scanlon, B. R., King, C. W., & Alves, A. I. (2022).
New improved Brazilian daily weather gridded data (1961–2020).
International Journal of Climatology, 42(16), 8390-8404.
"""

print(__doc__)
