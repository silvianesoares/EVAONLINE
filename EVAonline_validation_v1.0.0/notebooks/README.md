# EVAonline Jupyter Notebooks

Este diretório contém notebooks Jupyter demonstrando o uso das APIs climáticas do EVAonline.

## 📚 Notebooks Disponíveis

### Validação e Sistema Principal

1. **01_validation_kalman.ipynb** - Validação do sistema Kalman Fusion (2 APIs globais)
2. **quick_start_example.ipynb** - Exemplo rápido de uso do EVAonline

### Demonstração Individual das APIs (com Dados Reais)

Cada notebook demonstra como baixar e visualizar dados reais de uma API climática específica:

3. **02_nasa_power_api_demo.ipynb** - NASA POWER API
   - Cobertura: Global
   - Período: 1981-presente
   - Variáveis: 7 (temp, humidity, wind, solar, precipitation)
   - Exemplo: Piracicaba/SP (ESALQ/USP)

4. **03_openmeteo_archive_api_demo.ipynb** - Open-Meteo Archive API
   - Cobertura: Global
   - Período: 1940 até hoje-30 dias
   - Variáveis: 10 (temp, humidity, wind, solar, precipitation, ET0)
   - Exemplo: Brasília/DF

5. **04_openmeteo_forecast_api_demo.ipynb** - Open-Meteo Forecast API
   - Cobertura: Global
   - Período: Hoje-25 dias até hoje+5 dias
   - Variáveis: 10 (temp, humidity, wind, solar, precipitation, ET0)
   - Exemplo: São Paulo/SP (dados recentes + previsão)

6. **05_met_norway_api_demo.ipynb** - MET Norway API
   - Cobertura: Global (estratégia regional)
   - Período: Dados diários
   - Variáveis: 8 (temp, humidity, wind, precipitation*)
   - Exemplos: Oslo (Nordic + precipitação) vs Rio de Janeiro (Global - sem precipitação)

7. **06_nws_forecast_api_demo.ipynb** - NWS Forecast API (NOAA)
   - Cobertura: USA Continental + Alaska/Hawaii
   - Período: Previsão até 7 dias
   - Variáveis: 7 (temp, humidity, wind, precipitation)
   - Exemplos: New York City e San Francisco

8. **07_nws_stations_api_demo.ipynb** - NWS Stations API (NOAA)
   - Cobertura: USA (~1,800 estações)
   - Período: Dados observacionais horários (agregados diários)
   - Variáveis: 7 (temp, humidity, wind, solar, precipitation)
   - Exemplos: Chicago e Miami

---

## 🎯 Arquitetura EVAonline

O sistema EVAonline integra **6 APIs climáticas** em uma estratégia de fusão Kalman:

### APIs de Validação (Globais)
- **NASA POWER** - Dados históricos globais (1981-presente)
- **Open-Meteo Archive** - Dados históricos globais (1940-hoje-30d)

### APIs Operacionais (Regionais)
- **Open-Meteo Forecast** - Previsão global (hoje-25d até hoje+5d)
- **MET Norway** - Cobertura global com especialização nórdica
- **NWS Forecast** - Previsão oficial USA (NOAA)
- **NWS Stations** - Observações em tempo real USA

---

## 🚀 Como Usar

### Pré-requisitos

```bash
# Criar ambiente conda
conda env create -f ../environment.yml
conda activate evaonline_validation

# Ou usar pip
pip install -r ../requirements.txt
```

### Executar Notebooks

```bash
# Navegar para o diretório de notebooks
cd EVAonline_validation_v1.0.0/notebooks

# Iniciar Jupyter Lab
jupyter lab

# Ou Jupyter Notebook
jupyter notebook
```

### Estrutura de Cada Notebook

Todos os notebooks de demonstração de API seguem a mesma estrutura:

