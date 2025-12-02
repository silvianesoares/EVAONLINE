# Integração de Elevação com OpenTopoData

## Importância da Elevação no Cálculo de ETo

A **elevação** afeta diretamente três componentes críticos da evapotranspiração de referência (ETo) calculada pelo método FAO-56 Penman-Monteith:

### 1. Pressão Atmosférica (P)
A pressão diminui com a altitude segundo a equação FAO-56 (Eq. 7):

```
P = 101.3 × [(293 - 0.0065 × z) / 293]^5.26
```

Onde:
- P = pressão atmosférica (kPa)
- z = elevação acima do nível do mar (m)

**Impacto**: -1.2 kPa a cada 100m de elevação

### 2. Constante Psicrométrica (γ)
Depende diretamente da pressão atmosférica (FAO-56 Eq. 8):

```
γ = 0.665 × 10^-3 × P
```

Onde:
- γ = constante psicrométrica (kPa/°C)
- P = pressão atmosférica (kPa)

**Impacto**: Afeta o cálculo do déficit de pressão de vapor, componente fundamental da ETo

### 3. Radiação Solar
Aumenta ~10% por 1000m devido a menor absorção atmosférica:

```
Rs_ajustado = Rs × (1 + 0.0001 × z)
```

## Fontes de Dados de Elevação

### Estratégia de Priorização

O EVAonline utiliza uma estratégia de múltiplas fontes com fallback:

1. **Prioridade 1**: Entrada do usuário (se fornecida)
2. **Prioridade 2**: OpenTopoData (SRTM 30m - maior precisão)
3. **Prioridade 3**: Open-Meteo (interpolado, resolução ~7-30m)
4. **Prioridade 4**: Padrão (0m - nível do mar)

### Comparação de Fontes

| Fonte | Resolução | Cobertura | Precisão Vertical | Melhor Para |
|-------|-----------|-----------|-------------------|-------------|
| **SRTM 30m** | 30m | 60°S - 60°N | ±16m | Áreas agrícolas |
| **ASTER 30m** | 30m | Global | ±20m | Regiões polares |
| **Open-Meteo** | Variável | Global | ±7-30m | Backup geral |

## Impacto da Elevação no Cálculo de ETo

### 1. Calcular Fatores de Correção

```python
from backend.api.services import ElevationUtils

# Elevação conhecida (ex: 1172m - Brasília)
elevation = 1172

# Calcular pressão atmosférica (FAO-56 Eq. 7)
pressure = ElevationUtils.calculate_atmospheric_pressure(elevation)
print(f"Pressão: {pressure:.2f} kPa")
# Output: Pressão: 87.78 kPa

# Calcular constante psicrométrica (FAO-56 Eq. 8)
gamma = ElevationUtils.calculate_psychrometric_constant(elevation)
print(f"Gamma: {gamma:.5f} kPa/°C")
# Output: Gamma: 0.05840 kPa/°C

# Ajustar radiação solar
radiation_sea_level = 20.0  # MJ/m²/dia
radiation_adjusted = ElevationUtils.adjust_solar_radiation_for_elevation(
    radiation_sea_level, elevation
)
print(f"Radiação ajustada: {radiation_adjusted:.2f} MJ/m²/dia")
# Output: Radiação ajustada: 22.34 MJ/m²/dia (+11.7%)
```

### 2. Obter Todos os Fatores de Uma Vez

```python
# Retorna pressão, gamma, e fator solar em um único dict
factors = ElevationUtils.get_elevation_correction_factor(1172)

print(factors)
# Output: {
#   'pressure': 87.78,
#   'gamma': 0.05840,
#   'solar_factor': 1.1172,
#   'elevation': 1172
# }
```

### 3. Integração com OpenTopoData

```python
from backend.api.services import OpenTopoClient

# Inicializar cliente
client = OpenTopoClient()

# Obter elevação de um ponto (Brasília)
location = await client.get_elevation(-15.7801, -47.9292)

print(f"Elevação: {location.elevation:.1f}m")
print(f"Dataset: {location.dataset}")
# Output: Elevação: 1172.0m
#         Dataset: srtm30m

await client.close()
```

### 4. Obter Elevações em Lote (Batch)

```python
# Até 100 pontos por request
locations = [
    (-15.7801, -47.9292),  # Brasília
    (-23.5505, -46.6333),  # São Paulo
    (-22.9068, -43.1729),  # Rio de Janeiro
]

results = await client.get_elevations_batch(locations)

for loc in results:
    print(f"({loc.lat}, {loc.lon}): {loc.elevation}m")
# Output:
# (-15.7801, -47.9292): 1172m
# (-23.5505, -46.6333): 760m
# (-22.9068, -43.1729): 11m
```

### 5. Validação Cruzada: OpenTopo vs Open-Meteo

