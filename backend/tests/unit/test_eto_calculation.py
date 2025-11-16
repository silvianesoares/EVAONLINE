"""
Testes unitários para eto_calculation.py
"""

import pandas as pd

from backend.core.eto_calculation.eto_calculation import calculate_eto


class TestCalculateEto:
    """Testes para função calculate_eto."""

    def test_calculate_eto_basic(self):
        """Testa cálculo ETo básico."""
        # Dados de teste simples com todas as variáveis obrigatórias
        weather_data = pd.DataFrame(
            {
                "T2M_MAX": [30.0],
                "T2M_MIN": [20.0],
                "T2M_MEAN": [25.0],  # Temperatura média obrigatória
                "RH2M": [60.0],
                "WS2M": [2.0],
                "ALLSKY_SFC_SW_DWN": [20.0],
                "PRECTOTCORR": [0.0],
            },
            index=pd.date_range("2023-01-01", periods=1),  # Índice de data
        )

        result_df, warnings = calculate_eto(weather_data, 100.0, -23.0)

        assert len(result_df) == 1
        assert "ETo" in result_df.columns
        assert result_df["ETo"].iloc[0] > 0
