import asyncio
import json
import os
import redis
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from celery.result import AsyncResult
import asyncio


from celery.result import AsyncResult
from loguru import logger

# Criar roteador
router = APIRouter()

# Conexão com Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL)


async def broadcast_to_task_subscribers(task_id: str, message: dict):
    """
    Publica mensagem no canal Redis correspondente ao task_id.
    """
    channel = f"task_status:{task_id}"
    redis_client.publish(channel, json.dumps(message))


async def monitor_task_timeout(
    websocket: WebSocket, task_id: str, timeout_minutes: int = 30
):
    """
    Monitora o timeout da tarefa e fecha a conexão se exceder o limite.
    """
    try:
        await asyncio.sleep(timeout_minutes * 60)
        await websocket.send_json(
            {
                "status": "TIMEOUT",
                "error": f"Monitoramento excedeu {timeout_minutes} minutos",
            }
        )
        await websocket.close()
    except Exception as e:
        logger.error(f"Erro no monitor de timeout: {str(e)}")


@router.websocket("/task_status/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    Endpoint WebSocket para monitorar status de tarefas Celery.

    Args:
        websocket: Conexão WebSocket
        task_id: ID da tarefa Celery a ser monitorada
    """
    await websocket.accept()

    # Assinar canal Redis para o task_id
    pubsub = redis_client.pubsub()
    channel = f"task_status:{task_id}"
    pubsub.subscribe(channel)

    # Iniciar monitor de timeout
    timeout_task = asyncio.create_task(
        monitor_task_timeout(websocket, task_id)
    )

    try:
        task = AsyncResult(task_id)

        # Enviar estado inicial
        current_state = {
            "status": task.state,
            "info": task.info or {},
            "timestamp": datetime.now().isoformat(),
        }
        await websocket.send_json(current_state)
        await broadcast_to_task_subscribers(task_id, current_state)

        # Monitorar mensagens do Redis
        async def listen_redis():
            while True:
                message = pubsub.get_message(timeout=1.0)
                if message and message["type"] == "message":
                    await websocket.send_json(json.loads(message["data"]))
                await asyncio.sleep(0.1)

        # Monitorar tarefa Celery
        async def monitor_task():
            while not task.ready():
                if task.state == "PROGRESS":
                    current_state = {
                        "status": "PROGRESS",
                        "info": task.info or {},
                        "timestamp": datetime.now().isoformat(),
                    }
                    await broadcast_to_task_subscribers(task_id, current_state)
                await asyncio.sleep(1)

            if task.failed():
                error_info = {
                    "status": "FAILURE",
                    "error": str(task.info),
                    "timestamp": datetime.now().isoformat(),
                }
                await broadcast_to_task_subscribers(task_id, error_info)
            else:
                task_result = task.get()
                result, warnings = task_result if task_result else (None, None)
                success_info = {
                    "status": "SUCCESS",
                    "result": (
                        result.to_dict()
                        if hasattr(result, "to_dict")
                        else result
                    ),
                    "warnings": warnings,
                    "timestamp": datetime.now().isoformat(),
                }
                await broadcast_to_task_subscribers(task_id, success_info)

        # Executar monitoramento do Redis e da tarefa em paralelo
        await asyncio.gather(listen_redis(), monitor_task())

    except WebSocketDisconnect:
        logger.info(
            f"Cliente desconectado do monitoramento da tarefa {task_id}"
        )
    except Exception as e:
        error_message = {
            "status": "ERROR",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        try:
            await websocket.send_json(error_message)
        except Exception:
            logger.error(
                f"Erro ao enviar mensagem de erro para o cliente: {str(e)}"
            )
    finally:
        timeout_task.cancel()
        pubsub.close()
        await websocket.close()