```python
async def validate_elevation(lat: float, lon: float) -> dict:
    """Compara elevação de duas fontes."""
    from backend.api.services import OpenMeteoForecastClient
    
    meteo = OpenMeteoForecastClient()
    topo = OpenTopoClient()
    
    # Open-Meteo (interpolado)
    meteo_data = await meteo.get_daily_forecast(lat, lon, ...)
    meteo_elevation = meteo_data['location']['elevation']
    
    # OpenTopoData (SRTM 30m - mais preciso)
    topo_data = await topo.get_elevation(lat, lon)
    topo_elevation = topo_data.elevation
    
    return {
        "open_meteo": meteo_elevation,
        "opentopo_srtm": topo_elevation,
        "source_recommended": "opentopo",  # Mais preciso
        "difference_m": abs(meteo_elevation - topo_elevation),
    }

# Exemplo de uso
result = await validate_elevation(-15.7801, -47.9292)
print(result)
# Output: {
#   "open_meteo": 1168,
#   "opentopo_srtm": 1172,
#   "source_recommended": "opentopo",
#   "difference_m": 4
# }
```

## Integração no Fluxo de Validação

O módulo de validação regional (`data_preprocessing.py`) utiliza elevação para:

1. **Validação de Pressão Atmosférica**
   - Limites ajustados por elevação
   - Brasil: 900-1100 hPa (nível do mar)
   - Ajuste: -12 hPa por 100m

2. **Validação de Radiação Solar**
   - Ra (radiação extraterrestre) ajustada por elevação
   - Constraint: 0.03×Ra ≤ Rs < Ra

3. **Cálculo de ETo FAO-56**
   - Pressão e gamma calculados com elevação real
   - Radiação solar corrigida para altitude

## Cobertura e Limitações

### Cobertura SRTM (Recomendado)
- **Latitudes**: 60°S a 60°N
- **Área coberta**: ~80% da superfície terrestre
- **Inclui**: Toda América do Sul, África, Ásia, Europa
- **Exclui**: Regiões polares (>60° latitude)

### Fallback para Regiões Polares
```python
# Para latitudes >60° ou <-60°, usa ASTER30m automaticamente
location = await client.get_elevation(70, 25)  # Noruega
# Retorna com dataset='aster30m'
```

## Performance e Cache

### Tempos de Resposta

| Operação | Tempo | Cache TTL |
|----------|-------|-----------|
| Single request | ~500ms | 30 dias |
| Batch (100 pts) | ~800ms | Individual |
| Cache hit | <1ms | Redis |

### Otimizações Recomendadas

1. **Usar Batch para Múltiplos Pontos**
   ```python
   # Eficiente: 1 request para 100 pontos
   results = await client.get_elevations_batch(locations)
   
   # Ineficiente: 100 requests individuais
   for lat, lon in locations:
       result = await client.get_elevation(lat, lon)
   ```

2. **Cache Redis para Requisições Frequentes**
   ```python
   from backend.infrastructure.cache import ClimateCache
   
   cache = ClimateCache()
   client = OpenTopoClient(cache=cache)
   
   # Primeira chamada: API request (~500ms)
   loc1 = await client.get_elevation(-15.7801, -47.9292)
   
   # Segunda chamada: cache hit (<1ms)
   loc2 = await client.get_elevation(-15.7801, -47.9292)
   ```

3. **Pré-calcular para Grids Frequentes**
   ```python
   # Para área de interesse (ex: Matopiba)
   lat_range = (-10, -3)  # Sul-Norte
   lon_range = (-50, -42)  # Oeste-Leste
   
   # Grid 0.1° = ~11km
   locations = [
       (lat, lon) 
       for lat in range(int(lat_range[0] * 10), int(lat_range[1] * 10))
       for lon in range(int(lon_range[0] * 10), int(lon_range[1] * 10))
   ]
   
   # Batch request + cache
   elevations = await client.get_elevations_batch(locations)
   ```

## Recomendações de Uso

### Para Cálculo de ETo
**Sempre usar OpenTopoData** para:
- Regiões montanhosas
- Planaltos (ex: Cerrado brasileiro)
- Áreas acima de 500m
- Validação de artigos científicos

**Aceitável usar Open-Meteo** para:
- Previsões de curto prazo (1-7 dias)
- Dashboard em tempo real
- Áreas abaixo de 500m
- Tolerância de erro ~5%

**Nunca assumir 0m** (nível do mar) para:
- Cálculos históricos
- Regiões interiores
- Artigos científicos
- Comparações regionais

### Para Validação Regional
- Combinar com limites do Xavier et al. (Brasil)
- Ajustar limites de pressão por elevação
- Validar radiação solar com Ra corrigido

## Referências

- **FAO-56**: Allen et al. (1998). Crop evapotranspiration - Guidelines for computing crop water requirements. Equações 7 e 8.
- **SRTM**: Shuttle Radar Topography Mission, NASA/USGS, resolução 30m.
- **ASTER GDEM**: Advanced Spaceborne Thermal Emission and Reflection Radiometer Global Digital Elevation Model.
- **OpenTopoData**: Open-source elevation API, <https://www.opentopodata.org/>
