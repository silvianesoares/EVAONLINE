"""
Testes unitários para Kalman Ensemble
- SimpleKalmanFilter
- AdaptiveKalmanFilter
- ClimateKalmanFusion
"""

import numpy as np
import pytest

from backend.core.data_processing.kalman_ensemble import (
    AdaptiveKalmanFilter,
    ClimateKalmanFusion,
    SimpleKalmanFilter,
)


class TestSimpleKalmanFilter:
    """Testes para SimpleKalmanFilter (sem histórico)"""

    def test_initialization(self):
        """Teste de inicialização"""
        kf = SimpleKalmanFilter(
            process_variance=1e-4, measurement_variance=0.1, initial_value=0.0
        )
        assert kf.state.posterior_estimate == 0.0
        assert kf.state.posterior_error_estimate == 1.0

    def test_single_update(self):
        """Teste de uma medição"""
        kf = SimpleKalmanFilter()

        measurement = 10.0
        result = kf.update(measurement)

        # Deve ser entre 0 e 10 (mas mais perto de 10)
        assert 0 < result <= 10
        assert len(kf.state.history) == 1

    def test_convergence(self):
        """Teste de convergência com medições consistentes"""
        kf = SimpleKalmanFilter(process_variance=1e-5)

        # Múltiplas medições do mesmo valor
        measurements = [5.0] * 20
        results = [kf.update(m) for m in measurements]

        # Deve convergir para ~5.0
        final_estimate = results[-1]
        assert 4.8 < final_estimate < 5.2

        # Erro deve diminuir
        assert kf.state.posterior_error_estimate < kf.state.posterior_estimate

    def test_handles_missing_values(self):
        """Teste com valores faltando (NaN)"""
        kf = SimpleKalmanFilter(initial_value=5.0)

        result = kf.update(float("nan"))

        # Deve manter a estimativa anterior
        assert result == 5.0
        # Adiciona ao histórico para consistência temporal
        assert len(kf.state.history) == 1

    def test_state_retrieval(self):
        """Teste de recuperação de estado"""
        kf = SimpleKalmanFilter()
        kf.update(10.0)

        state = kf.get_state()

        assert "estimate" in state
        assert "error_estimate" in state
        assert "history_length" in state
        assert state["history_length"] == 1


class TestAdaptiveKalmanFilter:
    """Testes para AdaptiveKalmanFilter (com histórico)"""

    def test_initialization_with_normals(self):
        """Teste de inicialização com normais históricos"""
        kf = AdaptiveKalmanFilter(
            monthly_normal=5.0, historical_std=1.5, station_confidence=0.9
        )

        assert kf.state.posterior_estimate == 5.0
        assert kf.state.posterior_error_estimate == 1.5

    def test_initialization_without_normals(self):
        """Teste com normais faltando"""
        kf = AdaptiveKalmanFilter()

        assert kf.state.posterior_estimate == 0.0
        assert kf.monthly_normal == 0.0

    def test_update_with_weight(self):
        """Teste com pesos diferentes"""
        kf1 = AdaptiveKalmanFilter(monthly_normal=5.0)
        kf2 = AdaptiveKalmanFilter(monthly_normal=5.0)

        measurement = 8.0
        result1 = kf1.update(measurement, weight=1.0)
        result2 = kf2.update(measurement, weight=0.5)

        # Peso menor → menos movimento
        assert abs(measurement - result2) > abs(measurement - result1)

    def test_confidence_impact(self):
        """Teste de impacto da confiança na estação"""
        kf_high_conf = AdaptiveKalmanFilter(
            monthly_normal=5.0, historical_std=1.0, station_confidence=0.95
        )
        kf_low_conf = AdaptiveKalmanFilter(
            monthly_normal=5.0, historical_std=1.0, station_confidence=0.5
        )

        measurement = 10.0
        result_high = kf_high_conf.update(measurement)
        result_low = kf_low_conf.update(measurement)

        # Alta confiança NA ESTAÇÃO = confia mais na MEDIÇÃO
        # Logo, se move MAIS em direção à medição (10.0)
        # Baixa confiança = confia menos na medição, fica mais próximo do normal
        assert abs(10.0 - result_high) < abs(10.0 - result_low)

    def test_confidence_interval(self):
        """Teste de intervalo de confiança 95%"""
        kf = AdaptiveKalmanFilter(monthly_normal=5.0, historical_std=2.0)
        kf.update(6.0)

        state = kf.get_state()

        assert "confidence_interval_95" in state
        lower, upper = state["confidence_interval_95"]
        assert lower < state["estimate"] < upper

    def test_anomaly_detection(self):
        """Teste de detecção de anomalia"""
        kf = AdaptiveKalmanFilter(monthly_normal=5.0)
        kf.update(5.0)  # Normal
        kf.update(5.5)  # Ligeiramente acima
        anomaly_result = kf.update(15.0)  # Anomalia

        # Filtro deve resistir à anomalia
        assert anomaly_result < 10  # Menos influência da anomalia


