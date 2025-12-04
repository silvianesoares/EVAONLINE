# Documentation Index

This folder contains detailed technical documentation for the EVAonline validation dataset.

---

## Available Documents

### Core Technical Documentation

#### 1. [Data Sources Specifications](data_sources_specifications.md)
**What**: Detailed technical specifications for all climate data sources  
**Includes**:
- **Xavier BR-DWGD** (Brazilian reference dataset, 1991-2020 validation period)
- **NASA POWER** (MERRA-2 global reanalysis, 1990 to today-2d)
- **Open-Meteo Archive** (ERA5-Land high-resolution, 1990 to today-2d)
- **Open-Meteo Forecast** (7-day forecast, gap filling)
- Technical details: spatial resolution, temporal coverage, methodology
- API endpoints, variables, resolutions, coverage periods
- Quality control, validation steps, cross-validation results
- Data attribution and licenses

**Read this if**: You need to understand the data sources, their technical characteristics, or how to cite them.

---

#### 2. [Wind Height Conversion](wind_height_conversion.md)
**What**: FAO-56 Equation 47 methodology for converting 10m wind to 2m  
**Includes**:
- Problem statement (why conversion is needed)
- Mathematical formulation (logarithmic wind profile)
- Practical examples with code
- Impact on ETo calculation (~15% if not applied)
- Implementation in EVAonline
- Common mistakes to avoid

**Read this if**: You're implementing FAO-56 Penman-Monteith or wondering why wind speed measurement height matters.

---

#### 3. [Kalman Methodology](kalman_methodology.md)
**What**: Adaptive Kalman filter implementation details  
**Includes**:
- **6 climate data sources** (NASA POWER, Open-Meteo Archive/Forecast, Met.no, NWS Forecast/Stations)
- Why NASA POWER + Open-Meteo Archive for validation
- **Two operational modes**: Adaptive (with Xavier normals) vs Simple (without normals)
- Why Kalman fusion (vs simple averaging or ML)
- Mathematical formulation (scalar state-space model)
- Three-stage pipeline: Climate Fusion → ETo Calculation → ETo Refinement
- EVAonline configuration (Q adaptive, R 3-level anomaly detection)
- Bias correction strategy (monthly, Xavier climatology)
- Validation results and convergence analysis
- Sensitivity analysis and comparison with alternatives

**Read this if**: You want to understand how EVAonline fuses multiple data sources, the two operational modes, or implement similar methodology.

---

#### 4. [Performance Analysis](performance_analysis.md)
**What**: Detailed validation results and spatial resolution impact  
**Includes**:
- Aggregate statistics (17 cities, 30 years)
- Spatial resolution comparison (0.1° vs 0.5°)
- Why EVAonline outperforms single sources
- Metric interpretation (KGE, NSE, PBIAS)
- Regional adaptation and consistency
- Agricultural relevance

**Read this if**: You need detailed performance metrics, want to understand spatial resolution trade-offs, or are writing a paper.

---

#### 5. [API Operational Details](api_operational_details.md)
**What**: Practical guidelines for using NASA POWER and Open-Meteo APIs  
**Includes**:
- Temporal coverage and latency (NASA: 0 days, Open-Meteo Archive: 2 days)
- **Multi-API gap filling strategy** (handling Open-Meteo 2-day delay)
- Three operational scenarios: Real-time Dashboard, Historical Analysis, Forecast
- Rate limits and caching best practices
- Error handling and fallback strategies
- API request examples with code
- Performance considerations

**Read this if**: You're building an application that uses these APIs or need to understand operational constraints and latency.

---

#### 6. [EVAonline Architecture](evaonline_architecture.md)
**What**: System architecture and design patterns
**Includes**:
- **Clean Hexagonal DDD Architecture** (Clean + Hexagonal + Domain-Driven Design)
- Architectural principles (Dependency Rule, Ports & Adapters, SOLID)
- Layer structure: Presentation → Application → Domain → Infrastructure
- Entities, Value Objects, Repositories, Services pattern
- Data flow: Request → Response with timing diagrams
- Three operating modes: Dashboard Current, Forecast, Historical Email
- Performance metrics (2.0-3.5s cache miss, <100ms cache hit)
- Technology stack and design decisions

**Read this if**: You want to understand the system design, architectural patterns, or implement similar architecture.

---

#### 7. [Elevation Integration](elevation_integration.md)
**What**: OpenTopoData integration for elevation correction (documento em português)
**Includes**:
- Why elevation matters (affects pressure, gamma, solar radiation)
- Impact on ETo calculation (+13.3% at 1172m vs sea level)
- Data sources comparison (SRTM 30m, ASTER 30m, Open-Meteo)
- Priority strategy (user input → OpenTopo → Open-Meteo → default)
- FAO-56 correction factors (pressure, psychrometric constant, radiation)
- Practical examples with code
- Implementation in EVAonline services

**Read this if**: You're implementing FAO-56 with elevation correction or need precise altitude data.

---

