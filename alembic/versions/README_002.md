# Alembic Migration: Regional Coverage PostGIS

Migration que adiciona suporte para queries espaciais de cobertura regional usando PostGIS.

## 📋 Visão Geral

**Revision ID**: `002_regional_coverage`  
**Revises**: `001_climate_6apis`  
**Created**: 2025-11-15

Esta migration cria:

1. **Tabela `regional_coverage`**: Armazena geometrias PostGIS (POLYGONs) das regiões
2. **Índices espaciais**: GIST indexes para queries rápidas
3. **Seeds de regiões**: Nordic, Brazil, USA, Global
4. **Funções helper SQL**: Para queries espaciais

## 🚀 Como Aplicar

### 1. Verificar Status Atual

```bash
# Ver migrations pendentes
alembic current
alembic heads

# Ver histórico
alembic history --verbose
```

### 2. Aplicar Migration

```bash
# Aplicar migration (upgrade)
alembic upgrade head

# Ou especificamente esta migration
alembic upgrade 002_regional_coverage
```

### 3. Verificar Aplicação

```bash
# Conectar ao PostgreSQL
docker exec -it evaonline-postgres psql -U evaonline -d evaonline

# Verificar tabela
\d regional_coverage

# Ver dados inseridos
SELECT region_id, region_name, quality_tier, resolution_km 
FROM regional_coverage;
```

## 📊 Estrutura da Tabela

```sql
CREATE TABLE regional_coverage (
    id SERIAL PRIMARY KEY,
    region_id VARCHAR(50) UNIQUE NOT NULL,          -- 'nordic', 'brazil', 'usa', 'global'
    region_name VARCHAR(100) NOT NULL,              -- Nome legível
    geometry GEOMETRY(POLYGON, 4326) NOT NULL,      -- Polígono da área
    sources TEXT[] NOT NULL DEFAULT '{}',           -- Fontes disponíveis
    quality_tier VARCHAR(20) NOT NULL,              -- 'high', 'medium', 'low'
    resolution_km FLOAT,                            -- Resolução típica
    variables TEXT[] NOT NULL DEFAULT '{}',         -- Variáveis climáticas
    metadata JSONB,                                 -- Dados adicionais
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX idx_regional_coverage_geometry 
    ON regional_coverage USING GIST (geometry);
CREATE INDEX idx_regional_coverage_region_id 
    ON regional_coverage (region_id);
```

## 🗺️ Regiões Inseridas (Seeds)

| region_id | Bbox (lon_min, lat_min, lon_max, lat_max) | Quality | Resolution | Sources |
|-----------|-------------------------------------------|---------|------------|---------|
| `nordic`  | (4.0, 54.0, 32.0, 72.0)                  | high    | 1 km       | met_norway, open_meteo |
| `brazil`  | (-74.0, -34.0, -34.0, 5.0)               | medium  | 11 km      | nasa_power, open_meteo, met_norway |
| `usa`     | (-125.0, 24.0, -66.0, 50.0)              | high    | 2.5 km     | nws_forecast, nws_stations, open_meteo |
| `global`  | (-180, -90, 180, 90)                      | medium  | 9 km       | met_norway, open_meteo, nasa_power |

## 🔍 Queries Espaciais

### 1. Verificar Região por Coordenadas

```sql
-- Usando função helper
SELECT get_region_by_coordinates(-15.7939, -47.8828);  -- Brasília → 'brazil'
SELECT get_region_by_coordinates(59.9139, 10.7522);    -- Oslo → 'nordic'
SELECT get_region_by_coordinates(40.7128, -74.0060);   -- NY → 'usa'

-- Usando ST_Contains diretamente
SELECT region_id, region_name
FROM regional_coverage
WHERE ST_Contains(
    geometry,
    ST_SetSRID(ST_MakePoint(-47.8828, -15.7939), 4326)  -- (lon, lat)
);
```

### 2. Obter Fontes Disponíveis

```sql
-- Usando função helper
SELECT get_sources_for_location(-15.7939, -47.8828);
-- Retorna: {nasa_power, open_meteo, met_norway}

-- Query manual
SELECT sources, quality_tier, resolution_km
FROM regional_coverage
WHERE ST_Contains(
    geometry,
    ST_SetSRID(ST_MakePoint(-47.8828, -15.7939), 4326)
)
LIMIT 1;
```

### 3. Verificar Sobreposição de Regiões

```sql
-- Regiões que contêm um ponto
SELECT region_id, quality_tier
FROM regional_coverage
WHERE ST_Contains(
    geometry,
    ST_SetSRID(ST_MakePoint(10.0, 60.0), 4326)
)
ORDER BY quality_tier;
```

### 4. Distância até Região Mais Próxima

```sql
-- Encontrar região mais próxima de um ponto
SELECT 
    region_id,
    ST_Distance(
        geometry::geography,
        ST_SetSRID(ST_MakePoint(-47.8828, -15.7939), 4326)::geography
    ) / 1000 AS distance_km
FROM regional_coverage
WHERE region_id != 'global'
ORDER BY distance_km
LIMIT 1;
```

## 🐍 Uso em Python

### 1. Query com SQLAlchemy

