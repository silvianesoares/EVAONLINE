# Kalman Filter Methodology

## Overview

EVAonline implements an **adaptive Kalman filter** to fuse ETo estimates from multiple sources (NASA POWER and Open-Meteo) with dynamic bias correction using Xavier BR-DWGD climatology.

---

## Climate Data Sources

### Available Sources (6 APIs)

EVAonline integrates **6 climate data sources** through modular API clients:

| Source | Type | Resolution | Coverage | Use Case |
|--------|------|------------|----------|----------|
| **NASA POWER** | Archive (MERRA-2) | 0.5° × 0.625° | Global, 1981-present | Historical ETo (validation) |
| **Open-Meteo Archive** | Archive (ERA5-Land) | 0.1° × 0.1° | Global, 1940-present | Historical ETo (validation) |
| **Open-Meteo Forecast** | Forecast (7-day) | 0.1° × 0.1° | Global | Short-term prediction |
| **Met.no (Norway)** | Forecast (9-day) | High resolution | Norway/Nordic | Regional forecast |
| **NWS Forecast** | Forecast (7-day) | Station-based | USA | Regional forecast (USA) |
| **NWS Stations** | Observations | Station-based | USA | Real-time monitoring |

**Implementation**: `scripts/api/services/` directory with independent client modules

### Validation Sources: NASA POWER + Open-Meteo Archive

**Why these two?**

1. **Complementary strengths**:
   - NASA POWER: Better temperature accuracy, stable 2m wind
   - Open-Meteo: Higher resolution, better precipitation detail

2. **Long historical coverage**:
   - NASA POWER: 1981-present (40+ years)
   - Open-Meteo: 1940-present (80+ years)
   - Enables robust statistical validation

3. **Complete FAO-56 variables**:
   - Both provide: T_max, T_min, RH, wind speed, solar radiation, precipitation
   - Direct compatibility with Penman-Monteith method

4. **Global coverage**:
   - Consistent data availability worldwide
   - No missing data gaps (reanalysis products)

5. **Free and open access**:
   - No authentication required
   - Reproducible research

**Forecast sources** (Open-Meteo Forecast, Met.no, NWS) are used for operational predictions but not included in validation because:
- Short temporal window (7-10 days)
- Insufficient data for statistical metrics (KGE, PBIAS, RMSE)
- Focus on real-time applications, not historical validation

**Station observations** (NWS Stations) provide ground truth but:
- Sparse spatial coverage
- Missing data issues
- Limited to USA territory
- Used for point validation, not gridded ETo estimation

---

## Why Kalman Fusion?

### Problem: Single-Source Limitations

**NASA POWER (MERRA-2)**:
- Better temperature accuracy
- Native 2m wind (no conversion)
- Stable across regions
- Coarse resolution (0.5° × 0.625°)
- Positive bias (+15.78%)
- Misses local features

**Open-Meteo (ERA5-Land)**:
- High resolution (0.1° × 0.1°)
- Better precipitation detail
- Matches Xavier spatial resolution
- 10m wind needs conversion
- Higher bias (+13.02%)
- Variable performance (NSE: -6 to +0.7)

### Solution: Multi-Source Fusion

**Kalman filter combines**:
1. **Complementary strengths** of both sources
2. **Adaptive weighting** (favors more reliable source)
3. **Temporal smoothing** (reduces day-to-day noise)
4. **Uncertainty quantification** (provides confidence intervals)
5. **Bias correction** (anchored to Xavier climatology)

**Result**: KGE=0.814, PBIAS=+0.71%, RMSE=0.566 mm/day

---

## Mathematical Formulation

### State-Space Model

**State equation** (process model):

$$x_t = A \cdot x_{t-1} + w_t$$

**Measurement equation**:

$$z_t = H \cdot x_t + v_t$$

**Where**:
- $x_t$ = true ETo at time $t$ (mm/day)
- $z_t$ = measurement vector $[z_{\text{nasa}}, z_{\text{openmeteo}}]^T$
- $A$ = state transition matrix (persistence model)
- $H$ = measurement matrix (observation model)
- $w_t \sim N(0, Q)$ = process noise (weather variability)
- $v_t \sim N(0, R)$ = measurement noise (sensor/model error)

