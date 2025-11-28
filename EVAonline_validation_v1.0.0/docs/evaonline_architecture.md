# Arquitetura do Sistema EVAonline

## Visão Geral

O **EVAonline** implementa uma arquitetura híbrida moderna para cálculo de evapotranspiração de referência (ETo) combinando três padrões arquiteturais:

### Clean Hexagonal DDD Architecture

1. **Clean Architecture** (Robert C. Martin)
   - Separação em camadas concêntricas
   - Dependências sempre apontam para dentro
   - Núcleo isolado de frameworks e infraestrutura

2. **Hexagonal Architecture** (Alistair Cockburn)
   - Domínio no centro hexagonal
   - Ports (interfaces) e Adapters (implementações)
   - Facilita substituição de infraestrutura sem afetar lógica de negócio

3. **Domain-Driven Design** (Eric Evans)
   - **Entities**: Objetos com identidade única (`EToCalculation`, `ClimateData`)
   - **Value Objects**: Imutáveis sem identidade (`Temperature`, `Location`)
   - **Repositories**: Abstração de persistência
   - **Services**: Lógica de domínio sem estado
   - **Application Services**: Orquestração de casos de uso

## Princípios Arquiteturais

### 1. Dependency Rule (Clean Architecture)
```
Dependências sempre apontam para DENTRO:
Presentation → Application → Domain ✓
Domain → Infrastructure ✗ (NUNCA!)

Domain é o núcleo: sem dependências externas
```

### 2. Ports & Adapters (Hexagonal)
```python
# Port (interface no domínio)
class ClimateDataPort(ABC):
    @abstractmethod
    async def fetch_climate_data(self, lat, lon, dates) -> ClimateData:
        pass

# Adapter (implementação na infraestrutura)
class NASAPowerAdapter(ClimateDataPort):
    async def fetch_climate_data(self, lat, lon, dates) -> ClimateData:
        # Implementação específica da NASA
        pass

# Domain usa Port (não conhece NASA)
class EToCalculationService:
    def __init__(self, climate_port: ClimateDataPort):
        self.climate_port = climate_port
```

### 3. Ubiquitous Language (DDD)
Termos do negócio refletidos no código:
- ETo (Evapotranspiração de Referência)
- FAO-56 Penman-Monteith
- Kalman Ensemble
- Climate Source
- Data Fusion

### 4. Single Responsibility (SOLID)
Cada módulo tem UMA razão para mudar:
- **EToEngine**: apenas cálculo FAO-56
- **KalmanEnsemble**: apenas fusão de dados
- **ClimateSourceManager**: apenas orquestração de fontes

## Arquitetura em Camadas

