"""
VALIDAÇÃO OFICIAL ETo EVAonline

- Métricas padrão internacional (R², NSE, KGE, MAE, RMSE, PBIAS, slope)
- Gráficos de dispersão (scatter plots) com métricas anotadas
- Validação do algoritmo de cálculo de ETo do EVAonline com:
  - Dados oficiais de ETo do Open-Meteo; e
  - Dados Brazilian Daily  Weather  Gridded  Data (BR-DWGD) de Xavier et al. (2022).

Versão 1.0.0
Autor: Ângela S. M. Cunha Soares| 2025
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from loguru import logger
import matplotlib.pyplot as plt

# Configuração do logger
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | {message}",
)


# =============================================================================
# MÉTRICAS
# =============================================================================
def calculate_metrics(
    obs: np.ndarray, sim: np.ndarray, site: str = ""
) -> dict:
    mask = ~(np.isnan(obs) | np.isnan(sim))
    obs, sim = obs[mask], sim[mask]
    n = len(obs)

    if n < 10:
        return {
            "Site": site,
            "n": n,
            **{
                k: np.nan for k in "R2 NSE KGE MAE RMSE ME PBIAS slope".split()
            },
        }

    mean_obs = obs.mean()
    error = sim - obs

    # R² e correlação
    R2 = np.corrcoef(obs, sim)[0, 1] ** 2

    # NSE
    NSE = 1 - np.sum(error**2) / np.sum((obs - mean_obs) ** 2)

    # KGE (Kling-Gupta 2012) – padrão em hidrologia
    r = np.corrcoef(obs, sim)[0, 1]
    alpha = np.std(sim) / np.std(obs)
    beta = np.mean(sim) / mean_obs
    KGE = 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)

    # Erros
    MAE = np.mean(np.abs(error))
    RMSE = np.sqrt(np.mean(error**2))
    ME = np.mean(error)
    PBIAS = 100 * np.sum(error) / np.sum(obs)

    # Regressão forçada na origem (FAO-56 recomenda)
    slope_forced = np.sum(sim * obs) / np.sum(obs**2)

    return {
        "Site": site,
        "n": n,
        "R2": R2,
        "NSE": NSE,
        "KGE": KGE,
        "MAE": MAE,
        "RMSE": RMSE,
        "ME": ME,
        "PBIAS": PBIAS,
        "slope": slope_forced,
    }


# =============================================================================
# GRÁFICO SCATTER
# =============================================================================
def create_scatter(obs, sim, metrics, title, output_path, color="steelblue"):
    plt.figure(figsize=(7.5, 7))
    plt.scatter(obs, sim, s=8, alpha=0.5, edgecolors="none", color=color)

    min_val, max_val = 0, max(obs.max(), sim.max()) * 1.05
    plt.plot([min_val, max_val], [min_val, max_val], "r--", lw=2, label="1:1")

    # Regressão forçada na origem
    slope = metrics["slope"]
    x_line = np.array([min_val, max_val])
    plt.plot(x_line, slope * x_line, "k-", lw=1.5, label=f"y = {slope:.3f}x")

    text = "\n".join(
        [
            f"n = {metrics['n']:,}",
            f"R² = {metrics['R2']:.3f}",
            f"NSE = {metrics['NSE']:.3f}",
            f"KGE = {metrics['KGE']:.3f}",
            f"RMSE = {metrics['RMSE']:.3f}",
            f"MAE = {metrics['MAE']:.3f}",
            f"PBIAS = {metrics['PBIAS']:+.2f}%",
            f"Slope = {metrics['slope']:.3f}",
        ]
    )
    plt.text(
        0.05,
        0.95,
        text,
        transform=plt.gca().transAxes,
        fontsize=11,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.9),
    )

    plt.xlabel(f"{title.split(' vs ')[0]} (mm day⁻¹)", fontsize=12)
    plt.ylabel(f"{title.split(' vs ')[1]} (mm day⁻¹)", fontsize=12)
    plt.title(title, fontsize=13, pad=15)
    plt.grid(True, alpha=0.3)
    plt.axis("equal")
    plt.xlim(min_val, max_val)
    plt.ylim(min_val, max_val)
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.success(f"Gráfico salvo: {output_path.name}")


# =============================================================================
# MAIN
# =============================================================================
def main():
    logger.info(
        "VALIDAÇÃO DO CÁLCULO DE ETo EVAonline - 17 cidades (1991-2020)"
    )

    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / "data"
    # Diretório com ETo calcudado pelo EVAonline
    calc_dir_evaonline = data_dir / "eto_openmeteo_only"

    # Diretório com dados de ETo oficiais do Open-Meteo Archive e Xavier et al.(2022)
    orig_dir = data_dir / "original_data"
    val_dir = data_dir / "results_eto_calc_validation"
    val_dir.mkdir(exist_ok=True)

    # 1. Carregar ETo calculado
    file = calc_dir_evaonline / "ALL_CITIES_ETo_OpenMeteo_ONLY_1991_2020.csv"
    if not file.exists():
        logger.error("Arquivo calculado não encontrado!")
        return
    df = pd.read_csv(file)
    df["date"] = df["date"].astype(str)

    # 2. Carregar referências
    def load_reference(folder, col_name):
        files = list((orig_dir / folder).glob("*.csv"))
        if not files:
            logger.warning(f"{folder} não encontrado")
            return None
        dfs = []
        for f in files:
            # Extrair nome da cidade corretamente
            filename = f.stem
            if "_OpenMeteo_ETo" in filename:
                city = filename.replace("_OpenMeteo_ETo", "")
            else:
                # Para Xavier: nome do arquivo é o nome da cidade
                city = filename

            tmp = pd.read_csv(f)
            tmp["city"] = city
            tmp["date"] = tmp["date"].astype(str)
            dfs.append(tmp[["date", "city", col_name]])
        return pd.concat(dfs, ignore_index=True)

    df_om = load_reference("eto_open_meteo", "eto_openmeteo")
    df_xv = load_reference("eto_xavier_csv", "eto_xavier")

    df = (
        df.merge(df_om, on=["date", "city"], how="left")
        if df_om is not None
        else df
    )
    df = (
        df.merge(df_xv, on=["date", "city"], how="left")
        if df_xv is not None
        else df
    )

    # 3. Validações
    comparisons = [
        ("eto_openmeteo", "Open-Meteo oficial", "steelblue"),
        ("eto_xavier", "BR-DWGD", "forestgreen"),
    ]

    for ref_col, ref_name, color in comparisons:
        if ref_col not in df.columns or df[ref_col].isna().all():
            logger.warning(f"{ref_name} não disponível")
            continue

        logger.info(f"\nVALIDAÇÃO: EVAonline vs {ref_name}")

        results = []
        for city in sorted(df["city"].unique()):
            df_city = df[df["city"] == city]
            obs = df_city[ref_col].values
            sim = df_city["eto_evaonline"].values
            met = calculate_metrics(obs, sim, city)
            results.append(met)

        results_df = pd.DataFrame(results)
        summary = (
            results_df[
                ["R2", "NSE", "KGE", "MAE", "RMSE", "ME", "PBIAS", "slope"]
            ]
            .agg(["mean", "std"])
            .round(4)
        )

        logger.info(f"Resumo {ref_name}:")
        for col in summary.columns:
            mean_val = summary.loc["mean", col]
            std_val = summary.loc["std", col]
            logger.info(f"  {col:5s}: {mean_val:.4f} ± {std_val:.4f}")

        # Salvar
        results_df.to_csv(
            val_dir / f"validation_vs_{ref_col.split('_')[1]}_by_city.csv",
            index=False,
        )
        summary.to_csv(val_dir / f"summary_vs_{ref_col.split('_')[1]}.csv")

        # Gráfico geral
        mask = ~(df[ref_col].isna() | df["eto_evaonline"].isna())
        overall = calculate_metrics(
            np.array(df[ref_col][mask]),
            np.array(df["eto_evaonline"][mask]),
            "Todas",
        )
        # Usar médias das métricas locais para o gráfico (consistente com CSV)
        metrics_for_plot = {
            "R2": summary.loc["mean", "R2"],
            "NSE": summary.loc["mean", "NSE"],
            "KGE": summary.loc["mean", "KGE"],
            "MAE": summary.loc["mean", "MAE"],
            "RMSE": summary.loc["mean", "RMSE"],
            "ME": summary.loc["mean", "ME"],
            "PBIAS": summary.loc["mean", "PBIAS"],
            "slope": summary.loc["mean", "slope"],
            "n": overall["n"],  # Manter n global
            "Site": "Média das cidades",
        }
        create_scatter(
            np.array(df[ref_col][mask]),
            np.array(df["eto_evaonline"][mask]),
            metrics_for_plot,
            f"EVAonline vs {ref_name}\n17 cidades · 1991-2020",
            val_dir / f"scatter_vs_{ref_col.split('_')[1]}.png",
            color,
        )

    logger.success("\nVALIDAÇÃO CONCLUÍDA! Resultados em:", str(val_dir))


if __name__ == "__main__":
    main()
