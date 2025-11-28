# EVAOnline Validation Dataset v1.0.0

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Data](https://img.shields.io/badge/Data-Open%20Access-brightgreen.svg)](https://zenodo.org/)

**Complete validation dataset for EVAOnline: An open-source adaptive Kalman fusion system for reference evapotranspiration estimation in Brazil**

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

### Load Data

```python
import pandas as pd

# Recommended: Use consolidated file
df = pd.read_csv("all_cities_daily_eto_1994_2024.csv", parse_dates=["date"])

# Filter by city
piracicaba = df[df["city"] == "Piracicaba_SP"]

# Compare methods
print(piracicaba[["date", "eto_xavier", "eto_nasa", "eto_openmeteo", "eto_evaonline"]].head())
```

📓 **Interactive tutorial**: See `notebooks/quick_start_example.ipynb`

---

## 📂 Repository Structure

```
EVAonline_validation_v1.0.0/
├── data/                          # Validation datasets
│   ├── original_data/            # Raw sources (Xavier, NASA, OpenMeteo)
│   ├── 4_eto_nasa_only/          # NASA ETo (Script 4)
│   ├── 4_eto_openmeteo_only/     # OpenMeteo ETo (Script 4)
│   ├── 6_validation_full_pipeline/ # EVAonline Kalman fusion (Script 6)
│   └── 7_comparison_all_sources/  # 4-source comparison (Script 7)
│
├── scripts/                       # Validation scripts
│   ├── 4_calculate_eto_data_from_openmeteo_or_nasapower.py
│   ├── 5_validate_eto_calc.py    # Single-source validation
│   ├── 6_validate_full_pipeline.py # Full Kalman fusion ⭐
│   └── 7_compare_all_eto_sources.py # Comprehensive comparison
│
├── docs/                          # Detailed documentation
│   ├── data_sources_specifications.md   # API technical specs
│   ├── wind_height_conversion.md        # FAO-56 Eq. 47 methodology
│   ├── kalman_methodology.md            # Kalman filter details
│   ├── performance_analysis.md          # Detailed results
│   ├── api_operational_details.md       # Operational guidelines
│   └── validation_eto_evaonline.md      # Full validation report
│
└── notebooks/                     # Jupyter tutorials
    └── quick_start_example.ipynb
```

---

## 📊 Data Sources

### Overview

| Source | Resolution | Period | Latency | Purpose |
|--------|-----------|--------|---------|---------||
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
- **Open-Meteo**: Native 10m wind → **must convert to 2m** using FAO-56 Eq. 47
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

## 📈 Validation Scripts

### Run Validations

```bash
# Script 4: Calculate ETo from raw data (NASA or OpenMeteo)
python scripts/4_calculate_eto_data_from_openmeteo_or_nasapower.py --source nasa
python scripts/4_calculate_eto_data_from_openmeteo_or_nasapower.py --source openmeteo

# Script 5: Single-source validation (no Kalman)
python scripts/5_validate_eto_calc.py

# Script 6: Full pipeline with Kalman fusion ⭐ RECOMMENDED
python scripts/6_validate_full_pipeline.py

# Script 7: Compare all 4 ETo sources
python scripts/7_compare_all_eto_sources.py
```

### Key Outputs

| Script | Output Directory | Description |
|--------|-----------------|-------------|
| 4 | `data/4_eto_nasa_only/` | NASA ETo calculated with FAO-56 |
| 4 | `data/4_eto_openmeteo_only/` | OpenMeteo ETo calculated with FAO-56 |
| 6 | `data/6_validation_full_pipeline/` | **EVAonline full Kalman fusion** ⭐ |
| 7 | `data/7_comparison_all_sources/` | Comprehensive 4-source comparison |

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

![Study Area Map](data/1_figures/study_area_map.png)

---

## 📝 Citation

If you use this dataset, please cite:

```bibtex
@dataset{soares2025evaonline,
  author       = {Soares, Ângela Silviane Moura Cunha and
                  Maciel, Carlos Dias and
                  Marques, Patricia Angélica Alves},
  title        = {EVAonline Validation Dataset v1.0.0: Kalman Fusion System for Reference Evapotranspiration in Brazil (1991-2020)},
  year         = {2025},
  publisher    = {Zenodo},
  version      = {1.0.0},
  doi          = {10.5281/zenodo.XXXXXXX},
  url          = {https://doi.org/10.5281/zenodo.XXXXXXX}
}
```

**Also cite the reference data:**

```bibtex
@misc{xavier2024brdwgd,
  author       = {Xavier, Alexandre Candido},
  title        = {Brazilian Daily Weather Gridded Data (BR-DWGD)},
  year         = {2024},
  howpublished = {\url{https://sites.google.com/site/alexandrecandidoxavierufes/brazilian-daily-weather-gridded-data}},
  note         = {Daily gridded meteorological data (1961/01/01-2024/03/20), 0.1° resolution, 3,625+ stations}
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

All data files listed in [`data_manifest.csv`](data_manifest.csv) with MD5 checksums.

Verify integrity:
```bash
python scripts/generate_data_manifest.py
md5sum data/xavier/Piracicaba_SP.csv  # Compare with manifest
```

---

## 📜 License

- **Code**: AGPL-3.0 (see [LICENSE](LICENSE))
- **Data**: 
  - Xavier BR-DWGD: [See publication terms](https://doi.org/10.1002/joc.7731)
  - NASA POWER: Public Domain
  - Open-Meteo: CC BY 4.0

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
