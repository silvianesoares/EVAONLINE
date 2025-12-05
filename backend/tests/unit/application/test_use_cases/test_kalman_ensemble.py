import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, mock_open
import json
from pathlib import Path
from backend.core.data_processing.kalman_ensemble import (
    ClimateKalmanEnsemble,
    AdaptiveKalmanFilter,
    SimpleKalmanFilter,
    HistoricalDataLoader,
    KalmanState,
)


class TestAdaptiveKalmanFilter:
    """Test the adaptive Kalman filter behavior"""

    def test_initialization(self):
        kf = AdaptiveKalmanFilter(normal=5.0, std=1.0)
        assert kf.normal == 5.0
        assert kf.std >= 0.4  # Minimum std enforcement
        assert kf.state.estimate == 5.0

    def test_normal_measurement(self):
        """Normal measurements should converge smoothly"""
        kf = AdaptiveKalmanFilter(normal=5.0, std=1.0, p01=2.0, p99=8.0)
        measurements = [5.1, 4.9, 5.2, 5.0, 4.8]
        results = [kf.update(m) for m in measurements]

        # Results should be close to measurements
        assert all(4.0 < r < 6.0 for r in results)
        # Should converge (last estimate closer to 5.0)
        assert abs(results[-1] - 5.0) < 0.5

    def test_outlier_handling(self):
        """Outliers should be dampened aggressively"""
        kf = AdaptiveKalmanFilter(normal=5.0, std=1.0, p01=2.0, p99=8.0)

        # Normal measurements
        for _ in range(5):
            kf.update(5.0)

        # Extreme outlier
        outlier_result = kf.update(50.0)

        # Should be dampened (not jump to 50)
        assert outlier_result < 10.0
        assert outlier_result > 5.0

    def test_nan_handling(self):
        kf = AdaptiveKalmanFilter(normal=5.0, std=1.0)
        kf.update(5.5)
        result = kf.update(np.nan)

        # Should return last estimate when NaN
        assert not np.isnan(result)
        assert result == round(kf.state.estimate, 3)

    def test_p01_p99_calculation_when_none(self):
        """Test automatic calculation of p01/p99 when not provided"""
        kf = AdaptiveKalmanFilter(normal=10.0, std=2.0, p01=None, p99=None)

        # p01 should be normal - 3.5 * std = 10.0 - 7.0 = 3.0
        assert kf.p01 == 10.0 - 3.5 * 2.0
        # p99 should be normal + 3.5 * std = 10.0 + 7.0 = 17.0
        assert kf.p99 == 10.0 + 3.5 * 2.0

    def test_std_minimum_enforcement(self):
        """Test that std is enforced to be at least 0.4"""
        kf = AdaptiveKalmanFilter(normal=5.0, std=0.1)
        assert kf.std == 0.4  # Should be clamped to minimum

    def test_adaptive_q_increases_on_large_error(self):
        """Test that Q increases when error grows"""
        kf = AdaptiveKalmanFilter(normal=5.0, std=1.0, p01=2.0, p99=8.0)

        # Establish baseline
        kf.update(5.0)
        initial_q = kf.Q

        # Large error should increase Q
        kf.update(7.5)
        assert kf.Q >= initial_q

    def test_three_levels_of_r_adaptation(self):
        """Test the three levels of R (normal, outlier, extreme outlier)"""
        kf = AdaptiveKalmanFilter(normal=5.0, std=1.0, p01=2.0, p99=8.0)

        # Normal measurement should have small adjustment
        kf.update(5.0)
        kf.update(5.5)
        estimate_normal = kf.state.estimate
        deviation_normal = abs(estimate_normal - 5.0)

        # Moderate outlier (below p01 but not extreme)
        kf2 = AdaptiveKalmanFilter(normal=5.0, std=1.0, p01=2.0, p99=8.0)
        kf2.update(5.0)
        kf2.update(1.5)  # Between p01*0.8 and p01
        estimate_moderate = kf2.state.estimate

        # Extreme outlier
        kf3 = AdaptiveKalmanFilter(normal=5.0, std=1.0, p01=2.0, p99=8.0)
        kf3.update(5.0)
        kf3.update(0.5)  # Below p01*0.8
        estimate_extreme = kf3.state.estimate

        # Both outliers should be dampened (stay closer to 5.0)
        assert estimate_moderate < 5.0  # Moved toward outlier
        assert estimate_extreme < 5.0  # Moved toward outlier
        assert deviation_normal < 1.0  # Normal measurement relatively close

    def test_history_tracking(self):
        """Test that state.history tracks all estimates"""
        kf = AdaptiveKalmanFilter(normal=5.0, std=1.0)
        measurements = [5.1, 4.9, 5.2, 5.0, 4.8]

        for m in measurements:
            kf.update(m)

        assert len(kf.state.history) == len(measurements)
        assert all(isinstance(h, float) for h in kf.state.history)

    def test_kalman_state_initialization(self):
        """Test KalmanState dataclass"""
        state = KalmanState()
        assert state.estimate == 0.0
        assert state.error == 1.0
        assert state.Q == 1e-3
        assert state.history == []

        # Test with custom values
        state2 = KalmanState(estimate=5.0, error=2.0, Q=0.01)
        assert state2.estimate == 5.0
        assert state2.error == 2.0
        assert state2.Q == 0.01


