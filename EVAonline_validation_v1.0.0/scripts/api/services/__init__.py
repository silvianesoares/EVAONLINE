"""
Climate Data Services Module - EVAonline

Este módulo contém todos os serviços de dados climáticos da aplicação
EVAonline. Suporta 6 fontes de dados climáticos globais e regionais
com cache inteligente.

ARCHITECTURE OVERVIEW:
======================

Core Services (Factory Pattern):
├── ClimateClientFactory          - Factory para criar clients com DI
├── ClimateSourceManager          - Configuração centralizada das APIs
├── ClimateSourceSelector         - Seleção automática de API por localização
└── ClimateValidationService      - Validação centralizada de inputs

API Clients (6 Fontes de Dados):
├── NASA POWER                  - Dados históricos globais (1990+)
├── MET Norway Locationforecast - Previsão global (padronizado 5 dias)
├── NWS/NOAA Forecast           - Previsão USA Continental (padronizado 5 dias)
├── NWS/NOAA Stations           - Observações USA Continental
├── Open-Meteo Archive          - Histórico global (1990+)
└── Open-Meteo Forecast         - Previsão global (padronizado 5 dias)

CACHE STRATEGY:
==============
- Redis-based intelligent caching
- TTL varies by data type (30 days for historical, 6 hours for forecast)
- Automatic cache invalidation
- Compression optional

ERROR HANDLING:
==============
- Comprehensive validation
- Retry logic with exponential backoff
- Proper logging with loguru
- Graceful degradation

PERFORMANCE:
===========
- Async clients for concurrent requests
- Sync adapters for legacy/Celery compatibility
- Connection pooling
- Rate limiting per API requirements

ATTRIBUTIONS REQUIRED:
=====================
All data sources require proper attribution in publications and displays.
See individual client docstrings for specific attribution text.

Author: EVAonline Development Team
Date: November 2025  # Atualizado para data atual (15/11/2025)
Version: 1.0.0
"""
