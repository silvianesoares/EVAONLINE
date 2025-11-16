"""
# Download histórico + email
Celery task para processamento de downloads históricos de dados climáticos.

Esta task processa requisições de dados históricos (>30 dias) de forma assíncrona,
enviando emails de confirmação e com os dados processados anexados.

Fluxo:
1. Email de confirmação inicial
2. Download de dados climáticos (download_weather_data)
3. Pré-processamento (preprocessing)
4. Cálculo de ETo (calculate_eto)
5. Geração de arquivo (CSV/Excel)
6. Email com anexo
7. Limpeza de arquivos temporários
"""

import time
from datetime import datetime

from celery import shared_task
from loguru import logger

from backend.api.middleware.prometheus_metrics import (
    CELERY_TASK_DURATION,
    CELERY_TASKS_TOTAL,
)


@shared_task(
    bind=True,
    max_retries=3,
    name="backend.infrastructure.celery.tasks.process_historical_download",
)
def process_historical_download(
    self,
    email: str,
    lat: float,
    lon: float,
    source: str,
    start_date: str,
    end_date: str,
    file_format: str = "csv",
):
    """
    Processa download histórico e envia email (síncrono).

    Esta task é executada de forma assíncrona pelo Celery worker,
    mas internamente usa código síncrono para compatibilidade.

    Fluxo:
    1. Envia email de confirmação inicial
    2. Baixa dados (download_weather_data)
    3. Processa dados (preprocessing)
    4. Calcula ETo
    5. Gera arquivo (CSV/Excel)
    6. Envia email com anexo
    7. Em caso de erro, envia email de notificação

    Args:
        self: Contexto Celery (bind=True)
        email: Email do usuário
        lat: Latitude (-90 a 90)
        lon: Longitude (-180 a 180)
        source: Fonte de dados ou "data fusion"
        start_date: Data inicial (YYYY-MM-DD)
        end_date: Data final (YYYY-MM-DD)
        file_format: Formato do arquivo ("csv" ou "excel")

    Returns:
        dict: Status e metadados do processamento

    Raises:
        ValueError: Se dados inválidos ou nenhum dado obtido
        Exception: Erros de processamento (com retry automático)

    Example:
        >>> process_historical_download.delay(
        ...     email="user@example.com",
        ...     lat=-23.5505,
        ...     lon=-46.6333,
        ...     source="data fusion",
        ...     start_date="2024-01-01",
        ...     end_date="2024-03-31",
        ...     file_format="csv"
        ... )
    """
    start_time = time.time()
    task_name = "process_historical_download"

    try:
        # Envio de email inicial
        from backend.core.utils.email_utils import (
            send_email,
            send_email_with_attachment,
        )

        send_email(
            to=email,
            subject="EVAonline: Processamento iniciado",
            body=(
                f"Olá,\n\n"
                f"Seus dados climatológicos estão sendo processados.\n\n"
                f"Detalhes da requisição:\n"
                f"- Localização: ({lat}, {lon})\n"
                f"- Período: {start_date} a {end_date}\n"
                f"- Fonte: {source}\n"
                f"- Formato: {file_format}\n\n"
                f"Você receberá um email quando os dados estiverem prontos.\n\n"
                f"Equipe EVAonline"
            ),
        )

        logger.info(
            f"Processamento histórico iniciado para {email}: "
            f"{start_date} a {end_date}"
        )

        # 1. Baixar dados
        from backend.api.services.data_download import (
            download_weather_data,
        )

        weather_df, warnings = download_weather_data(
            data_source=source,
            data_inicial=start_date,
            data_final=end_date,
            longitude=lon,
            latitude=lat,
        )

        if weather_df is None or weather_df.empty:
            raise ValueError("Nenhum dado obtido das fontes")

        # 2. Processar dados
        from backend.core.data_processing.data_preprocessing import (
            preprocessing,
        )

        df_processed, preprocess_warnings = preprocessing(
            weather_df, latitude=lat
        )
        warnings.extend(preprocess_warnings)

        # 3. Calcular ETo (elevação padrão 0m - TODO: obter elevação real)
        from backend.core.eto_calculation.eto_calculation import (
            calculate_eto,
        )

        df_eto, eto_warnings = calculate_eto(
            weather_df=df_processed,
            elevation=0.0,  # TODO: Integrar serviço de elevação
            latitude=lat,
        )
        warnings.extend(eto_warnings)

        # 4. Gerar arquivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        lat_str = f"{abs(lat):.4f}{'N' if lat >= 0 else 'S'}"
        lon_str = f"{abs(lon):.4f}{'E' if lon >= 0 else 'W'}"
        filename = (
            f"EVAonline_{lat_str}_{lon_str}_"
            f"{start_date}_{end_date}_{timestamp}"
        )

        if file_format.lower() == "excel":
            file_path = f"/tmp/{filename}.xlsx"
            df_eto.to_excel(file_path, index=True)
        else:
            file_path = f"/tmp/{filename}.csv"
            df_eto.to_csv(file_path, index=True)

        logger.info(f"Arquivo gerado: {file_path}")

        # 5. Enviar email com anexo
        send_email_with_attachment(
            to=email,
            subject="EVAonline: Dados prontos!",
            body=(
                f"Olá,\n\n"
                f"Seus dados climatológicos foram processados!\n\n"
                f"Detalhes:\n"
                f"- Localização: ({lat}, {lon})\n"
                f"- Período: {start_date} a {end_date}\n"
                f"- Fonte: {source}\n"
                f"- Formato: {file_format}\n"
                f"- Avisos: {len(warnings)} mensagens\n\n"
                f"O arquivo está anexado a este email.\n\n"
                f"Equipe EVAonline"
            ),
            attachment_path=file_path,
        )

        # TODO: Limpar arquivo temporário após envio SMTP real
        # import os
        # os.remove(file_path)

        # Métricas
        duration = time.time() - start_time
        CELERY_TASKS_TOTAL.labels(task_name=task_name, status="SUCCESS").inc()
        CELERY_TASK_DURATION.labels(task_name=task_name).observe(duration)

        logger.info(
            f"Processamento histórico concluído em {duration:.2f}s "
            f"para {email}"
        )

        return {
            "status": "success",
            "email": email,
            "file_path": file_path,
            "duration": duration,
            "warnings": len(warnings),
            "rows": len(df_eto),
        }

    except Exception as e:
        logger.error(f"Erro no processamento histórico para {email}: {str(e)}")

        # Enviar email de erro
        from backend.core.utils.email_utils import send_email

        send_email(
            to=email,
            subject="EVAonline: Erro no processamento",
            body=(
                f"Olá,\n\n"
                f"Infelizmente ocorreu um erro ao processar seus dados.\n\n"
                f"Detalhes do erro:\n{str(e)}\n\n"
                f"Por favor, tente novamente ou entre em contato.\n\n"
                f"Equipe EVAonline"
            ),
        )

        # Métricas
        CELERY_TASKS_TOTAL.labels(task_name=task_name, status="FAILURE").inc()
        CELERY_TASK_DURATION.labels(task_name=task_name).observe(
            time.time() - start_time
        )

        # Retry com backoff exponencial se não for erro de validação
        if not isinstance(e, ValueError):
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

        raise
