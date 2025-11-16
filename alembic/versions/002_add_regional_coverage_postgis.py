"""
Add regional coverage table with PostGIS geometries.

Revision ID: 002_regional_coverage
Revises: 001_climate_6apis
Create Date: 2025-11-15

Esta migration adiciona suporte para queries espaciais de cobertura regional:

1. Tabela regional_coverage com geometrias PostGIS (POLYGON)
2. Índices espaciais (GIST) para queries rápidas
3. Seeds com bboxes das regiões: Nordic, USA, Brazil, Global
4. Funções helper para verificar cobertura por coordenadas

Casos de uso:
- Queries espaciais: ST_Contains(geometry, point)
- Detecção de região por coordenadas
- Visualização de áreas de cobertura em mapas
- Análise de sobreposição de fontes de dados
"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "002_regional_coverage"
down_revision = "001_climate_6apis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Cria tabela regional_coverage com geometrias PostGIS.

    Estrutura:
    - region_id: Identificador único (nordic, brazil, usa, global)
    - region_name: Nome legível da região
    - geometry: POLYGON da área de cobertura (SRID 4326)
    - sources: Array de fontes disponíveis na região
    - quality_tier: Nível de qualidade (high, medium, low)
    - resolution_km: Resolução típica em km
    - metadata: Dados adicionais (JSONB)
    """

    # Garantir que PostGIS está habilitado
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # Criar tabela regional_coverage
    op.create_table(
        "regional_coverage",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column(
            "region_id",
            sa.String(50),
            nullable=False,
            unique=True,
            comment="Identificador único da região (nordic, brazil, usa, global)",
        ),
        sa.Column(
            "region_name",
            sa.String(100),
            nullable=False,
            comment="Nome legível da região",
        ),
        sa.Column(
            "geometry",
            Geometry(geometry_type="POLYGON", srid=4326),
            nullable=False,
            comment="Polígono da área de cobertura (WGS84)",
        ),
        sa.Column(
            "sources",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
            comment="Fontes de dados disponíveis",
        ),
        sa.Column(
            "quality_tier",
            sa.String(20),
            nullable=False,
            comment="Nível de qualidade: high, medium, low",
        ),
        sa.Column(
            "resolution_km",
            sa.Float(),
            nullable=True,
            comment="Resolução típica em quilômetros",
        ),
        sa.Column(
            "variables",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
            comment="Variáveis climáticas disponíveis",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=True,
            comment="Metadados adicionais (modelos, atualizações, etc.)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Criar índice espacial (GIST) para queries rápidas
    op.create_index(
        "idx_regional_coverage_geometry",
        "regional_coverage",
        ["geometry"],
        postgresql_using="gist",
    )

    # Criar índice em region_id
    op.create_index(
        "idx_regional_coverage_region_id",
        "regional_coverage",
        ["region_id"],
    )

    # Inserir seeds das regiões
    _insert_regional_seeds()

    print("✅ Tabela regional_coverage criada com geometrias PostGIS")


def downgrade() -> None:
    """Remove tabela regional_coverage."""
    op.drop_index(
        "idx_regional_coverage_region_id", table_name="regional_coverage"
    )
    op.drop_index(
        "idx_regional_coverage_geometry",
        table_name="regional_coverage",
        postgresql_using="gist",
    )
    op.drop_table("regional_coverage")

    print("✅ Tabela regional_coverage removida")


def _insert_regional_seeds() -> None:
    """
    Insere seeds das regiões com geometrias PostGIS.

    Bboxes convertidos para POLYGONs no formato WKT:
    - Nordic: (lon_min, lat_min, lon_max, lat_max)
    - Brazil: (-74.0, -34.0, -34.0, 5.0)
    - USA: (-125.0, 24.0, -66.0, 50.0)
    - Global: Todos os outros (representado como cobertura mundial)
    """

    conn = op.get_bind()

    # Região Nordic
    conn.execute(
        sa.text(
            """
            INSERT INTO regional_coverage (
                region_id, region_name, geometry, sources, quality_tier,
                resolution_km, variables, metadata
            ) VALUES (
                'nordic',
                'Nordic Region',
                ST_GeomFromText(
                    'POLYGON((4.0 54.0, 32.0 54.0, 32.0 72.0, 4.0 72.0, 4.0 54.0))',
                    4326
                ),
                ARRAY['met_norway', 'open_meteo'],
                'high',
                1.0,
                ARRAY[
                    'air_temperature_max', 'air_temperature_min',
                    'relative_humidity_mean', 'precipitation_sum',
                    'wind_speed_mean'
                ],
                '{"model": "MEPS 2.5km + MET Nordic", "updates": "hourly", 
                  "post_processing": "radar + Netatmo crowdsourced"}'::jsonb
            )
        """
        )
    )

    # Região Brazil
    conn.execute(
        sa.text(
            """
            INSERT INTO regional_coverage (
                region_id, region_name, geometry, sources, quality_tier,
                resolution_km, variables, metadata
            ) VALUES (
                'brazil',
                'Brazil',
                ST_GeomFromText(
                    'POLYGON((-74.0 -34.0, -34.0 -34.0, -34.0 5.0, -74.0 5.0, -74.0 -34.0))',
                    4326
                ),
                ARRAY['nasa_power', 'open_meteo', 'met_norway'],
                'medium',
                11.0,
                ARRAY[
                    'air_temperature_max', 'air_temperature_min',
                    'relative_humidity_mean'
                ],
                '{"model": "ECMWF IFS", "validation": "Xavier et al.",
                  "note": "Use NASA POWER for historical precipitation"}'::jsonb
            )
        """
        )
    )

    # Região USA
    conn.execute(
        sa.text(
            """
            INSERT INTO regional_coverage (
                region_id, region_name, geometry, sources, quality_tier,
                resolution_km, variables, metadata
            ) VALUES (
                'usa',
                'United States',
                ST_GeomFromText(
                    'POLYGON((-125.0 24.0, -66.0 24.0, -66.0 50.0, -125.0 50.0, -125.0 24.0))',
                    4326
                ),
                ARRAY['nws_forecast', 'nws_stations', 'open_meteo', 'nasa_power'],
                'high',
                2.5,
                ARRAY[
                    'air_temperature_max', 'air_temperature_min',
                    'relative_humidity_mean', 'precipitation_sum',
                    'wind_speed_mean'
                ],
                '{"model": "NOAA HRRR + NBM", "updates": "hourly",
                  "note": "NWS has highest quality for USA"}'::jsonb
            )
        """
        )
    )

    # Região Global (resto do mundo)
    conn.execute(
        sa.text(
            """
            INSERT INTO regional_coverage (
                region_id, region_name, geometry, sources, quality_tier,
                resolution_km, variables, metadata
            ) VALUES (
                'global',
                'Global (Rest of World)',
                ST_GeomFromText(
                    'POLYGON((-180 -90, 180 -90, 180 90, -180 90, -180 -90))',
                    4326
                ),
                ARRAY['met_norway', 'open_meteo', 'nasa_power'],
                'medium',
                9.0,
                ARRAY[
                    'air_temperature_max', 'air_temperature_min',
                    'relative_humidity_mean'
                ],
                '{"model": "ECMWF IFS", "resolution": "9km",
                  "note": "Lower precipitation quality - use Open-Meteo"}'::jsonb
            )
        """
        )
    )

    print(
        "✅ Seeds de cobertura regional inseridos (Nordic, Brazil, USA, Global)"
    )


def _create_helper_functions() -> None:
    """
    Cria funções SQL helper para queries espaciais.

    Funções criadas:
    - get_region_by_coordinates(lat, lon): Retorna region_id por coordenadas
    - get_sources_for_location(lat, lon): Retorna fontes disponíveis
    """

    conn = op.get_bind()

    # Função: get_region_by_coordinates
    conn.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION get_region_by_coordinates(
                p_lat DOUBLE PRECISION,
                p_lon DOUBLE PRECISION
            )
            RETURNS TEXT AS $$
            DECLARE
                v_region_id TEXT;
            BEGIN
                -- Criar ponto a partir das coordenadas
                -- Ordem de prioridade: nordic > usa > brazil > global
                SELECT region_id INTO v_region_id
                FROM regional_coverage
                WHERE ST_Contains(
                    geometry,
                    ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326)
                )
                AND region_id != 'global'
                ORDER BY 
                    CASE region_id
                        WHEN 'nordic' THEN 1
                        WHEN 'usa' THEN 2
                        WHEN 'brazil' THEN 3
                        ELSE 4
                    END
                LIMIT 1;
                
                -- Se não encontrou, retorna global
                RETURN COALESCE(v_region_id, 'global');
            END;
            $$ LANGUAGE plpgsql IMMUTABLE;
        """
        )
    )

    # Função: get_sources_for_location
    conn.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION get_sources_for_location(
                p_lat DOUBLE PRECISION,
                p_lon DOUBLE PRECISION
            )
            RETURNS TEXT[] AS $$
            DECLARE
                v_sources TEXT[];
            BEGIN
                -- Retorna fontes disponíveis para a região
                SELECT sources INTO v_sources
                FROM regional_coverage
                WHERE ST_Contains(
                    geometry,
                    ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326)
                )
                AND region_id != 'global'
                ORDER BY 
                    CASE quality_tier
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        WHEN 'low' THEN 3
                    END
                LIMIT 1;
                
                -- Se não encontrou, retorna fontes globais
                IF v_sources IS NULL THEN
                    SELECT sources INTO v_sources
                    FROM regional_coverage
                    WHERE region_id = 'global';
                END IF;
                
                RETURN v_sources;
            END;
            $$ LANGUAGE plpgsql IMMUTABLE;
        """
        )
    )

    print("✅ Funções helper PostGIS criadas")
