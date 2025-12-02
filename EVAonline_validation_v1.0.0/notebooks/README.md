# EVAonline Jupyter Notebooks

This directory contains Jupyter notebooks demonstrating the use of EVAonline climate APIs.

### Individual API Demonstrations (with Real Data)

Each notebook demonstrates how to download and visualize real data from a specific climate API:

1. **01_nasa_power_api_demo.ipynb** - NASA POWER API
   - Coverage: Global
   - Period: 1990-present
   - Variables: 7 (temp, humidity, wind, solar, precipitation)
   - Example: Piracicaba/SP (ESALQ/USP)

2. **02_openmeteo_archive_api_demo.ipynb** - Open-Meteo Archive API
   - Coverage: Global
   - Period: 1990 until today-30 days
   - Variables: 10 (temp, humidity, wind, solar, precipitation, ET0)
   - Example: Brasília/DF

3. **03_openmeteo_forecast_api_demo.ipynb** - Open-Meteo Forecast API
   - Coverage: Global
   - Period: Today-25 days until today+5 days = 30 days
   - Variables: 10 (temp, humidity, wind, solar, precipitation, ET0)
   - Example: São Paulo/SP (recent data + forecast)

4. **04_met_norway_api_demo.ipynb** - MET Norway API
   - Coverage: Global (regional strategy)
   - Period: Daily data
   - Variables: 8 (temp, humidity, wind, precipitation*)
   - Examples: Oslo (Nordic + precipitation) vs Rio de Janeiro (Global - no precipitation)

5. **05_nws_forecast_api_demo.ipynb** - NWS Forecast API (NOAA)
   - Coverage: USA Continental + Alaska/Hawaii
   - Period: Forecast up to 6 days
   - Variables: 6 (temp, humidity, wind, precipitation)
   - Examples: New York City and San Francisco

6. **06_nws_stations_api_demo.ipynb** - NWS Stations API (NOAA)
   - Coverage: USA (~1,800 stations)
   - Period: Hourly observational data (aggregated daily)
   - Variables: 7 (temp, humidity, wind, solar, precipitation)
   - Examples: Fairplay, Park, Colorado and Miami

---

## EVAonline Architecture

The EVAonline system integrates **6 climate APIs** in an adaptive Kalman fusion strategy:

### Validation APIs (Global)
- **NASA POWER** - Global historical data (1990-present)
- **Open-Meteo Archive** - Global historical data (1990-today-30d)

### Operational APIs (Regional)
- **Open-Meteo Forecast** - Global forecast (today-25d until today+5d = 30 days)
- **MET Norway** - Global coverage with Nordic specialization
- **NWS Forecast** - Official USA forecast (NOAA)
- **NWS Stations** - Real-time observations USA

---

## How to Use

### Prerequisites

```bash
# Create conda environment
conda env create -f ../environment.yml
conda activate evaonline_validation

# Or use pip
pip install -r ../requirements.txt
```

### Running Notebooks

```bash
# Navigate to notebooks directory
cd EVAonline_validation_v1.0.0/notebooks

# Start Jupyter Lab
jupyter lab

# Or Jupyter Notebook
jupyter notebook
```

### Structure of Each Notebook

All API demonstration notebooks follow the same structure:

1. **Imports and Configuration** - Python environment setup
2. **Initialize Client** - Create API adapter
3. **Download Real Data** - Requests with real coordinates
4. **Convert to DataFrame** - Exploration with pandas
5. **Visualizations** - Charts with matplotlib/seaborn
6. **Health Check** - Verify API availability
7. **Save Data** - Export CSV for future analyses

---

## Generated Data

Notebook data is saved in `../data/csv/`:

```
data/csv/
├── nasa_power_piracicaba_demo.csv
├── openmeteo_archive_brasilia_demo.csv
├── openmeteo_forecast_saopaulo_demo.csv
├── met_norway_oslo_demo.csv
├── met_norway_rio_demo.csv
├── nws_forecast_nyc_demo.csv
├── nws_forecast_sf_demo.csv
├── nws_stations_fairplay_demo.csv
└── nws_stations_miami_demo.csv
```---

## Troubleshooting

### Import Error

If you encounter `ModuleNotFoundError`, verify that the scripts path is correct:

```python
import sys
from pathlib import Path

project_root = Path.cwd().parent
sys.path.insert(0, str(project_root))
```

### API Error

If the API does not respond:

1. Check your internet connection
2. Consult the health check at the end of the notebook
3. Check API rate limits (some endpoints have throttling)

### Missing Data

Some APIs may return `None`/`NaN` values for unavailable variables:
- **MET Norway**: Precipitation available only in Nordic Region
- **NWS APIs**: Coverage limited to USA

---

## References

### APIs Used

1. **NASA POWER**
   - URL: https://power.larc.nasa.gov/
   - API: https://power.larc.nasa.gov/docs/tutorials/api-getting-started/
   - License: Public Domain

2. **Open-Meteo**
   - URL: https://open-meteo.com/
   - DOI: https://doi.org/10.5281/zenodo.14582479
   - Data License: CC BY 4.0
   - Open-Meteo is open-source, License: GNU Affero General Public Licence Version 3 AGPLv3
   - GitHub: https://github.com/open-meteo/open-meteo

3. **MET Norway**
   - URL: https://www.met.no/
   - API: https://api.met.no/weatherapi/locationforecast/2.0/documentation
   - License: Norwegian Licence for Open Government Data (NLOD) 2.0 and Creative Commons 4.0 BY International

4. **NWS (NOAA)**
   - URL: https://www.weather.gov/
   - API: https://www.weather.gov/documentation/services-web-api
   - License: US Government Public Domain

### Reference Dataset for Validation

**Xavier BR-DWGD** (Brazilian Daily Weather Gridded Data)
- Period: 1961-01-01 to 2024-03-20
- Resolution: 0.1° × 0.1°
- URL: https://sites.google.com/site/alexandrecandidoxavierufes/brazilian-daily-weather-gridded-data---

## Citation

If you use these notebooks in your research, please cite:

```bibtex
@software{evaonline2025,
  author = {Soares, Ângela Silviane Moura Cunha and
            Maciel, Carlos Dias and
            Marques, Patricia Angélica Alves},
  title = {EVAonline Validation Dataset (1991-2020)},
  year = {2025},
  publisher = {Zenodo},
  url = {https://github.com/silvianesoares/EVAONLINE}
}
```

---

## License

- **Code**: AGPL-3.0
- **Data**: Follow licenses of original APIs (see references above)

---

## Authors

- **Ângela Silviane Moura Cunha Soares** - ESALQ/USP - https://orcid.org/0000-0002-1253-7193
- **Carlos Dias Maciel** - UNESP - https://orcid.org/0000-0003-0137-6678
- **Patricia Angélica Alves Marques** - ESALQ/USP - https://orcid.org/0000-0002-6818-4833

---

## Contact

- GitHub: https://github.com/silvianesoares/EVAONLINE
- Issues: https://github.com/silvianesoares/EVAONLINE/issues

---

**Last updated**: November 2025
