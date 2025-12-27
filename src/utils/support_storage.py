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
        else:
            # Миграция старого формата к новому
            self._migrate_old_format()
    
    def save_mapping(self, support_msg_id: int, user_id: int, topic_id: int, topic_type: str = 'other'):
        """Сохранить связь: сообщение в поддержке → пользователь"""
        try:
            data = self._load()
            data["mappings"][str(support_msg_id)] = {
                "user_id": user_id,
                "topic_id": topic_id,
                "topic_type": topic_type
            }
            self._save(data)
            logger.debug(f"Сохранена связь: msg_id={support_msg_id}, user_id={user_id}, topic_id={topic_id}, topic_type={topic_type}")
        except Exception as e:
            logger.error(f"Ошибка сохранения связи сообщения: {e}")
    
    def get_mapping(self, support_msg_id: int) -> Optional[Dict]:
        """Получить данные пользователя по ID сообщения в поддержке"""
        try:
            data = self._load()
            mapping = data["mappings"].get(str(support_msg_id))
            # Поддержка старого формата без topic_type
            if mapping and 'topic_type' not in mapping:
                mapping['topic_type'] = 'other'
            return mapping
        except Exception as e:
            logger.error(f"Ошибка получения связи сообщения: {e}")
            return None
    
    def save_user_topic(self, user_id: int, topic_id: int, topic_type: str = 'other'):
        """Сохранить тему пользователя для повторного использования с учётом типа обращения"""
        try:
            data = self._load()
            user_id_str = str(user_id)
            if user_id_str not in data["user_topics"]:
                data["user_topics"][user_id_str] = {}
            data["user_topics"][user_id_str][topic_type] = topic_id
            self._save(data)
            logger.info(f"Сохранена тема для пользователя {user_id}, тип: {topic_type}, topic_id={topic_id}")
        except Exception as e:
            logger.error(f"Ошибка сохранения темы пользователя: {e}")
    
    def get_user_topic(self, user_id: int, topic_type: str = 'other') -> Optional[int]:
        """Получить существующую тему пользователя по типу обращения"""
        try:
            data = self._load()
            user_id_str = str(user_id)
            user_topics = data["user_topics"].get(user_id_str)
            
            # Поддержка старого формата (когда topic_id хранился напрямую)
            if isinstance(user_topics, int):
                # Старый формат - возвращаем только если topic_type == 'other'
                if topic_type == 'other':
                    return user_topics
                return None
            
            # Новый формат
            if isinstance(user_topics, dict):
                return user_topics.get(topic_type)
            
            return None
        except Exception as e:
            logger.error(f"Ошибка получения темы пользователя: {e}")
            return None
    
    def _migrate_old_format(self):
        """Миграция старого формата хранилища к новому"""
        try:
            data = self._load()
            migrated = False
            
            # Миграция user_topics: {user_id: topic_id} -> {user_id: {topic_type: topic_id}}
            for user_id_str, topic_data in data.get("user_topics", {}).items():
                if isinstance(topic_data, int):
                    # Старый формат - конвертируем в новый
                    data["user_topics"][user_id_str] = {"other": topic_data}
                    migrated = True
            
            # Миграция mappings: добавляем topic_type если отсутствует
            for msg_id, mapping in data.get("mappings", {}).items():
                if isinstance(mapping, dict) and "topic_type" not in mapping:
                    mapping["topic_type"] = "other"
                    migrated = True
            
            if migrated:
                self._save(data)
                logger.info("Выполнена миграция старого формата хранилища поддержки")
        except Exception as e:
            logger.error(f"Ошибка миграции формата хранилища: {e}")
    
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



