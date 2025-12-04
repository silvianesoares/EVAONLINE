# EVAonline System Architecture

## Overview

The **EVAonline** implements a modern hybrid architecture for calculating reference evapotranspiration (ETo) combining three architectural patterns:

### Clean Hexagonal DDD Architecture

1. **Clean Architecture** (Robert C. Martin)
   - Separation into concentric layers
   - Dependencies always point inward
   - Core isolated from frameworks and infrastructure

2. **Hexagonal Architecture** (Alistair Cockburn)
   - Domain at the center of hexagon
   - Ports (interfaces) and Adapters (implementations)
   - Facilitates infrastructure replacement without affecting business logic

3. **Domain-Driven Design** (Eric Evans)
   - **Entities**: Objects with unique identity (`EToCalculation`, `ClimateData`)
   - **Value Objects**: Immutable without identity (`Temperature`, `Location`)
   - **Repositories**: Persistence abstraction
   - **Services**: Stateless domain logic
   - **Application Services**: Use case orchestration

## Architectural Principles

### 1. Dependency Rule (Clean Architecture)
```
Dependencies always point INWARD:
Presentation → Application → Domain
Domain → Infrastructure 

Domain is the core: no external dependencies
```

### 2. Ports & Adapters (Hexagonal)
```python
# Port (interface in domain)
class ClimateDataPort(ABC):
    @abstractmethod
    async def fetch_climate_data(self, lat, lon, dates) -> ClimateData:
        pass

# Adapter (implementation in infrastructure)
class NASAPowerAdapter(ClimateDataPort):
    async def fetch_climate_data(self, lat, lon, dates) -> ClimateData:
        # NASA-specific implementation
        pass

# Domain uses Port (doesn't know NASA)
class EToCalculationService:
    def __init__(self, climate_port: ClimateDataPort):
        self.climate_port = climate_port
```

### 3. Ubiquitous Language (DDD)
Business terms reflected in code:
- ETo (Reference Evapotranspiration)
- FAO-56 Penman-Monteith
- Kalman Ensemble
- Climate Source
- Data Fusion

### 4. Single Responsibility (SOLID)
Each module has ONE reason to change:
- **EToEngine**: only FAO-56 calculation
- **KalmanEnsemble**: only data fusion
- **ClimateSourceManager**: only source orchestration

## Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  Dash App    │  │  FastAPI     │  │  WebSocket   │       │
│  │  (Frontend)  │  │  (REST API)  │  │  (Real-time) │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   APPLICATION LAYER                         │
│  ┌──────────────────────────────────────────────────┐       │
│  │         Use Cases / Application Services         │       │
│  │  - CalculateEToUseCase                           │       │
│  │  - HistoricalDataExportUseCase                   │       │
│  │  - ForecastEToUseCase                            │       │
│  └──────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     DOMAIN LAYER                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   Entities   │  │ Value Objects│  │   Services   │       │
│  │ - ETo        │  │ - Temperature│  │ - EToEngine  │       │
│  │ - Climate    │  │ - Location   │  │ - Kalman     │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│  ┌────────────────────────────────────────────────┐         │
│  │           Domain Ports (Interfaces)            │         │
│  │  - ClimateDataPort                             │         │
│  │  - EToCalculationPort                          │         │
│  │  - DataFusionPort                              │         │
│  └────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE LAYER                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Adapters     │  │  Databases   │  │    Cache     │       │
│  │ - NASA       │  │ - PostgreSQL │  │ - Redis      │       │
│  │ - OpenMeteo  │  │ - PostGIS    │  │ - TTL        │       │
│  │ - MET Norway │  │              │  │              │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   Celery     │  │  Monitoring  │  │  External    │       │
│  │ - Tasks      │  │ - Prometheus │  │ - OpenTopo   │       │
│  │ - Queue      │  │ - Grafana    │  │ - APIs       │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow: Request → Response

### Response Time Per Stage

