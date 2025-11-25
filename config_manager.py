import os
import yaml
import threading
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class ConfigManager:
    """Управление конфигурацией бота в YAML файле"""
    
    _lock = threading.Lock()
    _default_config = {
        'mode': 'polling',
        'enabled': False,
        'webhook_url': None
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Инициализация менеджера конфигурации
        
        Args:
            config_path: Путь к конфиг файлу. Если не указан, определяется автоматически:
                        /data/bot_config.yaml на хостинге, ./data/bot_config.yaml локально
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            # Автоматическое определение пути
            if os.path.exists('/data'):
                self.config_path = Path('/data/bot_config.yaml')
            else:
                self.config_path = Path('./data/bot_config.yaml')
        
        # Создаем директорию, если её нет
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Инициализируем конфиг, если файла нет
        if not self.config_path.exists():
            self._write_config(self._default_config.copy())
    
    def _read_config(self) -> Dict[str, Any]:
        """Чтение конфига из файла (thread-safe)"""
        with self._lock:
            try:
                if not self.config_path.exists():
                    return self._default_config.copy()
                
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                
                # Объединяем с дефолтными значениями
                result = self._default_config.copy()
                result.update(config)
                return result
            except Exception as e:
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

