# EVAOnline Validation Dataset v1.0.0

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Data](https://img.shields.io/badge/Data-Open%20Access-brightgreen.svg)](https://zenodo.org/)

**Complete validation dataset for EVAonline: Validation Dataset v1.0.0: Adaptive Kalman Fusion System for Reference Evapotranspiration in Brazil (1991-2020)**

---

## 📋 Overview

This repository contains the complete validation dataset for **EVAonline**, an adaptive Kalman fusion system integrating **6 climate APIs** (NASA POWER, Open-Meteo Archive/Forecast, Met Norway, NWS USA) for reference evapotranspiration (ETo) estimation. This validation evaluates ETo accuracy using **2 global reanalysis sources** (NASA POWER + Open-Meteo Archive) across **17 Brazilian cities** in the MATOPIBA region plus Piracicaba/SP (1991-2020, 30 years, 186,287 observations).

### 🎯 Key Results

| Method | R² | KGE | NSE | MAE (mm/day) | RMSE (mm/day) | PBIAS (%) |
|--------|-------|------|------|--------------|---------------|-----------|
| **Xavier et al. (Reference)** | 1.000 | 1.000 | 1.000 | 0.00 | 0.00 | 0.0 |
| **EVAonline (Kalman Fusion)** | **0.694** | **0.814** | **0.676** | **0.423** | **0.566** | **+0.71** |
| OpenMeteo API (ERA5-Land) | 0.649 | 0.584 | 0.216 | 0.690 | 0.860 | +8.27 |
| NASA POWER (FAO-56 calc) | 0.740 | 0.411 | -0.363 | 0.845 | 1.117 | +15.78 |
| OpenMeteo (FAO-56 calc) | 0.636 | 0.432 | -0.547 | 0.859 | 1.097 | +13.02 |

**✅ EVAonline achieves:**
- **Best KGE = 0.814** (98% higher than NASA, 88% higher than OpenMeteo calc, 39% higher than OpenMeteo API)
- **Lowest MAE = 0.423 mm/day** (50% lower than NASA, 51% lower than OpenMeteo calc)
- **Near-zero bias (0.71%)** vs NASA (+15.78%), OpenMeteo calc (+13.02%), OpenMeteo API (+8.27%)
- **Most consistent performance** across all 17 cities (smallest metric amplitude)

📊 **Detailed analysis**: See [docs/performance_analysis.md](docs/performance_analysis.md)

---

## 🚀 Quick Start

### Installation

```bash
# Using pip
pip install -r requirements.txt

# Using conda
conda env create -f environment.yml
conda activate evaonline-validation
```

### Recommended Start Path

**🎯 NEW USERS - Start here:**

| Path | Notebook | Best For | Time |
|------|----------|----------|------|
| **1️⃣ Tutorial** | [`tutorial_full_pipeline.ipynb`](tutorial_full_pipeline.ipynb) | Learning methodology, understanding pipeline | ~10 min |
| **2️⃣ Complete Study** | [`complete_validation_analysis.ipynb`](complete_validation_analysis.ipynb) | Reproducing results, comparing all sources | ~30 min |

**Why start with notebooks?**
- ✅ **Interactive** - Run code cells step-by-step, see immediate results
- ✅ **Educational** - Detailed markdown explanations for each step
- ✅ **Visual** - High-quality plots generated automatically
- ✅ **Complete** - No need to run multiple scripts separately
- ✅ **Accurate** - Implements all scientific fixes (elevation API, wind conversion, region detection)

**Tutorial Notebook** (`tutorial_full_pipeline.ipynb`):
- Single city demonstration (Piracicaba/SP)
- Shows complete EVAonline pipeline from raw data to validation
- Automatic elevation fetching from OpenTopoData API
- Wind height conversion (10m → 2m) using FAO-56 Eq. 47
- Region-specific validation limits (Xavier for Brazil)
- Kalman fusion with uncertainty quantification
- **Perfect for understanding how EVAonline works**

**Complete Analysis Notebook** (`complete_validation_analysis.ipynb`):
- All 17 cities automated analysis
- 4 ETo sources: NASA POWER, Open-Meteo API, Open-Meteo calc, EVAonline Fusion
- Individual city reports (time series + 4 scatter plots each)
- Summary statistics, boxplots, heatmaps, ranking tables
- Complete CSV exports for further analysis
- **Reproduces all paper results in one run**

### Alternative: Load Pre-Processed Data

```python
import pandas as pd

# Load consolidated climate data (1991-2020)
df = pd.read_csv("data/3_combined_datasets/all_climate_data_1991_2020.csv", parse_dates=["date"])

# Load ETo comparison (4 sources: Xavier, NASA, OpenMeteo, EVAonline)
df_eto = pd.read_csv("data/7_comparison_all_sources/COMPARISON_ALL_SOURCES.csv", parse_dates=["date"])

# Filter by city
piracicaba = df_eto[df_eto["city"] == "Piracicaba_SP"]

# Compare methods
print(piracicaba[["date", "eto_xavier", "eto_nasa", "eto_openmeteo_api", "eto_evaonline"]].head())
```

📓 **Additional tutorials**: See `notebooks/` directory for 6 API demo notebooks

---

## 📂 Repository Structure

```
EVAonline_validation_v1.0.0/
├── data/                          # Validation datasets
│   ├── info_cities.csv           # 17 cities metadata (coordinates, elevation)
│   ├── 1_figures/                # Study area maps and plots
│   ├── 2_statistics_raw_dataset/ # Descriptive statistics (Script 2)
│   ├── 3_combined_datasets/      # Consolidated raw data (Script 3)
│   │   ├── all_climate_data_1991_2020.csv        # All sources combined
│   │   ├── all_nasa_power_raw_1991_2020.csv      # NASA POWER raw
│   │   └── all_open_meteo_raw_1991_2020.csv      # Open-Meteo raw
│   ├── 4_eto_nasa_only/          # NASA ETo calculations (Script 4)
│   ├── 4_eto_openmeteo_only/     # OpenMeteo ETo calculations (Script 4)
│   ├── 5_validation_eto_evaonline/ # Single-source validation (Script 5)
│   ├── 6_validation_full_pipeline/ # EVAonline Kalman fusion (Script 6)
│   ├── 7_comparison_all_sources/ # 4-source comparison (Script 7)
│   │   ├── COMPARISON_ALL_SOURCES.csv  # Complete comparison data
│   │   ├── SUMMARY_BY_SOURCE.csv       # Summary metrics by source
│   │   └── plots/                      # Comparison visualizations
│   ├── csv/                      # Additional CSV data
│   └── original_data/            # Raw sources (Xavier, NASA, OpenMeteo)
│       ├── eto_xavier_csv/       # Xavier ETo reference data
│       ├── nasa_power_raw/       # NASA POWER API downloads
│       ├── open_meteo_raw/       # Open-Meteo API downloads
│       ├── eto_open_meteo/       # Open-Meteo ETo API data
│       ├── historical/           # Historical climate data
│       └── map_data/             # Geospatial data (shapefiles, GeoJSON)
│
├── scripts/                       # Validation scripts
│   ├── 1_generate_matopiba_map.py        # Study area map generation
│   ├── 2_generate_descriptive_stats.py   # Descriptive statistics
│   ├── 3_concat_row_dataset_nasapower_openmeteo.py  # Data consolidation
│   ├── 4_calculate_eto_data_from_openmeteo_or_nasapower.py  # ETo calculation
│   ├── 5_validate_eto_calc.py            # Single-source validation
│   ├── 6_validate_full_pipeline.py       # Full Kalman fusion ⭐
│   ├── 7_compare_all_eto_sources.py      # 4-source comparison
│   ├── config.py                         # Configuration settings
│   ├── api/                      # API client modules
│   │   └── services/             # Climate API services
│   │       ├── nasa_power/       # NASA POWER client
│   │       ├── openmeteo_archive/  # Open-Meteo Archive client
│   │       ├── openmeteo_forecast/ # Open-Meteo Forecast client
│   │       ├── met_norway/       # Met Norway client
│   │       ├── nws_forecast/     # NWS Forecast client
│   │       ├── nws_stations/     # NWS Stations client
│   │       ├── opentopo/         # OpenTopoData elevation client
│   │       ├── geographic_utils.py   # Geographic utilities
│   │       ├── weather_utils.py      # Weather data utilities
│   │       ├── climate_validation.py # Data validation
│   │       └── climate_source_*.py   # Source management
│   └── core/                     # Core processing modules
│       ├── data_processing/      # Data preprocessing, Kalman ensemble
│       └── eto_calculation/      # ETo calculation services
│
├── docs/                          # Detailed documentation
│   ├── data_sources_specifications.md   # API technical specs
│   ├── wind_height_conversion.md        # FAO-56 Eq. 47 methodology
│   ├── kalman_methodology.md            # Kalman filter details
│   ├── performance_analysis.md          # Detailed results
│   ├── api_operational_details.md       # Operational guidelines
│   ├── validation_eto_evaonline.md      # Full validation report
│   ├── elevation_integration.md         # OpenTopoData integration
│   ├── evaonline_architecture.md        # System architecture
│   ├── regional_validation_system.md    # Regional validation
│   ├── study_area_map_generation.md     # Map generation guide
│   └── README.md                        # Documentation index
│
├── notebooks/                     # Jupyter tutorials (6 API demos)
│   ├── 01_nasa_power_api_demo.ipynb     # NASA POWER demonstration
│   ├── 02_openmeteo_archive_api_demo.ipynb  # Open-Meteo Archive demo
│   ├── 03_openmeteo_forecast_api_demo.ipynb # Open-Meteo Forecast demo
│   ├── 04_met_norway_api_demo.ipynb     # Met Norway demonstration
│   ├── 05_nws_forecast_api_demo.ipynb   # NWS Forecast demonstration
│   ├── 06_nws_stations_api_demo.ipynb   # NWS Stations demonstration
│   └── README.md                        # Notebooks documentation
│
├── tutorial_full_pipeline.ipynb       # ⭐ RECOMMENDED START - Single city tutorial
├── complete_validation_analysis.ipynb # ⭐ Complete 17-city validation study
│
├── CITATION.cff               # Citation metadata (CFF format)
├── zenodo.json                # Zenodo deposit metadata
├── LICENSE                    # AGPL-3.0 license
├── README.md                  # This file
├── requirements.txt           # Python dependencies (pip)
└── environment.yml            # Conda environment specification
```

---

## 📊 Data Sources

### Overview

| Source | Resolution | Period | Latency | Purpose |
|--------|-----------|--------|---------|---------|
| **Xavier BR-DWGD** | 0.1° (~10 km) | 1961-2024 | 6-12 months | Reference ✅ |
| **NASA POWER** | 0.5° × 0.625° (~55 km) | 1981-present | 5-7 days | Global reanalysis (validation) |
| **Open-Meteo Archive** | 0.1° (~10 km) | 1940-present | 5-7 days | High-res reanalysis (validation) |
| **Open-Meteo Forecast** | 0.1° (~10 km) | 7-day forecast | Real-time | Global forecast |
| **Met Norway** | ~1 km | 10-day forecast | Real-time | Regional (Europe) |
| **NWS USA** | Station/grid | 7-day forecast | Real-time | Regional (USA) |
| **EVAonline** | Multi-resolution | 1990-present | Real-time | Kalman fusion ⭐ |

### Key Technical Details

**Wind Speed Measurement Height** ⚠️ **Critical**:
- **NASA POWER**: Native 2m wind ✅ (no conversion)
- **Open-Meteo**: Native 10m wind -> **must convert to 2m** using FAO-56 Eq. 47
- **Impact**: Not converting causes ~15% ETo overestimation

**Data Aggregation**:
- Both APIs provide **daily data directly** (pre-aggregated)
- No hourly-to-daily conversion performed by EVAonline
- Solar radiation already in MJ/m²/day (not W/m²)

📖 **Technical specifications**: [docs/data_sources_specifications.md](docs/data_sources_specifications.md)  
📖 **Wind conversion methodology**: [docs/wind_height_conversion.md](docs/wind_height_conversion.md)  
📖 **API operational details**: [docs/api_operational_details.md](docs/api_operational_details.md)

---

## 🔬 Methodology

### FAO-56 Penman-Monteith

Standard equation for reference evapotranspiration:

$$
\\text{ETo} = \\frac{0.408 \\cdot \\Delta \\cdot (R_n - G) + \\gamma \\cdot \\frac{900}{T + 273} \\cdot u_2 \\cdot (e_s - e_a)}{\\Delta + \\gamma \\cdot (1 + 0.34 \\cdot u_2)}
$$

**Critical**: $u_2$ must be wind speed at **2m height**

### Kalman Fusion

EVAonline implements an **adaptive Kalman filter**:

1. **State estimation**: Combines NASA + Open-Meteo with adaptive weighting
2. **Process noise**: Seasonal (from Xavier monthly variability)
3. **Measurement noise**: R_NASA=0.3, R_OpenMeteo=0.4 (relative uncertainty)
4. **Bias correction**: Anchored to Xavier BR-DWGD climatology
5. **Output**: Fused ETo + uncertainty estimates

**Result**: 98% improvement in KGE, near-zero bias

📖 **Detailed methodology**: [docs/kalman_methodology.md](docs/kalman_methodology.md)

---

## 📈 Validation Options

### Option 1: Interactive Notebooks (⭐ RECOMMENDED)

**For learning and exploration:**

```bash
# Start with the single-city tutorial
jupyter notebook tutorial_full_pipeline.ipynb
```

**For complete validation study:**

```bash
# Run the comprehensive 17-city analysis
jupyter notebook complete_validation_analysis.ipynb
```

**What the notebooks provide:**
- `tutorial_full_pipeline.ipynb`:
  - Interactive step-by-step guide (single city: Piracicaba/SP)
  - Automatic elevation fetching from OpenTopoData API
  - Wind height conversion (10m → 2m) using FAO-56 Eq. 47
  - Region-specific validation limits (Xavier for Brazil, global elsewhere)
  - Kalman fusion demonstration with visualizations
  - Complete metrics calculation and interpretation

- `complete_validation_analysis.ipynb`:
  - Automated analysis for all 17 cities
  - Loads 4 ETo sources: NASA POWER, Open-Meteo API, Open-Meteo calc, EVAonline Fusion
  - Generates individual city reports (time series + 4 scatter plots each)
  - Summary statistics and comparative boxplots
  - KGE heatmap across cities and sources
  - Performance ranking tables
  - Complete CSV exports for further analysis

### Option 2: Python Scripts (Advanced)

**For batch processing or automation:**

```bash
# Script 1: Generate study area map
python scripts/1_generate_matopiba_map.py

# Script 2: Generate descriptive statistics
python scripts/2_generate_descriptive_stats.py

# Script 3: Consolidate raw datasets (NASA + OpenMeteo)
python scripts/3_concat_row_dataset_nasapower_openmeteo.py

# Script 4: Calculate ETo from raw data (NASA or OpenMeteo)
python scripts/4_calculate_eto_data_from_openmeteo_or_nasapower.py --source nasa
python scripts/4_calculate_eto_data_from_openmeteo_or_nasapower.py --source openmeteo

# Script 5: Single-source validation (no Kalman)
python scripts/5_validate_eto_calc.py

# Script 6: Full pipeline with Kalman fusion ⭐ RECOMMENDED
python scripts/6_validate_full_pipeline.py

# Script 7: Compare all 4 ETo sources (comprehensive analysis)
python scripts/7_compare_all_eto_sources.py
```

### Key Outputs

| Script | Output Directory | Key Files | Description |
|--------|-----------------|-----------|-------------|
| 1 | `data/1_figures/` | `study_area_map.png` | MATOPIBA region map with climate zones |
| 2 | `data/2_statistics_raw_dataset/` | `descriptive_stats_*.csv` | Descriptive statistics for all sources |
| 3 | `data/3_combined_datasets/` | `all_climate_data_1991_2020.csv` | Consolidated raw climate data (28 MB) |
| 4 | `data/4_eto_nasa_only/` | `ALL_CITIES_ETo_NASA_ONLY_1991_2020.csv` | NASA ETo calculated with FAO-56 |
| 4 | `data/4_eto_openmeteo_only/` | `ALL_CITIES_ETo_OPENMETEO_ONLY_1991_2020.csv` | OpenMeteo ETo calculated with FAO-56 |
| 5 | `data/5_validation_eto_evaonline/` | `summary_vs_*.csv` | Single-source validation results |
| 6 | `data/6_validation_full_pipeline/` | City-specific validation files | **EVAonline full Kalman fusion** ⭐ |
| 7 | `data/7_comparison_all_sources/` | `COMPARISON_ALL_SOURCES.csv`, `SUMMARY_BY_SOURCE.csv` | Comprehensive 4-source comparison |

---

## 🌍 Study Area

**17 Cities** in MATOPIBA region (Maranhão, Tocantins, Piauí, Bahia) + control site:

- Alvorada do Gurguéia, PI
- Araguaína, TO
- Balsas, MA
- Barreiras, BA
- Bom Jesus, PI
- Campos Lindos, TO
- Carolina, MA
- Corrente, PI
- Formosa do Rio Preto, BA
- Imperatriz, MA
- Luiz Eduardo Magalhães, BA
- Pedro Afonso, TO
- **Piracicaba, SP** *(control site)*
- Porto Nacional, TO
- São Desidério, BA
- Tasso Fragoso, MA
- Uruçuí, PI

**Period**: 1991-01-01 to 2020-12-31 (30 years)  
**Total observations**: 186,286 daily ETo values (17 cities × 10,958 days)

**City Metadata**: See `data/info_cities.csv` for coordinates and elevation

![Study Area Map](data/1_figures/study_area_map.png)

*Note: Map generated by `scripts/1_generate_matopiba_map.py`*

---

## 📓 Jupyter Notebooks

### Validation Notebooks (Root Directory)

| Notebook | Description | Use Case |
|----------|-------------|----------|
| **`tutorial_full_pipeline.ipynb`** | ⭐ **Start here** - Single city interactive tutorial | Learning EVAonline methodology step-by-step |
| **`complete_validation_analysis.ipynb`** | Complete 17-city validation study | Reproducing paper results, comprehensive analysis |

### API Demo Notebooks (notebooks/ Directory)

Additional tutorials demonstrating each climate API integration:

- `01_nasa_power_api_demo.ipynb` - NASA POWER API usage
- `02_openmeteo_archive_api_demo.ipynb` - Open-Meteo Archive (ERA5-Land reanalysis)
- `03_openmeteo_forecast_api_demo.ipynb` - Open-Meteo Forecast (7-day)
- `04_met_norway_api_demo.ipynb` - Met Norway API (Nordic region)
- `05_nws_forecast_api_demo.ipynb` - NWS Forecast API (USA)
- `06_nws_stations_api_demo.ipynb` - NWS Station data (USA)

**Key Features of Validation Notebooks:**
- ✅ Automatic region detection (Brazil vs global validation limits)
- ✅ Real elevation fetching from OpenTopoData API
- ✅ Correct wind height conversion (10m → 2m FAO-56 Eq. 47)
- ✅ Kalman fusion with uncertainty quantification
- ✅ Complete metrics (R², KGE, NSE, MAE, RMSE, PBIAS)
- ✅ High-quality publication-ready visualizations

---

## 📝 Citation

If you use this dataset, please cite:

```bibtex
@dataset{soares2025evaonline,
  author       = {Soares, Ângela Silviane Moura Cunha and
                  Maciel, Carlos Dias and
                  Marques, Patricia Angélica Alves},
  title        = {EVAonline Validation Dataset v1.0.0: Adaptive Kalman Fusion System for Reference Evapotranspiration in Brazil (1991-2020)},
  year         = {2025},
  publisher    = {Zenodo},
  version      = {1.0.0},
  doi          = {10.5281/zenodo.XXXXXXX},
  url          = {https://doi.org/10.5281/zenodo.XXXXXXX}
}
```

**Also cite the reference data:**

```bibtex
@article{Xavier2022BRDWGD,
  author = {Xavier, Alexandre C. and Scanlon, Bridget R. and King, Carey W. and Alves, Ana I.},
  title  = {New improved {B}razilian daily weather gridded data (1961--2020)},
  journal = {International Journal of Climatology},
  volume = {42},
  number = {16},
  pages  = {8390--8404},
  year   = {2022},
  doi    = {10.1002/joc.7731}
}
```

See [`CITATION.cff`](CITATION.cff) for machine-readable metadata.

---

## 📚 Documentation

### Core Documentation

- [**Data Sources Specifications**](docs/data_sources_specifications.md) - Technical details of NASA POWER, Open-Meteo, Xavier
- [**Wind Height Conversion**](docs/wind_height_conversion.md) - FAO-56 Equation 47 methodology (10m → 2m)
- [**Kalman Methodology**](docs/kalman_methodology.md) - Adaptive Kalman filter implementation
- [**Performance Analysis**](docs/performance_analysis.md) - Detailed results and spatial resolution impact
- [**API Operational Details**](docs/api_operational_details.md) - Rate limits, caching, gap filling strategies
- [**Validation Report**](docs/validation_eto_evaonline.md) - Complete validation study

### Additional Resources

- [Study Area Map Generation](docs/study_area_map_generation.md)
- [Quick Start Notebook](notebooks/quick_start_example.ipynb)
- [CITATION.cff](CITATION.cff) - Citation metadata

---

## 🔐 Data Integrity

All primary datasets are version-controlled with MD5 checksums available in Zenodo deposit.

Verify file integrity:
```powershell
# Check consolidated datasets
Get-ChildItem -Path "data\3_combined_datasets" | Select-Object Name, Length | Format-Table

# Verify CSV structure
Get-Content "data\3_combined_datasets\all_climate_data_1991_2020.csv" -TotalCount 5

# Check comparison results
Get-Content "data\7_comparison_all_sources\SUMMARY_BY_SOURCE.csv"
```

---

## 📜 License

- **Code**: AGPL-3.0 (see [LICENSE](LICENSE))

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

For major changes, open an issue first to discuss proposed changes.

---

## 📧 Contact

- **Repository**: https://github.com/silvianesoares/EVAONLINE
- **Issues**: https://github.com/silvianesoares/EVAONLINE/issues
- **Zenodo**: https://doi.org/10.5281/zenodo.XXXXXXX

---

## 🙏 Acknowledgments

**Data Providers**:
- NASA Langley Research Center POWER Project (https://power.larc.nasa.gov/)
- Open-Meteo / ECMWF ERA5-Land (https://open-meteo.com/)
- Met Norway Locationforecast API (https://api.met.no/)
- National Weather Service USA (https://www.weather.gov/)
- OpenTopoData Elevation API (https://www.opentopodata.org/)
- Xavier et al. / Brazilian Daily Weather Gridded Data (BR-DWGD)

**Funding**:
- [Add funding sources if applicable]

**References**:
- Allen, R.G., et al., 1998. FAO Irrigation and Drainage Paper 56
- Xavier, A.C., et al., 2022. International Journal of Climatology
- Kalman, R.E., 1960. Journal of Basic Engineering

---

**Last updated**: November 2025