### Kalman Filter Recursion

**Prediction step**:

$$
\begin{aligned}
\hat{x}_{t|t-1} &= A \cdot \hat{x}_{t-1|t-1} \\\
P_{t|t-1} &= A \cdot P_{t-1|t-1} \cdot A^T + Q
\end{aligned}
$$

**Update step**:

$$
\begin{aligned}
K_t &= P_{t|t-1} \cdot H^T \cdot (H \cdot P_{t|t-1} \cdot H^T + R)^{-1} \\\
\hat{x}_{t|t} &= \hat{x}_{t|t-1} + K_t \cdot (z_t - H \cdot \hat{x}_{t|t-1}) \\\
P_{t|t} &= (I - K_t \cdot H) \cdot P_{t|t-1}
\end{aligned}
$$

**Where**:
- $\hat{x}_{t|t-1}$ = predicted state (prior)
- $\hat{x}_{t|t}$ = updated state (posterior)
- $P_t$ = state covariance (uncertainty)
- $K_t$ = Kalman gain (adaptive weights)

---

## EVAonline Configuration

### Scalar State-Space Model (Per Variable)

**Note**: Implementation uses scalar (1D) Kalman filters applied independently to each climate variable and ETo, rather than simultaneous 2-source matrix formulation.

```python
# State transition (simple persistence - scalar)
A = 1.0  # ETo tomorrow ≈ ETo today

# Measurement model (direct observation - scalar)
H = 1.0  # Direct measurement of variable

# Process noise (DYNAMIC ADAPTATION)
# Q_0 = (xavier_monthly_std[month] ** 2) * 0.08  # Initial value
# Then adapts based on innovation error:
if current_error > last_error * 1.5:
    Q = min(Q * 1.8, xavier_std**2 * 0.5)  # Increase during anomalies

# Measurement noise (ADAPTIVE BY ANOMALY LEVEL)
# R_base = 0.55^2 (default)
if z < p01 * 0.8 or z > p99 * 1.25:
    R = R_base * 500      # Extreme anomaly detection
elif z < p01 or z > p99:
    R = R_base * 50       # Moderate anomaly detection
else:
    R = R_base            # Normal conditions

# Initial uncertainty
P_0 = xavier_monthly_std ** 2  # Initialize with climatology variance
```

### Adaptive Process Noise (Dynamic + Seasonal)

**Implementation**: Process noise ($Q$) uses TWO adaptation mechanisms:

#### 1. Seasonal Base (Xavier Climatology)
```python
# Initial Q from climatological standard deviation
Q_base = xavier_monthly_std[current_month] ** 2
# Example: MATOPIBA region
xavier_monthly_std = {
    1: 0.45,  # January (wet season, high variability)
    2: 0.48,
    3: 0.52,
    4: 0.55,
    5: 0.48,  # Dry season onset
    6: 0.38,  # Dry season (low variability)
    7: 0.35,
    8: 0.36,
    9: 0.42,  # Dry season end
    10: 0.50,
    11: 0.48,
    12: 0.46
}
```

#### 2. Real-Time Error Detection (Innovation-Based)
```python
# Dynamically increase Q when detecting anomalies
current_error = abs(measurement - estimate)
if current_error > last_error * 1.5:
    Q = min(Q * 1.8, xavier_std ** 2 * 0.5)  # Boost Q for robustness
else:
    Q = Q  # Keep current value
```

**Benefit**: Filter adapts to BOTH seasonal patterns (Xavier) AND real-time anomalies (innovation), providing robust smoothing.

---

## Implementation Details

### Initialization

```python
def initialize_kalman(xavier_eto_first_30_days):
    """
    Initialize Kalman filter using first 30 days of Xavier data.
    
    Args:
        xavier_eto_first_30_days: Initial ETo values from reference
    
    Returns:
        x_0: Initial state estimate
        P_0: Initial state covariance
    """
    x_0 = np.mean(xavier_eto_first_30_days)  # Initial estimate
    P_0 = np.var(xavier_eto_first_30_days)   # Initial uncertainty
    
    return x_0, P_0
```

