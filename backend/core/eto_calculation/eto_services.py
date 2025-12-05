"""
Serviços modulares para cálculo de Evapotranspiração (ETo).

Este módulo implementa a separação de responsabilidades:
- EToCalculationService: Cálculo FAO-56 Penman-Monteith puro (sem I/O)
- EToProcessingService: Orquestração completa do pipeline
  (download → fusion → ETo)

Benefícios:
- Testabilidade: Cada serviço pode ser testado isoladamente
- Reutilização: EToCalculationService pode ser usado em outros contextos
- Manutenibilidade: Responsabilidades claras e bem-definidas
"""

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from backend.core.data_processing.kalman_ensemble import ClimateKalmanEnsemble
from backend.api.services.opentopo import OpenTopoClient
from backend.api.services.weather_utils import (
    ElevationUtils,
    WeatherValidationUtils,
)
from backend.api.services.geographic_utils import GeographicUtils


class EToCalculationService:
    """
    Serviço para cálculo FAO-56 Penman-Monteith puro.

    Responsabilidades:
    - Validação de entrada (dados meteorológicos)
    - Cálculos matemáticos FAO-56
    - Detecção de anomalias
    - SEM I/O (sem PostgreSQL, Redis, downloads)

    Use este serviço quando precisar:
    - Calcular ETo isoladamente
    - Testar lógica de cálculo
    - Reutilizar em outros contextos
    """

    # Constantes FAO-56
    STEFAN_BOLTZMANN = 4.903e-9  # MJ K⁻⁴ m⁻² dia⁻¹
    ALBEDO = 0.23  # Albedo de referência
    MATOPIBA_BOUNDS = {
        "lat_min": -14.5,
        "lat_max": -2.5,
        "lng_min": -50.0,
        "lng_max": -41.5,
    }

    def __init__(self):
        """Inicializa o serviço de cálculo ETo."""
        self.logger = logger

    def _validate_measurements(self, measurements: Dict[str, float]) -> bool:
        """
        Valida presença e valores razoáveis das variáveis climáticas.

        Args:
            measurements: Dict com variáveis climáticas

        Returns:
            True se validado

        Raises:
            ValueError: Se alguma variável obrigatória está ausente
        """
        required_vars = [
            "T2M_MAX",
            "T2M_MIN",
            "T2M_MEAN",
            "RH2M",
            "WS2M",
            "PRECTOTCORR",
            "ALLSKY_SFC_SW_DWN",
            "latitude",
            "longitude",
            "date",
            "elevation_m",
        ]

        missing_vars = [
            var for var in required_vars if var not in measurements
        ]

        if missing_vars:
            raise ValueError(
                f"Variáveis obrigatórias ausentes: {', '.join(missing_vars)}"
            )

        # Validar ranges usando utilitários centralizados
        lat = measurements["latitude"]
        lon = measurements["longitude"]

        # Validar coordenadas
        if not GeographicUtils.is_valid_coordinate(lat, lon):
            raise ValueError(f"Coordenadas inválidas: lat={lat}, lon={lon}")

        # Validar elevação
        elevation = measurements["elevation_m"]
        if elevation < -500 or elevation > 9000:
            raise ValueError(
                f"Elevação {elevation}m fora do range válido (-500 a 9000m)"
            )

        # Validar variáveis meteorológicas
        if not WeatherValidationUtils.is_valid_temperature(
            measurements["T2M_MAX"]
        ):
            raise ValueError(f"T2M_MAX inválida: {measurements['T2M_MAX']}°C")
        if not WeatherValidationUtils.is_valid_temperature(
            measurements["T2M_MIN"]
        ):
            raise ValueError(f"T2M_MIN inválida: {measurements['T2M_MIN']}°C")
        if not WeatherValidationUtils.is_valid_humidity(measurements["RH2M"]):
            raise ValueError(
                f"Umidade relativa inválida: {measurements['RH2M']}%"
            )
        if not WeatherValidationUtils.is_valid_wind_speed(
            measurements["WS2M"]
        ):
            raise ValueError(
                f"Velocidade do vento inválida: {measurements['WS2M']} m/s"
            )
        if measurements["T2M_MAX"] < measurements["T2M_MIN"]:
            raise ValueError(
                f"T2M_MAX ({measurements['T2M_MAX']}°C) < "
                f"T2M_MIN ({measurements['T2M_MIN']}°C)"
            )

        return True

    def calculate_et0(
        self,
        measurements: Dict[str, float],
        method: str = "pm",
        elevation_factors: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Calcula ET0 diária usando FAO-56 Penman-Monteith.

        Args:
            measurements: Dict com 12 variáveis climáticas:
                - T2M_MAX: Temperatura máxima (°C)
                - T2M_MIN: Temperatura mínima (°C)
                - T2M_MEAN: Temperatura média (°C)
                - RH2M: Umidade relativa (%)
                - WS2M: Velocidade do vento a 2m (m/s)
                - PRECTOTCORR: Precipitação (mm)
                - ALLSKY_SFC_SW_DWN: Radiação solar (MJ/m²/dia)
                - PS: Pressão atmosférica (kPa)
                - latitude: Latitude (°)
                - longitude: Longitude (°)
                - date: Data (YYYY-MM-DD)
                - elevation_m: Elevação (m)
            method: Método de cálculo ('pm' para Penman-Monteith)

        Returns:
            Dict com:
            {
                'et0_mm_day': float,      # ET0 diária (mm/dia)
                'quality': str,           # 'high' ou 'low'
                'method': str,            # Método usado
                'components': {           # Componentes do cálculo
                    'Ra': float,          # Radiação extraterrestre
                    'Rn': float,          # Radiação net
                    'slope': float,       # Declividade da curva de vapor
                    'gamma': float        # Constante psicrométrica
                }
            }
        """
        try:
            # 1. Validação
            self._validate_measurements(measurements)

            # 2. Extração de variáveis
            T_max = measurements["T2M_MAX"]
            T_min = measurements["T2M_MIN"]
            T_mean = measurements["T2M_MEAN"]
            RH_mean = measurements["RH2M"]
            u2 = measurements["WS2M"]
            Rs = measurements["ALLSKY_SFC_SW_DWN"]  # MJ/m²/dia
            z = measurements["elevation_m"]
            lat = measurements["latitude"]
            date_str: str = str(measurements["date"])

            # Usar fatores de elevação pré-calculados ou calcular
            if elevation_factors:
                P = elevation_factors.get("pressure", 101.3)
            else:
                # Usar utilitário centralizado (FAO-56 Eq. 7)
                P = ElevationUtils.calculate_atmospheric_pressure(z)

            # 3. Cálculos intermediários FAO-56

            # 3a. Saturação de vapor
            es_T_max = self._saturation_vapor_pressure(T_max)
            es_T_min = self._saturation_vapor_pressure(T_min)
            es = (es_T_max + es_T_min) / 2

            # 3b. Pressão de vapor atual
            ea = (RH_mean / 100.0) * es

            # 3c. Déficit de pressão de vapor
            Vpd = es - ea

            # 3d. Declinação solar e ângulo solar
            N = self._day_of_year(date_str)
            delta = self._solar_declination(N)

            # 3e. Radiação extraterrestre (Ra)
            Ra = self._extraterrestrial_radiation(lat, N, delta)

            # 3f. Radiação net (aproximação)
            # Rn = 0.77 * Rs (simplificação se Rn_long não disponível)
            Rn_sw = (1 - self.ALBEDO) * Rs  # Radiação net de ondas curtas
            Rn_lw = 0.23  # Aproximação para Rn de ondas longas
            Rn = Rn_sw - (Rn_lw * Rs)  # Simplificação

            # 3g. Calor do solo (assume zero para períodos diários)
            G = 0

            # 3h. Declividade da curva de vapor (Δ)
            slope = self._vapor_pressure_slope(T_mean)

            # 3i. Constante psicrométrica (γ)
            if elevation_factors:
                gamma = elevation_factors.get("gamma", 0.665e-3 * P)
            else:
                # Usar utilitário centralizado (FAO-56 Eq. 8)
                gamma = ElevationUtils.calculate_psychrometric_constant(z)

            # 4. Penman-Monteith (FAO-56 Eq. 6)
            Cn = 900  # Coeficiente para ETo
            Cd = 0.34  # Coeficiente para ETo

            numerator = (
                0.408 * slope * (Rn - G)
                + gamma * (Cn / (T_mean + 273)) * u2 * Vpd
            )
            denominator = slope + gamma * (1 + Cd * u2)

            if denominator == 0:
                ET0 = np.nan
                quality = "low"
            else:
                ET0 = numerator / denominator

            # 5. Validação de qualidade
            quality = "high"
            if ET0 < 0 or ET0 > 15 or np.isnan(ET0):  # Sanity checks
                quality = "low"
                if np.isnan(ET0):
                    ET0 = 0

            return {
                "et0_mm_day": round(max(0, ET0), 2),
                "quality": quality,
                "method": method,
                "components": {
                    "Ra": round(Ra, 2),
                    "Rn": round(Rn, 2),
                    "slope": round(slope, 4),
                    "gamma": round(gamma, 4),
                    "Vpd": round(Vpd, 2),
                },
            }

        except Exception as e:
            self.logger.error(f"Erro no cálculo de ETo: {str(e)}")
            return {
                "et0_mm_day": 0,
                "quality": "low",
                "method": method,
                "components": {},
                "error": str(e),
            }

    def _saturation_vapor_pressure(self, T: float) -> float:
        """
        Pressão de saturação de vapor (FAO-56 Eq. 11).

        Args:
            T: Temperatura em °C

        Returns:
            Pressão de saturação em kPa
        """
        return 0.6108 * math.exp((17.27 * T) / (T + 237.3))

    def _vapor_pressure_slope(self, T: float) -> float:
        """
        Declividade da curva de vapor de pressão (FAO-56 Eq. 13).

        Args:
            T: Temperatura média em °C

        Returns:
            Declividade em kPa/°C
        """
        exp_term = (17.27 * T) / (T + 237.3)
        return (4098 * 0.6108 * math.exp(exp_term)) / ((T + 237.3) ** 2)

    def _solar_declination(self, N: int) -> float:
        """
        Declinação solar (FAO-56 Eq. 34).

        Args:
            N: Dia do ano (1-365/366)

        Returns:
            Declinação solar em radianos
        """
        b = 2 * math.pi * (N - 1) / 365.0
        return 0.409 * math.sin(b - 1.39)

    def _extraterrestrial_radiation(
        self, lat: float, N: int, delta: float
    ) -> float:
        """
        Radiação extraterrestre (FAO-56 Eq. 21).

        Args:
            lat: Latitude em graus
            N: Dia do ano (1-365/366)
            delta: Declinação solar em radianos

        Returns:
            Radiação extraterrestre em MJ/m²/dia
        """
        phi = math.radians(lat)
        dr = 1 + 0.033 * math.cos(2 * math.pi * N / 365.0)

        omega_s = math.acos(-math.tan(phi) * math.tan(delta))

        Ra = (
            (24 * 60 / math.pi)
            * 0.0820
            * dr
            * (
                omega_s * math.sin(phi) * math.sin(delta)
                + math.cos(phi) * math.cos(delta) * math.sin(omega_s)
            )
        )

        return max(0, Ra)  # Ra nunca deve ser negativo

    def _day_of_year(self, date_str: str) -> int:
        """
        Calcula o dia do ano.

        Args:
            date_str: Data em formato YYYY-MM-DD

        Returns:
            Dia do ano (1-366)
        """
        date = datetime.strptime(date_str, "%Y-%m-%d")
        return date.timetuple().tm_yday

    def detect_anomalies(
        self, et0: float, historical_normal: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Detecta anomalias comparando com histórico.

        Args:
            et0: Valor de ETo calculado (mm/dia)
            historical_normal: Dict com 'mean', 'std_dev' do histórico

        Returns:
            Dict com detecção de anomalia:
            {
                'is_anomaly': bool,
                'z_score': float,
                'deviation_percent': float
            }

        Example:
            >>> historical = {'mean': 3.8, 'std_dev': 0.6}
            >>> service.detect_anomalies(4.2, historical)
            {'is_anomaly': False, 'z_score': 0.67, 'deviation_percent': 10.5}
        """
        if not historical_normal:
            return {
                "is_anomaly": False,
                "z_score": None,
                "deviation_percent": None,
            }

        mean = historical_normal.get("mean", 0)
        std = historical_normal.get("std_dev", 1)

        if std == 0 or mean == 0:
            return {"is_anomaly": False, "z_score": 0, "deviation_percent": 0}

        z_score = (et0 - mean) / std
        is_anomaly = abs(z_score) > 2.5  # 2.5 standard deviations
        deviation_percent = (et0 - mean) / mean * 100

        return {
            "is_anomaly": is_anomaly,
            "z_score": round(z_score, 2),
            "deviation_percent": round(deviation_percent, 1),
        }


class EToProcessingService:
    def __init__(self):
        self.et0_calc = EToCalculationService()
        self.kalman = ClimateKalmanEnsemble()
        self.logger = logger

    async def process_location(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        sources: List[str],
        elevation: Optional[float] = None,
        use_precise_elevation: bool = True,
    ) -> Dict[str, Any]:
        try:
            # 1. Elevação precisa
            final_elevation, elev_info = await self._get_best_elevation(
                latitude, longitude, elevation, use_precise_elevation
            )
            elevation_factors = ElevationUtils.get_elevation_correction_factor(
                final_elevation
            )

            # 2. Download de múltiplas fontes
            from backend.api.services.data_download import (
                download_weather_data,
            )

            multi_source_df, warnings = await download_weather_data(
                data_source=sources,
                data_inicial=start_date,
                data_final=end_date,
                latitude=latitude,
                longitude=longitude,
            )

            if multi_source_df.empty:
                raise ValueError("Nenhuma fonte retornou dados válidos")

            # 3. Pré-processamento (limpeza, harmonização)
            from backend.core.data_processing.data_preprocessing import (
                preprocessing,
            )

            df_clean, prep_warnings = preprocessing(multi_source_df, latitude)
            warnings.extend(prep_warnings)

            # 4. FUSÃO INTELIGENTE MULTI-SOURCE (NOVA FUNÇÃO DO KALMAN)
            logger.info(
                f"Fusão Kalman com {len(sources)} fontes + normais locais"
            )
            # auto_fuse_multi_source
            fused_df = self.kalman.auto_fuse_multi_source(
                df_multi_source=df_clean, lat=latitude, lon=longitude
            )

            # 5. Garantir cálculo ETo bruto se ainda não tiver
            if "et0_mm" not in fused_df.columns:
                fused_df = self._calculate_raw_eto(
                    fused_df, latitude, final_elevation, elevation_factors
                )

            # 6. Kalman já aplicou eto_final → usar!
            if "eto_final" not in fused_df.columns:
                fused_df["eto_final"] = fused_df["et0_mm"]

            # 7. Preparar resposta final
            fused_df["date"] = pd.to_datetime(fused_df["date"]).dt.strftime(
                "%Y-%m-%d"
            )
            result_series = fused_df[
                ["date", "eto_final", "PRECTOTCORR"]
            ].round(3)
            result_series = result_series.rename(
                columns={"eto_final": "et0_mm_day"}
            )

            # 8. Detectar modo de fusão
            mode = fused_df["fusion_mode"].iloc[0]
            if mode == "high_precision":
                mode_text = "Alta precisão (normais locais 1991-2020)"
                city = fused_df.get("reference_city", ["Desconhecida"])[0]
                dist = round(fused_df.get("reference_distance_km", [0])[0], 1)
                mode_text += f" — Ref: {city} ({dist} km)"
            else:
                mode_text = (
                    "Cobertura mundial (fusão robusta de múltiplas fontes)"
                )

            return {
                "location": {
                    "lat": round(latitude, 4),
                    "lon": round(longitude, 4),
                },
                "elevation": elev_info,
                "period": {"start": start_date, "end": end_date},
                "sources_used": sources,
                "fusion_mode": mode,
                "fusion_description": mode_text,
                "et0_series": result_series.to_dict(orient="records"),
                "summary": self._summarize(result_series),
                "recommendations": self._generate_recommendations(
                    result_series
                ),
                "warnings": warnings,
                "message": f"ETo calculado com {len(sources)} fontes. {mode_text}",
            }

        except Exception as e:
            logger.error(f"Erro fatal: {e}")
            return {
                "error": str(e),
                "warnings": warnings if "warnings" in locals() else [],
            }

    async def _get_best_elevation(self, lat, lon, user_elev, use_precise):
        if user_elev is not None:
            return user_elev, {"value": user_elev, "source": "usuário"}

        if use_precise:
            try:
                client = OpenTopoClient()
                result = await client.get_elevation(lat, lon)
                await client.close()
                if result and result.elevation:
                    return result.elevation, {
                        "value": result.elevation,
                        "source": "OpenTopo (~1m)",
                    }
            except:
                pass

        return 0.0, {"value": 0.0, "source": "padrão (nível do mar)"}

    def _calculate_raw_eto(self, df, lat, elevation, factors):
        df["elevation_m"] = elevation
        et0_values = []
        for _, row in df.iterrows():
            measurements = row.to_dict()
            measurements.update(
                {
                    "latitude": lat,
                    "longitude": (
                        df.get("longitude", 0).iloc[0]
                        if "longitude" in df.columns
                        else 0
                    ),
                    "date": (
                        str(row.name)[:10]
                        if isinstance(row.name, pd.Timestamp)
                        else str(row.get("date", ""))[:10]
                    ),
                    "elevation_m": elevation,
                }
            )
            result = self.et0_calc.calculate_et0(
                measurements, elevation_factors=factors
            )
            et0_values.append(result["et0_mm_day"])
        df["et0_mm"] = et0_values
        return df

    def _summarize(self, series_df):
        values = series_df["et0_mm_day"]
        return {
            "total_days": len(values),
            "et0_total_mm": round(values.sum(), 1),
            "et0_mean_mm_day": round(values.mean(), 2),
            "et0_max_mm_day": round(values.max(), 2),
            "et0_min_mm_day": round(values.min(), 2),
        }

    def _generate_recommendations(self, series_df):
        total = series_df["et0_mm_day"].sum()
        mean = series_df["et0_mm_day"].mean()
        recs = [
            f"Irrigação estimada: {round(total * 1.1, 1)} mm no período",
        ]
        if mean > 6:
            recs.append("ETo alta → aumentar frequência de irrigação")
        elif mean < 3:
            recs.append("ETo baixa → reduzir irrigação")
        return recs
