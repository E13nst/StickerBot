import logging
from typing import Optional, Dict, Any, List

from src.managers.gallery_client import GalleryClient

logger = logging.getLogger(__name__)


class GalleryService:
    """Сервис для работы с галереей стикеров"""
    
    def __init__(
        self,
        base_url: Optional[str],
        service_token: Optional[str],
        default_language: str = 'ru'
    ):
        self.client = GalleryClient(
            base_url=base_url,
            service_token=service_token,
            default_language=default_language
        )
    
    def is_configured(self) -> bool:
        """Проверяет, настроен ли клиент галереи"""
        return self.client.is_configured()
    
    def check_sticker_set(
        self,
        url: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Проверяет наличие стикерсета в галерее по имени или URL"""
        return self.client.check_sticker_set(url=url, name=name)
    
    def save_sticker_set(
        self,
        user_id: int,
        sticker_set_id: Optional[int],
        sticker_set_link: str,
        title: Optional[str] = None,
        visibility: str = "PRIVATE",
        language: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Сохраняет стикерсет в галерею"""
        return self.client.save_sticker_set(
            user_id=user_id,
            sticker_set_id=sticker_set_id,
            sticker_set_link=sticker_set_link,
            title=title,
            visibility=visibility,
            language=language,
        )
    
    def publish_sticker_set(
        self,
        sticker_set_id: int,
        user_id: int,
        language: Optional[str] = None,
        is_public: bool = True,
    ) -> bool:
        """Публикует стикерсет в галерее"""
        return self.client.publish_sticker_set(
            sticker_set_id=sticker_set_id,
            user_id=user_id,
            language=language,
            is_public=is_public,
        )
    
    def unpublish_sticker_set(
        self,
        sticker_set_id: int,
        user_id: int,
        language: Optional[str] = None,
    ) -> bool:
        """Снимает стикерсет с публикации"""
        return self.client.unpublish_sticker_set(
            sticker_set_id=sticker_set_id,
            user_id=user_id,
            language=language,
        )
    
    def get_user_sticker_sets(
        self,
        user_id: int,
        language: Optional[str] = None,
        page: int = 0,
        size: int = 10,
        sort: str = 'createdAt',
        direction: str = 'DESC',
        short_info: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Получает список стикерсетов пользователя из галереи"""
        return self.client.get_user_sticker_sets(
            user_id=user_id,
            language=language,
            page=page,
            size=size,
            sort=sort,
            direction=direction,
            short_info=short_info,
        )
    
    async def search_stickers_inline(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Поиск стикеров для inline-режима
        
        Сервис возвращает СПИСОК СЕТОВ, где у каждого есть file_id для превью.
        Для каждого стикерсета возвращается одна превьюшка (первый стикер).
        
        Args:
            query: текст запроса для поиска
            limit: размер страницы
            offset: смещение для пагинации
            
        Returns:
            Список объектов с полями file_id, stickerFileId, setId, setTitle
            (по одному элементу на стикерсет)
        """
        import asyncio
        
        if not query:
            return []
        
        if not self.client or not self.client.is_configured():
            return []

        result = await asyncio.to_thread(
            self.client.search_stickers_inline,
            query,
            limit,
            offset,
            None,  # language - client использует свой default_language
        )
        
        return result if result else []
    
    async def search_sticker_sets_inline(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Поиск стикерсетов для inline-режима
        
        Args:
            query: текст запроса для поиска
            limit: размер страницы
            offset: смещение для пагинации
            
        Returns:
            Список стикерсетов с полями id, title, description, previewUrl
        """
        import asyncio
        
        if not self.client or not self.client.is_configured():
            return []
        
        result = await asyncio.to_thread(
            self.client.search_sticker_sets_inline,
            query,
            limit,
            offset
        )
        
        if not result:
            return []
        
        if isinstance(result, list):
            return result
        
        return []