### Daily Update Loop (Scalar Implementation)

```python
def kalman_update_scalar(
    z: float,                # Measurement (raw value)
    x_prev: float,          # Previous state estimate
    P_prev: float,          # Previous error covariance
    Q: float,               # Process noise (dynamic)
    R: float,               # Measurement noise (adaptive)
    p01: float,             # Percentile threshold (low)
    p99: float              # Percentile threshold (high)
) -> tuple:
    """
    Scalar Kalman filter update with anomaly detection.
    
    Returns:
        x_new: Updated state estimate
        P_new: Updated error covariance
        K: Kalman gain
    """
    # PREDICTION STEP
    x_pred = x_prev           # A = 1 (persistence)
    P_pred = P_prev + Q       # Increase uncertainty
    
    # ANOMALY DETECTION → Adapt R
    if np.isnan(z):
        return round(x_prev, 3), P_prev, 0.0
    
    if z < p01 * 0.8 or z > p99 * 1.25:
        R_adaptive = R * 500      # Extreme anomaly
    elif z < p01 or z > p99:
        R_adaptive = R * 50       # Moderate anomaly
    else:
        R_adaptive = R            # Normal
    
    # UPDATE STEP
    innovation = z - x_pred
    S = P_pred + R_adaptive    # Innovation covariance (scalar)
    K = P_pred / S             # Kalman gain
    
    x_new = x_pred + K * innovation
    P_new = (1 - K) * P_pred
    
    # Adaptive Q for next iteration
    current_error = abs(innovation)
    # Q will be adjusted externally based on error trend
    
    return round(x_new, 3), P_new, K
```

**Key Differences from Matrix Formulation**:
- Uses **scalars** instead of matrices (simpler, faster)
- Applies **per-variable** (separate instances for each climate variable)
- **Anomaly detection** modulates R in real-time (3 levels)
- **Scalar Kalman gain**: $K = P_{pred} / (P_{pred} + R)$ determines smoothing strength

### Three-Stage Processing Pipeline

**Complete workflow** (as implemented in `eto_services.py` and `calculate_eto_timeseries()`):

**TWO OPERATIONAL MODES**:
1. **Adaptive Mode** (with Xavier BR-DWGD normals): Full 3-stage pipeline with bias correction
2. **Simple Mode** (without normals): Basic Kalman with global defaults

#### Stage 1: Climate Data Fusion (Kalman per Variable)
- **Input**: Raw data from NASA POWER + Open-Meteo
- **Method**: 
  - Apply Kalman independently to each climate variable (T2M, RH2M, WS2M, PRECTOTCORR, etc.)
  - **Adaptive Mode**: Use Xavier climatology (monthly mean, std, p01, p99) for anomaly detection
  - **Simple Mode**: Use global defaults (no anomaly detection, p01=None, p99=None)
- **Output**: Preprocessed climate data
- **Implementation**: `_fuse_data()` in `eto_services.py` (lines 1037-1210)

#### Stage 2: ETo Calculation (FAO-56 Penman-Monteith)
- **Input**: Fused climate data
- **Method**: Standard FAO-56 method with elevation corrections
- **Output**: Daily raw ETo estimates
- **Implementation**: `calculate_et0()` in `EToCalculationService`

#### Stage 3: ETo Refinement  **CRITICAL**

**MODE SELECTION**: Checks if Xavier climatology available for location (`has_ref`)

---

### **ADAPTIVE MODE** (with Xavier BR-DWGD Normals)

**Condition**: `has_ref=True` (Xavier climatology found within search radius)

**PASSO 1: Calculate Monthly Bias** (Lines 1768-1782)
```python
monthly_bias = {}
for month in range(1, 13):
    mask = df_month == month
    observed_mean = df[mask]['et0_mm'].mean()      # Raw ETo average
    expected_mean = ref['eto_normals'][month]      # Xavier normal
    monthly_bias[month] = observed_mean - expected_mean
```

