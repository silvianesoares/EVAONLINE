"""
Cálculo de ETo FAO-56 Penman-Monteith (Allen et al., 1998)
com dados brutos de qualquer fonte (NASA POWER, Open-Meteo, etc).

Uso:
    python 4_calculate_eto_data_from_openmeteo.py --source nasa
    python 4_calculate_eto_data_from_openmeteo.py --source openmeteo
"""

from pathlib import Path
import pandas as pd
import numpy as np
from loguru import logger
import sys

# Configuração do logger
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | {message}",
)


class EToFAO56:
    """FAO-56 Penman-Monteith"""

    Gsc = 0.0820  # Constante solar [MJ m⁻² min⁻¹]
    sigma = 4.903e-9  # Stefan-Boltzmann [MJ K⁻⁴ m⁻² day⁻¹]
    albedo = 0.23  # Albedo grama referência

    @staticmethod
    def fractional_day_of_year(date_str: str) -> float:
        """
        Retorna o dia do ano fracionário (1.0 a 366.0).
        Usado diretamente nas equações 21-25 da FAO-56.
        """
        from datetime import datetime

        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.timetuple().tm_yday + 0.0  # 0.0 = início do dia

    @staticmethod
    def atmospheric_pressure(elevation: float) -> float:
        """Eq. 7 - Pressão atmosférica (kPa)"""
        return 101.3 * ((293.0 - 0.0065 * elevation) / 293.0) ** 5.26

    @staticmethod
    def psychrometric_constant(elevation: float) -> float:
        """Eq. 8 - Y (kPa °C⁻¹)"""
        P = EToFAO56.atmospheric_pressure(elevation)
        return 0.000665 * P

    @staticmethod
    def wind_speed_2m(
        u_height: np.ndarray, height: float = 10.0
    ) -> np.ndarray:
        """
        Eq. 47 - Conversão logarítmica de vento para 2m

        Args:
            u_height: Velocidade do vento na altura de medição (m/s)
            height: Altura da medição (m) - default 10m para Open-Meteo
                    NASA POWER já vem em 2m, então height=2.0

        Returns:
            Velocidade do vento a 2m (m/s)
        """
        if height == 2.0:
            # NASA POWER já está em 2m
            return np.maximum(u_height, 0.5)

        # Conversão logarítmica FAO-56 Eq. 47
        u2 = u_height * (4.87 / np.log(67.8 * height - 5.42))
        return np.maximum(u2, 0.5)  # Limite físico mínimo

    @staticmethod
    def extraterrestrial_radiation(lat: float, doy: np.ndarray) -> np.ndarray:
        """
        Extraterrestrial radiation (Ra) — FAO-56 Eqs. 21-25 (Allen et al., 1998)

        Args:
            lat: Latitude em graus decimais (ex: -15.78)
            doy: Dia do ano fracionário (1.0 = 1º jan 00:00, 1.5 = 1º jan 12:00)

        Returns:
            Ra em MJ m⁻² day⁻¹
        """
        phi = np.radians(lat)  # Latitude em radianos
        doy = np.asarray(doy, dtype=float)

        # Eq. 23: Inverso da distância relativa Terra-Sol
        dr = 1.0 + 0.033 * np.cos(2.0 * np.pi * doy / 365.0)

        # Eq. 24: Declinação solar (radianos)
        delta = 0.409 * np.sin(2.0 * np.pi * doy / 365.0 - 1.39)

        # Ângulo horário do nascer/pôr do sol (ωs) — Eq. 25
        # Evita NaN com np.clip e trata casos polares
        cos_ws = -np.tan(phi) * np.tan(delta)
        cos_ws = np.clip(cos_ws, -1.0, 1.0)  # Garante domínio do arccos

        # Caso polar: sol nunca nasce (ws=0) ou nunca se põe (ws=π)
        ws = np.zeros_like(cos_ws)
        ws = np.where(cos_ws <= -1.0, np.pi, ws)  # Sol nunca se põe
        ws = np.where((cos_ws > -1.0) & (cos_ws < 1.0), np.arccos(cos_ws), ws)
        # cos_ws >= 1.0 → sol nunca nasce → ws = 0 (já é zero)

        # Eq. 21: Radiação extraterrestre
        Ra = (
            (24.0 * 60.0 / np.pi)
            * EToFAO56.Gsc
            * dr
            * (
                ws * np.sin(phi) * np.sin(delta)
                + np.cos(phi) * np.cos(delta) * np.sin(ws)
            )
        )

        return np.maximum(Ra, 0.0)  # Garante não negativo

    @staticmethod
    def clear_sky_radiation(Ra: np.ndarray, elevation: float) -> np.ndarray:
        """Eq. 37 - Rso (MJ m⁻² day⁻¹)"""
        return (0.75 + 2e-5 * elevation) * Ra

    @staticmethod
    def net_longwave_radiation(
        Rs: np.ndarray,
        Ra: np.ndarray,
        Tmax: np.ndarray,
        Tmin: np.ndarray,
        ea: np.ndarray,
        elevation: float,
    ) -> np.ndarray:
        """Eq. 39 - Rnl completa (com Rso e elevação)"""
        Tmax_K = Tmax + 273.15
        Tmin_K = Tmin + 273.15

        Rso = EToFAO56.clear_sky_radiation(Ra, elevation)

        # Fator de cobertura de nuvens
        ratio = np.divide(Rs, Rso, out=np.ones_like(Rs), where=Rso > 1e-6)
        fcd = np.clip(1.35 * ratio - 0.35, 0.3, 1.0)

        Rnl = (
            EToFAO56.sigma
            * ((Tmax_K**4 + Tmin_K**4) / 2)
            * (0.34 - 0.14 * np.sqrt(np.maximum(ea, 0.01)))
            * fcd
        )
        return Rnl

    @staticmethod
    def calculate_et0(
        df: pd.DataFrame,
        lat: float,
        elevation: float,
        wind_height: float = 10.0,
    ) -> pd.Series:
        """
        Cálculo vetorizado completo da ETo (mm day⁻¹)

        Args:
            df: DataFrame com dados meteorológicos
            lat: Latitude (graus decimais)
            elevation: Elevação (metros)
            wind_height: Altura da medição do vento (m)
                        - 10.0 para Open-Meteo (WS10M)
                        - 2.0 para NASA POWER (WS2M)

        Returns:
            Série com ETo calculado (mm/dia)
        """

        # 1. Variáveis de entrada
        Tmax = df["T2M_MAX"].to_numpy()
        Tmin = df["T2M_MIN"].to_numpy()
        Tmean = df["T2M"].to_numpy()
        RH = df["RH2M"].to_numpy()
        Rs = np.maximum(df["ALLSKY_SFC_SW_DWN"].to_numpy(), 0.1)

        # Detectar coluna de vento (WS10M ou WS2M)
        if "WS10M" in df.columns:
            u_wind = df["WS10M"].to_numpy()
        elif "WS2M" in df.columns:
            u_wind = df["WS2M"].to_numpy()
        else:
            raise ValueError("Coluna de vento não encontrada (WS10M ou WS2M)")

        # Dia do ano fracionário (J) — essencial para precisão astronômica
        dates = pd.to_datetime(df["date"])
        doy = dates.dt.dayofyear.astype(float).to_numpy()

        # 2. Variáveis derivadas
        # Pressão de saturação (es)
        es_Tmax = 0.6108 * np.exp(17.27 * Tmax / (Tmax + 237.3))
        es_Tmin = 0.6108 * np.exp(17.27 * Tmin / (Tmin + 237.3))
        es = 0.5 * (es_Tmax + es_Tmin)

        # Pressão real de vapor (ea)
        ea = (RH / 100.0) * es
        VPD = np.maximum(es - ea, 0.01)  # Déficit mínimo

        u2 = EToFAO56.wind_speed_2m(u_wind, height=wind_height)

        Ra = EToFAO56.extraterrestrial_radiation(lat, doy)

        Rn_s = (1 - EToFAO56.albedo) * Rs

        Rn_l = EToFAO56.net_longwave_radiation(
            Rs, Ra, Tmax, Tmin, ea, elevation
        )
        Rn = Rn_s - Rn_l
        G = np.zeros_like(Rn)  # Calor do solo ≈ 0 (período diário)

        # Declividade da curva de saturação
        delta = (
            4098
            * (0.6108 * np.exp(17.27 * Tmean / (Tmean + 237.3)))
            / ((Tmean + 237.3) ** 2)
        )

        # Constante psicrométrica com correção de altitude
        gamma = EToFAO56.psychrometric_constant(elevation)

        # 3. Penman-Monteith FAO-56 Eq. 6
        numerator = (
            0.408 * delta * (Rn - G)
            + gamma * (900 / (Tmean + 273.15)) * u2 * VPD
        )
        denominator = delta + gamma * (1 + 0.34 * u2)

        ETo = np.where(denominator > 1e-6, numerator / denominator, 0.0)
        ETo = np.maximum(ETo, 0.0)

        return pd.Series(
            np.round(ETo, 3), index=df.index, name="eto_evaonline"
        )


