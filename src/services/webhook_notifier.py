"""Backend webhook notifier с фоновой очередью и retry логикой"""
import asyncio
import hmac
import hashlib
import json
import time
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)


@dataclass
class WebhookTask:
    """Задача для отправки webhook"""
    webhook_url: str
    payload: Dict[str, Any]
    invoice_id: str
    attempt: int = 0
    max_attempts: int = 3


class WebhookNotifier:
    """
    Уведомитель backend через webhook с фоновой очередью и retry
    
    Использует asyncio.Queue для неблокирующей обработки webhook'ов.
    Реализует exponential backoff для повторных попыток.
    Добавляет HMAC подпись для безопасности.
    """
    
    def __init__(
        self,
        shared_secret: Optional[str] = None,
        timeout_seconds: int = 10,
        max_attempts: int = 3
    ):
        """
        Args:
            shared_secret: Секретный ключ для HMAC подписи (опционально)
            timeout_seconds: Таймаут HTTP запроса в секундах
            max_attempts: Максимальное количество попыток отправки
        """
        self._shared_secret = shared_secret
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # HTTP клиент для отправки запросов
        self._client: Optional[httpx.AsyncClient] = None
        
        logger.info(
            f"WebhookNotifier initialized: "
            f"timeout={timeout_seconds}s, max_attempts={max_attempts}, "
            f"hmac_enabled={bool(shared_secret)}"
        )
    
    async def start(self):
        """Запустить фоновый worker для обработки очереди"""
        if self._worker_task and not self._worker_task.done():
            logger.warning("WebhookNotifier worker already running")
            return
        
        # Создаём HTTP клиент
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True
        )
        
        self._shutdown_event.clear()
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("WebhookNotifier worker started")
    
    async def stop(self):
        """Остановить worker и дождаться завершения обработки очереди"""
        if not self._worker_task:
            return
        
        logger.info("Stopping WebhookNotifier worker...")
        self._shutdown_event.set()
        
        # Ждём завершения worker'а
        try:
            await asyncio.wait_for(self._worker_task, timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("WebhookNotifier worker did not finish in time, cancelling")
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        # Закрываем HTTP клиент
        if self._client:
            await self._client.aclose()
            self._client = None
        
        logger.info("WebhookNotifier worker stopped")
    
    async def notify_payment_success(
        self,
        webhook_url: str,
        user_id: int,
        amount_stars: int,
        currency: str,
        telegram_charge_id: str,
        invoice_payload: str,
        invoice_id: str
    ):
        """
        Поставить уведомление о платеже в очередь
        
        Args:
            webhook_url: URL backend для уведомления
            user_id: ID пользователя
            amount_stars: Количество Stars
            currency: Валюта (XTR)
            telegram_charge_id: ID charge от Telegram
            invoice_payload: Оригинальный payload invoice
            invoice_id: ID invoice для логирования
        """
        payload = {
            "event": "telegram_stars_payment_succeeded",
            "user_id": user_id,
            "amount_stars": amount_stars,
            "currency": currency,
            "telegram_charge_id": telegram_charge_id,
            "invoice_payload": invoice_payload,
            "timestamp": int(time.time())
        }
        
        task = WebhookTask(
            webhook_url=webhook_url,
            payload=payload,
            invoice_id=invoice_id,
            attempt=0,
            max_attempts=self._max_attempts
        )
        
        await self._queue.put(task)
        
        logger.info(
            f"Payment webhook queued: invoice_id={invoice_id}, "
            f"webhook_url={webhook_url[:50]}..., user_id={user_id}"
        )
    
    async def _worker(self):
        """Фоновый worker для обработки очереди webhook'ов"""
        logger.info("WebhookNotifier worker loop started")
        
        while not self._shutdown_event.is_set():
            try:
                # Ждём задачу с таймаутом, чтобы проверять shutdown_event
                try:
                    task = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # Таймаут - проверяем shutdown_event и продолжаем
                    continue
                
                # Обрабатываем задачу
                await self._process_task(task)
                
            except Exception as e:
                logger.error(f"Error in webhook worker loop: {e}", exc_info=True)
                # Продолжаем работу, не падаем из-за одной ошибки
        
        # Обрабатываем оставшиеся задачи в очереди перед остановкой
        logger.info("Processing remaining webhook tasks before shutdown...")
        while not self._queue.empty():
            try:
                task = self._queue.get_nowait()
                await self._process_task(task)
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.error(f"Error processing remaining task: {e}", exc_info=True)
        
        logger.info("WebhookNotifier worker loop stopped")
    
    async def _process_task(self, task: WebhookTask):
        """
        Обработать одну задачу webhook
        
        Args:
            task: Задача для обработки
        """
        task.attempt += 1
        
        logger.info(
            f"Processing webhook: invoice_id={task.invoice_id}, "
            f"attempt={task.attempt}/{task.max_attempts}, "
            f"url={task.webhook_url[:50]}..."
        )
        
        try:
            success = await self._send_webhook(task.webhook_url, task.payload)
            
            if success:
                logger.info(
                    f"Webhook delivered successfully: invoice_id={task.invoice_id}, "
                    f"attempt={task.attempt}"
                )
                return
            
            # Неуспешная попытка
            if task.attempt < task.max_attempts:
                # Exponential backoff: 1s, 2s, 4s
                delay = 2 ** (task.attempt - 1)
                logger.warning(
                    f"Webhook failed, will retry in {delay}s: "
                    f"invoice_id={task.invoice_id}, attempt={task.attempt}"
                )
                
                await asyncio.sleep(delay)
                
                # Возвращаем задачу в очередь для повторной попытки
                await self._queue.put(task)
            else:
                logger.error(
                    f"Webhook delivery failed after {task.max_attempts} attempts: "
                    f"invoice_id={task.invoice_id}, url={task.webhook_url}"
                )
        
        except Exception as e:
            logger.error(
                f"Exception processing webhook task: {e}, "
                f"invoice_id={task.invoice_id}",
                exc_info=True
            )
    
    async def _send_webhook(self, url: str, payload: Dict[str, Any]) -> bool:
        """
        Отправить HTTP POST запрос на webhook URL
        
        Args:
            url: URL для отправки
            payload: Данные для отправки
            
        Returns:
            True если успешно (2xx response), False иначе
        """
        if not self._client:
            logger.error("HTTP client not initialized")
            return False
        
        try:
            # Сериализуем payload в JSON
            json_body = json.dumps(payload, ensure_ascii=False)
            
            # Генерируем HMAC подпись если есть secret
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "StickerBot-WebhookNotifier/1.0"
            }
            
            if self._shared_secret:
                signature = self._generate_hmac_signature(json_body)
                headers["X-Webhook-Signature"] = signature
                logger.debug(f"HMAC signature generated for webhook request")
            
            # Отправляем запрос
            logger.debug(f"Sending webhook POST to {url}")
            response = await self._client.post(
                url,
                content=json_body,
                headers=headers
            )
            
            # Проверяем статус ответа
            if 200 <= response.status_code < 300:
                logger.info(
                    f"Webhook response: status={response.status_code}, "
                    f"body={response.text[:200]}"
                )
                return True
            else:
                logger.warning(
                    f"Webhook returned non-2xx status: status={response.status_code}, "
                    f"body={response.text[:200]}"
                )
                return False
        
        except httpx.TimeoutException as e:
            logger.warning(f"Webhook request timeout: {e}, url={url}")
            return False
        
        except httpx.HTTPError as e:
            logger.warning(f"Webhook HTTP error: {e}, url={url}")
            return False
        
        except Exception as e:
            logger.error(f"Unexpected error sending webhook: {e}, url={url}", exc_info=True)
            return False
    
    def _generate_hmac_signature(self, json_body: str) -> str:
        """
        Генерировать HMAC-SHA256 подпись для тела запроса
        
        Args:
            json_body: JSON строка тела запроса
            
        Returns:
            Hex строка подписи
        """
        if not self._shared_secret:
            return ""
        
        # HMAC-SHA256(shared_secret, json_body)
        signature = hmac.new(
            self._shared_secret.encode('utf-8'),
            json_body.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    async def get_queue_size(self) -> int:
        """Получить размер очереди (для мониторинга)"""
        return self._queue.qsize()
