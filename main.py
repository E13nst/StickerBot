import asyncio
import logging
import signal
import sys
from config_manager import ConfigManager
from config import CONFIG_PATH
from api_server import run_api_server
import api_server
from bot import StickerBot

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Глобальные переменные
api_task = None
shutdown_event = asyncio.Event()


async def start_bot_if_enabled():
    """Запустить бота, если он включен в конфиге"""
    config_manager = ConfigManager(CONFIG_PATH)
    config = config_manager.get_config()
    
    if not config.get('enabled', False):
        logger.info("Бот отключен в конфиге, не запускаем")
        return
    
    mode = config.get('mode', 'polling')
    logger.info(f"Запуск бота в режиме {mode}")
    
    # Используем глобальные переменные из api_server
    api_server.bot_instance = StickerBot()
    
    if mode == 'webhook':
        api_server.bot_task = asyncio.create_task(api_server.bot_instance.run_webhook())
    else:
        api_server.bot_task = asyncio.create_task(api_server.bot_instance.run_polling())


async def stop_bot():
    """Остановить бота"""
    if api_server.bot_instance and api_server.bot_task:
        logger.info("Остановка бота...")
        try:
            await api_server.bot_instance.stop()
            if api_server.bot_task and not api_server.bot_task.done():
                api_server.bot_task.cancel()
                try:
                    await api_server.bot_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            logger.error(f"Ошибка при остановке бота: {e}")
        
        api_server.bot_task = None
        api_server.bot_instance = None


async def main():
    """Главная функция для координации запуска"""
    global api_task
    
    logger.info("Запуск StickerBot Control System")
    
    # Инициализируем конфиг менеджер
    config_manager = ConfigManager(CONFIG_PATH)
    logger.info(f"Конфиг загружен из: {config_manager.config_path}")
    
    # Запускаем API сервер
    logger.info("Запуск API сервера...")
    api_task = asyncio.create_task(run_api_server())
    
    # Небольшая задержка для запуска API сервера
    await asyncio.sleep(1)
    
    # Запускаем бота, если он включен
    await start_bot_if_enabled()
    
    # Обработка сигналов для graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Получен сигнал {signum}, начинаем остановку...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Ждем сигнала остановки
        await shutdown_event.wait()
    except KeyboardInterrupt:
        logger.info("Получен KeyboardInterrupt, начинаем остановку...")
    finally:
        # Останавливаем бота
        await stop_bot()
        
        # Останавливаем API сервер
        if api_task and not api_task.done():
            logger.info("Остановка API сервера...")
            api_task.cancel()
            try:
                await api_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Система остановлена")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
