"""Клиент для работы с WaveSpeed API"""
import asyncio
import logging
import random
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)

WAVESPEED_BASE_URL = "https://api.wavespeed.ai/api/v3"
SUBMIT_TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0)
GET_RESULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
MAX_RETRIES = 2


class WaveSpeedClient:
    """Асинхронный клиент для WaveSpeed API"""
    
    def __init__(self, api_key: str):
        """
        Args:
            api_key: API ключ WaveSpeed
        """
        if not api_key:
            raise ValueError("WAVESPEED_API_KEY is required")
        
        self._api_key = api_key
        # Логируем только первые 4 символа для диагностики
        logger.info(f"WaveSpeedClient initialized with API key: {api_key[:4]}...")
        
        self._client = httpx.AsyncClient(
            timeout=SUBMIT_TIMEOUT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )
    
    async def submit_flux_schnell(
        self,
        final_prompt: str,
        *,
        size: str = "512*512",
        output_format: str = "png",
        seed: int = -1,
        num_images: int = 1,
        strength: float = 0.8,
        image: str = "",
    ) -> str:
        """
        Отправить задачу на генерацию
        
        Args:
            final_prompt: Финальный промпт (с system prompt)
            size: Размер изображения (по умолчанию "512*512")
            output_format: Формат вывода (по умолчанию "png", поддерживается также "webp")
            seed: Seed для генерации (-1 = случайный)
            num_images: Количество изображений (по умолчанию 1)
            strength: Strength для генерации (по умолчанию 0.8)
            image: Base64 изображения для img2img (по умолчанию пустая строка)
            
        Returns:
            request_id
            
        Raises:
            Exception при ошибке API
        """
        url = f"{WAVESPEED_BASE_URL}/wavespeed-ai/flux-schnell"
        
        payload = {
            "enable_base64_output": False,
            "enable_sync_mode": False,
            "image": image,
            "num_images": num_images,
            "output_format": output_format,
            "prompt": final_prompt,
            "seed": seed,
            "size": size,
            "strength": strength,
        }
        
        # Ретраи на сетевые ошибки/5xx/429
        last_exception = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._client.post(url, json=payload, timeout=SUBMIT_TIMEOUT)
                response.raise_for_status()
                
                data = response.json()
                # Поддержка нового формата с вложенным data
                if "data" in data and isinstance(data.get("data"), dict):
                    request_id = data["data"].get("id") or data["data"].get("requestId")
                else:
                    # Fallback на старый формат для обратной совместимости
                    request_id = data.get("id") or data.get("requestId")
                
                if not request_id:
                    raise ValueError(f"Invalid response from WaveSpeed API: {data}")
                
                logger.info(f"WaveSpeed task submitted: request_id={request_id}")
                return request_id
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 500, 502, 503, 504):
                    if attempt < MAX_RETRIES:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(
                            f"WaveSpeed API error {e.response.status_code}, "
                            f"retrying in {wait_time:.1f}s (attempt {attempt + 1}/{MAX_RETRIES + 1})"
                        )
                        await asyncio.sleep(wait_time)
                        last_exception = e
                        continue
                raise
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt < MAX_RETRIES:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"WaveSpeed network error, retrying in {wait_time:.1f}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES + 1}): {e}"
                    )
                    await asyncio.sleep(wait_time)
                    last_exception = e
                    continue
                raise
        
        if last_exception:
            raise last_exception
    
    async def get_prediction_result(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить результат генерации
        
        Args:
            request_id: ID запроса
            
        Returns:
            Словарь с результатом или None при ошибке
        """
        url = f"{WAVESPEED_BASE_URL}/predictions/{request_id}/result"
        
        try:
            response = await self._client.get(url, timeout=GET_RESULT_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            
            # Логируем только статус и executionTime (без полного ответа)
            status = data.get("status", "unknown")
            execution_time = data.get("executionTime")
            logger.debug(
                f"WaveSpeed result: request_id={request_id}, "
                f"status={status}, executionTime={execution_time}"
            )
            
            return data
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"WaveSpeed prediction not found: request_id={request_id}")
                return None
            logger.error(f"WaveSpeed API error {e.response.status_code}: {e}")
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.error(f"WaveSpeed network error: {e}")
            return None
    
    async def submit_background_remover(self, image_url: str) -> str:
        """
        Отправить задачу на удаление фона
        
        Args:
            image_url: URL изображения из результата flux-schnell
            
        Returns:
            request_id
            
        Raises:
            Exception при ошибке API
        """
        url = f"{WAVESPEED_BASE_URL}/wavespeed-ai/image-background-remover"
        
        payload = {
            "enable_base64_output": False,
            "enable_sync_mode": False,
            "image": image_url,
        }
        
        # Логируем только домен + последний сегмент пути (без полного URL)
        try:
            from urllib.parse import urlparse
            parsed = urlparse(image_url)
            log_url = f"{parsed.netloc}{parsed.path.split('/')[-1]}" if parsed.path else "image_url"
        except Exception:
            log_url = "image_url"
        
        # Ретраи на сетевые ошибки/5xx/429
        last_exception = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._client.post(url, json=payload, timeout=SUBMIT_TIMEOUT)
                response.raise_for_status()
                
                data = response.json()
                # Поддержка нового формата с вложенным data
                if "data" in data and isinstance(data.get("data"), dict):
                    request_id = data["data"].get("id") or data["data"].get("requestId")
                else:
                    # Fallback на старый формат для обратной совместимости
                    request_id = data.get("id") or data.get("requestId")
                
                if not request_id:
                    raise ValueError(f"Invalid response from WaveSpeed API: {data}")
                
                logger.info(f"WaveSpeed bg-remover task submitted: request_id={request_id}, image={log_url}")
                return request_id
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 500, 502, 503, 504):
                    if attempt < MAX_RETRIES:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(
                            f"WaveSpeed API error {e.response.status_code}, "
                            f"retrying in {wait_time:.1f}s (attempt {attempt + 1}/{MAX_RETRIES + 1})"
                        )
                        await asyncio.sleep(wait_time)
                        last_exception = e
                        continue
                raise
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt < MAX_RETRIES:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"WaveSpeed network error, retrying in {wait_time:.1f}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES + 1}): {e}"
                    )
                    await asyncio.sleep(wait_time)
                    last_exception = e
                    continue
                raise
        
        if last_exception:
            raise last_exception
    
    async def close(self):
        """Закрыть клиент"""
        await self._client.aclose()