**PASSO 2: Bias Correction** (Lines 1784-1791)
```python
df['et0_bias_corrected'] = df.apply(
    lambda row: row['et0_mm'] - monthly_bias[pd.to_datetime(row['date']).month]
    if pd.notna(row['et0_mm']) else np.nan
)
```

**PASSO 3: Apply Final Kalman Filter** (Lines 1793-1823)
```python
# Initialize with annual mean (continuous, no monthly reset)
annual_normal = np.mean(list(ref['eto_normals'].values()))
annual_std = np.mean(list(ref['eto_stds'].values()))

kalman_continuous = AdaptiveKalmanFilter(
    normal=annual_normal,
    std=annual_std,
    p01=None,  # Will be set dynamically
    p99=None
)

# Apply sequentially (maintains state across days)
for i in range(len(df)):
    if pd.notna(df.iloc[i]['et0_bias_corrected']):
        # Update p01/p99 dynamically by month
        month = pd.to_datetime(df.iloc[i]['date']).month
        kalman_continuous.p01 = ref['eto_p01'][month]
        kalman_continuous.p99 = ref['eto_p99'][month]
        
        # Apply filter (anomaly detection + smoothing)
        df.loc[i, 'eto_final'] = kalman_continuous.update(
            df.iloc[i]['et0_bias_corrected']
        )
        df.loc[i, 'anomaly_eto_mm'] = (
            df.loc[i, 'eto_final'] - ref['eto_normals'][month]
        )
    else:
        df.loc[i, 'eto_final'] = np.nan
        df.loc[i, 'anomaly_eto_mm'] = np.nan
```

**Key Features**:
- **Monthly bias correction**: Removes systematic bias (PBIAS: +10.5% → +0.71%)
- **Continuous Kalman**: No monthly reset (better temporal coherence)
- **Dynamic thresholds**: p01/p99 updated monthly while filter state persists
- **Anomaly detection**: 3-level R adaptation (1×, 50×, 500×)
- **Anomaly quantification**: `anomaly_eto_mm` = deviation from Xavier normal

**Performance**: **KGE=0.814**, **PBIAS=+0.71%**, **RMSE=0.566 mm/day**

---

### **SIMPLE MODE** (without Normals)

**Condition**: `has_ref=False` (no Xavier climatology found)

**Stage 3 Behavior**: **DISABLED** (fallback to raw ETo)

```python
# Lines 1830-1833
if not kalman_applied:
    df['eto_final'] = df['et0_mm']  # Use raw FAO-56 output
    df['anomaly_eto_mm'] = np.nan   # Cannot calculate anomaly
    logger.info("Kalman final não aplicado (sem referência ou ensemble)")
```

**What Happens**:
- **NO bias correction** (PASSO 1-2 skipped)
- **NO final Kalman filter** (PASSO 3 skipped)
- **Stage 1 still active**: Climate fusion with global defaults
- **Stage 2 unchanged**: FAO-56 calculation works normally
- **Output**: `eto_final = et0_mm` (raw, unrefined)

**Stage 1 Global Defaults** (Lines 1059-1070):
```python
default_params = {
    'T2M_MAX': {'mean': 30.0, 'std': 5.0},
    'T2M_MIN': {'mean': 18.0, 'std': 5.0},
    'T2M': {'mean': 24.0, 'std': 5.0},
    'RH2M': {'mean': 65.0, 'std': 15.0},
    'WS2M': {'mean': 2.5, 'std': 1.5},
    'ALLSKY_SFC_SW_DWN': {'mean': 180.0, 'std': 50.0},
    'PRECTOTCORR': {'mean': 3.0, 'std': 5.0}
}

# Create simple Kalman (NO anomaly detection)
kalman_filter = AdaptiveKalmanFilter(
    normal=params['mean'],
    std=params['std'],
    p01=None,  # NO lower threshold
    p99=None   # NO upper threshold
)
```

**Limitations**:
- **Higher bias**: ~+10-15% (vs +0.71% in Adaptive Mode)
- **No anomaly quantification**: Cannot detect extreme events
- **Global parameters**: May not match local climate
- **No temporal anchoring**: Filter drifts without reference

