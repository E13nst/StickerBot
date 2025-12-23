import json
from pathlib import Path
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class SupportStorage:
    """Персистентное хранилище для связей сообщений поддержки"""
    
    def __init__(self, filepath: str = "data/support_mapping.json"):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        if not self.filepath.exists():
            self.filepath.write_text('{"mappings": {}, "user_topics": {}}')
            logger.info(f"Создан файл хранилища поддержки: {self.filepath}")
    
    def save_mapping(self, support_msg_id: int, user_id: int, topic_id: int):
        """Сохранить связь: сообщение в поддержке → пользователь"""
        try:
            data = self._load()
            data["mappings"][str(support_msg_id)] = {
                "user_id": user_id,
                "topic_id": topic_id
            }
            self._save(data)
            logger.debug(f"Сохранена связь: msg_id={support_msg_id}, user_id={user_id}, topic_id={topic_id}")
        except Exception as e:
            logger.error(f"Ошибка сохранения связи сообщения: {e}")
    
    def get_mapping(self, support_msg_id: int) -> Optional[Dict]:
        """Получить данные пользователя по ID сообщения в поддержке"""
        try:
            data = self._load()
            return data["mappings"].get(str(support_msg_id))
        except Exception as e:
            logger.error(f"Ошибка получения связи сообщения: {e}")
            return None
    
    def save_user_topic(self, user_id: int, topic_id: int):
        """Сохранить тему пользователя для повторного использования"""
        try:
            data = self._load()
            data["user_topics"][str(user_id)] = topic_id
            self._save(data)
            logger.info(f"Сохранена тема для пользователя {user_id}: topic_id={topic_id}")
        except Exception as e:
            logger.error(f"Ошибка сохранения темы пользователя: {e}")
    
    def get_user_topic(self, user_id: int) -> Optional[int]:
        """Получить существующую тему пользователя"""
        try:
            data = self._load()
            return data["user_topics"].get(str(user_id))
        except Exception as e:
            logger.error(f"Ошибка получения темы пользователя: {e}")
            return None
    
    def _load(self) -> dict:
        """Загрузить данные из файла"""
        try:
            return json.loads(self.filepath.read_text())
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON в {self.filepath}: {e}. Создаю новый файл.")
            # Если файл поврежден, создаём новый
            self.filepath.write_text('{"mappings": {}, "user_topics": {}}')
            return {"mappings": {}, "user_topics": {}}
    
    def _save(self, data: dict):
        """Сохранить данные в файл"""
        self.filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False))