def calculate_eto_from_source(source: str = "openmeteo"):
    """
    Calcula ETo de qualquer fonte de dados RAW.

    Args:
        source: 'nasa' para NASA POWER ou 'openmeteo' para Open-Meteo
    """
    logger.info("=" * 90)
    logger.info(f"CÁLCULO DE ETo (FAO-56) - FONTE: {source.upper()}")
    logger.info("=" * 90)

    script_dir = Path(__file__).parent
    base_dir = script_dir.parent
    data_dir = base_dir / "data" / "original_data"

    # Configurar diretórios de entrada baseado na fonte
    if source.lower() == "nasa":
        input_dir = data_dir / "nasa_power_raw"
        file_pattern = "*_NASA_RAW.csv"
        wind_height = 2.0  # NASA POWER vento em 2m
        output_suffix = "NASA_ONLY"
    elif source.lower() == "openmeteo":
        input_dir = data_dir / "open_meteo_raw"
        file_pattern = "*_OpenMeteo_RAW.csv"
        wind_height = 10.0  # Open-Meteo vento em 10m
        output_suffix = "OpenMeteo_ONLY"
    else:
        logger.error(f"Fonte desconhecida: {source}")
        return

    output_dir = base_dir / "data" / f"eto_{source.lower()}_only"
    cities_csv = base_dir / "data" / "info_cities.csv"

    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        logger.error(f"Diretório não encontrado: {input_dir}")
        return

    logger.info(f"Lendo de: {input_dir}")
    logger.info(f"Salvando em: {output_dir}")

    # 1. Carregar metadados das cidades
    logger.info("Carregando info_cities.csv...")
    df_cities = pd.read_csv(cities_csv)
    logger.success(f"{len(df_cities)} cidades carregadas")

    city_info = df_cities.set_index("city")[["lat", "alt"]].to_dict(
        orient="index"
    )

    # 2. Processar arquivos
    csv_files = sorted(input_dir.glob(file_pattern))
    logger.info(f"{len(csv_files)} arquivos encontrados")

    all_results = []

    for file_path in csv_files:
        # Extrair nome da cidade
        # Formato: CityName_1991-01-01_2020-12-31_SOURCE_RAW.csv
        filename = file_path.stem
        parts = filename.split("_")
        city_name = None

        # Encontrar onde começa a data (YYYY-MM-DD)
        for i, part in enumerate(parts):
            if "-" in part and len(part) == 10:
                city_name = "_".join(parts[:i])
                break

        if city_name is None or city_name not in city_info:
            logger.warning(f"Cidade não identificada: {filename}")
            continue

        lat = city_info[city_name]["lat"]
        elevation = city_info[city_name]["alt"]

        logger.info(
            f"{city_name} (lat={lat:.2f}, elev={elevation}m, wind_h={wind_height}m)"
        )

        df = pd.read_csv(file_path, parse_dates=["date"])

        # Cálculo vetorizado com altura do vento correta
        df["eto_evaonline"] = EToFAO56.calculate_et0(
            df, lat, elevation, wind_height=wind_height
        )

        # Estatísticas
        valid = df["eto_evaonline"].notna().sum()
        mean_eto = df["eto_evaonline"].mean()
        logger.success(
            f"{valid:,}/{len(df):,} dias | "
            f"ETo médio = {mean_eto:.3f} mm/dia"
        )

        # Salvar individual
        output_file = output_dir / f"{city_name}_ETo_{output_suffix}.csv"

        # Colunas básicas + vento (detectar WS2M ou WS10M)
        wind_col = "WS2M" if "WS2M" in df.columns else "WS10M"
        cols = [
            "date",
            "T2M_MAX",
            "T2M_MIN",
            "T2M",
            "RH2M",
            wind_col,
            "ALLSKY_SFC_SW_DWN",
            "eto_evaonline",
        ]
        df[cols].to_csv(output_file, index=False, float_format="%.3f")

        all_results.append(
            df[cols].assign(city=city_name, lat=lat, elevation=elevation)
        )

    # 3. Consolidado
    if not all_results:
        logger.error("Nenhum dado processado!")
        return

    df_final = pd.concat(all_results, ignore_index=True)
    consolidated_path = (
        output_dir / f"ALL_CITIES_ETo_{output_suffix}_1991_2020.csv"
    )
    df_final.to_csv(consolidated_path, index=False, float_format="%.3f")

    logger.success(f"\nConsolidado salvo: {consolidated_path}")
    logger.success(
        f"ETo médio geral ({source.upper()}): "
        f"{df_final['eto_evaonline'].mean():.3f} mm/dia"
    )
    logger.success(
        f"PROCESSO CONCLUÍDO - {len(csv_files)} cidades processadas!"
    )


def main():
    """Main com suporte a argumentos de linha de comando
    # Para calcular ETo com NASA POWER
    python 4_calculate_eto_data_from_openmeteo_or_nasapower.py --source nasa

    # Para calcular ETo com Open-Meteo
    python 4_calculate_eto_data_from_openmeteo_or_nasapower.py --source openmeteo

    # Se não passar nada, usa Open-Meteo (default)
    python 4_calculate_eto_data_from_openmeteo_or_nasapower.py
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Calcula ETo FAO-56 de fontes RAW (NASA POWER ou Open-Meteo)"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="openmeteo",
        choices=["nasa", "openmeteo"],
        help="Fonte de dados: 'nasa' ou 'openmeteo' (default: openmeteo)",
    )

    args = parser.parse_args()

    calculate_eto_from_source(source=args.source)


if __name__ == "__main__":
    main()
