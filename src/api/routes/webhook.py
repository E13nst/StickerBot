import json
import logging
import secrets
from typing import Optional
from fastapi import Request, HTTPException, Header, Depends

from src.config.settings import WEBHOOK_SECRET_TOKEN, WEBHOOK_IP_CHECK_ENABLED
from src.api.middleware.telegram_ip_check import verify_telegram_ip

logger = logging.getLogger(__name__)

# Глобальная переменная для хранения экземпляра бота
bot_instance = None


def set_bot_instance(instance):
    """Установить экземпляр бота"""
    global bot_instance
    bot_instance = instance


async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(
        None,
        alias="X-Telegram-Bot-Api-Secret-Token",
        description="Секретный токен для проверки подлинности запроса от Telegram"
    )
):
    """
    Защищенный webhook endpoint для получения обновлений от Telegram
    
    Использует:
    1. Secret token проверку (обязательно)
    2. Rate limiting (защита от DoS)
    3. IP-адреса проверку (опционально, если WEBHOOK_IP_CHECK_ENABLED=true)
    """
    # Опциональная проверка IP-адреса Telegram
    if WEBHOOK_IP_CHECK_ENABLED:
        await verify_telegram_ip(request)
    
    # Проверка секретного токена (ОБЯЗАТЕЛЬНО)
    if not WEBHOOK_SECRET_TOKEN:
        logger.error("WEBHOOK_SECRET_TOKEN не настроен! Webhook небезопасен!")
        raise HTTPException(
            status_code=500,
            detail="Webhook secret token not configured"
        )
    
    if not x_telegram_bot_api_secret_token:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(f"Попытка доступа к webhook без токена от IP: {client_ip}")
        raise HTTPException(status_code=401, detail="Missing secret token")
    
    # Сравниваем токен из заголовка с сохраненным токеном
    # Используем secrets.compare_digest для защиты от timing attacks
    if not secrets.compare_digest(x_telegram_bot_api_secret_token, WEBHOOK_SECRET_TOKEN):
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(
            f"Неверный секретный токен webhook от IP: {client_ip}, "
            f"получен токен: {x_telegram_bot_api_secret_token[:10]}..."
        )
        raise HTTPException(status_code=401, detail="Invalid secret token")
    
    # Токен верный - обрабатываем обновление
    if not bot_instance:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(f"Получено обновление от IP {client_ip}, но bot_instance не установлен")
        return {"ok": False, "error": "Bot not initialized"}
    
    if not bot_instance.application:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(f"Получено обновление от IP {client_ip}, но application не инициализирован")
        return {"ok": False, "error": "Bot application not initialized"}
    
    try:
        body = await request.body()
        client_ip = request.client.host if request.client else "unknown"
        
        logger.info(f"Обработка webhook обновления от IP: {client_ip}, размер: {len(body)} байт")
        
        data = json.loads(body)
        
        if not isinstance(data, dict):
            logger.error(f"Неверный формат обновления от IP {client_ip}")
            return {"ok": False, "error": "Invalid update format"}
        
        from telegram import Update
        update = Update.de_json(data, bot_instance.application.bot)
        
        await bot_instance.application.process_update(update)
        
        logger.info(f"Webhook обновление успешно обработано от IP: {client_ip}, update_id: {update.update_id}")
        return {"ok": True}
        
    except json.JSONDecodeError as e:
        client_ip = request.client.host if request.client else "unknown"
        logger.error(f"Ошибка парсинга JSON в webhook от IP {client_ip}: {e}")
        return {"ok": False, "error": "Invalid JSON"}
    except Exception as e:
        client_ip = request.client.host if request.client else "unknown"
        logger.error(
            f"Ошибка обработки webhook обновления от IP {client_ip}: {e}",
            exc_info=True
        )
        return {"ok": False, "error": str(e)}