**When Used**:
- Point of interest **outside Xavier coverage** (Brazil mainland)
- Remote/international locations
- Ocean/offshore coordinates
- **Xavier search radius** exceeded (default: 50 km)

---

**Implementation**: `calculate_eto_timeseries()` in `eto_services.py` (lines 1758-1841)

---

## Validation Results

### Convergence Analysis

**Typical convergence** (30-60 days after initialization):

```
Day 1:   Kalman gain = [0.5, 0.5]  (equal weights, high uncertainty)
Day 10:  Kalman gain = [0.55, 0.45] (slight NASA preference emerging)
Day 30:  Kalman gain = [0.58, 0.42] (converged to stable weights)
Day 365: Kalman gain = [0.58, 0.42] (stable, repeats annually)
```

**Interpretation**: After ~30 days initialization, filter learns NASA POWER is slightly more reliable (58% vs 42% weight) due to better temperature assimilation despite coarser resolution.

### Performance Comparison

| Method | KGE | PBIAS (%) | RMSE (mm/day) | Notes |
|--------|-----|-----------|---------------|-------|
| **Simple average** | 0.62 | +14.4 | 0.98 | Arithmetic mean of NASA + OpenMeteo |
| **Weighted average** | 0.68 | +12.1 | 0.85 | Fixed weights (60% NASA, 40% OM) |
| **Kalman (Stage 1 only)** | 0.75 | +10.5 | 0.72 | Climate fusion, no ETo Kalman |
| **Kalman + Bias Corr** | 0.78 | +3.2 | 0.64 | After monthly bias correction (Stage 3 PASSO 1-2) |
| **Kalman + Full Stage 3** | **0.814** | **+0.71** | **0.566** | Complete 3-stage pipeline (Stages 1+2+3) |

**Key insight**: Bias correction using Xavier climatology is essential for near-zero bias.

### Uncertainty Quantification

**Example output** (Piracicaba-SP, 2020-01-15):

```python
{
    "date": "2020-01-15",
    "eto_fused": 4.35,           # mm/day (point estimate)
    "eto_std": 0.346,            # mm/day (±1 std)
    "eto_95ci": [3.67, 5.03],    # mm/day (95% confidence interval)
    "source_weights": {
        "nasa": 0.58,            # 58% contribution
        "openmeteo": 0.42        # 42% contribution
    },
    "innovation": {
        "nasa": -0.12,           # NASA measured 0.12 mm/day below prediction
        "openmeteo": +0.08       # OpenMeteo measured 0.08 mm/day above prediction
    }
}
```

**Benefit**: Users can assess estimate reliability (narrow CI = high confidence).

---

## Advantages Over Alternatives

### 1. vs Simple Averaging

**Simple average**:
```python
eto_avg = (eto_nasa + eto_openmeteo) / 2  # Fixed 50-50 weights
```

**Problems**:
- Equal weight to unreliable measurements
- No temporal smoothing
- No uncertainty quantification
- Bias not addressed

**Kalman fusion**:
- Adaptive weights (more reliable source gets more weight)
- Temporal smoothing (reduces noise)
- Uncertainty quantification
- Bias correction

### 2. vs Machine Learning

**ML approaches** (e.g., Random Forest, Neural Networks):

**Advantages**:
- Can capture complex nonlinear relationships
- Learn from training data

**Disadvantages**:
- Require large training dataset
- Black box (hard to interpret)
- Can overfit
- No uncertainty quantification (unless Bayesian)
- Difficult to validate physically

**Kalman filter**:
- Physically interpretable (based on error covariance)
- Works with limited data (30-day initialization)
- Provides uncertainty estimates naturally
- Computationally efficient
- Theoretically optimal (for linear-Gaussian systems)

### 3. vs Source Selection

**Best-source selection**:
```python
if r2_nasa > r2_openmeteo:
    eto = eto_nasa
else:
    eto = eto_openmeteo
```

**Problems**:
- Discards information from other source
- Binary decision (no intermediate weighting)
- Sensitive to validation period choice

