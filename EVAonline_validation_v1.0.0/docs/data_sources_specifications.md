# Data Sources Technical Specifications

## Overview

This document provides detailed technical specifications for all climate data sources used in the EVAonline validation study.

---

## 1. Xavier BR-DWGD (Reference Dataset)

- **Full Name**: New improved Brazilian daily weather gridded data (1961–2020)
- **Source**: Xavier et al. 2016, 2022 - Brazilian Daily  Weather  Gridded  Data (BR-DWGD)
- **Website**: https://sites.google.com/site/alexandrecandidoxavierufes/brazilian-daily-weather-gridded-data
- **Papers**:
  - [Xavier et al. 2022 (IJC)](https://doi.org/10.1002/joc.7731) - Updated dataset (1961-2024)

### Technical Details

- **Variables**: Precipitation (pr, mm) and evapotranspiration (ETo, mm).
- **Spatial Resolution**: 0.1° x 0.1° (~11 km) just Brazil territory
- **Temporal Coverage**: 1961-2024 (varies by city)
- **Methodology**:
  - Interpolated from 3,625+ weather stations (INMET network)
  - Thin-plate spline interpolation with elevation covariate
  - Cross-validation: R² > 0.90 for most variables
- **Quality Control**: Multiple validation steps, bias correction, homogeneity tests
- **Update 2022**: Extended temporal range, improved precipitation estimates
- **Purpose**: Gold standard reference for Brazil agricultural/hydrological studies

---

## 2. NASA POWER

- **Full Name**: Prediction Of Worldwide Energy Resources
- **Version**: Daily 2.x.x (Community: AG - Agronomy)
- **Website**: https://power.larc.nasa.gov/
- **Documentation**: https://power.larc.nasa.gov/docs/services/api/
- **Citation**: https://power.larc.nasa.gov/docs/referencing/
- **License**: Public Domain (NASA Earth Science Directorate)

### Technical Details

- **Data Source**: MERRA-2 (Modern-Era Retrospective analysis for Research and Applications, Version 2)
- **Coverage**: Global
- **Spatial Resolution**: **0.5° × 0.625° (MERRA-2 native grid)** (~55 km × 70 km at equator)
- **Temporal Resolution**: **Daily** (aggregated internally from MERRA-2 hourly data)
- **Temporal Coverage**: **1990-01-01 to (today - 2 days)** - 2-day delay

### Variables Retrieved

| Variable | Description | Unit | Spatial Resolution | Source |
|----------|-------------|------|-------------------|--------|
| `T2M` | Temperature at 2m | °C | 0.5° × 0.625° | MERRA-2 |
| `T2M_MAX` | Temperature at 2m Maximum | °C | 0.5° × 0.625° | MERRA-2 |
| `T2M_MIN` | Temperature at 2m Minimum | °C | 0.5° × 0.625° | MERRA-2 |
| `RH2M` | Relative Humidity at 2m | % | 0.5° × 0.625° | MERRA-2 |
| `WS2M` | Wind Speed at 2m | m/s | 0.5° × 0.625° | MERRA-2 |
| `ALLSKY_SFC_SW_DWN` | Solar Radiation | MJ/m²/day | 1° × 1° | CERES SYN1deg |
| `PRECTOTCORR` | Precipitation Corrected | mm/day | 0.5° × 0.625° | MERRA-2 |

### Key Features

- **Native 2m wind**: No height conversion needed for FAO-56
- **Zero latency**: Updates daily with no delay
- **Global coverage**: Suitable for any location worldwide
- **Validated**: Cross-validated against ground stations globally

### Methodology

- Global atmospheric reanalysis assimilating satellite and ground observations
- ETo calculated using FAO-56 Penman-Monteith with POWER meteorological inputs
- Grid-cell values represent area average (not point measurements)

### Attribution

> "Data obtained from NASA Langley Research Center POWER Project funded through the NASA Earth Science Directorate Applied Science Program."

---

## 3. Open-Meteo Archive API

- **Full Name**: Open-Meteo Historical Weather API
- **Endpoint**: https://archive-api.open-meteo.com/v1/archive
- **Documentation**: https://open-meteo.com/en/docs
- **Source Code**: https://github.com/open-meteo/open-meteo (AGPLv3)
- **License**: CC BY 4.0 (data) + AGPLv3 (source code)

### Technical Details

- **Data Source**: ERA5-Land reanalysis (ECMWF - European Centre for Medium-Range Weather Forecasts)
- **Coverage**: Global
- **Spatial Resolution**: **~9 km (0.1° × 0.1°, ERA5-Land native grid)**
- **Temporal Resolution**: **Daily** (aggregated internally from ERA5-Land hourly data)
- **Temporal Coverage**: **1990-01-01 to (today - 2 days)** - 2-day delay for quality control

### Variables Retrieved

| Variable | Description | Unit | Notes |
|----------|-------------|------|-------|
| `temperature_2m_max` | Daily maximum temperature | °C | Pre-aggregated by API |
| `temperature_2m_min` | Daily minimum temperature | °C | Pre-aggregated by API |
| `temperature_2m_mean` | Daily mean temperature | °C | Pre-aggregated by API |
| `relative_humidity_2m_max` | Daily maximum humidity | % | Pre-aggregated by API |
| `relative_humidity_2m_min` | Daily minimum humidity | % | Pre-aggregated by API |
| `relative_humidity_2m_mean` | Daily mean humidity | % | Pre-aggregated by API |
| `wind_speed_10m_mean` | Daily mean wind at 10m | m/s | **Requires 10m→2m conversion** ⚠️ |
| `shortwave_radiation_sum` | Daily solar radiation | MJ/m²/day | Pre-aggregated by API |
| `precipitation_sum` | Daily precipitation | mm | Pre-aggregated by API |
| `et0_fao_evapotranspiration` | Daily reference ETo | mm/day | API's own FAO-56 calculation |

### Key Features

- **High spatial resolution**: 0.1° matches Xavier reference exactly
- **2-day latency**: Allows for quality control
- **ERA5-Land based**: Enhanced resolution version of ERA5 reanalysis
- **Native 10m wind**: ⚠️ Requires conversion to 2m for FAO-56 compliance

### Methodology

- ERA5-Land: Enhanced resolution version of ERA5 reanalysis
- Combines model forecasts with observations using data assimilation
- `et0_fao_evapotranspiration`: Calculated using FAO-56 Penman-Monteith based on hourly ERA5-Land variables
- Elevation adjustment: Uses 90m DEM for statistical downscaling

### Attribution

> Citation: Zippenfenig, P. (2023). Open-Meteo.com Weather API [Computer software]. Zenodo. https://doi.org/10.5281/ZENODO.7970649

---

## 4. Open-Meteo Forecast API

- **Endpoint**: https://api.open-meteo.com/v1/forecast
- **Purpose**: Gap filling for recent data (last 2 days) and short-term forecast
- **Coverage**: (today - 29 days) to (today + 5 days) = 35 days total

### Technical Details

- Same variables as Open-Meteo Archive
- Used **only for gap filling** in dashboard 30-day view
- Not used in validation study (1991-2020 uses Archive exclusively)

---

## EVAonline Operation Modes

EVAonline operates in **3 distinct modes**, each with specific temporal coverage rules and API combinations:

### Mode 1: HISTORICAL_EMAIL (Historical Analysis)

**Purpose**: Historical data analysis with flexible date selection  
**Delivery**: Email export  
**Period**: min = 1 day, max = 90 days (user free choice)  
**Restriction**: `end_date <= today - 29 days` (avoids overlap with dashboard)

**Data Sources**:
- **NASA POWER**: 1990-01-01 → (today - 2 days) (2-day delay)
- **Open-Meteo Archive**: 1990-01-01 → (today - 2 days) (2-day latency)

**Use Cases**:
- Long-term climatological studies
- Seasonal analysis (any year since 1990)
- Validation against ground stations
- Historical ETo calculation for any period

**Examples** (reference: Dec 1, 2025):
- `2013-05-01 to 2013-07-29` ✅ (90 days, year 2013)
- `2025-07-18 to 2025-10-15` ✅ (89 days, year 2025, ends before Nov 2)
- `1990-01-01 to 1990-01-31` ✅ (31 days, earliest available)

---

### Mode 2: DASHBOARD_CURRENT (Recent Monitoring)

**Purpose**: Recent data monitoring with predefined periods  
**Interface**: Web dashboard with dropdown selection  
**Periods**: 7, 14, 21, or 30 days  
**Fixed End**: Always `today` (auto-updating)

**Data Sources**:
- **NASA POWER**: (today - 29 days) → (today - 2 days) (28 days, 2-day delay)
- **Open-Meteo Archive**: (today - 29 days) → (today - 2 days) (28 days, 2-day latency)
- **Open-Meteo Forecast**: (today - 29 days) → today (fills 2-day gap for NASA + Archive)

**Use Cases**:
- Real-time crop monitoring
- Recent weather pattern analysis
- Short-term irrigation planning
- Current season tracking

**Examples** (reference: Dec 1, 2025):
- **30 days**: `Nov 2, 2025 to Dec 1, 2025` (today - 29d to today)
- **7 days**: `Nov 25, 2025 to Dec 1, 2025` (today - 6d to today)
- **14 days**: `Nov 18, 2025 to Dec 1, 2025` (today - 13d to today)

---

### Mode 3: DASHBOARD_FORECAST (Future Projection)

**Purpose**: Short-term ETo forecasting  
**Interface**: Web dashboard (fixed 6 days period)  
**Period**: 6 days fixed → `today to today + 5 days` (inclusive)

#### Standard Mode (Global Coverage)

**Data Sources**:
- **Open-Meteo Forecast**: today -> today + 5 days (all variables)
- **Met Norway**: today -> today + 5 days (temperature + humidity globally; full variables in Nordic region)
- **NWS Forecast**: today -> today + 5 days (USA only; temperature, humidity, precipitation)

#### USA Enhanced Mode

**For locations in USA**, user can choose via radio button:

**Option A: "Data Fusion" (default)**
- **Open-Meteo Forecast**: today → today + 5 days
- **Met Norway**: today → today + 5 days (temperature + humidity)
- **NWS Forecast**: today → today + 5 days (if request time < 20h UTC)

**Option B: "Real Station Data"**
- **NWS Stations**: today only (real-time observations)
- Shows number of nearby stations found
- All variables available from ground measurements
- Download button for station data

**Use Cases**:
- Short-term irrigation scheduling
- Weather-responsive farm management
- Near-future water requirement planning
- Forecast-based decision support

**Example** (reference: Dec 1, 2025):
- **Fixed period**: `Dec 1, 2025 to Dec 6, 2025` (6 days: 1, 2, 3, 4, 5, 6)

---

## Temporal Coverage Summary

| Data Source | Start Date | End Date | Update Frequency | Latency | Mode |
|-------------|-----------|----------|-----------------|---------|----------|
| **Xavier BR-DWGD** | 1991-01-01 | 2020-12-31 | Annual updates | - | Reference/validation only |
| **NASA POWER** | 1990-01-01 | Today - 2 days | Daily | **2 days** | HISTORICAL_EMAIL + DASHBOARD_CURRENT |
| **Open-Meteo Archive** | 1990-01-01 | Today - 2 days | Daily | **2 days** | HISTORICAL_EMAIL + DASHBOARD_CURRENT |
| **Open-Meteo Forecast** | Today - 29 days | Today + 5 days | Daily | **0 days** (real-time) | DASHBOARD_CURRENT + DASHBOARD_FORECAST |
| **Met Norway** | Today | Today + 5 days | Hourly | **0 days** | DASHBOARD_FORECAST |
| **NWS Forecast** | Today | Today + 5 days | Hourly | **0 days** | DASHBOARD_FORECAST (USA) |
| **NWS Stations** | Today - 2 days | Today | Hourly, Real-time | **0 days** | DASHBOARD_FORECAST (USA stations) |

**\*** Xavier dataset extended to 2024 but official publication covers 1961-2020

---

## API Rate Limits & Best Practices

### NASA POWER

- **Rate Limit**: <1 req/s (recommended fair use)
- **Max Parameters**: 20 parameters per request (single point)
- **No Authentication**: Free API, no key required
- **Cache Strategy**: 24h TTL for historical data

### Open-Meteo Archive/Forecast

- **Rate Limit**: <10 req/s (recommended)
- **Daily Limit**: ~10,000 req/day (free plan)
- **No Authentication**: Free for non-commercial use
- **Cache Strategy**: 24h TTL for Archive, 1h for Forecast

---

## Data Aggregation

**Important**: Both NASA POWER and Open-Meteo provide **daily data directly**. The aggregation from hourly observations to daily values is performed internally by each API provider:

- **NASA POWER**: Uses MERRA-2 reanalysis hourly data, aggregates to daily internally
- **Open-Meteo**: Uses ERA5-Land reanalysis hourly data, aggregates to daily internally

**EVAonline does NOT perform temporal aggregation** - it receives daily data ready to use.

---

## References

**Xavier BR-DWGD**:
- Xavier, A. C., Scanlon, B. R., King, C. W., & Alves, A. I. (2022). New improved Brazilian daily weather gridded data (1961–2020). *International Journal of Climatology*, 42(16), 8390-8404. https://doi.org/10.1002/joc.7731

**FAO-56 Penman-Monteith**:
- Allen, R.G., Pereira, L.S., Raes, D., Smith, M., 1998. Crop evapotranspiration - Guidelines for computing crop water requirements. FAO Irrigation and Drainage Paper 56. Food and Agriculture Organization, Rome. http://www.fao.org/3/x0490e/x0490e00.htm