#### 8. [Regional Validation System](regional_validation_system.md)
**What**: Region-specific validation limits for climate data
**Includes**:
- **Brazil limits** (Xavier et al. 2016, 2022): -30 to 50°C, 0-450mm precipitation
- **Global limits** (world records): -90 to 60°C, 0-2000mm precipitation
- Impact comparison (Brazil 3× more restrictive on temperature)
- Wind speed limits (0-100 m/s)
- Relative humidity limits (0-100%)
- Technical implementation in `weather_utils.py` and `data_preprocessing.py`
- Usage examples for different regions
- How to add new regions (e.g., Australia)

**Read this if**: You're processing regional climate data, need scientific validation limits, or implementing quality control.

---

#### 9. [Validation Report](validation_eto_evaonline.md)
**What**: Complete validation study results  
**Includes**:
- City-by-city validation metrics
- Time series plots and scatter plots
- Statistical summaries
- Data quality assessment

**Read this if**: You need complete validation results or city-specific performance data.

---

#### 10. [Study Area Map Generation](study_area_map_generation.md)
**What**: How the study area map was created  
**Includes**:
- Geographic data sources (IBGE, MATOPIBA definition)
- Python/Cartopy implementation
- Customization options

**Read this if**: You need to recreate or modify the study area map.

---

## Documentation Roadmap

```
Start Here
    │
    ├─→ Quick Start? 
    │       └─→ ../README.md (main README)
    │
    ├─→ Understanding Data Sources?
    │       └─→ data_sources_specifications.md
    │
    ├─→ Implementing FAO-56?
    │       ├─→ wind_height_conversion.md
    │       └─→ elevation_integration.md
    │
    ├─→ Understanding Kalman Fusion?
    │       └─→ kalman_methodology.md (includes 6 data sources)
    │
    ├─→ Analyzing Performance?
    │       └─→ performance_analysis.md
    │
    ├─→ Building Applications?
    │       └─→ api_operational_details.md
    │
    └─→ Complete Validation Results?
            └─→ validation_eto_evaonline.md
```

---

## Quick Reference

### For Researchers

**Priority reading**:
1. [Performance Analysis](performance_analysis.md) - Validation results
2. [Kalman Methodology](kalman_methodology.md) - Technical approach (Adaptive vs Simple modes)
3. [Data Sources Specifications](data_sources_specifications.md) - Data provenance
4. [Regional Validation System](regional_validation_system.md) - Xavier et al. limits
5. [Validation Report](validation_eto_evaonline.md) - Complete results

### For Developers

**Priority reading**:
1. [EVAonline Architecture](evaonline_architecture.md) - System design
2. [Kalman Methodology](kalman_methodology.md) - **6 data sources** + Algorithm implementation
3. [API Operational Details](api_operational_details.md) - Practical guidelines
4. [Data Sources Specifications](data_sources_specifications.md) - API endpoints & technical specs
5. [Wind Height Conversion](wind_height_conversion.md) - Critical implementation detail
6. [Elevation Integration](elevation_integration.md) - Altitude correction
7. [Regional Validation System](regional_validation_system.md) - Validation by region

### For Practitioners

**Priority reading**:
1. [Performance Analysis](performance_analysis.md) - Which method to use?
2. [API Operational Details](api_operational_details.md) - How to get data?
3. [Elevation Integration](elevation_integration.md) - Impact of altitude on ETo
4. [Validation Report](validation_eto_evaonline.md) - City-specific results

---

## External Resources

### FAO-56 Penman-Monteith
- [FAO-56 Full Text](http://www.fao.org/3/x0490e/x0490e00.htm)
- [FAO-56 Chapter 4 (Wind)](http://www.fao.org/3/x0490e/x0490e06.htm)

### Data Source Documentation
- [NASA POWER API Docs](https://power.larc.nasa.gov/docs/services/api/)
- [Open-Meteo API Docs](https://open-meteo.com/en/docs)
- [Xavier BR-DWGD Website](https://sites.google.com/site/alexandrecandidoxavierufes/brazilian-daily-weather-gridded-data)

### Kalman Filter Theory
- Kalman, R. E. (1960). A new approach to linear filtering and prediction problems. *Journal of Basic Engineering*, 82(1), 35-45.
- Welch, G., & Bishop, G. (2006). An introduction to the Kalman filter. [Technical Report](https://www.cs.unc.edu/~welch/media/pdf/kalman_intro.pdf)

### Validation Metrics
- Gupta et al. (2009). Decomposition of the mean squared error and NSE. *Journal of Hydrology*, 377(1-2), 80-91. [DOI](https://doi.org/10.1016/j.jhydrol.2009.08.003)

---

## Questions?

- **GitHub Issues**: https://github.com/angelasilviane/EVAONLINE/issues
- **Email**: [Add contact email]

---

## Contributing to Documentation

Found an error or want to improve documentation?

1. Fork the repository
2. Edit the relevant Markdown file
3. Submit a pull request

**Documentation guidelines**:
- Use clear headings and subheadings
- Include practical examples and code snippets
- Add visual aids (equations, diagrams, tables)
- Provide external references
- Keep language accessible (explain jargon)

---

**Last updated**: November 2025
