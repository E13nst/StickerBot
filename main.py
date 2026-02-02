import asyncio
import logging
import signal
import sys
import threading
import json
from datetime import datetime
from pathlib import Path
from src.config.manager import ConfigManager
from src.config.settings import CONFIG_PATH, API_PORT
from src.api.server import app
from src.api.routes.control import set_bot_instance, set_bot_task, bot_instance, bot_task
from src.api.routes.webhook import set_bot_instance as set_webhook_bot_instance
from src.api.routes.payments import set_bot_instance as set_payments_bot_instance
from src.bot.bot import StickerBot
import uvicorn

# #region agent log
DEBUG_LOG_PATH = Path(__file__).parent / '.cursor' / 'debug.log'
def _debug_log(location, message, data=None, hypothesis_id=None):
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": int(datetime.now().timestamp() * 1000),
            "location": location,
            "message": message,
            "data": data or {},
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": hypothesis_id
        }
        with open(DEBUG_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass
# #endregion

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
    # #region agent log
    _debug_log("main.py:start_bot_if_enabled:entry", "Начало start_bot_if_enabled", {"CONFIG_PATH": CONFIG_PATH}, "A")
    # #endregion
    try:
        # #region agent log
        _debug_log("main.py:start_bot_if_enabled:before_config", "Перед созданием ConfigManager", {}, "A")
        # #endregion
        config_manager = ConfigManager(CONFIG_PATH)
        # #region agent log
        _debug_log("main.py:start_bot_if_enabled:after_config", "ConfigManager создан", {"config_path": str(config_manager.config_path)}, "A")
        # #endregion
        config = config_manager.get_config()
        # #region agent log
        _debug_log("main.py:start_bot_if_enabled:config_loaded", "Конфиг загружен", {"config": config, "enabled": config.get('enabled', True)}, "A")
        # #endregion
        
        if not config.get('enabled', True):
            # #region agent log
            _debug_log("main.py:start_bot_if_enabled:disabled", "Бот отключен в конфиге", {}, "A")
            # #endregion
            logger.info("Бот отключен в конфиге, не запускаем")
            return
        
        mode = config.get('mode', 'polling')
        # #region agent log
        _debug_log("main.py:start_bot_if_enabled:before_bot_init", "Перед созданием StickerBot", {"mode": mode}, "B")
        # #endregion
        logger.info(f"Запуск бота в режиме {mode}")
        
        # Используем глобальные переменные из control routes
        bot_inst = StickerBot()
        # #region agent log
        _debug_log("main.py:start_bot_if_enabled:after_bot_init", "StickerBot создан", {}, "B")
        # #endregion
        set_bot_instance(bot_inst)
        # Также устанавливаем экземпляр в webhook endpoint и payments
        set_webhook_bot_instance(bot_inst)
        set_payments_bot_instance(bot_inst)
        # #region agent log
        _debug_log("main.py:start_bot_if_enabled:before_task", "Перед созданием задачи", {"mode": mode}, "B")
        # #endregion
        
        if mode == 'webhook':
            task = asyncio.create_task(bot_inst.run_webhook())
        else:
            task = asyncio.create_task(bot_inst.run_polling())
        # #region agent log
        _debug_log("main.py:start_bot_if_enabled:task_created", "Задача создана", {"mode": mode, "task_done": task.done()}, "B")
        # #endregion
        
        set_bot_task(task)
        # #region agent log
        _debug_log("main.py:start_bot_if_enabled:success", "start_bot_if_enabled завершен успешно", {}, "B")
        # #endregion
    except Exception as e:
        # #region agent log
        _debug_log("main.py:start_bot_if_enabled:error", "Ошибка в start_bot_if_enabled", {"error": str(e), "type": type(e).__name__}, "C")
        # #endregion
        logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)
        raise


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
        # Очищаем экземпляр в webhook endpoint и payments
        set_webhook_bot_instance(None)
        set_payments_bot_instance(None)