```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Dash App    │  │  FastAPI     │  │  WebSocket   │      │
│  │  (Frontend)  │  │  (REST API)  │  │  (Real-time) │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   APPLICATION LAYER                          │
│  ┌──────────────────────────────────────────────────┐       │
│  │         Use Cases / Application Services          │       │
│  │  • CalculateEToUseCase                           │       │
│  │  • HistoricalDataExportUseCase                   │       │
│  │  • ForecastEToUseCase                            │       │
│  └──────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     DOMAIN LAYER                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Entities   │  │ Value Objects│  │   Services   │      │
│  │ • ETo        │  │ • Temperature│  │ • EToEngine  │      │
│  │ • Climate    │  │ • Location   │  │ • Kalman     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌────────────────────────────────────────────────┐         │
│  │           Domain Ports (Interfaces)            │         │
│  │  • ClimateDataPort                             │         │
│  │  • EToCalculationPort                          │         │
│  │  • DataFusionPort                              │         │
│  └────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE LAYER                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Adapters     │  │  Databases   │  │    Cache     │      │
│  │ • NASA       │  │ • PostgreSQL │  │ • Redis      │      │
│  │ • OpenMeteo  │  │ • PostGIS    │  │ • TTL        │      │
│  │ • MET Norway │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Celery     │  │  Monitoring  │  │  External    │      │
│  │ • Tasks      │  │ • Prometheus │  │ • OpenTopo   │      │
│  │ • Queue      │  │ • Grafana    │  │ • APIs       │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Fluxo de Dados: Request → Response

### Tempo de Resposta por Etapa

| Etapa | Tempo | Otimização |
|-------|-------|-----------|
| **Frontend Validation** | < 10ms | Client-side JS |
| **API + Cache Check** | 15-30ms | Redis in-memory |
| **Enqueue Task** | 5-10ms | Celery async |
| **Queue → Worker** | 50-200ms | Priority queue |
| **Use Case Setup** | 20-50ms | Minimal overhead |
| **Fetch Climate APIs** | 1000-2000ms | **Gargalo principal** |
| **Data Preprocessing** | 100-200ms | Numpy vectorization |
| **Kalman Fusion** | 300-500ms | Optimized matrices |
| **ETo Calculation** | 80-150ms | Vectorized FAO-56 |
| **Save DB + Cache** | 50-100ms | Bulk insert |
| **WebSocket Notify** | < 20ms | Binary protocol |
| **Render Results** | 100-300ms | Plotly.js |
| | | |
| **TOTAL (Cache Miss)** | **2.0-3.5s** | Meta < 5s |
| **TOTAL (Cache Hit)** | **< 100ms** | 95% requests |

## Modos de Operação

### 1. Dashboard Current (últimos 30 dias)
```
User Request: {"start": "hoje-30d", "end": "hoje"}
→ Prioriza: OpenMeteo Archive (completo até hoje-2d)
→ Complementa: OpenMeteo Forecast (últimos 2 dias)
→ TTL Cache: 6 horas (dados recentes mudam)
```

### 2. Dashboard Forecast (próximos 6 dias)
```
User Request: {"start": "hoje", "end": "hoje+6d"}
→ Fontes: OpenMeteo Forecast + MET Norway
→ Fusão Kalman com pesos maiores para MET
→ TTL Cache: 1 hora (previsões atualizam)
```

### 3. Historical Email (90+ dias passados)
```
User Request: {"start": "2023-01-01", "end": "2023-03-31"}
→ Fonte: NASA POWER (histórico desde 1990)
→ Gera PDF com relatório completo
→ Envia email com anexo
→ TTL Cache: 90 dias (dados imutáveis)
```

## Padrões Complementares

### Event-Driven Architecture
- Celery para processamento assíncrono com eventos
- Workers escalam horizontalmente
- Retry automático com backoff exponencial

### CQRS Lite
- Separação entre comandos (write) e queries (read)
- Cache otimizado para leitura
- Write-through cache strategy

### Repository Pattern
- Abstração completa de acesso a dados
- Troca de banco sem afetar domínio
- Testes com repositórios in-memory

### Service Layer Pattern
- Orquestração de operações complexas
- Transações e consistência
- Error handling centralizado

### Modular Monolith
- Módulos desacoplados
- Preparado para microservices no futuro
- Deployment unificado

## Integrações Externas

### APIs Climáticas
- **NASA POWER**: MERRA-2, 0.5° × 0.625°, histórico desde 1990
- **Open-Meteo Archive**: ERA5-Land, 0.1° × 0.1°, últimos 90 dias
- **Open-Meteo Forecast**: ICON/GFS, previsão 7-16 dias
- **MET Norway**: ECMWF, previsão 10 dias, maior acurácia Europa

### Serviços de Elevação
- **OpenTopoData**: SRTM 30m, ASTER 30m
- Correção FAO-56 para pressão atmosférica
- Ajuste de radiação solar por altitude

### Cache e Persistência
- **Redis**: Cache distribuído, TTL inteligente
- **PostgreSQL + PostGIS**: Dados históricos, geometria
- **MinIO**: Armazenamento de arquivos (CSVs, PDFs)

## Benefícios da Arquitetura

### Testabilidade
- Domain isolado: unit tests sem I/O
- Mocks de adapters para integration tests
- End-to-end tests com infraestrutura real

### Manutenibilidade
- Mudanças localizadas em camadas específicas
- Troca de APIs sem afetar domínio
- Evolução independente de módulos

### Escalabilidade
- Workers Celery escalam horizontalmente
- Cache Redis distribui carga de APIs
- Database sharding possível (PostGIS)

### Qualidade de Código
- Princípios SOLID aplicados
- Dependency Injection explícita
- Type hints completos (mypy)

## Referências

- **Clean Architecture**: Martin, R. C. (2017). Clean Architecture: A Craftsman's Guide to Software Structure and Design.
- **Hexagonal Architecture**: Cockburn, A. (2005). Hexagonal Architecture Pattern.
- **Domain-Driven Design**: Evans, E. (2003). Domain-Driven Design: Tackling Complexity in the Heart of Software.
- **FAO-56**: Allen et al. (1998). Crop evapotranspiration - Guidelines for computing crop water requirements.
