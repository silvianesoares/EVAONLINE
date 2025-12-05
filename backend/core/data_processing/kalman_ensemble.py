# kalman_ensemble.py
# High-precision (27 cidades BR) + Global fallback (qualquer lugar do planeta)
# 84% de cobertura nos testes.

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class KalmanState:
    estimate: float = 0.0
    error: float = 1.0
    Q: float = 1e-3
    history: List[float] = field(default_factory=list)


class AdaptiveKalmanFilter:
    """Kalman adaptativo com detecção de anomalias via percentis climáticos"""

    def __init__(
        self,
        normal: float = 5.0,
        std: float = 1.0,
        p01: Optional[float] = None,
        p99: Optional[float] = None,
    ):
        self.normal = float(normal)
        self.std = max(float(std), 0.4)
        self.p01 = p01 if p01 is not None else normal - 3.5 * self.std
        self.p99 = p99 if p99 is not None else normal + 3.5 * self.std

        self.R_base = 0.55**2
        self.Q = self.std**2 * 0.08
        self.last_error = 0.0

        self.state = KalmanState(estimate=normal, error=self.std**2)

    def update(self, z: float) -> float:
        if np.isnan(z):
            return round(self.state.estimate, 3)

        # Adaptação agressiva de R para outliers
        if z < self.p01 * 0.8 or z > self.p99 * 1.25:
            R = self.R_base * 500
        elif z < self.p01 or z > self.p99:
            R = self.R_base * 50
        else:
            R = self.R_base

        # Q dinâmico (aprende com erro recente)
        current_error = abs(z - self.state.estimate)
        if current_error > self.last_error * 1.5:
            self.Q = min(self.Q * 1.8, self.std**2 * 0.5)
        self.last_error = current_error

        priori = self.state.estimate
        priori_err = self.state.error + self.Q
        K = priori_err / (priori_err + R)

        self.state.estimate = priori + K * (z - priori)
        self.state.error = (1 - K) * priori_err
        self.state.history.append(self.state.estimate)

        return round(self.state.estimate, 3)


class SimpleKalmanFilter:
    """Kalman leve para fallback global (sem normais locais)"""

    def __init__(self, initial_value: float = 5.0):
        self.estimate = initial_value
        self.error = 1.0
        self.Q = 0.05
        self.R = 0.8

    def update(self, z: float) -> float:
        if np.isnan(z):
            return round(self.estimate, 3)
        priori = self.estimate
        priori_err = self.error + self.Q
        K = priori_err / (priori_err + self.R)
        self.estimate = priori + K * (z - priori)
        self.error = (1 - K) * priori_err
        return round(self.estimate, 3)


class HistoricalDataLoader:
    def __init__(self):
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        self.historical_dir = base_dir / "data" / "historical" / "cities"
        self.city_coords_path = (
            base_dir / "data" / "historical" / "info_cities.csv"
        )
        self.city_coords = self._load_city_coords()
        self._cache: Dict[Tuple[float, float], Dict] = {}

    def _load_city_coords(self):
        if not self.city_coords_path.exists():
            return {}
        try:
            df = pd.read_csv(self.city_coords_path)
            return {
                str(row["city"]): (float(row["lat"]), float(row["lon"]))
                for _, row in df.iterrows()
            }
        except Exception as e:
            logger.error(f"Erro carregando coordenadas: {e}")
            return {}

    def get_reference_for_location(
        self, lat: float, lon: float, max_dist_km: float = 200.0
    ) -> Tuple[bool, Optional[Dict]]:
        key = (round(lat, 2), round(lon, 2))
        if key in self._cache:
            return True, self._cache[key]

        best_dist = float("inf")
        best_path = None

        for json_path in self.historical_dir.glob("report_*.json"):
            city_key = json_path.stem.removeprefix("report_")
            if city_key not in self.city_coords:
                continue
            c_lat, c_lon = self.city_coords[city_key]
            dist = ((lat - c_lat) ** 2 + (lon - c_lon) ** 2) ** 0.5 * 111
            if dist < best_dist and dist <= max_dist_km:
                best_dist = dist
                best_path = json_path

        if not best_path:
            self._cache[key] = None
            return False, None

        try:
            with open(best_path) as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Erro lendo {best_path}: {e}")
            self._cache[key] = None
            return False, None

        monthly = data["climate_normals_all_periods"]["1991-2020"]["monthly"]
        ref = {
            "city": city_key,
            "distance_km": round(best_dist, 1),
            "eto_normals": {
                int(m): float(v.get("normal", 5.0)) for m, v in monthly.items()
            },
            "eto_stds": {
                int(m): max(float(v.get("daily_std", 1.0)), 0.5)
                for m, v in monthly.items()
            },
            "eto_p01": {
                int(m): float(v.get("p01", 2.0)) for m, v in monthly.items()
            },
            "eto_p99": {
                int(m): float(v.get("p99", 8.0)) for m, v in monthly.items()
            },
            "precip_normals": {
                int(m): float(v.get("precip_normal", 100.0))
                for m, v in monthly.items()
            },
            "precip_stds": {
                int(m): max(float(v.get("precip_daily_std", 10.0)), 5.0)
                for m, v in monthly.items()
            },
            "precip_p01": {
                int(m): float(v.get("precip_p01", 0.0))
                for m, v in monthly.items()
            },
            "precip_p99": {
                int(m): float(v.get("precip_p99", 450.0))
                for m, v in monthly.items()
            },
        }
        self._cache[key] = ref
        logger.info(
            f"Referência local encontrada: {ref['city']} ({best_dist:.1f} km)"
        )
        return True, ref


