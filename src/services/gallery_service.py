import logging
from typing import Optional, Dict, Any

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