def run_api_server_thread():
    """Запуск API сервера в отдельном потоке"""
    # #region agent log
    _debug_log("main.py:run_api_server_thread:entry", "Начало run_api_server_thread", {"API_PORT": API_PORT}, "D")
    # #endregion
    try:
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=API_PORT,
            log_level="info"
        )
        # #region agent log
        _debug_log("main.py:run_api_server_thread:config_created", "Uvicorn config создан", {"port": API_PORT}, "D")
        # #endregion
        server = uvicorn.Server(config)
        # #region agent log
        _debug_log("main.py:run_api_server_thread:before_serve", "Перед запуском сервера", {}, "D")
        # #endregion
        asyncio.run(server.serve())
        # #region agent log
        _debug_log("main.py:run_api_server_thread:after_serve", "Сервер завершил работу", {}, "D")
        # #endregion
    except Exception as e:
        # #region agent log
        _debug_log("main.py:run_api_server_thread:error", "Ошибка в run_api_server_thread", {"error": str(e), "type": type(e).__name__}, "D")
        # #endregion
        logger.error(f"Ошибка в API сервере: {e}", exc_info=True)
        raise


async def main():
    """Главная функция для координации запуска"""
    global api_thread
    
    # #region agent log
    _debug_log("main.py:main:entry", "Начало main()", {"CONFIG_PATH": CONFIG_PATH, "API_PORT": API_PORT}, "E")
    # #endregion
    logger.info("Запуск StickerBot Control System")
    
    # Инициализируем конфиг менеджер
    # #region agent log
    _debug_log("main.py:main:before_config_manager", "Перед созданием ConfigManager", {"CONFIG_PATH": CONFIG_PATH}, "E")
    # #endregion
    config_manager = ConfigManager(CONFIG_PATH)
    # #region agent log
    _debug_log("main.py:main:after_config_manager", "ConfigManager создан", {"config_path": str(config_manager.config_path)}, "E")
    # #endregion
    logger.info(f"Конфиг загружен из: {config_manager.config_path}")
    
    # Запускаем API сервер в отдельном потоке
    # #region agent log
    _debug_log("main.py:main:before_api_thread", "Перед запуском API потока", {}, "E")
    # #endregion
    logger.info("Запуск API сервера...")
    api_thread = threading.Thread(target=run_api_server_thread, daemon=True)
    api_thread.start()
    # #region agent log
    _debug_log("main.py:main:after_api_thread", "API поток запущен", {"thread_alive": api_thread.is_alive()}, "E")
    # #endregion
    
    # Небольшая задержка для запуска API сервера
    await asyncio.sleep(2)
    # #region agent log
    _debug_log("main.py:main:after_sleep", "После задержки 2 сек", {}, "E")
    # #endregion
    
    # Запускаем бота, если он включен
    # #region agent log
    _debug_log("main.py:main:before_start_bot", "Перед вызовом start_bot_if_enabled", {}, "E")
    # #endregion
    await start_bot_if_enabled()
    # #region agent log
    _debug_log("main.py:main:after_start_bot", "После вызова start_bot_if_enabled", {}, "E")
    # #endregion
    
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
    # #region agent log
    _debug_log("main.py:__main__:entry", "Точка входа программы", {}, "F")
    # #endregion
    try:
        # #region agent log
        _debug_log("main.py:__main__:before_asyncio_run", "Перед asyncio.run(main)", {}, "F")
        # #endregion
        asyncio.run(main())
        # #region agent log
        _debug_log("main.py:__main__:after_asyncio_run", "После asyncio.run(main)", {}, "F")
        # #endregion
    except KeyboardInterrupt:
        # #region agent log
        _debug_log("main.py:__main__:keyboard_interrupt", "Получен KeyboardInterrupt", {}, "F")
        # #endregion
        logger.info("Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        # #region agent log
        _debug_log("main.py:__main__:exception", "Критическая ошибка", {"error": str(e), "type": type(e).__name__}, "F")
        # #endregion
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