class TestClimateKalmanFusion:
    """Testes para ClimateKalmanFusion (orquestrador)"""

    def test_fuse_simple(self):
        """Teste de fusão simples"""
        fusion = ClimateKalmanFusion()

        measurements = {
            "temperature": 25.0,
            "humidity": 65.0,
            "precipitation": 10.0,
        }

        result = fusion.fuse_simple(measurements, station_confidence=0.8)

        assert result["temperature"] == measurements["temperature"]
        assert result["temperature_quality"] == "simple_kalman"
        assert fusion.fusion_strategy == "simple"

    def test_fuse_adaptive(self):
        """Teste de fusão adaptada"""
        fusion = ClimateKalmanFusion()

        measurements = {"temperature": 25.0, "precipitation": 50.0}

        normals = {"temperature": 22.0, "precipitation": 100.0}

        stds = {"temperature": 2.0, "precipitation": 30.0}

        result = fusion.fuse_adaptive(
            measurements, normals, stds, station_confidence=0.85
        )

        assert "temperature" in result
        assert "temperature_anomaly" in result
        assert result["temperature_quality"] == "adaptive_kalman"
        assert fusion.fusion_strategy == "adaptive"

    def test_fuse_multiple_stations_simple(self):
        """Teste de fusão de múltiplas estações (sem histórico)"""
        fusion = ClimateKalmanFusion()

        stations_data = [
            {"temperature": 24.0, "humidity": 60.0},
            {"temperature": 26.0, "humidity": 65.0},
            {"temperature": 25.5, "humidity": 62.0},
        ]

        result = fusion.fuse_multiple_stations(
            stations_data,
            distance_weights=[0.5, 0.3, 0.2],
            has_historical_data=False,
        )

        # Deve estar perto da média ponderada
        expected_temp = 24.0 * 0.5 + 26.0 * 0.3 + 25.5 * 0.2
        assert abs(result["temperature"] - expected_temp) < 1.0

    def test_fuse_multiple_stations_adaptive(self):
        """Teste de fusão de múltiplas estações (com histórico)"""
        fusion = ClimateKalmanFusion()

        stations_data = [
            {"temperature": 24.0},
            {"temperature": 26.0},
        ]

        normals = {"temperature": 25.0}
        stds = {"temperature": 1.5}

        result = fusion.fuse_multiple_stations(
            stations_data,
            distance_weights=[0.6, 0.4],
            has_historical_data=True,
            monthly_normals=normals,
            historical_stds=stds,
        )

        assert "temperature" in result

    def test_missing_data_handling(self):
        """Teste com dados faltando"""
        fusion = ClimateKalmanFusion()

        measurements = {
            "temperature": 25.0,
            "humidity": None,
            "precipitation": float("nan"),
        }

        result = fusion.fuse_simple(measurements)

        assert result["temperature"] is not None
        assert result["humidity_quality"] == "missing"
        assert result["precipitation_quality"] == "missing"

    def test_sequential_updates(self):
        """Teste de atualizações sequenciais (série temporal)"""
        fusion = ClimateKalmanFusion()

        # Série de medições
        measurements_series = [
            {"eto": 4.0},
            {"eto": 4.5},
            {"eto": 5.0},
            {"eto": 4.8},
            {"eto": 5.2},
        ]

        results = []
        for measurements in measurements_series:
            result = fusion.fuse_simple(measurements)
            results.append(result["eto"])

        # Deve suavizar a série
        assert len(results) == 5
        # Variância dos resultados deve ser menor
        results_std = np.std(results)
        measurements_std = np.std([m["eto"] for m in measurements_series])
        assert results_std < measurements_std

    def test_reset_filters(self):
        """Teste de reset de filtros"""
        fusion = ClimateKalmanFusion()

        fusion.fuse_simple({"temperature": 25.0})
        assert "temperature" in fusion.filters

        fusion.reset("temperature")
        assert "temperature" not in fusion.filters

        # Reset geral
        fusion.fuse_simple({"humidity": 65.0})
        fusion.reset()
        assert len(fusion.filters) == 0

    def test_get_all_states(self):
        """Teste de recuperação de todos os estados"""
        fusion = ClimateKalmanFusion()

        measurements = {"temperature": 25.0, "humidity": 65.0}

        fusion.fuse_simple(measurements)
        states = fusion.get_all_states()

        assert "temperature" in states
        assert "humidity" in states
        assert states["temperature"]["estimate"] == 25.0


