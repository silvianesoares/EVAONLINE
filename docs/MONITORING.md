# Monitoramento EVAonline - Prometheus & Grafana

Guia completo para configurar e monitorar métricas do sistema EVAonline usando Prometheus e Grafana.

## 📊 Visão Geral

O EVAonline utiliza Prometheus para coletar métricas e Grafana para visualização, com foco especial em:

- **Weather Validation Errors**: Métricas de qualidade de dados climáticos
- **API Performance**: Latência e throughput das APIs externas
- **Cache Efficiency**: Hit/miss rates do Redis
- **Database Health**: Performance do PostgreSQL
- **Celery Tasks**: Monitoramento de tarefas assíncronas

## 🚀 Quick Start

### 1. Iniciar Stack de Monitoramento

```bash
# Subir todos os serviços incluindo monitoramento
docker-compose up -d

# Verificar status
docker-compose ps
```

### 2. Acessar Dashboards

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000
  - User: `admin`
  - Password: definido em `.env` (`GRAFANA_ADMIN_PASSWORD`)

### 3. Verificar Métricas

```bash
# Endpoint de métricas da API
curl http://localhost:8000/metrics

# Health check
curl http://localhost:8000/health
```

---

## 🔍 Métricas Principais

### Weather Validation Errors

**Métrica**: `weather_validation_errors_total`

Contador de erros de validação de dados climáticos, exposto via `prometheus_client`.

**Labels**:
- `variable`: Nome da variável (`temperature`, `humidity`, `precipitation`, etc.)
- `region`: Região geográfica (`nordic`, `brazil`, `usa`, `global`)
- `source`: Fonte de dados (`met_norway`, `nasa_power`, `open_meteo`, etc.)

**Exemplos de Queries (PromQL)**:

```promql
# Total de erros de validação nas últimas 24h
increase(weather_validation_errors_total[24h])

# Taxa de erros por fonte
rate(weather_validation_errors_total[5m]) by (source)

# Erros de temperatura no Brasil
weather_validation_errors_total{variable="temperature", region="brazil"}

# Top 5 variáveis com mais erros
topk(5, sum by (variable) (weather_validation_errors_total))
```

**Alertas Recomendados**:

```yaml
# alerts.yml (Prometheus Alertmanager)
groups:
  - name: weather_validation
    interval: 5m
    rules:
      - alert: HighValidationErrorRate
        expr: rate(weather_validation_errors_total[5m]) > 0.1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Alta taxa de erros de validação"
          description: "{{ $labels.source }} está com {{ $value }} erros/s"

      - alert: CriticalValidationErrors
        expr: increase(weather_validation_errors_total[1h]) > 100
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Erros críticos de validação"
          description: "Mais de 100 erros na última hora"
```

---

### API Performance

**Métricas**:
- `http_request_duration_seconds`: Histograma de latência HTTP
- `http_requests_total`: Total de requisições HTTP
- `http_requests_in_progress`: Requisições em andamento

**Exemplos**:

```promql
# P95 de latência por endpoint
histogram_quantile(0.95, 
  rate(http_request_duration_seconds_bucket[5m])
) by (endpoint)

# Taxa de sucesso (2xx/3xx vs 4xx/5xx)
sum(rate(http_requests_total{status=~"2..|3.."}[5m])) 
/ 
sum(rate(http_requests_total[5m]))

# Throughput por API externa
rate(http_requests_total[5m]) by (external_api)
```

---

### Cache Efficiency (Redis)

**Métricas**:
- `redis_cache_hits_total`: Total de cache hits
- `redis_cache_misses_total`: Total de cache misses
- `redis_cache_evictions_total`: Evicções de cache

**Cache Hit Rate**:

```promql
# Hit rate global
sum(rate(redis_cache_hits_total[5m])) 
/ 
(
  sum(rate(redis_cache_hits_total[5m])) + 
  sum(rate(redis_cache_misses_total[5m]))
)

# Hit rate por tipo de dado
sum(rate(redis_cache_hits_total[5m])) by (cache_type)
/ 
sum(rate(redis_cache_hits_total[5m]) + rate(redis_cache_misses_total[5m])) by (cache_type)
```

**Alerta de Cache Degradado**:

