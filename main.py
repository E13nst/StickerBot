import asyncio
import logging
import signal
import sys
import threading
from src.config.manager import ConfigManager
from src.config.settings import CONFIG_PATH, API_PORT
from src.api.server import app
from src.api.routes.control import set_bot_instance, set_bot_task, bot_instance, bot_task
from src.bot.bot import StickerBot
import uvicorn

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Глобальные переменные
api_thread = None
shutdown_event = threading.Event()


async def start_bot_if_enabled():
    """Запустить бота, если он включен в конфиге"""
    config_manager = ConfigManager(CONFIG_PATH)
    config = config_manager.get_config()
    
    if not config.get('enabled', True):
        logger.info("Бот отключен в конфиге, не запускаем")
        return
    
    mode = config.get('mode', 'polling')
    logger.info(f"Запуск бота в режиме {mode}")
    
    # Используем глобальные переменные из control routes
    bot_inst = StickerBot()
    set_bot_instance(bot_inst)
    
    if mode == 'webhook':
        task = asyncio.create_task(bot_inst.run_webhook())
    else:
        task = asyncio.create_task(bot_inst.run_polling())
    
    set_bot_task(task)


async def stop_bot():
    """Остановить бота"""
    if bot_instance and bot_task:
        logger.info("Остановка бота...")
        try:
            await bot_instance.stop()
            if bot_task and not bot_task.done():
                bot_task.cancel()
                try:
                    await bot_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            logger.error(f"Ошибка при остановке бота: {e}")
        
        set_bot_task(None)
        set_bot_instance(None)


def run_api_server_thread():
    """Запуск API сервера в отдельном потоке"""
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=API_PORT,
        log_level="info"
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())


async def main():
    """Главная функция для координации запуска"""
    global api_thread
    
    logger.info("Запуск StickerBot Control System")
    
    # Инициализируем конфиг менеджер
    config_manager = ConfigManager(CONFIG_PATH)
    logger.info(f"Конфиг загружен из: {config_manager.config_path}")
    
    # Запускаем API сервер в отдельном потоке
    logger.info("Запуск API сервера...")
    api_thread = threading.Thread(target=run_api_server_thread, daemon=True)
    api_thread.start()
    
    # Небольшая задержка для запуска API сервера
    await asyncio.sleep(2)
    
    # Запускаем бота, если он включен
    await start_bot_if_enabled()
    
    # Обработка сигналов для graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Получен сигнал {signum}, начинаем остановку...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Ждем сигнала остановки (используем threading.Event в цикле)
        while not shutdown_event.is_set():
            await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Получен KeyboardInterrupt, начинаем остановку...")
    finally:
        # Останавливаем бота
        await stop_bot()
        
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