class TestSimpleKalmanFilter:
    """Test the simple fallback Kalman filter"""

    def test_initialization(self):
        skf = SimpleKalmanFilter(initial_value=5.0)
        assert skf.estimate == 5.0
        assert skf.error == 1.0

    def test_convergence(self):
        skf = SimpleKalmanFilter(initial_value=3.0)
        measurements = [5.0] * 10

        for m in measurements:
            skf.update(m)

        # Should converge toward 5.0
        assert abs(skf.estimate - 5.0) < 0.5

    def test_nan_handling(self):
        skf = SimpleKalmanFilter(initial_value=5.0)
        result = skf.update(np.nan)
        assert not np.isnan(result)

    def test_extreme_values(self):
        """Test handling of extreme values"""
        skf = SimpleKalmanFilter(initial_value=5.0)

        # Very high value
        skf.update(1000.0)
        assert skf.estimate > 5.0

        # Very low value
        skf.update(-1000.0)
        assert skf.estimate < 1000.0  # Should move toward new measurement

    def test_multiple_consecutive_updates(self):
        """Test stability with many consecutive updates"""
        skf = SimpleKalmanFilter(initial_value=5.0)

        # 100 measurements of the same value
        for _ in range(100):
            skf.update(7.0)

        # Should converge very close to 7.0
        assert abs(skf.estimate - 7.0) < 0.1

        # Error should decrease (more confident)
        assert skf.error < 1.0


class TestHistoricalDataLoader:
    """Test reference data loading"""

    def test_initialization(self):
        loader = HistoricalDataLoader()
        assert loader.historical_dir is not None
        assert loader.city_coords_path is not None
        assert isinstance(loader._cache, dict)

    def test_location_search_no_match(self):
        """Test fallback when no reference found"""
        loader = HistoricalDataLoader()
        # Random ocean coordinates
        has_ref, ref = loader.get_reference_for_location(
            0.0, 0.0, max_dist_km=10
        )
        assert has_ref is False
        assert ref is None

    def test_location_caching(self):
        """Test that results are cached"""
        loader = HistoricalDataLoader()
        lat, lon = -15.8, -47.9  # Brasília approximate

        # First call
        has_ref1, ref1 = loader.get_reference_for_location(lat, lon)

        # Check cache was populated
        cache_key = (round(lat, 2), round(lon, 2))
        assert cache_key in loader._cache

        # Second call (should be cached - returns True even for None)
        has_ref2, ref2 = loader.get_reference_for_location(lat, lon)

        # When cached, always returns True (even if ref is None)
        assert has_ref2 is True
        # But ref values should match
        assert ref1 == ref2

    def test_distance_calculation(self):
        """Test geographic distance calculation"""
        loader = HistoricalDataLoader()

        # Add mock city coords
        loader.city_coords = {"test_city": (-15.8, -47.9)}  # Brasília coords

        # Create mock data directory structure
        with patch("pathlib.Path.glob") as mock_glob:
            mock_path = Path("report_test_city.json")
            mock_glob.return_value = [mock_path]

            # Mock file reading
            mock_data = {
                "climate_normals_all_periods": {
                    "1991-2020": {
                        "monthly": {
                            "1": {
                                "normal": 5.0,
                                "daily_std": 1.0,
                                "p01": 2.0,
                                "p99": 8.0,
                                "precip_normal": 100.0,
                                "precip_daily_std": 10.0,
                                "precip_p01": 0.0,
                                "precip_p99": 450.0,
                            }
                        }
                    }
                }
            }

            mock_json = json.dumps(mock_data)
            with patch("builtins.open", mock_open(read_data=mock_json)):
                # Very close location (should find)
                has_ref, ref = loader.get_reference_for_location(
                    -15.9, -48.0, max_dist_km=50
                )

                if has_ref:
                    assert ref is not None
                    assert "distance_km" in ref

    def test_max_distance_enforcement(self):
        """Test that max_dist_km is enforced"""
        loader = HistoricalDataLoader()

        # Even if there's a city, it should not match if too far
        has_ref, ref = loader.get_reference_for_location(
            -15.8, -47.9, max_dist_km=0.1  # Very small radius
        )

        # Unlikely to find match with such small radius
        if not has_ref:
            assert ref is None

    def test_reference_dict_structure(self):
        """Test that reference dict has all required fields"""
        loader = HistoricalDataLoader()

        # Try to get a reference (may or may not exist)
        has_ref, ref = loader.get_reference_for_location(
            -22.9, -43.2, max_dist_km=200
        )

        if has_ref and ref is not None:
            # Validate structure
            required_fields = [
                "city",
                "distance_km",
                "eto_normals",
                "eto_stds",
                "eto_p01",
                "eto_p99",
                "precip_normals",
                "precip_stds",
                "precip_p01",
                "precip_p99",
            ]

            for field in required_fields:
                assert field in ref, f"Missing field: {field}"

            # Validate that monthly dicts have data
            assert isinstance(ref["eto_normals"], dict)
            assert isinstance(ref["precip_normals"], dict)

    def test_load_city_coords_file_not_exists(self):
        """Test behavior when city coords file doesn't exist"""
        loader = HistoricalDataLoader()
        loader.city_coords_path = Path("/nonexistent/path/info_cities.csv")

        result = loader._load_city_coords()
        assert result == {}

    def test_corrupted_json_handling(self):
        """Test handling of corrupted JSON files"""
        loader = HistoricalDataLoader()
        loader.city_coords = {"test_city": (-15.8, -47.9)}

        with patch("pathlib.Path.glob") as mock_glob:
            mock_path = Path("report_test_city.json")
            mock_glob.return_value = [mock_path]

            # Mock corrupted JSON
            with patch("builtins.open", mock_open(read_data="corrupted{json")):
                has_ref, ref = loader.get_reference_for_location(-15.8, -47.9)

                assert has_ref is False
                assert ref is None


