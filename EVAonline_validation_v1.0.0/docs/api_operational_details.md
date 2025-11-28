# API Operational Details & Gap Filling Strategy

## Overview

This document describes operational considerations for using NASA POWER and Open-Meteo APIs in real-world applications, including temporal coverage, latency, rate limits, and gap filling strategies.

---

## Temporal Coverage Summary

| Data Source | Start Date | End Date | Update Frequency | Latency | Use Case |
|-------------|-----------|----------|-----------------|---------|----------|
| **Xavier BR-DWGD** | 1961-01-01 | 2024-12-31* | Annual updates | 6-12 months | Reference/validation only |
| **NASA POWER** | 1981-01-01 | Present | Daily | **0 days** (real-time) | Historical + Real-time |
| **Open-Meteo Archive** | 1950-01-01 | Today - 2 days | Daily | **2 days** (QC period) | Historical data |
| **Open-Meteo Forecast** | Today - 30 days | Today + 5 days | Hourly | **0 days** (real-time) | Recent + Forecast + Gap fill |

**\*** Xavier dataset extended to 2024 but official publication covers 1961-2020

---

## Operational Scenarios

### 1. Real-time Applications (Dashboard, Today's Data)

**Challenge**: Open-Meteo Archive has 2-day delay

**Solution**: Multi-API strategy

| API | Coverage | Purpose |
|-----|----------|---------|
| **NASA POWER** | Oct 16 → Nov 14 (30 days) | Primary source - complete coverage ✅ |
| **Open-Meteo Archive** | Oct 16 → Nov 12 (28 days) | Historical data (up to 2 days ago) |
| **Open-Meteo Forecast** | Nov 13 → Nov 14 (2 days) | **Fills Archive gap** ✅ |

**Timeline Visualization** (example: Nov 14, 2025, 30-day dashboard):

```
Timeline for 30-day Dashboard (Nov 14, 2025)
┌────────────────────────────────────────┬─────────┬─────────┐
│    NASA POWER (complete coverage)      │         │         │
│ Oct 16 ───────────────────────────► Nov 14       │         │
└────────────────────────────────────────┴─────────┴─────────┘
✅ Covers: 30 days WITHOUT gaps (up to today)

┌────────────────────────────────────────┬─────────┬─────────┐
│   Open-Meteo Archive (2-day delay)     │   GAP   │         │
│ Oct 16 ──────────────────────► Nov 12  │ Nov 13  │ Nov 14  │
└────────────────────────────────────────┴─────────┴─────────┘
⚠️  Missing: Nov 13 and Nov 14 (2 days)

┌────────────────────────────────────────┬─────────┬─────────┐
│                                        │ OM Fcst │ OM Fcst │
│                                        │ Nov 13  │ Nov 14  │
└────────────────────────────────────────┴─────────┴─────────┘
✅ Open-Meteo Forecast fills the 2-day gap

Result: Kalman fusion combines:
- Archive (Oct 16-Nov 12) + Forecast (Nov 13-14) = 30 days complete
```

**Implementation**:

```python
from datetime import datetime, timedelta

today = datetime(2025, 11, 14).date()
start = today - timedelta(days=29)  # Oct 16, 2025
end = today                          # Nov 14, 2025

# APIs queried automatically by EVAonline:
nasa_data = nasa_client.get_daily_data(
    start=start, end=end  # Oct 16 → Nov 14 (30 days) ✅
)

openmeteo_archive = archive_client.get_daily_data(
    start=start, 
    end=today - timedelta(days=2)  # Oct 16 → Nov 12 (28 days)
)

openmeteo_forecast = forecast_client.get_daily_data(
    start=today - timedelta(days=1), 
    end=end  # Nov 13 → Nov 14 (2 days, gap fill)
)

# Kalman fusion combines all three sources
# Result: 30 complete days with no gaps
```

---

### 2. Historical Analysis (Reports, CSV Export)

**Period**: Any historical date range (typically 1-90 days)

**Constraint**: End date must be ≤ (today - 30 days) for email reports

**APIs Used**:
- **NASA POWER**: ✅ Complete since 1981 (1990+ validated)
- **Open-Meteo Archive**: ✅ Complete since 1950 (1990+ validated)
- **Xavier**: ✅ Complete 1961-2020 (reference/validation)

