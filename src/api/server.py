import asyncio
import logging
from fastapi import FastAPI, Request, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from src.api.routes.webhook import telegram_webhook, set_bot_instance as set_webhook_bot_instance
from src.api.routes.control import (
    initialize as init_control,
    get_status,
    start_bot,
    stop_bot,
    set_mode,
    set_enabled,
    set_bot_instance as set_control_bot_instance,
    set_bot_task,
    ModeRequest,
    EnableRequest,
    StatusResponse,
    get_verify_token_dependency,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="StickerBot Control API",
    description="API для управления ботом: переключение режимов polling/webhook, активация/деактивация",
    version="1.0.0"
)

security = HTTPBearer()

# Инициализация routes
init_control(security)

# Создаем зависимость для проверки токена
verify_token = get_verify_token_dependency()


@app.post("/webhook")
async def webhook_endpoint(request: Request):
    """Webhook endpoint для получения обновлений от Telegram"""
    return await telegram_webhook(request)


@app.get("/api/control/status", response_model=StatusResponse, tags=["control"])
async def status_endpoint(token=Depends(verify_token)):
    """Получить текущий статус бота"""
    return await get_status(token)


@app.post("/api/control/start", tags=["control"])
async def start_endpoint(token=Depends(verify_token)):
    """Запустить бота"""
    result = await start_bot(token)
    # Обновляем экземпляр бота в webhook
    from src.api.routes.control import bot_instance
    set_webhook_bot_instance(bot_instance)
    return result


@app.post("/api/control/stop", tags=["control"])
async def stop_endpoint(token=Depends(verify_token)):
    """Остановить бота"""
    return await stop_bot(token)


@app.post("/api/control/mode", tags=["control"])
async def mode_endpoint(request: ModeRequest, token=Depends(verify_token)):
    """Переключить режим работы бота"""
    return await set_mode(request, token)


@app.post("/api/control/enable", tags=["control"])
async def enable_endpoint(request: EnableRequest, token=Depends(verify_token)):
    """Включить/выключить бота"""
    return await set_enabled(request, token)


@app.get("/", tags=["info"])
async def root():
    """Корневой эндпоинт с информацией об API"""
    return {
        "service": "StickerBot Control API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }


async def run_api_server():
    """Запуск API сервера"""
    import uvicorn
    from src.config.settings import API_PORT
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=API_PORT,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

