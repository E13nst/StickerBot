import logging
from typing import Optional, Dict, Any, List

import requests

logger = logging.getLogger(__name__)


class GalleryClient:
    def __init__(self, base_url: Optional[str], service_token: Optional[str], default_language: str = 'ru'):
        self.base_url = base_url.rstrip('/') if base_url else None
        self.service_token = service_token
        self.default_language = default_language

    def is_configured(self) -> bool:
        return bool(self.base_url and self.service_token)

    def check_sticker_set(
        self,
        url: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Проверяет наличие стикерсета в галерее по имени или URL"""
        if not self.is_configured():
            logger.warning("Gallery client is not configured. Skipping sticker set check.")
            return None

        if not url and not name:
            logger.error("Either url or name must be provided for sticker set check")
            return None

        try:
            check_url = f"{self.base_url}/internal/stickersets/check"
            params = {}
            
            if url:
                params['url'] = url
            elif name:
                params['name'] = name

            headers = {
                'accept': 'application/json',
                'X-Service-Token': self.service_token,
            }

            response = requests.get(check_url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "Sticker set check result: exists=%s, name=%s",
                    result.get('exists'),
                    result.get('name')
                )
                return result

            # Обработка ошибок
            if response.status_code == 400:
                logger.error(
                    "Bad request for sticker set check. Status: %s, Response: %s",
                    response.status_code,
                    response.text,
                )
                return {'error': 'bad_request', 'status': 400, 'message': 'Некорректный запрос'}
            elif response.status_code == 401:
                logger.error(
                    "Unauthorized for sticker set check. Status: %s",
                    response.status_code,
                )
                return {'error': 'unauthorized', 'status': 401, 'message': 'Ошибка авторизации'}
            elif response.status_code == 403:
                logger.error(
                    "Forbidden for sticker set check. Status: %s",
                    response.status_code,
                )
                return {'error': 'forbidden', 'status': 403, 'message': 'Нет прав доступа'}
            elif response.status_code == 500:
                logger.error(
                    "Server error for sticker set check. Status: %s, Response: %s",
                    response.status_code,
                    response.text,
                )
                return {'error': 'server_error', 'status': 500, 'message': 'Внутренняя ошибка сервера'}
            else:
                logger.error(
                    "Unexpected error for sticker set check. Status: %s, Response: %s",
                    response.status_code,
                    response.text,
                )
                return {'error': 'unknown', 'status': response.status_code, 'message': 'Неизвестная ошибка'}

        except Exception as e:
            logger.error(f"Error checking sticker set: {e}")
            return None

    def save_sticker_set(
        self,
        user_id: int,
        sticker_set_id: Optional[int],
        sticker_set_link: str,
        title: Optional[str] = None,
        visibility: str = "PRIVATE",
        language: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            logger.warning("Gallery client is not configured. Skipping sticker set registration.")
            return None

        try:
            url = f"{self.base_url}/internal/stickersets"
            params = {
                'userId': user_id,
                'language': language or self.default_language,
            }

            payload: Dict[str, Any] = {
                'name': sticker_set_link,
                'visibility': visibility,
                'authorId': user_id,
            }

            if sticker_set_id is not None:
                payload['stickerSetId'] = sticker_set_id

            if title:
                payload['title'] = title

            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                'X-Service-Token': self.service_token,
                'X-Language': language or self.default_language,
            }

            response = requests.post(url, params=params, json=payload, headers=headers, timeout=10)

            if response.status_code == 201:
                result = response.json()
                logger.info(
                    "Sticker set saved to gallery (user_id=%s, name=%s, id=%s)",
                    user_id,
                    sticker_set_link,
                    result.get('id')
                )
                return result

            logger.error(
                "Failed to save sticker set to gallery. Status: %s, Response: %s",
                response.status_code,
                response.text,
            )
            return None

        except Exception as e:
            logger.error(f"Error saving sticker set to gallery: {e}")
            return None

    def publish_sticker_set(
        self,
        sticker_set_id: int,
        user_id: int,
        language: Optional[str] = None,
        is_public: bool = True,
    ) -> bool:
        if not self.is_configured():
            logger.warning("Gallery client is not configured. Skipping sticker set publish.")
            return False

        try:
            url = f"{self.base_url}/internal/stickersets/{sticker_set_id}/publish"
            params = {
                'userId': user_id,
            }
            payload: Dict[str, Any] = {
                'isPublic': is_public,
            }
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                'X-Service-Token': self.service_token,
                'X-Language': language or self.default_language,
            }

            response = requests.post(url, params=params, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                logger.info(
                    "Sticker set published (id=%s, user_id=%s)",
                    sticker_set_id,
                    user_id
                )
                return True

            logger.error(
                "Failed to publish sticker set. Status: %s, Response: %s",
                response.status_code,
                response.text,
            )
            return False

        except Exception as e:
            logger.error(f"Error publishing sticker set: {e}")
            return False

    def unpublish_sticker_set(
        self,
        sticker_set_id: int,
        user_id: int,
        language: Optional[str] = None,
    ) -> bool:
        if not self.is_configured():
            logger.warning("Gallery client is not configured. Skipping sticker set unpublish.")
            return False

        try:
            url = f"{self.base_url}/internal/stickersets/{sticker_set_id}/unpublish"
            params = {
                'userId': user_id,
            }
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                'X-Service-Token': self.service_token,
                'X-Language': language or self.default_language,
            }

            response = requests.post(url, params=params, json={}, headers=headers, timeout=10)
            if response.status_code == 200:
                logger.info(
                    "Sticker set unpublished (id=%s, user_id=%s)",
                    sticker_set_id,
                    user_id
                )
                return True

            logger.error(
                "Failed to unpublish sticker set. Status: %s, Response: %s",
                response.status_code,
                response.text,
            )
            return False

        except Exception as e:
            logger.error(f"Error unpublishing sticker set: {e}")
            return False

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
        if not self.is_configured():
            logger.warning("Gallery client is not configured. Skipping sticker set fetch.")
            return None

        try:
            url = f"{self.base_url}/internal/stickersets/author/{user_id}"
            params = {
                'page': page,
                'size': size,
                'sort': sort,
                'direction': direction,
                'shortInfo': str(short_info).lower(),
            }
            headers = {
                'accept': 'application/json',
                'X-Service-Token': self.service_token,
                'X-Language': language or self.default_language,
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                return response.json()

            logger.error(
                "Failed to fetch sticker sets from gallery. Status: %s, Response: %s",
                response.status_code,
                response.text,
            )
            return None

        except Exception as e:
            logger.error(f"Error fetching sticker sets from gallery: {e}")
            return None

    def search_stickers_inline(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Поиск стикеров для inline-режима
        
        Args:
            query: текст запроса для поиска
            limit: размер страницы
            offset: смещение для пагинации
            language: язык для заголовков (опционально)
            
        Returns:
            Список стикеров с полями stickerFileId или file_id
        """
        if not self.is_configured():
            logger.warning("Gallery client is not configured. Skipping inline search.")
            return []

        try:
            url = f"{self.base_url}/api/stickersets/search"
            params = {
                "query": query,
                "limit": limit,
                "offset": offset,
            }
            headers = {
                "accept": "application/json",
                "X-Service-Token": self.service_token,
                "X-Language": language or self.default_language,
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                # Поддерживаем оба формата: массив или объект с items
                if isinstance(data, dict) and "items" in data:
                    items = data.get("items", [])
                elif isinstance(data, list):
                    items = data
                else:
                    items = []
                
                # Извлекаем file_id из структуры стикерсета
                results: List[Dict[str, Any]] = []
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    
                    info = it.get("telegramStickerSetInfo") or {}
                    
                    # 1) Пробуем взять file_id из thumbnail/thumb
                    thumb = info.get("thumbnail") or info.get("thumb") or {}
                    file_id = thumb.get("file_id")
                    
                    # 2) Fallback - первый стикер из массива stickers
                    if not file_id:
                        stickers = info.get("stickers") or []
                        if stickers and isinstance(stickers, list) and len(stickers) > 0:
                            first_sticker = stickers[0] if isinstance(stickers[0], dict) else {}
                            file_id = first_sticker.get("file_id")
                    
                    if not file_id:
                        continue
                    
                    results.append({
                        "file_id": file_id,
                        "stickerFileId": file_id,  # для совместимости с handler
                        "id": it.get("id"),
                        "title": it.get("title"),
                    })
                
                return results

            logger.error(
                "Failed to search stickers inline. Status: %s, Response: %s",
                response.status_code,
                response.text,
            )
            return []

        except Exception as e:
            logger.error(f"Error during inline sticker search: {e}", exc_info=True)
            return []

    def search_sticker_sets_inline(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Поиск стикерсетов для inline-режима
        
        Args:
            query: текст запроса для поиска
            limit: размер страницы
            offset: смещение для пагинации
            
        Returns:
            Список стикерсетов с полями id, title, description, previewUrl
        """
        if not self.is_configured():
            logger.warning("Gallery client is not configured. Skipping sticker sets inline search.")
            return None

        try:
            url = f"{self.base_url}/api/stickersets/search"
            params = {
                "query": query,
                "limit": limit,
                "offset": offset,
            }
            headers = {
                "accept": "application/json",
                "X-Service-Token": self.service_token,
                "X-Language": self.default_language,
            }

            resp = requests.get(url, params=params, headers=headers, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                # Ожидаем объект с полем items или массив напрямую
                if isinstance(data, dict) and "items" in data:
                    return data["items"]
                elif isinstance(data, list):
                    return data
                else:
                    logger.warning(f"Неожиданный формат ответа от search endpoint: {type(data)}")
                    return []

            logger.error(
                "Failed to search sticker sets inline. Status: %s, Response: %s",
                resp.status_code,
                resp.text,
            )
            return None

        except Exception as e:
            logger.error(f"Error during inline sticker sets search: {e}", exc_info=True)
            return None

