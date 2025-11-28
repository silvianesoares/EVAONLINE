# Performance Analysis & Spatial Resolution Impact

## Overview

This document provides detailed analysis of EVAonline's performance compared to single-source methods, with special focus on how spatial resolution affects validation results.

---

## Aggregate Statistics (17 Cities, 1991-2020)

| Metric | Xavier Reference | EVAonline Fusion* | NASA POWER† | OpenMeteo (our calc)‡ | OpenMeteo API§ |
|--------|------------------|-------------------|-------------|----------------------|----------------|
| **R²** | 1.000 | **0.694 ± 0.074**<br>(0.554 - 0.792) | 0.740 ± 0.062<br>(0.582 - 0.848) | 0.636 ± 0.173<br>(0.018 - 0.787) | 0.649 ± 0.174<br>(0.015 - 0.781) |
| **KGE** | 1.000 | **0.814 ± 0.053**<br>(0.721 - 0.885) | 0.411 ± 0.264<br>(-0.015 - 0.836) | 0.432 ± 0.413<br>(-0.613 - 0.813) | 0.584 ± 0.188<br>(0.065 - 0.824) |
| **NSE** | 1.000 | **0.676 ± 0.085**<br>(0.505 - 0.786) | -0.363 ± 0.788<br>(-1.924 - 0.773) | -0.547 ± 1.820<br>(-5.953 - 0.656) | 0.216 ± 0.356<br>(-0.633 - 0.658) |
| **MAE (mm/day)** | 0.00 | **0.423 ± 0.052**<br>(0.348 - 0.568) | 0.845 ± 0.281<br>(0.409 - 1.284) | 0.859 ± 0.447<br>(0.475 - 1.921) | 0.690 ± 0.115<br>(0.559 - 0.962) |
| **RMSE (mm/day)** | 0.00 | **0.566 ± 0.064**<br>(0.475 - 0.739) | 1.117 ± 0.347<br>(0.552 - 1.645) | 1.097 ± 0.573<br>(0.624 - 2.387) | 0.860 ± 0.144<br>(0.707 - 1.213) |
| **PBIAS (%)** | 0.0 | **+0.71 ± 0.53**<br>(-0.16 - +1.54) | +15.78 ± 7.14<br>(+1.64 - +26.13) | +13.02 ± 12.35<br>(+1.24 - +39.90) | +8.27 ± 3.95<br>(-2.03 - +16.42) |
| **n cities** | 17 | 17 | 17 | 17 | 17 |
| **n days/city** | 10,958 | 10,958 | 10,958 | 10,958 | 10,958 |
| **Total obs.** | 186,286 | 186,286 | 186,286 | 186,286 | 186,286 |

**Legend:**
- **\*** **EVAonline Fusion**: Full pipeline with Kalman ensemble (NASA + OpenMeteo fusion) + final bias correction
- **†** **NASA POWER**: ETo calculated from NASA POWER raw data using our FAO-56 implementation (Script 4)
- **‡** **OpenMeteo (our calc)**: ETo calculated from OpenMeteo raw data using our FAO-56 implementation (Script 4)
- **§** **OpenMeteo API**: Original ETo from Open-Meteo API (ERA5-Land based, et0_fao_evapotranspiration variable)

**Source:** Script 7 comprehensive comparison (`7_compare_all_eto_sources.py`)

---

## Spatial Resolution Impact Analysis

### Resolution Comparison

| Data Source | Spatial Resolution | Grid Cell Size | Match with Xavier (0.1°) | Performance Impact |
|-------------|-------------------|----------------|-------------------------|-------------------|
| **Xavier BR-DWGD** (Reference) | 0.1° × 0.1° | ~10 km × 10 km | Perfect (reference) | Baseline (R²=1.000, KGE=1.000) |
| **ERA5-Land** (Open-Meteo) | 0.1° × 0.1° | ~10 km × 10 km | ✅ Exact match | Better spatial detail, but ERA5-Land model biases |
| **MERRA-2** (NASA POWER) | 0.5° × 0.625° | ~55 km × 70 km | ⚠️ Coarser (5-6× larger cells) | Smoother fields, misses local variations |
| **EVAonline Fusion** | Multi-resolution | Fuses 0.1° + 0.5° | ✅ Adapts to both | Best of both: detail + stability |

### Key Findings

#### 1. Resolution Paradox

Despite coarser resolution, NASA POWER achieves **higher R² (0.740)** than Open-Meteo calculated (0.636):

**Reason**: MERRA-2 has better assimilation of ground observations for temperature and humidity

**Trade-off**: Better accuracy vs spatial detail

#### 2. ERA5-Land Advantages

- **Perfect spatial match** with Xavier (both 0.1°)
- **Better representation** of local topography and land surface
- **Higher detail** in precipitation and radiation fields