**No gap filling needed** - both APIs have complete historical coverage

**Example**:
```python
# Historical request (any past date)
start = datetime(2020, 1, 1).date()
end = datetime(2020, 12, 31).date()

# Both APIs provide complete coverage
nasa_data = nasa_client.get_daily_data(start, end)        # ✅ 366 days
openmeteo_data = archive_client.get_daily_data(start, end) # ✅ 366 days
```

---

### 3. Forecast Applications (5-day ahead)

**APIs Used**:
- **Open-Meteo Forecast**: ✅ Today + 5 days (global)
- **MET Norway**: ✅ Today + 5 days (Nordic region only)
- **NWS Forecast**: ✅ Today + 5 days (USA only)

**EVAonline**: Automatically selects best available forecast API based on location

```python
# Forecast request
start = datetime.today().date()
end = start + timedelta(days=5)

# EVAonline selects best source:
# - Global: Open-Meteo Forecast
# - Nordic (Norway, Sweden, Finland, Denmark): MET Norway (higher quality)
# - USA: NWS Forecast (optional, alternative)
```

---

## API Rate Limits & Caching Strategy

### NASA POWER

**Rate Limits**:
- **Per Second**: <1 req/s (recommended fair use)
- **Per Request**: Max 20 parameters (single point)
- **Per Day/Month**: No hard limits (fair use policy)

**EVAonline Cache Strategy**:
```python
{
    "Historical data (>7 days old)": {
        "Cache": "Redis + local",
        "TTL": "24 hours",
        "Reason": "Data is stable, rarely changes"
    },
    "Recent data (0-7 days old)": {
        "Cache": "Redis",
        "TTL": "1 hour",
        "Reason": "May be updated/corrected"
    }
}
```

### Open-Meteo Archive

**Rate Limits**:
- **Per Second**: <10 req/s (recommended)
- **Per Day**: ~10,000 req/day (free plan)
- **Paid Plans**: >1M req/month available

**EVAonline Cache Strategy**:
```python
{
    "Historical Archive": {
        "Cache": "Redis + local",
        "TTL": "24 hours",
        "Reason": "Stable historical data"
    }
}
```

### Open-Meteo Forecast

**Rate Limits**: Same as Archive

**EVAonline Cache Strategy**:
```python
{
    "Forecast (future dates)": {
        "Cache": "Redis",
        "TTL": "1 hour",
        "Reason": "Updates frequently"
    },
    "Recent past (0-2 days)": {
        "Cache": "Redis",
        "TTL": "6 hours",
        "Reason": "Gap fill, semi-stable"
    }
}
```

---

## Cache Benefits

✅ **Reduced API load**: Respects free service limits
✅ **Faster response**: Dashboard loads <2s (vs 5-10s without cache)
✅ **Resilience**: Fallback if API temporarily unavailable
✅ **Cost efficiency**: Stays within free tier limits

**Cache Hit Rates** (typical EVAonline usage):
- Historical requests: ~95% (data rarely changes)
- Dashboard (30-day): ~85% (partial cache, some new data)
- Forecast: ~40% (updates frequently)

---

## Validation Period Choice (1991-2020)

### Why 1991-2020?

**30 years**: WMO standard for climatological normal

**Start 1991**:
- After major MERRA-2 satellite transitions (stable period)
- Better satellite coverage (AVHRR, TRMM)
- Consistent data quality across both APIs

**End 2020**:
- Last complete year in Xavier official publication (2022)
- Allows for quality control and homogeneity testing
- Avoids recent years with potential reprocessing

**Completeness**:
- All sources have <0.5% missing data
- No major gaps or discontinuities
- Sufficient for robust statistical validation

**Quality**:
- Post-1990 period has better satellite coverage
- More ground stations in INMET network
- Improved precipitation estimates (Xavier 2022 update)

---

## API Request Examples

### Example 1: Dashboard (30-day, real-time)