1. **Importações e Configuração** - Setup do ambiente Python
2. **Inicializar Cliente** - Criar adapter da API
3. **Baixar Dados Reais** - Requisições com coordenadas reais
4. **Converter para DataFrame** - Exploração com pandas
5. **Visualizações** - Gráficos com matplotlib/seaborn
6. **Health Check** - Verificar disponibilidade da API
7. **Salvar Dados** - Exportar CSV para análises futuras

---

## 📊 Dados Gerados

Os notebooks salvam dados em `../data/csv/`:

```
data/csv/
├── nasa_power_piracicaba_demo.csv
├── openmeteo_archive_brasilia_demo.csv
├── openmeteo_forecast_saopaulo_demo.csv
├── met_norway_oslo_demo.csv
├── met_norway_rio_demo.csv
├── nws_forecast_nyc_demo.csv
├── nws_forecast_sf_demo.csv
├── nws_stations_chicago_demo.csv
└── nws_stations_miami_demo.csv
```

---

## 🔧 Troubleshooting

### Erro de Import

Se encontrar erro `ModuleNotFoundError`, verifique que o path dos scripts está correto:

```python
import sys
from pathlib import Path

project_root = Path.cwd().parent
scripts_path = project_root / "scripts"
sys.path.insert(0, str(scripts_path))
```

### Erro de API

Se a API não responder:

1. Verifique sua conexão com internet
2. Consulte o health check no final do notebook
3. Verifique os limites de rate da API (alguns endpoints têm throttling)

### Dados Faltantes

Algumas APIs podem retornar valores `None`/`NaN` para variáveis não disponíveis:
- **MET Norway**: Precipitação disponível apenas na Nordic Region
- **NWS APIs**: Cobertura limitada aos EUA
- **OpenMeteo Archive**: Dados mais antigos podem ter lacunas

---

## 📚 Referências

### APIs Utilizadas

1. **NASA POWER**
   - URL: https://power.larc.nasa.gov/
   - Licença: Public Domain

2. **Open-Meteo**
   - URL: https://open-meteo.com/
   - DOI: 10.5281/zenodo.14582479
   - Licença: CC BY 4.0

3. **MET Norway**
   - URL: https://www.met.no/
   - Licença: CC BY 4.0

4. **NWS (NOAA)**
   - URL: https://www.weather.gov/
   - Licença: US Government Public Domain

### Dataset de Referência

**Xavier BR-DWGD** (Brazilian Daily Weather Gridded Data)
- Período: 1961-01-01 a 2024-03-20
- Resolução: 0.1° × 0.1°
- Estações: 3,625+ estações meteorológicas
- URL: https://sites.google.com/site/alexandrecandidoxavierufes/brazilian-daily-weather-gridded-data

---

## 📖 Citação

Se utilizar estes notebooks em sua pesquisa, por favor cite:

```bibtex
@software{soares2024evaonline,
  author = {Soares, Silviane Carvalho and 
            Maciel, Rodrigo Aparecido Fonseca and 
            Marques, Paulo Augusto Manfron Moraes},
  title = {EVAonline Validation Dataset (1991-2020)},
  year = {2024},
  publisher = {Zenodo},
  url = {https://github.com/silvianesoares/EVAONLINE}
}
```

---

## 📝 Licença

- **Código**: AGPL-3.0-or-later
- **Dados**: Seguem licenças das APIs originais (veja referências acima)

---

## 👥 Autores

- **Silviane Carvalho Soares** - ESALQ/USP - https://orcid.org/0000-0002-1253-7193
- **Rodrigo Aparecido Fonseca Maciel** - UNESP - https://orcid.org/0000-0003-0137-6678
- **Paulo Augusto Manfron Moraes Marques** - ESALQ/USP - https://orcid.org/0000-0002-6818-4833

---

## 📧 Contato

- GitHub: https://github.com/silvianesoares/EVAONLINE
- Issues: https://github.com/silvianesoares/EVAONLINE/issues

---

**Última atualização**: Novembro 2024
