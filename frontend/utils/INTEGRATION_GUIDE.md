# Guia de Integração: Frontend ↔ Backend com Detecção Automática de Modos

## 📊 Visão Geral

O sistema atual do frontend possui **3 opções de interface** que mapeiam automaticamente para os **3 modos operacionais** do backend:

```
┌─────────────────────────────────────────────────────────────────┐
│                     FRONTEND (UI Simples)                       │
├─────────────────────────────────────────────────────────────────┤
│ 1. Historical Data (1990 - today)                               │
│    ↓ DatePickerSingle: start_date + end_date                    │
│                                                                  │
│ 2. Current Data → Recent (last 7-30 days)                       │
│    ↓ Dropdown: [7, 14, 21, 30] days                            │
│                                                                  │
│ 3. Current Data → Forecast (next 5 days)                        │
│    ↓ Fixed: today → today+5d                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    (Auto-Detection)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND (3 Operational Modes)                │
├─────────────────────────────────────────────────────────────────┤
│ 1. HISTORICAL_EMAIL                                             │
│    • 1-90 days, free date selection                             │
│    • Sources: NASA POWER + Open-Meteo Archive                   │
│    • 1990-01-01 → today-2d                                      │
│                                                                  │
│ 2. DASHBOARD_CURRENT                                            │
│    • Fixed periods: 7, 14, 21, 30 days                          │
│    • Sources: NASA + Open-Meteo Archive + Open-Meteo Forecast   │
│    • today-29d → today                                          │
│                                                                  │
│ 3. DASHBOARD_FORECAST                                           │
│    • Fixed: 6 days (today → today+5d)                           │
│    • Sources: Open-Meteo Forecast + MET Norway + NWS Forecast   │
│    • USA option: NWS Stations (real-time)                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Implementação Atual

### Estrutura de Arquivos

```
frontend/
├── pages/
│   ├── dash_eto.py          # Layout com 3 radio options
│   └── home.py              # Mapa para seleção de localização
├── callbacks/
│   └── eto_callbacks.py     # Callbacks de validação e cálculo
└── utils/
    ├── mode_detector.py     # ✨ NOVO: Detecção automática de modos
    └── INTEGRATION_GUIDE.md # Este arquivo
```

### 1. Interface do Usuário (dash_eto.py)

```python
# Radio button principal (linhas 161-172)
dbc.RadioItems(
    id="data-type-radio",
    options=[
        {
            "label": "📅 Historical Data (1990 - today)",
            "value": "historical",
        },
        {
            "label": "🌤️ Current Data (last 7 days)",
            "value": "current",
        },
    ],
    value="historical",
)

# Sub-opções para "current" (linhas 749-761 em eto_callbacks.py)
dbc.RadioItems(
    id="current-subtype-radio",
    options=[
        {
            "label": "📊 Dados Recentes (até 30 dias atrás)",
            "value": "recent",
        },
        {
            "label": "🔮 Previsão (próximos 5 dias)",
            "value": "forecast",
        },
    ],
    value="recent",
)
```

### 2. Detecção Automática de Modo (mode_detector.py)

```python
from frontend.utils.mode_detector import OperationModeDetector
from datetime import date, timedelta

# Exemplo 1: Historical (90 days)
today = date.today()
start = today - timedelta(days=90)
end = today - timedelta(days=2)  # Delay de 2 dias

payload = OperationModeDetector.prepare_api_request(
    ui_selection="historical",
    latitude=-15.8,
    longitude=-47.9,
    start_date=start,
    end_date=end,
    email="user@example.com",  # Obrigatório para historical
)
# Resultado:
# {
#     "latitude": -15.8,
#     "longitude": -47.9,
#     "start_date": "2024-09-05",
#     "end_date": "2024-12-02",
#     "mode": "HISTORICAL_EMAIL",  # ← Auto-detectado!
#     "email": "user@example.com"
# }

# Exemplo 2: Recent (30 days dashboard)
payload = OperationModeDetector.prepare_api_request(
    ui_selection="recent",
    latitude=-15.8,
    longitude=-47.9,
    period_days=30,
)
# Resultado:
# {
#     "latitude": -15.8,
#     "longitude": -47.9,
#     "start_date": "2024-11-04",  # Calculado: today - 29 days
#     "end_date": "2024-12-04",    # Calculado: today
#     "mode": "DASHBOARD_CURRENT", # ← Auto-detectado!
#     "email": null
# }

# Exemplo 3: Forecast (6 days fixed)
payload = OperationModeDetector.prepare_api_request(
    ui_selection="forecast",
    latitude=40.7128,  # Nova York
    longitude=-74.0060,
    usa_forecast_source="fusion",  # ou "stations" para NWS real-time
)
# Resultado:
# {
#     "latitude": 40.7128,
#     "longitude": -74.0060,
#     "start_date": "2024-12-04",  # Calculado: today
#     "end_date": "2024-12-09",    # Calculado: today + 5d
#     "mode": "DASHBOARD_FORECAST", # ← Auto-detectado!
#     "email": null
# }
```

### 3. Callback de Cálculo ETo (eto_callbacks.py)

```python
from frontend.utils.mode_detector import OperationModeDetector
import requests