# Testes de Integração
class TestKalmanIntegration:
    """Testes de integração entre componentes"""

    def test_adaptive_then_simple(self):
        """Teste: começar com adaptado, depois simples"""
        fusion = ClimateKalmanFusion()

        # Primeiro com histórico
        fusion.fuse_adaptive(
            {"temperature": 25.0}, {"temperature": 23.0}, {"temperature": 2.0}
        )

        # Depois sem histórico (mesmo filtro)
        result = fusion.fuse_simple({"temperature": 26.0})

        # Deve funcionar sem erro
        assert "temperature" in result

    def test_realistic_scenario(self):
        """Teste cenário realista: múltiplas estações + histórico"""
        fusion = ClimateKalmanFusion()

        # Dados de 3 estações diferentes
        station_data = [
            {"eto": 4.2, "precip": 15.0, "temp": 24.0},
            {"eto": 4.5, "precip": 18.0, "temp": 25.0},
            {"eto": 4.8, "precip": 12.0, "temp": 26.0},
        ]

        result = fusion.fuse_multiple_stations(
            stations_data=station_data,
            distance_weights=[0.5, 0.3, 0.2],
            has_historical_data=True,
            monthly_normals={"eto": 4.5, "precip": 100.0, "temp": 25.0},
            historical_stds={"eto": 0.5, "precip": 30.0, "temp": 2.0},
        )

        # Verificar saídas
        assert result["eto"] is not None
        assert result["precip"] is not None
        assert result["temp"] is not None

        # Valores devem estar razoáveis
        assert 3.5 < result["eto"] < 5.0
        assert 15 < result["precip"] < 20
        assert 24 < result["temp"] < 26


# Fixture para dados de teste
@pytest.fixture
def sample_climate_data():
    """Dados climáticos de amostra para testes"""
    return {
        "temperature_2m_mean": [20.0, 21.0, 22.0, 23.0, 24.0],
        "precipitation_sum": [5.0, 10.0, 8.0, 12.0, 6.0],
        "wind_speed_10m_mean": [3.5, 4.0, 3.8, 4.2, 3.9],
    }


@pytest.fixture
def sample_monthly_normals():
    """Normais mensais de amostra"""
    return {
        "temperature_2m_mean": 22.0,
        "temperature_2m_mean_daily_std": 2.0,
        "precipitation_sum": 100.0,
        "precipitation_sum_daily_std": 20.0,
        "wind_speed_10m_mean": 4.0,
        "wind_speed_10m_mean_daily_std": 0.5,
    }