```yaml
- alert: LowCacheHitRate
  expr: |
    (
      sum(rate(redis_cache_hits_total[5m])) 
      / 
      (sum(rate(redis_cache_hits_total[5m])) + sum(rate(redis_cache_misses_total[5m])))
    ) < 0.7
  for: 15m
  labels:
    severity: warning
  annotations:
    summary: "Taxa de cache hit abaixo de 70%"
```

---

### Database Health (PostgreSQL)

**Métricas** (via `postgres_exporter` ou FastAPI middleware):
- `db_connection_pool_size`: Tamanho do pool de conexões
- `db_query_duration_seconds`: Tempo de execução de queries
- `db_active_connections`: Conexões ativas

**Exemplos**:

```promql
# Queries lentas (P99 > 1s)
histogram_quantile(0.99, 
  rate(db_query_duration_seconds_bucket[5m])
) > 1

# Pool de conexões próximo do limite
db_connection_pool_size / db_connection_pool_max > 0.8
```

---

### Celery Tasks

**Métricas**:
- `celery_task_duration_seconds`: Duração de tarefas
- `celery_task_total`: Total de tarefas executadas
- `celery_task_failures_total`: Tarefas falhadas

**Exemplos**:

```promql
# Taxa de falhas por tarefa
rate(celery_task_failures_total[5m]) by (task_name)

# P95 de duração de tarefas de download
histogram_quantile(0.95,
  rate(celery_task_duration_seconds_bucket{task_name="data_download"}[5m])
)

# Tasks pendentes na fila
celery_queue_length by (queue_name)
```

---

## 📈 Dashboards Grafana

### Dashboard 1: Weather Data Quality

**Painéis**:

1. **Validation Errors Over Time**
   ```json
   {
     "targets": [{
       "expr": "sum(rate(weather_validation_errors_total[5m])) by (variable)"
     }],
     "type": "graph"
   }
   ```

2. **Errors by Region**
   ```json
   {
     "targets": [{
       "expr": "sum(weather_validation_errors_total) by (region)"
     }],
     "type": "piechart"
   }
   ```

3. **Top Error Sources**
   ```json
   {
     "targets": [{
       "expr": "topk(10, sum by (source) (weather_validation_errors_total))"
     }],
     "type": "table"
   }
   ```

### Dashboard 2: API Performance

**Painéis**:

1. **Request Latency (P50, P95, P99)**
2. **Throughput by Endpoint**
3. **Error Rate (4xx/5xx)**
4. **Active Connections**

### Dashboard 3: Cache & Database

**Painéis**:

1. **Cache Hit Rate**
2. **Redis Memory Usage**
3. **PostgreSQL Active Connections**
4. **Slow Query Count (>1s)**

---

## 🛠️ Configuração Avançada

### 1. Exportar Métricas Customizadas

No código Python, use `prometheus_client`:

```python
from prometheus_client import Counter, Histogram, Gauge

# Contador de validações
VALIDATION_ERRORS = Counter(
    'weather_validation_errors_total',
    'Total validation errors',
    ['variable', 'region', 'source']
)

# Histograma de latência
API_LATENCY = Histogram(
    'api_request_duration_seconds',
    'API request duration',
    ['api_name', 'endpoint']
)

# Gauge para cache size
CACHE_SIZE = Gauge(
    'redis_cache_size_bytes',
    'Current cache size in bytes',
    ['cache_type']
)

# Uso
VALIDATION_ERRORS.labels(
    variable='temperature',
    region='brazil',
    source='met_norway'
).inc()

with API_LATENCY.labels(api_name='met_norway', endpoint='forecast').time():
    # Fazer requisição
    pass
```

### 2. Configurar Alertmanager

Criar `docker/monitoring/alertmanager.yml`:

```yaml
route:
  receiver: 'slack-notifications'
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 3h

receivers:
  - name: 'slack-notifications'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#evaonline-alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
```

### 3. Service Discovery (Kubernetes)

Para ambientes Kubernetes, adicionar annotations:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: evaonline-api
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"
```

---

## 🔧 Troubleshooting

### Métricas não aparecem no Prometheus

```bash
# Verificar se endpoint de métricas está acessível
curl http://localhost:8000/metrics

# Verificar targets no Prometheus
# Acesse http://localhost:9090/targets

