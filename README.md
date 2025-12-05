<table>
<tr>
  <td width="200">
    <img src="frontend/assets/images/logo_evaonline_png.png" alt="EVAonline Logo" width="200">
  </td>
  
  <td>
    🌦️ EVAonline is a comprehensive web application for calculating reference evapotranspiration (ET₀) using the FAO-56 Penman-Monteith method. It employs a sophisticated data fusion approach, integrating real-time meteorological data from multiple global sources (NASA POWER, MET Norway API, National Weather Service API, and NOAA Climate Data Online). Built with modern technologies, it provides interactive dashboards, real-time data processing, and advanced geospatial visualization capabilities.
  </td>
</tr>
</table>

## 🏗️ Architecture

### Tech Stack

**Frontend & Visualization:**
- **Dash**: Interactive dashboards and data visualization
- **Dash Bootstrap Components**: Responsive UI components
- **dash-leaflet**: Interactive maps with GeoJSON layers and heatmaps

**Backend & APIs:**
- **FastAPI**: High-performance API server with WebSocket support
- **Celery**: Asynchronous task processing
- **Redis**: Caching and message broker (Pub/Sub)

**Database & Storage:**
- **PostgreSQL + PostGIS**: Geospatial data management
- **Redis**: High-performance caching layer

**Infrastructure:**
- **Docker & Docker Compose**: Containerization
- **Nginx**: Reverse proxy and static file serving
- **Prometheus + Grafana**: Monitoring and metrics
- **Render**: Cloud deployment platform

## 📁 Project Structure

```
EVAonline_ElsevierSoftwareX/
├── backend/               # Backend application layer
│   ├── api/              # FastAPI REST API and WebSocket services
│   ├── core/             # Core business logic (data processing, ETo calculations)
│   ├── database/         # Database layer (models, connections, migrations)
│   ├── infrastructure/   # Infrastructure services (cache, Celery workers)
│   └── tests/            # Backend integration and unit tests
├── frontend/             # Frontend Dash application
│   ├── app.py           # Main Dash application
│   ├── assets/          # Static assets (CSS, JS, images)
│   ├── components/      # Reusable Dash components
│   └── pages/           # Page-level components
├── tests/                # Root-level integration and system tests
│   └── integration/     # Cross-service integration tests
├── scripts/              # Operational and maintenance scripts
│   ├── manage_db.py     # Database management utilities
│   └── get_hourly_data.py # Data ingestion scripts
├── docs/                 # Project documentation
│   ├── architecture.mmd  # System architecture diagram (Mermaid)
│   ├── DATABASE_README.md # Database schema documentation
│   └── guides/          # Setup and development guides
├── config/               # Configuration files
│   ├── settings/        # Application settings
│   └── translations/    # i18n translation files
├── utils/                # Shared utility modules
├── alembic/              # Database migration scripts (Alembic)
├── assets_generation/    # Static asset generation scripts
├── monitoring/           # Observability configuration (Prometheus, Grafana)
├── archive/              # Deprecated code and old versions
├── docker-compose.yml    # Multi-service orchestration
├── Dockerfile            # Multi-stage container build
├── alembic.ini          # Alembic migration configuration
└── requirements/         # Python dependencies (3-tier structure)
    ├── base.txt         # Core dependencies (50 packages)
    ├── production.txt    # Production additions (60 packages)
    └── development.txt   # Dev-only dependencies (100 packages)
```

## 🚀 Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.9+
- Git

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/angelacunhasoares/EVAonline_SoftwareX.git
   cd EVAonline_ElsevierSoftwareX
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Build and run with Docker Compose:**
   ```bash
   docker-compose up --build
   ```

4. **Access the application:**
   - **Dashboard:** http://localhost:8050
   - **API Documentation:** http://localhost:8000/docs
   - **Prometheus:** http://localhost:9090
   - **Grafana:** http://localhost:3000

## 🛠️ Management Scripts

The project includes unified management scripts for common operations:

### Windows (PowerShell)
```powershell
# Mostrar status dos serviços
docker-compose ps

# Iniciar todos os serviços
docker-compose up -d

# Parar todos os serviços
docker-compose down

# Ver logs
docker-compose logs -f api

# Executar testes
python -m pytest tests/ -v
```