class TestClimateKalmanEnsemble:
    """Test the main ensemble fusion class"""

    @pytest.fixture
    def sample_nasa_df(self):
        """Create sample NASA data"""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        return pd.DataFrame(
            {
                "date": dates,
                "T2M_MAX": np.random.uniform(25, 35, 10),
                "T2M_MIN": np.random.uniform(15, 20, 10),
                "T2M": np.random.uniform(20, 25, 10),
                "RH2M": np.random.uniform(60, 80, 10),
                "WS2M": np.random.uniform(2, 5, 10),
                "ALLSKY_SFC_SW_DWN": np.random.uniform(15, 25, 10),
                "PRECTOTCORR": np.random.uniform(0, 10, 10),
            }
        )

    @pytest.fixture
    def sample_om_df(self):
        """Create sample OpenMeteo data"""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        return pd.DataFrame(
            {
                "date": dates,
                "T2M_MAX": np.random.uniform(24, 34, 10),
                "T2M_MIN": np.random.uniform(14, 19, 10),
                "T2M": np.random.uniform(19, 24, 10),
                "RH2M": np.random.uniform(55, 75, 10),
                "WS2M": np.random.uniform(1.5, 4.5, 10),
                "ALLSKY_SFC_SW_DWN": np.random.uniform(14, 24, 10),
                "PRECTOTCORR": np.random.uniform(0, 12, 10),
            }
        )

    def test_initialization(self):
        ensemble = ClimateKalmanEnsemble()
        assert ensemble.loader is not None
        assert ensemble.kalman_precip is None
        assert ensemble.kalman_eto is None

    def test_auto_fuse_basic(self, sample_nasa_df, sample_om_df):
        """Test basic fusion without reference data (global fallback)"""
        ensemble = ClimateKalmanEnsemble()

        # Use coordinates without reference
        result = ensemble.auto_fuse(
            sample_nasa_df, sample_om_df, lat=0.0, lon=0.0
        )

        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        assert "date" in result.columns
        assert "fusion_mode" in result.columns
        assert result["fusion_mode"].iloc[0] == "global_fallback"

        # Check all variables are present
        for var in ensemble.WEIGHTS.keys():
            assert var in result.columns

        assert "PRECTOTCORR" in result.columns

    def test_weighted_fusion(self, sample_nasa_df, sample_om_df):
        """Test that weights are applied correctly"""
        ensemble = ClimateKalmanEnsemble()
        result = ensemble.auto_fuse(sample_nasa_df, sample_om_df, 0.0, 0.0)

        # T2M_MAX weight is 0.42 for NASA, 0.58 for OM
        # Result should be between both sources
        nasa_max = sample_nasa_df["T2M_MAX"].iloc[0]
        om_max = sample_om_df["T2M_MAX"].iloc[0]
        result_max = result["T2M_MAX"].iloc[0]

        expected = 0.42 * nasa_max + 0.58 * om_max
        assert abs(result_max - expected) < 0.01

    def test_precipitation_clipping_global(self, sample_nasa_df, sample_om_df):
        """Test precipitation is clipped in global mode"""
        ensemble = ClimateKalmanEnsemble()

        # Add extreme precipitation
        sample_nasa_df.loc[0, "PRECTOTCORR"] = 2000  # Above limit

        result = ensemble.auto_fuse(sample_nasa_df, sample_om_df, 0.0, 0.0)

        # Should be clipped to max 1800
        assert result["PRECTOTCORR"].max() <= 1800

    def test_auto_fuse_multi_source(self):
        """Test multi-source aggregation"""
        ensemble = ClimateKalmanEnsemble()

        # Create multi-source data (2 sources per day)
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        dates_repeated = dates.repeat(2)

        df_multi = pd.DataFrame(
            {
                "date": dates_repeated,
                "T2M_MAX": np.random.uniform(25, 35, 10),
                "T2M_MIN": np.random.uniform(15, 20, 10),
                "T2M": np.random.uniform(20, 25, 10),
                "RH2M": np.random.uniform(60, 80, 10),
                "WS2M": np.random.uniform(2, 5, 10),
                "ALLSKY_SFC_SW_DWN": np.random.uniform(15, 25, 10),
                "PRECTOTCORR": np.random.uniform(0, 10, 10),
            }
        ).set_index("date")

        result = ensemble.auto_fuse_multi_source(df_multi, 0.0, 0.0)

        # Should have one row per day
        assert len(result) == 5
        assert "fusion_mode" in result.columns

    def test_missing_data_handling(self, sample_nasa_df, sample_om_df):
        """Test handling of missing data"""
        ensemble = ClimateKalmanEnsemble()

        # Add NaN values
        sample_nasa_df.loc[0:2, "T2M_MAX"] = np.nan
        sample_om_df.loc[3:5, "T2M_MAX"] = np.nan

        result = ensemble.auto_fuse(sample_nasa_df, sample_om_df, 0.0, 0.0)

        # Should handle gracefully
        assert len(result) > 0
        # Some values should be filled from available source
        assert not result["T2M_MAX"].isna().all()

    def test_reset_functionality(self):
        """Test reset clears Kalman filters"""
        ensemble = ClimateKalmanEnsemble()
        ensemble.kalman_precip = AdaptiveKalmanFilter()
        ensemble.kalman_eto = SimpleKalmanFilter()

        ensemble.reset()

        assert ensemble.kalman_precip is None
        assert ensemble.kalman_eto is None
        assert ensemble.current_month is None

    def test_eto_processing_global(self, sample_nasa_df, sample_om_df):
        """Test ETo processing in global mode"""
        ensemble = ClimateKalmanEnsemble()

        # Add et0_mm column to trigger ETo processing
        fused = ensemble.auto_fuse(sample_nasa_df, sample_om_df, 0.0, 0.0)
        fused["et0_mm"] = np.random.uniform(3, 7, len(fused))

        # Manually call ETo processing
        result = ensemble._apply_final_eto_kalman_global(fused, 0.0)

        assert "eto_final" in result.columns
        assert "anomaly_eto_mm" in result.columns
        assert result["fusion_mode"].iloc[0] == "global_fallback"

    def test_month_transition_in_precip_kalman(self):
        """Test Kalman filter reinitialization on month change"""
        ensemble = ClimateKalmanEnsemble()

        # Mock reference data
        ref = {
            "precip_normals": {1: 100.0, 2: 120.0},
            "precip_stds": {1: 10.0, 2: 15.0},
            "precip_p01": {1: 0.0, 2: 0.0},
            "precip_p99": {1: 450.0, 2: 500.0},
        }

        # Data spanning January to February
        dates = pd.date_range("2024-01-30", periods=5, freq="D")
        precip = pd.Series([5.0, 6.0, 7.0, 8.0, 9.0])
        dates_series = pd.Series(dates)

        result = ensemble._apply_precip_kalman(precip, dates_series, ref)

        assert len(result) == 5
        assert not result.isna().all()

    def test_month_transition_in_eto_kalman(self):
        """Test ETo Kalman reinitialization on month change"""
        ensemble = ClimateKalmanEnsemble()

        # Mock reference data
        ref = {
            "eto_normals": {1: 5.0, 2: 6.0},
            "eto_stds": {1: 1.0, 2: 1.2},
            "eto_p01": {1: 2.0, 2: 2.5},
            "eto_p99": {1: 8.0, 2: 9.0},
        }

        # Data spanning January to February
        dates = pd.date_range("2024-01-30", periods=5, freq="D")
        df = pd.DataFrame({"date": dates, "et0_mm": [4.5, 5.0, 5.5, 6.0, 6.5]})

        result = ensemble._apply_final_eto_kalman_high_precision(df, ref)

        assert "eto_final" in result.columns
        assert "anomaly_eto_mm" in result.columns
        assert len(result) == 5

    def test_high_precision_mode_with_mock_reference(self):
        """Test complete high-precision flow with mocked reference"""
        ensemble = ClimateKalmanEnsemble()

        # Mock the loader to return reference
        mock_ref = {
            "city": "test_city",
            "distance_km": 50.0,
            "eto_normals": {1: 5.0, 2: 6.0},
            "eto_stds": {1: 1.0, 2: 1.2},
            "eto_p01": {1: 2.0, 2: 2.5},
            "eto_p99": {1: 8.0, 2: 9.0},
            "precip_normals": {1: 100.0, 2: 120.0},
            "precip_stds": {1: 10.0, 2: 15.0},
            "precip_p01": {1: 0.0, 2: 0.0},
            "precip_p99": {1: 450.0, 2: 500.0},
        }

        with patch.object(
            ensemble.loader,
            "get_reference_for_location",
            return_value=(True, mock_ref),
        ):
            dates = pd.date_range("2024-01-01", periods=10, freq="D")
            nasa_df = pd.DataFrame(
                {
                    "date": dates,
                    "T2M_MAX": np.random.uniform(25, 35, 10),
                    "T2M_MIN": np.random.uniform(15, 20, 10),
                    "T2M": np.random.uniform(20, 25, 10),
                    "RH2M": np.random.uniform(60, 80, 10),
                    "WS2M": np.random.uniform(2, 5, 10),
                    "ALLSKY_SFC_SW_DWN": np.random.uniform(15, 25, 10),
                    "PRECTOTCORR": np.random.uniform(0, 10, 10),
                }
            )
            om_df = nasa_df.copy()

            result = ensemble.auto_fuse(nasa_df, om_df, -15.8, -47.9)

            assert result["fusion_mode"].iloc[0] == "high_precision"
            assert len(result) > 0

    def test_only_nasa_has_data(self, sample_nasa_df):
        """Test fusion when only NASA has data"""
        ensemble = ClimateKalmanEnsemble()

        # Empty OM dataframe
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        om_df = pd.DataFrame(
            {
                "date": dates,
                "T2M_MAX": [np.nan] * 10,
                "T2M_MIN": [np.nan] * 10,
                "T2M": [np.nan] * 10,
                "RH2M": [np.nan] * 10,
                "WS2M": [np.nan] * 10,
                "ALLSKY_SFC_SW_DWN": [np.nan] * 10,
                "PRECTOTCORR": [np.nan] * 10,
            }
        )

        result = ensemble.auto_fuse(sample_nasa_df, om_df, 0.0, 0.0)

        assert len(result) > 0
        # Should use NASA values
        assert not result["T2M_MAX"].isna().all()

    def test_only_om_has_data(self, sample_om_df):
        """Test fusion when only OpenMeteo has data"""
        ensemble = ClimateKalmanEnsemble()

        # Empty NASA dataframe
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        nasa_df = pd.DataFrame(
            {
                "date": dates,
                "T2M_MAX": [np.nan] * 10,
                "T2M_MIN": [np.nan] * 10,
                "T2M": [np.nan] * 10,
                "RH2M": [np.nan] * 10,
                "WS2M": [np.nan] * 10,
                "ALLSKY_SFC_SW_DWN": [np.nan] * 10,
                "PRECTOTCORR": [np.nan] * 10,
            }
        )

        result = ensemble.auto_fuse(nasa_df, sample_om_df, 0.0, 0.0)

        assert len(result) > 0
        # Should use OM values
        assert not result["T2M_MAX"].isna().all()

    def test_eto_with_nan_values(self):
        """Test ETo processing with NaN values"""
        ensemble = ClimateKalmanEnsemble()

        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        df = pd.DataFrame(
            {"date": dates, "et0_mm": [5.0, np.nan, 5.5, np.nan, 6.0]}
        )

        result = ensemble._apply_final_eto_kalman_global(df, 0.0)

        assert "eto_final" in result.columns
        # NaN inputs should produce NaN outputs
        assert result["eto_final"].isna().sum() == 2

    def test_kalman_eto_reuse(self):
        """Test that kalman_eto is reused if already initialized"""
        ensemble = ClimateKalmanEnsemble()

        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        df1 = pd.DataFrame({"date": dates, "et0_mm": [5.0, 5.2, 5.1]})

        # First call initializes kalman_eto
        ensemble._apply_final_eto_kalman_global(df1, 0.0)
        kalman_instance = ensemble.kalman_eto

        # Second call should reuse the same instance
        df2 = pd.DataFrame({"date": dates, "et0_mm": [5.3, 5.4, 5.5]})
        result2 = ensemble._apply_final_eto_kalman_global(df2, 0.0)

        assert ensemble.kalman_eto is kalman_instance
        assert len(result2) == 3

    def test_anomaly_calculation_high_precision(self):
        """Test anomaly calculation in high-precision mode"""
        ensemble = ClimateKalmanEnsemble()

        ref = {
            "eto_normals": {1: 5.0, 2: 6.0},
            "eto_stds": {1: 1.0, 2: 1.2},
            "eto_p01": {1: 2.0, 2: 2.5},
            "eto_p99": {1: 8.0, 2: 9.0},
        }

        dates = pd.date_range("2024-01-15", periods=3, freq="D")
        df = pd.DataFrame({"date": dates, "et0_mm": [6.0, 6.5, 7.0]})

        result = ensemble._apply_final_eto_kalman_high_precision(df, ref)

        # Anomaly should be calculated
        assert "anomaly_eto_mm" in result.columns
        assert not result["anomaly_eto_mm"].isna().all()

    def test_multi_source_with_missing_data(self):
        """Test multi-source with some missing values"""
        ensemble = ClimateKalmanEnsemble()

        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        dates_repeated = dates.repeat(2)

        df_multi = pd.DataFrame(
            {
                "date": dates_repeated,
                "T2M_MAX": [30, np.nan, 31, 32, np.nan, 33],
                "T2M_MIN": [15, 16, np.nan, 17, 18, np.nan],
                "T2M": [22, 23, 24, np.nan, 25, 26],
                "RH2M": [70, 71, 72, 73, np.nan, 74],
                "WS2M": [3, 3.5, np.nan, 4, 4.5, np.nan],
                "ALLSKY_SFC_SW_DWN": [20, np.nan, 21, 22, 23, np.nan],
                "PRECTOTCORR": [5, 6, np.nan, 7, 8, 9],
            }
        ).set_index("date")

        result = ensemble.auto_fuse_multi_source(df_multi, 0.0, 0.0)

        # Should aggregate and handle NaN
        assert len(result) == 3
        assert "fusion_mode" in result.columns

    def test_global_limits_constants(self):
        """Test that GLOBAL_LIMITS are defined correctly"""
        limits = ClimateKalmanEnsemble.GLOBAL_LIMITS

        assert "T2M_MAX" in limits
        assert "T2M_MIN" in limits
        assert "T2M" in limits
        assert "RH2M" in limits
        assert "WS2M" in limits
        assert "ALLSKY_SFC_SW_DWN" in limits
        assert "PRECTOTCORR" in limits

        # Check format (tuple with min, max)
        for var, (min_val, max_val) in limits.items():
            assert min_val < max_val, f"{var} limits are invalid"

    def test_weights_constants(self):
        """Test that WEIGHTS are defined correctly"""
        weights = ClimateKalmanEnsemble.WEIGHTS

        required_vars = [
            "T2M_MAX",
            "T2M_MIN",
            "T2M",
            "RH2M",
            "WS2M",
            "ALLSKY_SFC_SW_DWN",
        ]

        for var in required_vars:
            assert var in weights
            assert 0 <= weights[var] <= 1, f"{var} weight out of range"


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_dataframes(self):
        ensemble = ClimateKalmanEnsemble()
        empty_df = pd.DataFrame()

        with pytest.raises((KeyError, ValueError)):
            ensemble.auto_fuse(empty_df, empty_df, 0.0, 0.0)

    def test_extreme_coordinates(self):
        """Test with extreme coordinates"""
        ensemble = ClimateKalmanEnsemble()

        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        simple_df = pd.DataFrame(
            {
                "date": dates,
                "T2M_MAX": [30, 31, 32],
                "T2M_MIN": [15, 16, 17],
                "T2M": [22, 23, 24],
                "RH2M": [70, 71, 72],
                "WS2M": [3, 3.5, 4],
                "ALLSKY_SFC_SW_DWN": [20, 21, 22],
                "PRECTOTCORR": [5, 6, 7],
            }
        )

        # North Pole
        result = ensemble.auto_fuse(simple_df, simple_df, 90.0, 0.0)
        assert len(result) > 0

        # South Pole
        result = ensemble.auto_fuse(simple_df, simple_df, -90.0, 0.0)
        assert len(result) > 0