# Verificar logs do Prometheus
docker logs evaonline-prometheus
```

### Grafana não conecta ao Prometheus

```bash
# Verificar network
docker network inspect evaonline-network

# Testar conectividade do container Grafana
docker exec evaonline-grafana curl http://prometheus:9090/-/ready

# Verificar datasource em Grafana → Configuration → Data Sources
```

### Alta taxa de erros de validação

```bash
# Verificar logs detalhados
docker logs evaonline-api | grep "VALIDATION_ERROR"

# Investigar fonte específica
curl "http://localhost:9090/api/v1/query?query=weather_validation_errors_total{source='met_norway'}"

# Testar API externa diretamente
curl -i "https://api.met.no/weatherapi/locationforecast/2.0/status"
```

---

## 📚 Recursos Adicionais

### Links Úteis

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Dashboards](https://grafana.com/grafana/dashboards/)
- [PromQL Guide](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Python prometheus_client](https://github.com/prometheus/client_python)

### Dashboards Prontos (Grafana)

Importar via Dashboard ID:

- **PostgreSQL**: Dashboard ID `9628`
- **Redis**: Dashboard ID `11835`
- **FastAPI**: Dashboard ID `16399`
- **Celery**: Dashboard ID `11794`

### Melhores Práticas

1. **Naming Conventions**:
   - Use sufixos: `_total` (Counter), `_seconds` (Histogram), `_bytes` (Gauge)
   - Prefixos por componente: `http_`, `db_`, `cache_`

2. **Cardinality**:
   - Evite labels com alta cardinalidade (ex: timestamps, IDs únicos)
   - Limite labels a valores conhecidos (regiões, fontes, tipos)

3. **Retention**:
   - Prometheus: 30 dias (configurado em `docker-compose.yml`)
   - Para longo prazo, use Thanos ou Cortex

4. **Alerting**:
   - Defina thresholds baseados em SLOs (Service Level Objectives)
   - Use `for:` para evitar alertas transientes
   - Agrupe alertas relacionados

---

## 🎯 Métricas Críticas - SLOs

### SLO 1: Disponibilidade da API
- **Target**: 99.9% uptime
- **Métrica**: `up{job="evaonline-api"}`
- **Alerta**: Downtime > 5 minutos

### SLO 2: Latência de Requisições
- **Target**: P95 < 500ms
- **Métrica**: `http_request_duration_seconds`
- **Alerta**: P95 > 1s por 10 minutos

### SLO 3: Qualidade de Dados
- **Target**: < 1% de erros de validação
- **Métrica**: `weather_validation_errors_total`
- **Alerta**: Taxa > 5% por 15 minutos

### SLO 4: Cache Hit Rate
- **Target**: > 80% hit rate
- **Métrica**: `redis_cache_hits_total / (hits + misses)`
- **Alerta**: Hit rate < 70% por 15 minutos

---

## 🚨 Runbook - Ações Operacionais

### Alert: HighValidationErrorRate

**Sintoma**: Taxa de erros de validação > 0.1/s

**Diagnóstico**:
```bash
# 1. Identificar fonte problemática
curl "http://localhost:9090/api/v1/query?query=topk(5, rate(weather_validation_errors_total[5m]) by (source))"

# 2. Verificar logs da fonte
docker logs evaonline-api --tail=100 | grep "met_norway"

# 3. Testar API externa
curl -i "https://api.met.no/weatherapi/locationforecast/2.0/status"
```

**Ações**:
1. Se API externa está down: Failover para fonte secundária
2. Se dados inválidos: Revisar thresholds de validação
3. Se bug no código: Rollback + hotfix

### Alert: LowCacheHitRate

**Sintoma**: Cache hit rate < 70%

**Diagnóstico**:
```bash
# Verificar memória do Redis
docker exec evaonline-redis redis-cli -a $REDIS_PASSWORD INFO memory

# Ver keys mais acessadas
docker exec evaonline-redis redis-cli -a $REDIS_PASSWORD --hotkeys
```

**Ações**:
1. Aumentar memória do Redis se próximo do limite
2. Revisar TTL de cache (pode ser muito baixo)
3. Analisar padrão de acesso (cache warming?)

---

**Última atualização**: 2025-01-15  
**Versão**: 1.0  
**Responsável**: DevOps Team