### Linux/macOS (Bash)
```bash
# Mostrar status dos serviços
docker-compose ps

# Iniciar todos os serviços
docker-compose up -d

# Parar todos os serviços
docker-compose down

# Ver logs
docker-compose logs -f api

# Executar testes
python -m pytest tests/ -v
```

##  🔧 Configuration

### Environment Variables

Key configuration options in `.env`:

- `POSTGRES_*`: PostgreSQL database settings
- `REDIS_*`: Redis cache and broker settings
- `FASTAPI_*`: API server configuration
- `DASH_*`: Dashboard application settings

## 📊 Features

### Data Sources and Processing

#### Real-Time Data Integration
EVAonline integrates multiple real-time weather data sources through RESTful APIs:

- **Global Coverage**:
  - **NASA POWER**: Primary meteorological satellite data
  - **Open-Meteo Forecast**: Global weather forecasting and historical data
  - **Open-Meteo Elevation API**: High-precision global elevation data

- **Regional Specialized Sources**:
  - **MET Norway API**: High-resolution European weather data
  - **National Weather Service API**: Detailed USA meteorological data
  - **Open-Meteo Forecast**: MATOPIBA region data (updated 3x daily)

#### Data Fusion and Processing
- **Multi-Source Integration**: 
  - Real-time data fusion from all available APIs
  - Weighted ensemble approach for robust estimates
  - Automated quality control and cross-validation

- **Brazilian Regional Validation**:
  - Validation against Xavier's Brazilian Daily Weather Gridded Dataset
  - High-resolution (0.25° x 0.25°) meteorological data covering Brazil
  - Extensive ground-truth validation using weather station data
  - Reference dataset specifically developed for Brazilian conditions

#### Automated Features
- **Global Elevation Integration**:
  - Automated elevation retrieval for any location
  - Ensures accurate ET₀ calculations worldwide

*Note: EVAonline employs data fusion algorithms to combine multiple real-time data sources, with AgERA5 serving as an independent validation dataset to ensure calculation accuracy.*

### Visualization
- **Interactive Maps**: GeoJSON layers with OpenStreetMap tiles
- **Heatmaps**: Kernel density estimation for city distribution
- **Real-time Updates**: WebSocket-powered live data refresh
- **Statistical Analysis**: Correlation matrices, trend analysis

### Performance
- **Redis Caching**: Sub-second response times for repeated queries
- **Async Processing**: Celery workers for heavy computations
- **Spatial Indexing**: PostGIS GIST indices for fast geospatial queries

## 🛠️ Development

### Local Development Setup

1. **Install dependencies:**
   ```bash
   # For production environment
   pip install -r requirements/production.txt
   
   # OR for development with testing/linting tools
   pip install -r requirements/development.txt
   ```

2. **Run services locally:**
   ```bash
   # Start database and cache
   docker-compose up postgres redis -d
   
   # Run API server
   uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
   
   # Run Dash app
   python pages/main.py
   
   # Run Celery worker
   celery -A api.celery_config worker --loglevel=info
   ```

### API Endpoints

- `GET /api/geo_data`: Retrieve GeoJSON data
- `WebSocket /ws/geo_data`: Real-time data updates
- `POST /api/calculate_eto`: Calculate evapotranspiration

## 📈 Monitoring

The application includes comprehensive monitoring:

- **Prometheus Metrics**: API response times, database queries, cache hit rates
- **Grafana Dashboards**: Visual monitoring of system performance
- **Application Logs**: Structured logging with Loguru

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## 📄 License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0). See the [LICENSE](LICENSE) file for details.

## 🎯 Citation

If you use EVAonline in your research, please cite:

```bibtex
@article{evaonline2024,
  title={EVAonline: An online tool for reference evapotranspiration estimation},
  author={Your Name},
  journal={SoftwareX},
  year={2024}
}
```

## 📞 Support

For questions and support:
- Create an issue in this repository
- Contact: [angelassilviane#gmail.com]

Built with ❤️ for the agricultural and environmental research community.