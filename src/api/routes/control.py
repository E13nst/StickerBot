import asyncio
import logging
from fastapi import HTTPException, Depends, Header
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional

from src.config.settings import API_TOKEN, WEBHOOK_URL
from src.config.manager import ConfigManager

logger = logging.getLogger(__name__)

# Глобальные переменные для управления ботом
bot_instance = None
bot_task = None
config_manager = None
security = None


def initialize(security_instance, bot_inst=None, bot_t=None, config_mgr=None):
    """Инициализация глобальных переменных"""
    global security, bot_instance, bot_task, config_manager
    security = security_instance
    bot_instance = bot_inst
    bot_task = bot_t
    config_manager = config_mgr


def set_bot_instance(instance):
    """Установить экземпляр бота"""
    global bot_instance
    bot_instance = instance


def set_bot_task(task):
    """Установить задачу бота"""
    global bot_task
    bot_task = task


def get_config_manager() -> ConfigManager:
    """Получить экземпляр ConfigManager"""
    global config_manager
    if config_manager is None:
        from src.config.settings import CONFIG_PATH
        config_manager = ConfigManager(CONFIG_PATH)
    return config_manager


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Проверка токена аутентификации
    
    Использует Bearer token из заголовка Authorization.
    """
    if not API_TOKEN:
        raise HTTPException(status_code=500, detail="API_TOKEN не настроен")
    
    if credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Неверный токен аутентификации")
    
    return credentials.credentials


# Альтернативная функция для получения токена из заголовка Authorization
async def get_token_from_header(authorization: str = Header(..., description="Bearer token", alias="Authorization")) -> str:
    """Получает токен из заголовка Authorization"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Не указан заголовок Authorization")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Неверный формат заголовка Authorization. Ожидается: Bearer <token>")
    
    token = authorization.replace("Bearer ", "")
    
    if not API_TOKEN:
        raise HTTPException(status_code=500, detail="API_TOKEN не настроен")
    
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Неверный токен аутентификации")
    
    return token


def get_verify_token_dependency():
    """Возвращает функцию verify_token для использования в маршрутах"""
    return verify_token


class ModeRequest(BaseModel):
    mode: str


class EnableRequest(BaseModel):
    enabled: bool


class StatusResponse(BaseModel):
    enabled: bool
    mode: str
    webhook_url: Optional[str] = None
    bot_running: bool


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
        if not WEBHOOK_URL:
            raise HTTPException(
                status_code=400,
                detail="WEBHOOK_URL не установлен в переменных окружения. Необходим для webhook режима"
            )
    
    # Импортируем бота здесь, чтобы избежать циклических импортов
    from src.bot.bot import StickerBot
    
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
        except RuntimeError as e:
            # RuntimeError возникает если задача привязана к другому event loop
            if "attached to a different loop" in str(e):
                logger.warning("bot_task принадлежит другому event loop, пропускаем await")
            else:
                logger.debug(f"RuntimeError при ожидании отмены задачи: {e}")
    
    bot_task = None
    bot_instance = None
    
    logger.info("Бот остановлен")
    
    return {
        "status": "stopped",
        "message": "Бот успешно остановлен"
    }


async def set_mode(request: ModeRequest, token: str = Depends(verify_token)):
    """
    Переключить режим работы бота (polling/webhook)
    
    - **mode**: 'polling' или 'webhook'
    
    При переключении на webhook проверяется наличие WEBHOOK_URL в переменных окружения.
    Если бот запущен, он будет остановлен и автоматически запущен в новом режиме.
    Бот автоматически включается (enabled = true) при переключении режима.
    """
    global bot_instance, bot_task
    
    if request.mode not in ('polling', 'webhook'):
        raise HTTPException(
            status_code=400,
            detail="Неверный режим. Допустимые значения: 'polling' или 'webhook'"
        )
    
    # Проверка WEBHOOK_URL для webhook режима
    if request.mode == 'webhook':
        if not WEBHOOK_URL:
            raise HTTPException(
                status_code=400,
                detail="WEBHOOK_URL не установлен в переменных окружения. Необходим для webhook режима"
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
        except RuntimeError as e:
            # RuntimeError возникает если задача привязана к другому event loop
            if "attached to a different loop" in str(e):
                logger.warning("bot_task принадлежит другому event loop, пропускаем await")
            else:
                logger.debug(f"RuntimeError при ожидании отмены задачи: {e}")
        
        bot_task = None
        bot_instance = None  # Очищаем экземпляр бота после остановки
    
    # Обновляем конфиг
    cm = get_config_manager()
    cm.set_mode(request.mode)
    cm.set_enabled(True)  # Автоматически включаем бота при переключении режима
    
    if request.mode == 'webhook':
        cm.set_webhook_url(WEBHOOK_URL)
    
    logger.info(f"Режим изменен на {request.mode}, бот включен")
    
    # Автоматически запускаем бота в новом режиме
    from src.bot.bot import StickerBot
    
    bot_instance = StickerBot()
    
    # Запускаем бота в фоновой задаче
    if request.mode == 'webhook':
        bot_task = asyncio.create_task(bot_instance.run_webhook())
    else:
        bot_task = asyncio.create_task(bot_instance.run_polling())
    
    logger.info(f"Бот автоматически запущен в режиме {request.mode}")
    
    return {
        "status": "updated",
        "mode": request.mode,
        "enabled": True,
        "message": f"Режим изменен на {request.mode}, бот автоматически запущен."
    }


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
        except RuntimeError as e:
            # RuntimeError возникает если задача привязана к другому event loop
            if "attached to a different loop" in str(e):
                logger.warning("bot_task принадлежит другому event loop, пропускаем await")
            else:
                logger.debug(f"RuntimeError при ожидании отмены задачи: {e}")
        
        bot_task = None
    
    logger.info(f"Бот {'включен' if request.enabled else 'выключен'}")
    
    return {
        "status": "updated",
        "enabled": request.enabled,
        "message": f"Бот {'включен' if request.enabled else 'выключен'}"
    }