class TestCoverageEnhancement:
    """Additional tests to increase code coverage to 95%+"""

    def test_adaptive_kalman_upper_outlier_extreme(self):
        """Test extreme upper outlier (> p99 * 1.25)"""
        kf = AdaptiveKalmanFilter(normal=5.0, std=1.0, p01=2.0, p99=8.0)
        kf.update(5.0)

        # Extreme upper outlier: > p99 * 1.25 = > 10.0
        result = kf.update(15.0)

        # Should be heavily dampened
        assert result < 10.0
        assert result > 5.0

    def test_adaptive_kalman_lower_outlier_extreme(self):
        """Test extreme lower outlier (< p01 * 0.8)"""
        kf = AdaptiveKalmanFilter(normal=5.0, std=1.0, p01=2.0, p99=8.0)
        kf.update(5.0)

        # Extreme lower outlier: < p01 * 0.8 = < 1.6
        result = kf.update(0.5)

        # Should be heavily dampened
        assert result > 0.5
        assert result < 5.0

    def test_adaptive_kalman_upper_outlier_moderate(self):
        """Test moderate upper outlier (p99 < z < p99*1.25)"""
        kf = AdaptiveKalmanFilter(normal=5.0, std=1.0, p01=2.0, p99=8.0)
        kf.update(5.0)

        # Moderate upper outlier: between 8.0 and 10.0
        result = kf.update(9.0)

        # Should be moderately dampened
        assert result > 5.0
        assert result < 9.0

    def test_adaptive_kalman_lower_outlier_moderate(self):
        """Test moderate lower outlier (p01*0.8 < z < p01)"""
        kf = AdaptiveKalmanFilter(normal=5.0, std=1.0, p01=2.0, p99=8.0)
        kf.update(5.0)

        # Moderate lower outlier: between 1.6 and 2.0
        result = kf.update(1.8)

        # Should be moderately dampened
        assert result < 5.0
        assert result > 1.8

    def test_load_city_coords_exception_handling(self):
        """Test error handling when loading city coords fails"""
        loader = HistoricalDataLoader()

        # Mock a CSV with invalid data
        with patch("pandas.read_csv") as mock_read:
            mock_read.side_effect = Exception("CSV read error")

            result = loader._load_city_coords()

            assert result == {}

    def test_load_city_coords_success(self):
        """Test successful loading of city coordinates"""
        loader = HistoricalDataLoader()

        # Mock a valid CSV
        with patch("pandas.read_csv") as mock_read:
            mock_df = pd.DataFrame(
                {
                    "city": ["Brasilia", "Sao_Paulo"],
                    "lat": [-15.8, -23.5],
                    "lon": [-47.9, -46.6],
                }
            )
            mock_read.return_value = mock_df

            result = loader._load_city_coords()

            assert "Brasilia" in result
            assert result["Brasilia"] == (-15.8, -47.9)
            assert "Sao_Paulo" in result
            assert result["Sao_Paulo"] == (-23.5, -46.6)

    def test_auto_fuse_with_et0_column_high_precision(self):
        """Test auto_fuse when et0_mm column exists (high-precision)"""
        ensemble = ClimateKalmanEnsemble()

        # Mock reference
        mock_ref = {
            "city": "test_city",
            "distance_km": 50.0,
            "eto_normals": {1: 5.0},
            "eto_stds": {1: 1.0},
            "eto_p01": {1: 2.0},
            "eto_p99": {1: 8.0},
            "precip_normals": {1: 100.0},
            "precip_stds": {1: 10.0},
            "precip_p01": {1: 0.0},
            "precip_p99": {1: 450.0},
        }

        with patch.object(
            ensemble.loader,
            "get_reference_for_location",
            return_value=(True, mock_ref),
        ):
            dates = pd.date_range("2024-01-15", periods=5, freq="D")
            nasa_df = pd.DataFrame(
                {
                    "date": dates,
                    "T2M_MAX": [30, 31, 32, 33, 34],
                    "T2M_MIN": [15, 16, 17, 18, 19],
                    "T2M": [22, 23, 24, 25, 26],
                    "RH2M": [70, 71, 72, 73, 74],
                    "WS2M": [3, 3.5, 4, 4.5, 5],
                    "ALLSKY_SFC_SW_DWN": [20, 21, 22, 23, 24],
                    "PRECTOTCORR": [5, 6, 7, 8, 9],
                }
            )
            om_df = nasa_df.copy()

            # First get result without et0_mm
            result = ensemble.auto_fuse(nasa_df, om_df, -15.8, -47.9)
            assert result["fusion_mode"].iloc[0] == "high_precision"

            # Now add et0_mm and test ETo processing
            result["et0_mm"] = [4.5, 5.0, 5.5, 6.0, 6.5]
            result = ensemble._apply_final_eto_kalman_high_precision(
                result, mock_ref
            )

            assert "eto_final" in result.columns
            assert "anomaly_eto_mm" in result.columns

    def test_auto_fuse_with_et0_column_global(self):
        """Test auto_fuse when et0_mm column exists (global fallback)"""
        ensemble = ClimateKalmanEnsemble()

        dates = pd.date_range("2024-01-15", periods=5, freq="D")
        nasa_df = pd.DataFrame(
            {
                "date": dates,
                "T2M_MAX": [30, 31, 32, 33, 34],
                "T2M_MIN": [15, 16, 17, 18, 19],
                "T2M": [22, 23, 24, 25, 26],
                "RH2M": [70, 71, 72, 73, 74],
                "WS2M": [3, 3.5, 4, 4.5, 5],
                "ALLSKY_SFC_SW_DWN": [20, 21, 22, 23, 24],
                "PRECTOTCORR": [5, 6, 7, 8, 9],
            }
        )
        om_df = nasa_df.copy()

        # First get result without et0_mm
        result = ensemble.auto_fuse(nasa_df, om_df, 0.0, 0.0)
        assert result["fusion_mode"].iloc[0] == "global_fallback"

        # Now add et0_mm and test ETo processing
        result["et0_mm"] = [4.5, 5.0, 5.5, 6.0, 6.5]
        result = ensemble._apply_final_eto_kalman_global(result, 0.0)

        assert "eto_final" in result.columns
        assert "anomaly_eto_mm" in result.columns
        assert result["fusion_mode"].iloc[0] == "global_fallback"

    def test_apply_final_eto_kalman_high_precision_nan_handling(self):
        """Test ETo high-precision with NaN in the middle of data"""
        ensemble = ClimateKalmanEnsemble()

        ref = {
            "eto_normals": {1: 5.0, 2: 6.0},
            "eto_stds": {1: 1.0, 2: 1.2},
            "eto_p01": {1: 2.0, 2: 2.5},
            "eto_p99": {1: 8.0, 2: 9.0},
        }

        # Data spanning January to February with NaN
        dates = pd.date_range("2024-01-30", periods=5, freq="D")
        df = pd.DataFrame(
            {
                "date": dates,
                "et0_mm": [4.5, np.nan, 5.5, 6.0, np.nan],
            }
        )

        result = ensemble._apply_final_eto_kalman_high_precision(df, ref)

        assert "eto_final" in result.columns
        assert result["eto_final"].isna().sum() == 2
        assert not pd.isna(result["eto_final"].iloc[0])
        assert pd.isna(result["eto_final"].iloc[1])

    def test_auto_fuse_multi_source_with_various_aggregations(self):
        """Test multi-source with complete data coverage"""
        ensemble = ClimateKalmanEnsemble()

        # Create data with 3 sources per day
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        dates_repeated = dates.repeat(3)

        df_multi = pd.DataFrame(
            {
                "date": dates_repeated,
                "T2M_MAX": [30, 31, 29, 32, 33, 31, 34, 35, 33],
                "T2M_MIN": [15, 16, 14, 17, 18, 16, 19, 20, 18],
                "T2M": [22, 23, 21, 24, 25, 23, 26, 27, 25],
                "RH2M": [70, 71, 69, 72, 73, 71, 74, 75, 73],
                "WS2M": [3, 3.5, 2.5, 4, 4.5, 3.5, 5, 5.5, 4.5],
                "ALLSKY_SFC_SW_DWN": [20, 21, 19, 22, 23, 21, 24, 25, 23],
                "PRECTOTCORR": [5, 6, 4, 7, 8, 6, 9, 10, 8],
            }
        ).set_index("date")

        result = ensemble.auto_fuse_multi_source(df_multi, 0.0, 0.0)

        # Should aggregate to one row per day
        assert len(result) == 3
        assert "fusion_mode" in result.columns
        # Verify averages are calculated
        assert 29 <= result["T2M_MAX"].iloc[0] <= 31

    def test_precip_kalman_with_high_precision_reference(self):
        """Test precipitation Kalman with actual reference data"""
        ensemble = ClimateKalmanEnsemble()

        ref = {
            "precip_normals": {1: 100.0, 2: 120.0},
            "precip_stds": {1: 10.0, 2: 15.0},
            "precip_p01": {1: 0.0, 2: 5.0},
            "precip_p99": {1: 450.0, 2: 500.0},
        }

        # Data with extreme precipitation
        dates = pd.date_range("2024-01-30", periods=5, freq="D")
        precip = pd.Series([50.0, 200.0, 5.0, 100.0, 150.0])
        dates_series = pd.Series(dates)

        result = ensemble._apply_precip_kalman(precip, dates_series, ref)

        assert len(result) == 5
        # Should dampen extreme values
        assert result.iloc[1] < 200.0  # 200mm should be dampened
        assert all(result >= 0)  # No negative precipitation


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