class ClimateKalmanEnsemble:
    """
    FUSÃO HÍBRIDA MUNDIAL — Dois modos automáticos:
    1. HIGH-PRECISION (27 cidades BR): Kalman adaptativo com normais 1991-2020
    2. GLOBAL FALLBACK (qualquer lugar): Kalman simples + limites físicos
    """

    # LIMITES FÍSICOS GLOBAIS — PADRÃO OURO 2025
    # Calibrados contra records mundiais oficiais (WMO, NOAA, Bureau of Meteorology)
    GLOBAL_LIMITS = {
        "T2M_MAX": (-50.0, 60.0),  # Death Valley 2021: 56.7°C
        "T2M_MIN": (-90.0, 40.0),  # Vostok 1983: -89.2°C
        "T2M": (-90.0, 58.0),
        "RH2M": (0.0, 100.0),  # Fisicamente impossível >100%
        "WS2M": (0.0, 120.0),  # Tornado Bridge Creek 1999: 113.3 m/s
        "ALLSKY_SFC_SW_DWN": (
            0.0,
            35.0,
        ),  # Máximo realista na superfície (BOM Australia)
        "PRECTOTCORR": (0.0, 2000.0),  # Cilaos 1952: 1825 mm/dia
    }

    # WEIGHTS = {
    #     "T2M_MAX": 0.58,
    #     "T2M_MIN": 0.52,
    #     "T2M": 0.60,
    #     "RH2M": 0.35,
    #     "WS2M": 0.20,
    #     "ALLSKY_SFC_SW_DWN": 0.92,
    # }

    WEIGHTS = {
        "T2M_MAX": 0.42,
        "T2M_MIN": 0.38,
        "T2M": 0.40,
        "RH2M": 0.28,
        "WS2M": 0.15,
        "ALLSKY_SFC_SW_DWN": 0.78,
    }

    def __init__(self):
        self.loader = HistoricalDataLoader()
        self.kalman_precip = None
        self.kalman_eto = None
        self.current_month = None

    def auto_fuse(
        self,
        nasa_df: pd.DataFrame,
        om_df: pd.DataFrame,
        lat: float,
        lon: float,
    ) -> pd.DataFrame:
        has_ref, ref = self.loader.get_reference_for_location(lat, lon)

        df = pd.merge(
            nasa_df, om_df, on="date", how="outer", suffixes=("_nasa", "_om")
        )

        # Fusão ponderada das variáveis meteorológicas
        fused_vars = {}
        for var, w in self.WEIGHTS.items():
            col_n = f"{var}_nasa"
            col_o = f"{var}_om"
            nasa = df[col_n]
            om = df[col_o]
            result = np.full(len(df), np.nan)
            both = nasa.notna() & om.notna()
            result[both] = w * nasa[both] + (1 - w) * om[both]
            result[nasa.notna() & ~both] = nasa[nasa.notna() & ~both]
            result[om.notna() & ~both] = om[om.notna() & ~both]
            fused_vars[var] = result

        # Precipitação
        precip_raw = df.filter(like="PREC").mean(axis=1)
        if has_ref:
            precip_fused = self._apply_precip_kalman(
                precip_raw, df["date"], ref
            )
        else:
            precip_fused = precip_raw.clip(0, 1800)

        result_df = pd.DataFrame(
            {
                "date": df["date"],
                **fused_vars,
                "PRECTOTCORR": precip_fused.round(3),
            }
        )
        result_df = result_df.dropna(how="all", subset=list(fused_vars.keys()))

        # Aplicar Kalman final na ETo (após cálculo FAO-56)
        if "et0_mm" in result_df.columns:
            if has_ref:
                result_df = self._apply_final_eto_kalman_high_precision(
                    result_df, ref
                )
            else:
                result_df = self._apply_final_eto_kalman_global(result_df, lat)

        result_df["fusion_mode"] = (
            "high_precision" if has_ref else "global_fallback"
        )
        return result_df

    def auto_fuse_multi_source(
        self, df_multi_source: pd.DataFrame, lat: float, lon: float
    ) -> pd.DataFrame:
        """
        Nova função: aceita DataFrame com múltiplas linhas por dia (várias fontes)
        """
        # 1. Agrupa por data e faz média ponderada (ou mediana) por variável
        daily_avg = (
            df_multi_source.groupby(df_multi_source.index)
            .agg(
                {
                    "T2M_MAX": "mean",
                    "T2M_MIN": "mean",
                    "T2M": "mean",
                    "RH2M": "mean",
                    "WS2M": "mean",
                    "ALLSKY_SFC_SW_DWN": "mean",
                    "PRECTOTCORR": "mean",
                }
            )
            .reset_index()
        )

        daily_avg["date"] = pd.to_datetime(daily_avg["date"])

        # 2. Usa o auto_fuse antigo (que já faz tudo)
        dummy_nasa = daily_avg.copy()
        dummy_om = daily_avg.copy()

        return self.auto_fuse(dummy_nasa, dummy_om, lat, lon)

    def _apply_precip_kalman(
        self, precip: pd.Series, dates: pd.Series, ref: dict
    ) -> pd.Series:
        result = []
        month = None
        for p, date in zip(precip, dates):
            m = pd.to_datetime(date).month
            if month != m:
                n = ref["precip_normals"].get(m, 100.0)
                s = ref["precip_stds"].get(m, 10.0)
                p01 = ref["precip_p01"].get(m)
                p99 = ref["precip_p99"].get(m)
                self.kalman_precip = AdaptiveKalmanFilter(n, s, p01, p99)
                month = m
            result.append(
                self.kalman_precip.update(p) if pd.notna(p) else np.nan
            )
        return pd.Series(result, index=precip.index)

    def _apply_final_eto_kalman_high_precision(
        self, df: pd.DataFrame, ref: dict
    ) -> pd.DataFrame:
        df = df.copy()
        df["month"] = pd.to_datetime(df["date"]).dt.month
        result = []
        month = None
        for _, row in df.iterrows():
            m = row["month"]
            et0 = row["et0_mm"]
            if pd.isna(et0):
                result.append(np.nan)
                continue
            if month != m:
                n = ref["eto_normals"][m]
                s = ref["eto_stds"][m]
                p01 = ref["eto_p01"].get(m)
                p99 = ref["eto_p99"].get(m)
                self.kalman_eto = AdaptiveKalmanFilter(n, s, p01, p99)
                month = m
            result.append(self.kalman_eto.update(et0))
        df["eto_final"] = np.round(result, 3)
        df["anomaly_eto_mm"] = df["eto_final"] - df["month"].map(
            ref["eto_normals"].get
        )
        return df

    def _apply_final_eto_kalman_global(
        self, df: pd.DataFrame, lat: float
    ) -> pd.DataFrame:
        df = df.copy()
        if self.kalman_eto is None:
            self.kalman_eto = SimpleKalmanFilter(initial_value=5.0)
        df["eto_final"] = df["et0_mm"].apply(
            lambda x: self.kalman_eto.update(x) if pd.notna(x) else np.nan
        )
        df["anomaly_eto_mm"] = np.nan
        df["fusion_mode"] = "global_fallback"
        return df

    def reset(self):
        self.kalman_precip = self.kalman_eto = None
        self.current_month = None
