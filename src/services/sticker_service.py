import logging
from typing import List, Dict, Optional

from src.managers.sticker_manager import StickerManager

logger = logging.getLogger(__name__)


class StickerService:
    """Сервис для работы со стикерами через Telegram API"""
    
    def __init__(self, bot_token: str):
        self.manager = StickerManager(bot_token)
    
    def get_user_sticker_sets(self, user_id: int) -> List[Dict]:
        """Получает список стикерсетов пользователя"""
        return self.manager.get_user_sticker_sets(user_id)
    
    def is_sticker_set_available(self, name: str) -> Optional[bool]:
        """Проверяет, доступно ли короткое имя стикерсета"""
        return self.manager.is_sticker_set_available(name)
    
    def create_new_sticker_set(
        self,
        user_id: int,
        name: str,
        title: str,
        png_sticker: bytes,
        emojis: str
    ) -> Optional[Dict]:
        """Создает новый стикерсет и возвращает ответ API"""
        return self.manager.create_new_sticker_set(
            user_id=user_id,
            name=name,
            title=title,
            png_sticker=png_sticker,
            emojis=emojis
        )
    
    def add_sticker_to_set(
        self,
        user_id: int,
        name: str,
        png_sticker: bytes,
        emojis: str
    ) -> bool:
        """Добавляет стикер в существующий стикерсет"""
        return self.manager.add_sticker_to_set(
            user_id=user_id,
            name=name,
            png_sticker=png_sticker,
            emojis=emojis
        )