@callback(
    Output("eto-results-container", "children"),
    Input("calculate-eto-btn", "n_clicks"),
    [
        State("navigation-coordinates", "data"),  # Coordenadas do Store
        State("data-type-radio", "value"),  # "historical" ou "current"
        State("start-date-historical", "date"),  # Para historical
        State("end-date-historical", "date"),
        State("current-subtype-radio", "value"),  # "recent" ou "forecast"
        State("days-current", "value"),  # 7, 14, 21, ou 30
    ],
    prevent_initial_call=True,
)
def calculate_eto(
    n_clicks,
    coords_data,
    data_type,
    start_date_hist,
    end_date_hist,
    current_subtype,
    days_current,
):
    """Calcula ETo com detecção automática de modo."""
    
    if not n_clicks or not coords_data:
        return None
    
    lat = float(coords_data["lat"])
    lon = float(coords_data["lon"])
    
    try:
        # 1. Determinar UI selection
        if data_type == "historical":
            ui_selection = "historical"
            start = datetime.fromisoformat(start_date_hist).date()
            end = datetime.fromisoformat(end_date_hist).date()
            payload = OperationModeDetector.prepare_api_request(
                ui_selection="historical",
                latitude=lat,
                longitude=lon,
                start_date=start,
                end_date=end,
                email=None,  # Opcional: pedir no formulário
            )
        
        elif current_subtype == "recent":
            ui_selection = "recent"
            days = int(days_current)
            payload = OperationModeDetector.prepare_api_request(
                ui_selection="recent",
                latitude=lat,
                longitude=lon,
                period_days=days,
            )
        
        elif current_subtype == "forecast":
            ui_selection = "forecast"
            # TODO: Detectar se está nos EUA para opção NWS Stations
            payload = OperationModeDetector.prepare_api_request(
                ui_selection="forecast",
                latitude=lat,
                longitude=lon,
                usa_forecast_source="fusion",
            )
        
        else:
            raise ValueError(f"Invalid data_type/subtype: {data_type}/{current_subtype}")
        
        # 2. Chamar API do backend
        logger.info(f"📡 Sending request: {payload}")
        
        response = requests.post(
            "http://localhost:8000/internal/eto/calculate",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        
        # 3. Renderizar resultados
        return render_eto_results(result, payload["mode"])
    
    except ValueError as e:
        logger.error(f"❌ Validation error: {e}")
        return dbc.Alert(
            f"Invalid input: {str(e)}",
            color="danger",
        )
    
    except requests.exceptions.Timeout:
        return dbc.Alert(
            "Backend timeout (>30s). Please try again.",
            color="warning",
        )
    
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ API error: {e}")
        return dbc.Alert(
            f"Backend error: {str(e)}",
            color="danger",
        )
```

---

## 📝 Validações Automáticas

O `OperationModeDetector` realiza validações automáticas:

### HISTORICAL_EMAIL
```python
✅ start_date >= 1990-01-01
✅ end_date <= today - 2 days
✅ 1 <= period_days <= 90
✅ start_date < end_date
```

### DASHBOARD_CURRENT
```python
✅ end_date == today
✅ period_days in [7, 14, 21, 30]
✅ start_date == today - (period_days - 1)
```

### DASHBOARD_FORECAST
```python
✅ start_date == today
✅ end_date == today + 5 days
✅ period_days == 6 (fixed)
```

---

## 🚀 Próximos Passos

### 1. Atualizar callback principal
- [ ] Importar `OperationModeDetector`
- [ ] Substituir lógica manual por `prepare_api_request()`
- [ ] Testar 3 cenários (historical, recent, forecast)

### 2. Adicionar indicador visual de modo
- [ ] Badge mostrando modo detectado
- [ ] Ícone das fontes de dados usadas
- [ ] Tooltip com limites do modo

### 3. Implementar opção NWS Stations (USA)
- [ ] Detectar se coordenadas estão nos EUA
- [ ] Mostrar radio button "Fusion vs Stations"
- [ ] Passar `usa_forecast_source` correto

### 4. Adicionar campo de email (opcional)
- [ ] Input para email no modo historical
- [ ] Validação de formato
- [ ] Envio para backend

---

## 🧪 Testes

Execute os seguintes cenários:

```bash
# 1. Historical: 30 dias (Brasília)
Lat: -15.8, Lon: -47.9
Modo: Historical
Start: 2024-11-01
End: 2024-11-30
Resultado esperado: HISTORICAL_EMAIL, 30 dias

# 2. Recent: 14 dias (São Paulo)
Lat: -23.5505, Lon: -46.6333
Modo: Current → Recent
Período: 14 dias
Resultado esperado: DASHBOARD_CURRENT, end_date=today

# 3. Forecast: 6 dias (Nova York)
Lat: 40.7128, Lon: -74.0060
Modo: Current → Forecast
Resultado esperado: DASHBOARD_FORECAST, today → today+5d

# 4. Forecast USA com Stations
Lat: 40.7128, Lon: -74.0060
Modo: Current → Forecast
Source: Stations
Resultado esperado: DASHBOARD_FORECAST_STATIONS
```

---

## 📚 Referências

- **Backend**: `backend/api/services/climate_source_availability.py`
- **Rotas**: `backend/api/routes/eto_routes.py`
- **Validação**: `backend/api/services/climate_validation.py`
- **Fontes**: `backend/api/services/climate_source_manager.py`