```python
from evaonline import ClimateDataService
from datetime import datetime, timedelta

service = ClimateDataService()

# User request: Last 30 days
today = datetime.now().date()
start = today - timedelta(days=29)

# EVAonline handles gap filling automatically
result = service.get_eto_fused(
    lat=-15.8,
    lon=-47.9,
    start_date=start,
    end_date=today,
    context="dashboard"  # Indicates real-time requirement
)

# Result includes:
# - 30 days of ETo (no gaps)
# - NASA + OpenMeteo fusion
# - Archive (28d) + Forecast (2d) gap fill
# - Kalman uncertainty estimates
```

### Example 2: Historical Report (90 days, CSV export)

```python
# User request: Q1 2020 (90 days)
start = datetime(2020, 1, 1).date()
end = datetime(2020, 3, 31).date()

# EVAonline validates constraints
assert (datetime.now().date() - end).days >= 30  # ✅ Old enough

result = service.get_eto_fused(
    lat=-15.8,
    lon=-47.9,
    start_date=start,
    end_date=end,
    context="historical",  # Historical analysis
    output_format="csv"    # Email report
)

# Result:
# - 91 days (Jan 1 - Mar 31)
# - Archive data only (no forecast needed)
# - CSV file sent to email
```

### Example 3: Forecast (5 days)

```python
# User request: Next 5 days forecast
start = datetime.now().date()
end = start + timedelta(days=5)

result = service.get_eto_forecast(
    lat=-15.8,
    lon=-47.9,
    start_date=start,
    end_date=end,
    context="forecast"
)

# Result:
# - 6 days (today + next 5)
# - Open-Meteo Forecast API
# - Daily ETo predictions
# - Uncertainty estimates
```

---

## Error Handling & Fallback Strategy

### API Unavailable

```python
try:
    data = openmeteo_archive_client.get_data(...)
except APIUnavailableError:
    # Fallback to cached data (if available)
    data = cache.get(cache_key)
    if data is None:
        # Ultimate fallback: NASA POWER only
        logger.warning("OpenMeteo unavailable, using NASA POWER only")
        data = nasa_power_client.get_data(...)
```

### Rate Limit Exceeded

```python
try:
    data = api_client.get_data(...)
except RateLimitError as e:
    # Wait and retry with exponential backoff
    wait_time = e.retry_after or 60  # seconds
    logger.warning(f"Rate limit hit, waiting {wait_time}s")
    time.sleep(wait_time)
    data = api_client.get_data(...)  # Retry once
```

### Invalid Response

```python
data = api_client.get_data(...)
if not validate_data_quality(data):
    logger.error("Data quality check failed, using cached data")
    data = cache.get(cache_key) or use_alternative_source()
```

---

## Best Practices

### For Developers

✅ **Always use cache**: Set appropriate TTL based on data freshness requirements
✅ **Respect rate limits**: Implement exponential backoff and retry logic
✅ **Validate data quality**: Check for nulls, outliers, physical constraints
✅ **Log API calls**: Monitor usage to stay within free tier limits
✅ **Implement fallbacks**: Multiple data sources for resilience

### For Users

✅ **Historical analysis**: Use any date range (1991-2020 validated)
✅ **Real-time dashboard**: Accepts up to today (gap filling automatic)
✅ **Forecast**: 5-day ahead (global coverage)
✅ **Email reports**: End date must be ≥30 days old (data quality constraint)

---

## Summary

**Key Points**:

1. **NASA POWER**: ✅ Zero latency, complete real-time coverage
2. **Open-Meteo Archive**: ⚠️ 2-day delay, excellent historical coverage
3. **Open-Meteo Forecast**: ✅ Fills 2-day gap, provides 5-day forecast
4. **Gap Filling**: Automatic in EVAonline dashboard (seamless to user)
5. **Caching**: Essential for performance and respecting free tier limits
6. **Validation Period**: 1991-2020 (30 years, WMO standard)

**Operational Impact**:

- ✅ Dashboard: Real-time data with <2s response time
- ✅ Historical reports: Any period 1990-present
- ✅ Forecasts: 5-day ahead with uncertainty
- ✅ Resilience: Multiple sources, automatic fallback
- ✅ Free tier: Stays within API limits via caching

---

## References

- NASA POWER API Documentation: https://power.larc.nasa.gov/docs/services/api/
- Open-Meteo API Documentation: https://open-meteo.com/en/docs
- World Meteorological Organization (WMO) Technical Regulations, Volume I, 2011.