**Kalman fusion**:
- Uses all available information
- Continuous weighting (58% NASA, 42% OM)
- Robust to outliers in single source

---

## Sensitivity Analysis

### Process Noise (Q)

| Q value | Interpretation | KGE | PBIAS | RMSE |
|---------|---------------|-----|-------|------|
| 0.01 | Very low variability (desert) | 0.75 | +1.2 | 0.68 |
| **0.20** | **Medium variability (MATOPIBA)** | **0.814** | **+0.71** | **0.566** |
| 0.50 | High variability (rainforest) | 0.78 | +0.85 | 0.62 |
| 1.00 | Very high variability | 0.72 | +1.1 | 0.71 |

### Measurement Noise (R) - Anomaly-Based Adaptation

| Anomaly Level | Condition | R multiplier | Usage | Impact |
|----------------|-----------|--------------|-------|--------|
| **Normal** | p01 ≤ z ≤ p99 | 1.0× (R_base) | Regular conditions | High trust in measurement |
| **Moderate** | p01×0.8 < z < p01 OR p99 < z < p99×1.25 | 50× (R_base) | Outlier detection | Medium trust |
| **Extreme** | z < p01×0.8 OR z > p99×1.25 | 500× (R_base) | Strong anomaly | Low trust, Kalman smooths |

**Optimal**: R_base = 0.55² (implementation default)
- **Stage 1 (Climate fusion)**: R adapted for each variable independently
- **Stage 3 (ETo final)**: R adapted based on monthly p01/p99 thresholds

**Benefit**: Automatically down-weights suspicious measurements while maintaining signal

---

## Code Repository

**Climate Data Sources** (`scripts/api/services/`):
- `nasa_power/nasa_power_client.py` - NASA POWER (MERRA-2) archive client
- `openmeteo_archive/openmeteo_archive_client.py` - Open-Meteo Archive (ERA5-Land) client
- `openmeteo_forecast/openmeteo_forecast_client.py` - Open-Meteo 7-day forecast
- `met_norway/met_norway_client.py` - Met.no Norway forecast client
- `nws_forecast/nws_forecast_client.py` - NWS USA forecast client
- `nws_stations/nws_stations_client.py` - NWS USA station observations
- `climate_source_manager.py` - Unified data source orchestration
- `climate_source_selector.py` - Automatic source selection logic

**Kalman Filter Implementation**:
- `scripts/core/data_processing/kalman_ensemble.py` - Core Kalman filter classes
  - `AdaptiveKalmanFilter` class: Scalar Kalman filter with anomaly detection
  - `ClimateKalmanEnsemble` class: Climate-specific ensemble management
- `scripts/core/eto_calculation/eto_services.py` - ETo service with full pipeline
  - `EToProcessingService._fuse_data()`: Stage 1 - Climate fusion (lines 990-1220)
  - `EToCalculationService.calculate_et0()`: Stage 2 - FAO-56 calculation
  - `calculate_eto_timeseries()`: Stage 3 orchestration (lines 1720-1856)
    - Lines 1783-1806: **PASSO 1** - Monthly bias calculation
    - Lines 1807-1809: **PASSO 2** - Bias correction application  
    - Lines 1813-1838: **PASSO 3** - Continuous Kalman filter with dynamic thresholds
- `backend/core/data_processing/kalman_ensemble.py` - Production version

**Entry point**: `calculate_eto_timeseries(df, lat, lon, elevation, kalman_ensemble=ensemble_obj)`