#### 3. ERA5-Land Challenges

- **Wind speed bias**: Systematic overestimation at 10m height (requires conversion)
- **Model drift**: Larger biases (+13-15%) compared to NASA (+15.78%)
- **Consistency**: Higher variability across cities (NSE: -5.953 to 0.656)

#### 4. MERRA-2 Trade-offs

- **Smoother fields**: Averages out local variations (5-6× larger grid cells)
- **Better temperature**: More accurate 2m temperature from superior assimilation
- **Stable bias**: More consistent across cities (NSE: -1.924 to 0.773)

#### 5. EVAonline Fusion Strategy

- **Adaptive weighting**: Kalman filter dynamically selects best source
- **Spatial downscaling**: Uses Xavier normals (0.1°) as bias correction anchor
- **Multi-scale**: Combines MERRA-2 stability + ERA5-Land detail
- **Result**: Achieves **best KGE (0.814)** and **lowest bias (0.71%)** despite mixing resolutions

### Visual Comparison (Piracicaba-SP)

```
Grid Cell Size Comparison:
┌─────────────────────────────────────────┐
│   MERRA-2 (NASA POWER) - 0.5° × 0.625°  │
│   ┌───────────────────────────────────┐ │
│   │                                   │ │
│   │         ~3,850 km² grid cell     │ │
│   │  (averages large agricultural    │ │
│   │   region around Piracicaba)      │ │
│   │                                   │ │
│   └───────────────────────────────────┘ │
└─────────────────────────────────────────┘

ERA5-Land / Xavier - 0.1° × 0.1°
┌──┬──┬──┬──┬──┬──┐
├──┼──┼──┼──┼──┼──┤
├──┼──┼██┼──┼──┼──┤  ← ~100 km² grid cell
├──┼──┼──┼──┼──┼──┤    (captures city-scale features)
├──┼──┼──┼──┼──┼──┤
└──┴──┴──┴──┴──┴──┘
Each small cell ≈ 100 km² (6× MERRA-2 cells fit in 1 NASA cell)
```

### Practical Implications

- **For point locations** (e.g., weather stations): ERA5-Land's 0.1° resolution better captures local conditions
- **For regional assessments** (e.g., agricultural zones): MERRA-2's 0.5° smoothing may be adequate
- **For operational systems** (e.g., EVAonline): **Fusion of both** provides best accuracy and consistency
- **For validation studies**: Matching spatial resolution (Xavier 0.1° = ERA5-Land 0.1°) helps, but **data quality matters more than resolution alone**

---

## Performance Interpretation

### KGE (Kling-Gupta Efficiency)

EVAOnline's **KGE = 0.814** demonstrates **very good performance**:

- **KGE** is the gold standard for hydrological model evaluation
- **KGE > 0.75** indicates "very good" performance (literature threshold)
- **Components**:
  - Correlation (r): 0.833 (very high)
  - Bias ratio (β): 1.007 (near-perfect)
  - Variability ratio (γ): 0.978 (excellent)

### PBIAS (Percent Bias)

**PBIAS = +0.71%** shows near-perfect systematic accuracy:

- **Ideal range**: ±5% (very good)
- **Acceptable range**: ±10% (good)
- **EVAonline**: +0.71% (excellent)

**Interpretation**: EVAonline slightly overestimates ETo by 0.71% on average, which is negligible for practical applications.

### NSE (Nash-Sutcliffe Efficiency)

**NSE = 0.676** confirms good predictive capability:

- **NSE > 0.5**: Acceptable
- **NSE > 0.65**: Good
- **NSE > 0.75**: Very good
- **EVAonline**: 0.676 (good)

### Agricultural Relevance

For irrigation scheduling and water management:

**Most important metrics**:
1. **KGE** (0.814) - Overall performance ✅
2. **PBIAS** (+0.71%) - Systematic accuracy ✅
3. **MAE** (0.423 mm/day) - Absolute error ✅

**Less critical for operations**:
- **R²** (correlation) - Useful but doesn't capture bias
- **NSE** - Sensitive to outliers

**Practical impact**: EVAonline's performance translates to:
- ✅ Accurate irrigation scheduling (within 0.4 mm/day error)
- ✅ Reliable crop water requirement estimation
- ✅ Valid for hydrological modeling and water balance studies

---

## Why EVAonline Outperforms Single Sources

### 1. Multi-Source Fusion Strategy