| Stage | Time | Optimization |
|-------|-------|-----------|
| **Frontend Validation** | < 10ms | Client-side JS |
| **API + Cache Check** | 15-30ms | Redis in-memory |
| **Enqueue Task** | 5-10ms | Celery async |
| **Queue → Worker** | 50-200ms | Priority queue |
| **Use Case Setup** | 20-50ms | Minimal overhead |
| **Fetch Climate APIs** | 1000-2000ms | **Main bottleneck** |
| **Data Preprocessing** | 100-200ms | Numpy vectorization |
| **Kalman Fusion** | 300-500ms | Optimized matrices |
| **ETo Calculation** | 80-150ms | Vectorized FAO-56 |
| **Save DB + Cache** | 50-100ms | Bulk insert |
| **WebSocket Notify** | < 20ms | Binary protocol |
| **Render Results** | 100-300ms | Plotly.js |
| | | |
| **TOTAL (Cache Miss)** | **2.0-3.5s** | Target < 5s |
| **TOTAL (Cache Hit)** | **< 100ms** | 95% requests |

## Operating Modes

### 1. Dashboard Current (last 30 days)
```
User Request: {"start": "today-30d", "end": "today"}
→ Prioritizes: OpenMeteo Archive (complete until today-2d)
→ Complements: OpenMeteo Forecast (last 2 days)
→ Cache TTL: 6 hours (recent data changes)
```

### 2. Dashboard Forecast (next 6 days)
```
User Request: {"start": "today", "end": "today+6d"}
→ Sources: OpenMeteo Forecast + MET Norway
→ Kalman fusion with higher weights for MET
→ Cache TTL: 1 hour (forecasts update)
```

### 3. Historical Email (90 past days)
```
User Request: {"start": "2023-01-01", "end": "2023-03-31", "email": "user@example.com"}
→ Source: NASA POWER (history since 1990)
→ Generates PDF with complete report
→ Sends email with attachment
→ Cache TTL: 90 days (immutable data)
```

## Complementary Patterns

### Event-Driven Architecture
- Celery for asynchronous event processing
- Workers scale horizontally
- Automatic retry with exponential backoff

### CQRS Lite
- Separation between commands (write) and queries (read)
- Cache optimized for reading
- Write-through cache strategy

### Repository Pattern
- Complete abstraction of data access
- Database swap without affecting domain
- Tests with in-memory repositories

### Service Layer Pattern
- Orchestration of complex operations
- Transactions and consistency
- Centralized error handling

### Modular Monolith
- Decoupled modules
- Prepared for microservices in the future
- Unified deployment

## External Integrations

### Climate APIs
- **NASA POWER**: MERRA-2, 0.5° × 0.625°, history since 1990
- **Open-Meteo Archive**: ERA5-Land, 0.1° × 0.1°, history since 1990
- **Open-Meteo Forecast**: ICON/GFS, 5 days forecast
- **MET Norway**: ECMWF, 5 days forecast, higher accuracy for Europe

### Elevation Services
- **OpenTopoData**: SRTM 30m, ASTER 30m
- FAO-56 pressure atmosphere correction
- Solar radiation adjustment by altitude

### Cache and Persistence
- **Redis**: Distributed cache, intelligent TTL
- **PostgreSQL + PostGIS**: Historical data, geometry
- **MinIO**: File storage (CSVs, Excel, PDFs)

## Architecture Benefits

### Testability
- Domain isolated: unit tests without I/O
- Adapter mocks for integration tests
- End-to-end tests with real infrastructure

### Maintainability
- Changes localized to specific layers
- API swap without affecting domain
- Independent module evolution

### Scalability
- Celery workers scale horizontally
- Redis cache distributes API load
- Database sharding possible (PostGIS)

### Code Quality
- SOLID principles applied
- Explicit Dependency Injection
- Complete type hints (mypy)

## References

- **Clean Architecture**: Martin, R. C. (2017). Clean Architecture: A Craftsman's Guide to Software Structure and Design.
- **Hexagonal Architecture**: Cockburn, A. (2005). Hexagonal Architecture Pattern.
- **Domain-Driven Design**: Evans, E. (2003). Domain-Driven Design: Tackling Complexity in the Heart of Software.
- **FAO-56**: Allen et al. (1998). Crop evapotranspiration - Guidelines for computing crop water requirements.