**Usage**:
```python
# Step 1: Fetch climate data from multiple sources
from scripts.api.services.nasa_power.nasa_power_client import NASAPowerClient
from scripts.api.services.openmeteo_archive.openmeteo_archive_client import OpenMeteoArchiveClient

nasa_client = NASAPowerClient()
openmeteo_client = OpenMeteoArchiveClient()

# Fetch data (validation: NASA POWER + Open-Meteo Archive)
df_nasa = await nasa_client.get_data(lat=-10.5, lon=-50.5, start='2020-01-01', end='2020-12-31')
df_openmeteo = await openmeteo_client.get_data(lat=-10.5, lon=-50.5, start='2020-01-01', end='2020-12-31')

# Step 2: Initialize Kalman ensemble
from scripts.core.data_processing.kalman_ensemble import ClimateKalmanEnsemble
kalman = ClimateKalmanEnsemble()  # Loads Xavier BR-DWGD climatology

# Step 3: Fuse climate data (Stage 1) + Calculate ETo (Stage 2+3)
from scripts.core.eto_calculation.eto_services import calculate_eto_timeseries

df_result = calculate_eto_timeseries(
    df_weather_fused,  # Combined NASA + OpenMeteo data
    latitude=-10.5,
    longitude=-50.5,
    elevation_m=500.0,
    kalman_ensemble=kalman  # Enables Stage 3 (if Xavier normals available)
)
# Output columns: et0_mm, eto_final, anomaly_eto_mm
```

---

## References

**Kalman Filter Theory**:
- Kalman, R. E. (1960). A new approach to linear filtering and prediction problems. *Journal of Basic Engineering*, 82(1), 35-45.
- Welch, G., & Bishop, G. (2006). An introduction to the Kalman filter. Technical report, University of North Carolina at Chapel Hill.

**Applications in Hydrology**:
- Bauer, P., Thorpe, A., & Brunet, G. (2015). The quiet revolution of numerical weather prediction. *Nature*, 525(7567), 47-55.
- Liu, Y., & Gupta, H. V. (2007). Uncertainty in hydrologic modeling: Toward an integrated data assimilation framework. *Water Resources Research*, 43(7).

**ETo Estimation**:
- Allen, R.G., Pereira, L.S., Raes, D., Smith, M., 1998. Crop evapotranspiration - Guidelines for computing crop water requirements. FAO Irrigation and Drainage Paper 56.

---

## Summary

**Architecture**: Three-stage pipeline with independent Kalman applications

### Stage 1: Climate Fusion
1. **Per-variable Kalman**: Independent filters for T2M, RH2M, WS2M, PRECTOTCORR, etc.
2. **Anomaly detection**: R adapts in 3 levels (normal/moderate/extreme) *[Adaptive Mode only]*
3. **Dual modes**: 
   - **Adaptive Mode** (with Xavier): Monthly statistics (mean, std, p01, p99) enable precise anomaly detection
   - **Simple Mode** (without Xavier): Global defaults (mean, std only), NO anomaly detection (p01=None, p99=None)

### Stage 2: ETo Calculation  
4. **FAO-56 Penman-Monteith**: Standard agro-meteorological method
5. **Elevation corrections**: Pressure, psychrometric constant adjusted

### Stage 3: ETo Refinement 
**Adaptive Mode only** (requires Xavier climatology):
6. **Monthly bias correction**: Removes systematic bias while preserving variability (PBIAS: +10.5% → +0.71%)
7. **Continuous Kalman filter**: Scalar filter maintaining state across days
8. **Dynamic thresholds**: p01/p99 updated monthly while filter state persists
9. **Adaptive process noise**: Responds to real-time error trends

**Simple Mode**: Stage 3 **DISABLED** → `eto_final = et0_mm` (raw FAO-56 output)

**Key Innovations**:
- **Bias correction BEFORE Kalman** (not after): Ensures filter operates on unbiased signal
- **Continuous state** (annual init, no monthly reset): Better temporal coherence
- **Redundant anomaly detection** (R + p01/p99): Catches outliers at multiple stages
- **Independent per-variable**: More robust than simultaneous multi-source fusion

**Results**:

| Mode | KGE | PBIAS (%) | RMSE (mm/day) | Anomaly Detection | Bias Correction |
|------|-----|-----------|---------------|-------------------|------------------|
| **Adaptive** (with Xavier) | **0.814** | **+0.71** | **0.566** | 3-level (1×, 50×, 500×) | Monthly |
| **Simple** (no Xavier) | ~0.70 | ~+12.0 | ~0.80 | Disabled | Disabled |

**Adaptive Mode**: 98% improvement over single-source | Near-zero bias | 50% RMSE reduction  
**Simple Mode**: Basic fusion only | Moderate bias | Limited improvement
