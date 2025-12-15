import os
import yaml
import threading
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# #region agent log
DEBUG_LOG_PATH = Path(__file__).parent.parent.parent / '.cursor' / 'debug.log'
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


class ConfigManager:
    """Управление конфигурацией бота в YAML файле"""
    
    _lock = threading.Lock()
    _default_config = {
        'mode': 'polling',
        'enabled': True,
        'webhook_url': None
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Инициализация менеджера конфигурации
        
        Args:
            config_path: Путь к конфиг файлу. Если не указан, определяется автоматически:
                        /data/bot_config.yaml на хостинге, ./data/bot_config.yaml локально
        """
        # #region agent log
        _debug_log("config/manager.py:__init__:entry", "Начало __init__ ConfigManager", {"config_path": config_path}, "G")
        # #endregion
        try:
            if config_path:
                self.config_path = Path(config_path)
            else:
                # Автоматическое определение пути
                # #region agent log
                _debug_log("config/manager.py:__init__:check_data", "Проверка /data", {"exists": os.path.exists('/data')}, "G")
                # #endregion
                if os.path.exists('/data'):
                    self.config_path = Path('/data/bot_config.yaml')
                else:
                    self.config_path = Path('./data/bot_config.yaml')
            # #region agent log
            _debug_log("config/manager.py:__init__:path_determined", "Путь определен", {"config_path": str(self.config_path)}, "G")
            # #endregion
            
            # Создаем директорию, если её нет
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            # #region agent log
            _debug_log("config/manager.py:__init__:dir_created", "Директория создана/проверена", {"exists": self.config_path.exists()}, "G")
            # #endregion
            
            # Инициализируем конфиг, если файла нет
            if not self.config_path.exists():
                # #region agent log
                _debug_log("config/manager.py:__init__:creating_default", "Создание дефолтного конфига", {}, "G")
                # #endregion
                self._write_config(self._default_config.copy())
                # #region agent log
                _debug_log("config/manager.py:__init__:default_created", "Дефолтный конфиг создан", {}, "G")
                # #endregion
            # #region agent log
            _debug_log("config/manager.py:__init__:success", "ConfigManager инициализирован", {"final_path": str(self.config_path)}, "G")
            # #endregion
        except Exception as e:
            # #region agent log
            _debug_log("config/manager.py:__init__:error", "Ошибка в __init__", {"error": str(e), "type": type(e).__name__}, "G")
            # #endregion
            raise
    
    def _read_config(self) -> Dict[str, Any]:
        """Чтение конфига из файла (thread-safe)"""
        # #region agent log
        _debug_log("config/manager.py:_read_config:entry", "Начало чтения конфига", {"path": str(self.config_path)}, "H")
        # #endregion
        with self._lock:
            try:
                if not self.config_path.exists():
                    # #region agent log
                    _debug_log("config/manager.py:_read_config:not_exists", "Файл конфига не существует, возврат дефолта", {}, "H")
                    # #endregion
                    return self._default_config.copy()
                
                # #region agent log
                _debug_log("config/manager.py:_read_config:before_open", "Перед открытием файла", {}, "H")
                # #endregion
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                # #region agent log
                _debug_log("config/manager.py:_read_config:after_load", "Конфиг загружен из YAML", {"config": config}, "H")
                # #endregion
                
                # Объединяем с дефолтными значениями
                result = self._default_config.copy()
                result.update(config)
                # #region agent log
                _debug_log("config/manager.py:_read_config:success", "Конфиг прочитан успешно", {"result": result}, "H")
                # #endregion
                return result
            except Exception as e:
                # #region agent log
                _debug_log("config/manager.py:_read_config:error", "Ошибка чтения конфига", {"error": str(e), "type": type(e).__name__}, "H")
                # #endregion
                logger.error(f"Ошибка чтения конфига: {e}")
                return self._default_config.copy()
    
    def _write_config(self, config: Dict[str, Any]) -> None:
        """Запись конфига в файл (thread-safe)"""
        with self._lock:
            try:
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            except Exception as e:
                logger.error(f"Ошибка записи конфига: {e}")
                raise
    
    def get_config(self) -> Dict[str, Any]:
        """Получить текущую конфигурацию"""
        return self._read_config()
    
    def get_mode(self) -> str:
        """Получить текущий режим (polling/webhook)"""
        config = self._read_config()
        return config.get('mode', 'polling')
    
    def is_enabled(self) -> bool:
        """Проверить, включен ли бот"""
        config = self._read_config()
        return config.get('enabled', False)
    
    def set_mode(self, mode: str) -> None:
        """
        Установить режим работы бота
        
        Args:
            mode: 'polling' или 'webhook'
        """
        if mode not in ('polling', 'webhook'):
            raise ValueError(f"Неверный режим: {mode}. Допустимые значения: polling, webhook")
        
        config = self._read_config()
        config['mode'] = mode
        self._write_config(config)
        logger.info(f"Режим изменен на: {mode}")
    
    def set_enabled(self, enabled: bool) -> None:
        """
        Включить/выключить бота
        
        Args:
            enabled: True для включения, False для выключения
        """
        config = self._read_config()
        config['enabled'] = enabled
        self._write_config(config)
        logger.info(f"Бот {'включен' if enabled else 'выключен'}")
    
    def set_webhook_url(self, url: Optional[str]) -> None:
        """
        Установить URL для webhook
        
        Args:
            url: URL для webhook или None
        """
        config = self._read_config()
        config['webhook_url'] = url
        self._write_config(config)
        logger.info(f"Webhook URL установлен: {url}")
    
    def update_config(self, **kwargs) -> None:
        """
        Обновить конфигурацию (частичное обновление)
        
        Args:
            **kwargs: Параметры для обновления (mode, enabled, webhook_url)
        """
        config = self._read_config()
        for key, value in kwargs.items():
            if key in self._default_config:
                config[key] = value
            else:
                logger.warning(f"Неизвестный параметр конфига: {key}")
        
        self._write_config(config)
        logger.info(f"Конфиг обновлен: {kwargs}")