```python
from sqlalchemy import text
from backend.database import engine

# Detectar região
with engine.connect() as conn:
    result = conn.execute(
        text("SELECT get_region_by_coordinates(:lat, :lon)"),
        {"lat": -15.7939, "lon": -47.8828}
    ).scalar()
    print(f"Região: {result}")  # 'brazil'

# Obter fontes disponíveis
with engine.connect() as conn:
    result = conn.execute(
        text("SELECT get_sources_for_location(:lat, :lon)"),
        {"lat": 59.9139, "lon": 10.7522}
    ).fetchone()
    print(f"Fontes: {result[0]}")  # ['met_norway', 'open_meteo']
```

### 2. Query com GeoAlchemy2

```python
from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_Contains, ST_MakePoint
from sqlalchemy.orm import Session

from backend.models import RegionalCoverage  # Assumindo modelo criado

def get_region_for_coordinates(session: Session, lat: float, lon: float) -> str:
    """Retorna region_id para coordenadas."""
    point = ST_MakePoint(lon, lat, type_=Geometry(srid=4326))
    
    region = session.query(RegionalCoverage.region_id).filter(
        ST_Contains(RegionalCoverage.geometry, point)
    ).filter(
        RegionalCoverage.region_id != 'global'
    ).first()
    
    return region[0] if region else 'global'
```

### 3. Integração com GeographicUtils

```python
# backend/api/services/geographic_utils.py

class GeographicUtils:
    @staticmethod
    def get_region_from_postgis(lat: float, lon: float) -> str:
        """
        Detecta região usando PostGIS (fonte única de verdade).
        
        Alternativa ao método baseado em bboxes hardcoded.
        Vantagens:
        - Queries espaciais otimizadas (GIST index)
        - Fácil adicionar/editar regiões via SQL
        - Suporte para polígonos complexos (não apenas retângulos)
        """
        from backend.database import engine
        from sqlalchemy import text
        
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT get_region_by_coordinates(:lat, :lon)"),
                {"lat": lat, "lon": lon}
            ).scalar()
            
        return result or "global"
```

## 🧪 Testes

### 1. Testar Detecção de Região

```python
import pytest
from backend.database import get_db

def test_postgis_region_detection():
    """Testa detecção de região com PostGIS."""
    from sqlalchemy import text
    
    test_cases = [
        (59.9139, 10.7522, "nordic"),    # Oslo
        (-15.7939, -47.8828, "brazil"),  # Brasília
        (40.7128, -74.0060, "usa"),      # New York
        (35.6762, 139.6503, "global"),   # Tokyo
    ]
    
    db = next(get_db())
    
    for lat, lon, expected_region in test_cases:
        result = db.execute(
            text("SELECT get_region_by_coordinates(:lat, :lon)"),
            {"lat": lat, "lon": lon}
        ).scalar()
        
        assert result == expected_region, \
            f"Expected {expected_region}, got {result} for ({lat}, {lon})"
```

### 2. Testar Índice Espacial

```bash
# Verificar uso de índice GIST
EXPLAIN ANALYZE
SELECT region_id FROM regional_coverage
WHERE ST_Contains(
    geometry,
    ST_SetSRID(ST_MakePoint(-47.8828, -15.7939), 4326)
);

# Deve mostrar: "Index Scan using idx_regional_coverage_geometry"
```

## 🔄 Rollback

Se precisar reverter:

```bash
# Voltar uma migration
alembic downgrade -1

# Voltar para revision específica
alembic downgrade 001_climate_6apis

# Ver o que será revertido
alembic downgrade 001_climate_6apis --sql
```

## 📝 Notas Importantes

1. **SRID 4326**: Todas as geometrias usam WGS84 (lon/lat)
2. **Ordem lon, lat**: PostGIS usa (longitude, latitude) - cuidado!
3. **Índice GIST**: Essencial para performance de queries espaciais
4. **Funções IMMUTABLE**: Otimizadas pelo PostgreSQL, podem ser cacheadas

## 🚨 Troubleshooting

### PostGIS não encontrado

```sql
-- Verificar se PostGIS está instalado
SELECT PostGIS_Version();

-- Se não estiver, instalar:
CREATE EXTENSION postgis;
```

### Geometria inválida

```sql
-- Validar geometrias
SELECT region_id, ST_IsValid(geometry), ST_IsValidReason(geometry)
FROM regional_coverage;

-- Corrigir geometrias inválidas
UPDATE regional_coverage
SET geometry = ST_MakeValid(geometry)
WHERE NOT ST_IsValid(geometry);
```

### Performance lenta

```sql
-- Verificar uso do índice
EXPLAIN ANALYZE
SELECT * FROM regional_coverage
WHERE ST_Contains(geometry, ST_MakePoint(-47, -15, 4326));

-- Recriar índice se necessário
REINDEX INDEX idx_regional_coverage_geometry;

-- Analisar tabela para atualizar estatísticas
ANALYZE regional_coverage;
```

## 🎯 Próximos Passos

1. **Criar modelo SQLAlchemy** (`backend/models/regional_coverage.py`)
2. **Adicionar endpoint FastAPI** (`/api/v1/regions/{lat}/{lon}`)
3. **Integrar com GeographicUtils** (usar PostGIS como fonte única)
4. **Criar testes de integração** (test_postgis_queries.py)
5. **Adicionar visualização** (mapa interativo das regiões no frontend)

---

**Documentação**: [docs/POSTGIS_QUERIES.md](../docs/POSTGIS_QUERIES.md)  
**Migration**: `alembic/versions/002_add_regional_coverage_postgis.py`
