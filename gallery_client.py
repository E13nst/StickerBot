import logging
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)


class GalleryClient:
    def __init__(self, base_url: Optional[str], service_token: Optional[str], default_language: str = 'ru'):
        self.base_url = base_url.rstrip('/') if base_url else None
        self.service_token = service_token
        self.default_language = default_language

    def is_configured(self) -> bool:
        return bool(self.base_url and self.service_token)

    def save_sticker_set(
        self,
        user_id: int,
        sticker_set_id: Optional[int],
        sticker_set_link: str,
        title: Optional[str] = None,
        is_public: bool = False,
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
                'isPublic': is_public,
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

