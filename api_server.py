import asyncio
import logging
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
import os
import json

from config import API_TOKEN, API_PORT, SERVICE_BASE_URL
from config_manager import ConfigManager

logger = logging.getLogger(__name__)

app = FastAPI(
    title="StickerBot Control API",
    description="API для управления ботом: переключение режимов polling/webhook, активация/деактивация",
    version="1.0.0"
)

# Webhook endpoint для Telegram (будет установлен при запуске бота в webhook режиме)
@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Webhook endpoint для получения обновлений от Telegram"""
    global bot_instance
    
    if not bot_instance or not bot_instance.application:
        logger.warning("Получено обновление, но бот не инициализирован")
        return {"ok": False, "error": "Bot not initialized"}
    
    try:
        # Получаем JSON из тела запроса
        body = await request.body()
        data = json.loads(body)
        
        # Создаем Update объект
        from telegram import Update
        update = Update.de_json(data, bot_instance.application.bot)
        
        # Обрабатываем обновление
        await bot_instance.application.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Ошибка обработки webhook обновления: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}

security = HTTPBearer()

# Глобальные переменные для управления ботом
bot_instance = None
bot_task = None
config_manager = None


def get_config_manager() -> ConfigManager:
    """Получить экземпляр ConfigManager"""
    global config_manager
    if config_manager is None:
        from config import CONFIG_PATH
        config_manager = ConfigManager(CONFIG_PATH)
    return config_manager


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Проверка токена аутентификации"""
    if not API_TOKEN:
        raise HTTPException(status_code=500, detail="API_TOKEN не настроен")
    
    if credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Неверный токен аутентификации")
    
    return credentials.credentials


class ModeRequest(BaseModel):
    mode: str


class EnableRequest(BaseModel):
    enabled: bool


class StatusResponse(BaseModel):
    enabled: bool
    mode: str
    webhook_url: Optional[str] = None
    bot_running: bool


@app.get("/api/control/status", response_model=StatusResponse, tags=["control"])
async def get_status(token: str = Depends(verify_token)):
    """
    Получить текущий статус бота
    
    - **enabled**: Включен ли бот
    - **mode**: Режим работы (polling/webhook)
    - **webhook_url**: URL для webhook (если применимо)
    - **bot_running**: Запущен ли бот в данный момент
    """
    cm = get_config_manager()
    config = cm.get_config()
    
    return StatusResponse(
        enabled=config.get('enabled', False),
        mode=config.get('mode', 'polling'),
        webhook_url=config.get('webhook_url'),
        bot_running=bot_task is not None and not bot_task.done()
    )


@app.post("/api/control/start", tags=["control"])
async def start_bot(token: str = Depends(verify_token)):
    """
    Запустить бота в режиме, указанном в конфиге
    
    Если бот уже запущен, вернет ошибку.
    """
    global bot_instance, bot_task
    
    if bot_task is not None and not bot_task.done():
        raise HTTPException(status_code=400, detail="Бот уже запущен")
    
    cm = get_config_manager()
    config = cm.get_config()
    
    if not config.get('enabled', False):
        raise HTTPException(status_code=400, detail="Бот отключен в конфиге. Используйте /api/control/mode для включения")
    
    mode = config.get('mode', 'polling')
    
    if mode == 'webhook':
        if not SERVICE_BASE_URL:
            raise HTTPException(
                status_code=400,
                detail="SERVICE_BASE_URL не установлен в переменных окружения. Необходим для webhook режима"
            )
    
    # Импортируем бота здесь, чтобы избежать циклических импортов
    from bot import StickerBot
    
    bot_instance = StickerBot()
    
    # Запускаем бота в фоновой задаче
    if mode == 'webhook':
        bot_task = asyncio.create_task(bot_instance.run_webhook())
    else:
        bot_task = asyncio.create_task(bot_instance.run_polling())
    
    logger.info(f"Бот запущен в режиме {mode}")
    
    return {
        "status": "started",
        "mode": mode,
        "message": f"Бот запущен в режиме {mode}"
    }


@app.post("/api/control/stop", tags=["control"])
async def stop_bot(token: str = Depends(verify_token)):
    """
    Остановить бота
    
    Выполняет graceful shutdown бота.
    """
    global bot_instance, bot_task
    
    if bot_task is None or bot_task.done():
        raise HTTPException(status_code=400, detail="Бот не запущен")
    
    # Останавливаем бота
    if bot_instance:
        try:
            await bot_instance.stop()
        except Exception as e:
            logger.error(f"Ошибка при остановке бота: {e}")
    
    # Отменяем задачу
    if bot_task and not bot_task.done():
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
    
    bot_task = None
    bot_instance = None
    
    logger.info("Бот остановлен")
    
    return {
        "status": "stopped",
        "message": "Бот успешно остановлен"
    }


@app.post("/api/control/mode", tags=["control"])
async def set_mode(request: ModeRequest, token: str = Depends(verify_token)):
    """
    Переключить режим работы бота (polling/webhook)
    
    - **mode**: 'polling' или 'webhook'
    
    При переключении на webhook проверяется наличие SERVICE_BASE_URL в переменных окружения.
    Если бот запущен, он будет остановлен. Необходимо запустить его заново через /api/control/start.
    Бот автоматически включается (enabled = true) при переключении режима.
    """
    global bot_task
    
    if request.mode not in ('polling', 'webhook'):
        raise HTTPException(
            status_code=400,
            detail="Неверный режим. Допустимые значения: 'polling' или 'webhook'"
        )
    
    # Проверка SERVICE_BASE_URL для webhook режима
    if request.mode == 'webhook':
        if not SERVICE_BASE_URL:
            raise HTTPException(
                status_code=400,
                detail="SERVICE_BASE_URL не установлен в переменных окружения. Необходим для webhook режима"
            )
    
    # Если бот запущен, останавливаем его
    if bot_task is not None and not bot_task.done():
        if bot_instance:
            try:
                await bot_instance.stop()
            except Exception as e:
                logger.error(f"Ошибка при остановке бота: {e}")
        
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
        
        bot_task = None
    
    # Обновляем конфиг
    cm = get_config_manager()
    cm.set_mode(request.mode)
    cm.set_enabled(True)  # Автоматически включаем бота при переключении режима
    
    if request.mode == 'webhook':
        cm.set_webhook_url(SERVICE_BASE_URL)
    
    logger.info(f"Режим изменен на {request.mode}, бот включен")
    
    return {
        "status": "updated",
        "mode": request.mode,
        "enabled": True,
        "message": f"Режим изменен на {request.mode}, бот включен. Используйте /api/control/start для запуска бота."
    }


@app.post("/api/control/enable", tags=["control"])
async def set_enabled(request: EnableRequest, token: str = Depends(verify_token)):
    """
    Включить/выключить бота
    
    - **enabled**: true для включения, false для выключения
    
    Если бот запущен и его выключают, он будет остановлен.
    """
    global bot_task
    
    cm = get_config_manager()
    cm.set_enabled(request.enabled)
    
    # Если выключаем бота и он запущен, останавливаем его
    if not request.enabled and bot_task is not None and not bot_task.done():
        if bot_instance:
            try:
                await bot_instance.stop()
            except Exception as e:
                logger.error(f"Ошибка при остановке бота: {e}")
        
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
        
        bot_task = None
    
    logger.info(f"Бот {'включен' if request.enabled else 'выключен'}")
    
    return {
        "status": "updated",
        "enabled": request.enabled,
        "message": f"Бот {'включен' if request.enabled else 'выключен'}"
    }


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
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=API_PORT,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

