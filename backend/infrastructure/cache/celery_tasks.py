import time

from celery import shared_task
from loguru import logger
from redis.asyncio import Redis

from backend.api.middleware.prometheus_metrics import (
    CELERY_TASK_DURATION,
    CELERY_TASKS_TOTAL,
)

# from config.settings import get_settings
from config.settings.app_config import get_settings

# Carregar configurações
settings = get_settings()
# REDIS_URL = settings.REDIS_URL
REDIS_URL = settings.redis.redis_url


@shared_task(
    name="backend.infrastructure.cache.celery_tasks.cleanup_expired_data"
)
async def cleanup_expired_data():
    start_time = time.time()
    try:
        redis_client = Redis.from_url(REDIS_URL)
        expired_keys = await redis_client.keys("forecast:expired:*")
        if expired_keys:
            await redis_client.delete(*expired_keys)
            logger.info(f"Removidas {len(expired_keys)} chaves expiradas")

        logger.info("Limpeza de dados expirados concluída com sucesso")
        CELERY_TASKS_TOTAL.labels(
            task_name="cleanup_expired_data", status="SUCCESS"
        ).inc()

    except Exception as e:
        logger.error(f"Erro na limpeza de dados: {str(e)}")
        CELERY_TASKS_TOTAL.labels(
            task_name="cleanup_expired_data", status="FAILURE"
        ).inc()
        raise
    finally:
        CELERY_TASK_DURATION.labels(task_name="cleanup_expired_data").observe(
            time.time() - start_time
        )


@shared_task(
    name="backend.infrastructure.cache.celery_tasks.update_popular_ranking"
)
async def update_popular_ranking():
    start_time = time.time()
    try:
        redis_client = Redis.from_url(REDIS_URL)
        keys = await redis_client.keys("acessos:*")
        for key in keys:
            acessos = int(await redis_client.get(key) or 0)
            await redis_client.zadd("ranking_acessos", {key.decode(): acessos})

        top_keys = await redis_client.zrange(
            "ranking_acessos", 0, 9, desc=True
        )
        logger.info(f"Chaves mais acessadas: {top_keys}")

        CELERY_TASKS_TOTAL.labels(
            task_name="update_popular_ranking", status="SUCCESS"
        ).inc()

    except Exception as e:
        logger.error(f"Erro ao atualizar ranking: {str(e)}")
        CELERY_TASKS_TOTAL.labels(
            task_name="update_popular_ranking", status="FAILURE"
        ).inc()
        raise
    finally:
        CELERY_TASK_DURATION.labels(
            task_name="update_popular_ranking"
        ).observe(time.time() - start_time)


@shared_task(
    name="backend.infrastructure.cache.celery_tasks.process_historical_download"
)
def process_historical_download(
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

    Fluxo:
    1. Envia email de confirmação inicial
    2. Baixa dados (download_weather_data)
    3. Processa dados (preprocessing)
    4. Calcula ETo
    5. Gera arquivo (CSV/Excel)
    6. Envia email com anexo
    7. Em caso de erro, envia email de notificação

    Args:
        email: Email do usuário
        lat: Latitude
        lon: Longitude
        source: Fonte de dados ou "data fusion"
        start_date: Data inicial (YYYY-MM-DD)
        end_date: Data final (YYYY-MM-DD)
        file_format: Formato do arquivo ("csv" ou "excel")
    """
    # import os  # Para futuro: remover arquivos temporários
    import time
    from datetime import datetime

    from loguru import logger

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
                f"Você receberá um novo email quando os dados estiverem prontos.\n\n"
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

        # 3. Calcular ETo (assumir elevação padrão de 0m se não disponível)
        from backend.core.eto_calculation.eto_calculation import calculate_eto

        df_eto, eto_warnings = calculate_eto(
            weather_df=df_processed,
            elevation=0.0,  # TODO: Obter elevação real
            latitude=lat,
        )
        warnings.extend(eto_warnings)

        # 4. Gerar arquivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"EVAonline_{lat}_{lon}_{start_date}_{end_date}_{timestamp}"

        if file_format.lower() == "excel":
            file_path = f"/tmp/{filename}.xlsx"
            df_eto.to_excel(file_path, index=True)
        else:
            file_path = f"/tmp/{filename}.csv"
            df_eto.to_csv(file_path, index=True)

        logger.info(f"Arquivo gerado: {file_path}")

        # Enviar email com anexo
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
                f"- Formato: {file_format}\n\n"
                f"O arquivo está anexado a este email.\n\n"
                f"Equipe EVAonline"
            ),
            attachment_path=file_path,
        )

        # Limpar arquivo temporário (TODO: ativar quando SMTP real)
        # os.remove(file_path)

        # Métricas
        duration = time.time() - start_time
        CELERY_TASKS_TOTAL.labels(task_name=task_name, status="SUCCESS").inc()
        CELERY_TASK_DURATION.labels(task_name=task_name).observe(duration)

        logger.info(
            f"Processamento histórico concluído em {duration:.2f}s para {email}"
        )

        return {
            "status": "success",
            "email": email,
            "file_path": file_path,
            "duration": duration,
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

        raise