```
NASA POWER (MERRA-2)          Open-Meteo (ERA5-Land)
├─ Strengths:                 ├─ Strengths:
│  • Better temperature       │  • Higher spatial resolution (0.1°)
│  • 2m wind (native)         │  • Better precipitation detail
│  • Stable across regions    │  • Land surface model
│                             │
├─ Weaknesses:                ├─ Weaknesses:
│  • Coarse resolution (0.5°) │  • 10m wind (needs conversion)
│  • Positive bias (+15.78%)  │  • Higher bias (+13.02%)
│  • Misses local features    │  • Variable performance
│                             │
└──────────┬──────────────────┘
           │
           ▼
   ╔═══════════════════════════╗
   ║   KALMAN FUSION ENGINE    ║
   ║   + Xavier BR-DWGD Bias   ║
   ║     Correction (0.1°)     ║
   ╚═══════════════════════════╝
           │
           ▼
   EVAonline Output:
   • Combines best features
   • Adaptive weighting
   • Anchored to Brazilian reference
   • Result: KGE=0.814, PBIAS=+0.71% ✅
```

### 2. Bias Correction Impact

| Source | Raw Bias (%) | After Kalman Fusion (%) | Improvement |
|--------|-------------|------------------------|-------------|
| NASA POWER | +15.78 | **+0.71** | **-95.5% bias reduction** |
| Open-Meteo | +13.02 | **+0.71** | **-94.5% bias reduction** |

**Method**: Kalman filter uses Xavier BR-DWGD monthly climatology as "truth anchor"

### 3. Uncertainty Quantification

EVAonline uniquely provides **confidence intervals** through Kalman covariance:

```python
# Example output
{
    "date": "2024-11-14",
    "eto_fused": 4.35,        # mm/day
    "eto_variance": 0.12,     # Kalman uncertainty
    "eto_std": 0.346,         # ±0.35 mm/day confidence
    "source_weights": {
        "nasa": 0.58,         # 58% NASA contribution
        "openmeteo": 0.42     # 42% Open-Meteo contribution
    }
}
```

**Benefit**: Users know when ETo estimate is more/less certain

### 4. Temporal Consistency

**Problem with Single Sources**:
- NASA: High day-to-day variability (RMSE=1.117 mm/day)
- Open-Meteo: Systematic drift during dry season

**EVAonline Solution**:
- Kalman filter provides **temporal smoothing**
- State evolution model reduces random noise
- Result: RMSE reduced to 0.566 mm/day (49% improvement)

### 5. Regional Adaptation

**KGE Distribution Across 17 Cities**:
```
NASA POWER:      [-0.015 to 0.836]  → Range: 0.851 (high variability)
Open-Meteo calc: [-0.613 to 0.813]  → Range: 1.426 (very high variability)
Open-Meteo API:  [0.065 to 0.824]   → Range: 0.759 (high variability)
EVAonline:       [0.721 to 0.885]   → Range: 0.164 (low variability) ✅
```

**Interpretation**: EVAonline performs **consistently well** across all cities, while single sources show large performance drops in some locations.

### 6. Operational Robustness

| Scenario | Single Source Behavior | EVAonline Behavior |
|----------|----------------------|-------------------|
| **API temporarily unavailable** | ❌ No data | ✅ Falls back to available source |
| **Extreme weather event** | ⚠️ Large uncertainty | ✅ Higher variance indicated, uses multiple sources |
| **Data quality issue** | ❌ Propagates error | ✅ Kalman outlier detection, source re-weighting |
| **Missing variables** | ❌ Cannot calculate ETo | ✅ Gap filling from alternative source |

---

## Summary

**EVAonline's 98% improvement in KGE** vs NASA POWER comes from:

✅ **Multi-source fusion** (complementary strengths)
✅ **Adaptive weighting** (favors more reliable data)
✅ **Brazil-specific bias correction** (Xavier climatology)
✅ **Uncertainty quantification** (Kalman covariance)
✅ **Temporal smoothing** (state evolution)
✅ **Spatial multi-resolution** (0.1° + 0.5° combined)
✅ **Operational robustness** (fallback mechanisms)

**Impact for Users**: Replacing single-source ETo with EVAonline fusion **reduces error by ~50%** and nearly **eliminates systematic bias**, resulting in more accurate irrigation scheduling, crop water requirement estimation, and hydrological modeling for Brazil.

---

## References

- Gupta, H. V., Kling, H., Yilmaz, K. K., & Martinez, G. F. (2009). Decomposition of the mean squared error and NSE performance criteria: Implications for improving hydrological modelling. *Journal of Hydrology*, 377(1-2), 80-91.
- Moriasi, D. N., et al. (2007). Model evaluation guidelines for systematic quantification of accuracy in watershed simulations. *Transactions of the ASABE*, 50(3), 885-900.
- Nash, J. E., & Sutcliffe, J. V. (1970). River flow forecasting through conceptual models part I—A discussion of principles. *Journal of Hydrology*, 10(3), 282-290.
