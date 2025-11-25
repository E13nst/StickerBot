import json
import logging
from fastapi import Request

logger = logging.getLogger(__name__)

# Глобальная переменная для хранения экземпляра бота
bot_instance = None


def set_bot_instance(instance):
    """Установить экземпляр бота"""
    global bot_instance
    bot_instance = instance


async def telegram_webhook(request: Request):
    """Webhook endpoint для получения обновлений от Telegram"""
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

