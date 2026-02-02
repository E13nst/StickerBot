"""In-memory storage для invoice и идемпотентности платежей"""
import asyncio
import time
import logging
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class InvoiceStatus(Enum):
    """Статусы invoice"""
    CREATED = "created"
    PAID = "paid"
    CONFIRMED = "confirmed"
    PENDING_DELIVERY = "pending_delivery"
    FAILED = "failed"


@dataclass
class Invoice:
    """Данные invoice"""
    invoice_id: str
    user_id: int
    amount_stars: int
    currency: str
    backend_webhook_url: Optional[str]
    status: InvoiceStatus
    created_at: float
    payload: str  # Оригинальный payload от Mini App


class InvoiceStore:
    """
    In-memory storage для invoice с TTL
    
    TODO: Заменить на Redis/PostgreSQL для:
    - Горизонтального масштабирования
    - Персистентности данных при рестартах
    - Аудита всех платежей
    """
    
    def __init__(self, ttl_hours: int = 24):
        """
        Args:
            ttl_hours: Время жизни invoice в часах (по умолчанию 24 часа)
        """
        self._store: Dict[str, Invoice] = {}
        self._ttl_seconds = ttl_hours * 3600
        # Locks для потокобезопасности
        self._lock = asyncio.Lock()
        logger.info(f"InvoiceStore initialized with TTL={ttl_hours} hours")
    
    async def create_invoice(
        self,
        invoice_id: str,
        user_id: int,
        amount_stars: int,
        currency: str,
        backend_webhook_url: Optional[str],
        payload: str
    ) -> Invoice:
        """
        Создать новый invoice
        
        Args:
            invoice_id: Уникальный ID invoice
            user_id: ID пользователя Telegram
            amount_stars: Количество Stars
            currency: Валюта (всегда XTR для Stars)
            backend_webhook_url: URL для уведомления backend (опционально)
            payload: Оригинальный payload от Mini App
            
        Returns:
            Созданный Invoice
        """
        async with self._lock:
            # Lazy cleanup перед созданием
            await self._cleanup_expired()
            
            invoice = Invoice(
                invoice_id=invoice_id,
                user_id=user_id,
                amount_stars=amount_stars,
                currency=currency,
                backend_webhook_url=backend_webhook_url,
                status=InvoiceStatus.CREATED,
                created_at=time.time(),
                payload=payload
            )
            
            self._store[invoice_id] = invoice
            
            logger.info(
                f"Invoice created: invoice_id={invoice_id}, "
                f"user_id={user_id}, amount={amount_stars} {currency}, "
                f"has_webhook={bool(backend_webhook_url)}"
            )
            
            return invoice
    
    async def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """
        Получить invoice по ID
        
        Args:
            invoice_id: ID invoice
            
        Returns:
            Invoice или None если не найден/истёк
        """
        async with self._lock:
            # Lazy cleanup
            await self._cleanup_expired()
            
            invoice = self._store.get(invoice_id)
            
            if not invoice:
                return None
            
            # Проверка TTL
            if time.time() - invoice.created_at > self._ttl_seconds:
                del self._store[invoice_id]
                logger.debug(f"Invoice expired and removed: {invoice_id}")
                return None
            
            return invoice
    
    async def update_status(self, invoice_id: str, status: InvoiceStatus) -> bool:
        """
        Обновить статус invoice
        
        Args:
            invoice_id: ID invoice
            status: Новый статус
            
        Returns:
            True если обновлено, False если invoice не найден
        """
        async with self._lock:
            invoice = self._store.get(invoice_id)
            
            if not invoice:
                logger.warning(f"Attempted to update non-existent invoice: {invoice_id}")
                return False
            
            old_status = invoice.status
            invoice.status = status
            
            logger.info(
                f"Invoice status updated: invoice_id={invoice_id}, "
                f"{old_status.value} → {status.value}"
            )
            
            return True
    
    async def _cleanup_expired(self):
        """Удалить просроченные invoice"""
        now = time.time()
        expired_keys = [
            invoice_id for invoice_id, invoice in self._store.items()
            if now - invoice.created_at > self._ttl_seconds
        ]
        
        if expired_keys:
            for key in expired_keys:
                del self._store[key]
            logger.info(f"Cleaned up {len(expired_keys)} expired invoices")
    
    async def get_stats(self) -> Dict:
        """Получить статистику хранилища (для мониторинга)"""
        async with self._lock:
            await self._cleanup_expired()
            
            stats = {
                "total_invoices": len(self._store),
                "by_status": {}
            }
            
            for invoice in self._store.values():
                status_name = invoice.status.value
                stats["by_status"][status_name] = stats["by_status"].get(status_name, 0) + 1
            
            return stats


class PaymentIdempotencyStore:
    """
    In-memory storage для проверки идемпотентности платежей
    
    Предотвращает повторную обработку платежа, если Telegram отправляет
    дублирующиеся webhook'и с одним и тем же telegram_payment_charge_id
    
    TODO: Заменить на Redis для персистентности и масштабирования
    """
    
    def __init__(self, ttl_days: int = 7):
        """
        Args:
            ttl_days: Время хранения charge_id в днях (по умолчанию 7 дней)
                     Должно быть больше чем TTL invoice для безопасности
        """
        self._store: Dict[str, float] = {}  # {charge_id: processed_at}
        self._ttl_seconds = ttl_days * 24 * 3600
        self._lock = asyncio.Lock()
        logger.info(f"PaymentIdempotencyStore initialized with TTL={ttl_days} days")
    
    async def is_duplicate(self, telegram_charge_id: str) -> bool:
        """
        Проверить, был ли платёж уже обработан
        
        Args:
            telegram_charge_id: ID charge от Telegram
            
        Returns:
            True если это дубликат (уже обработан), False если новый
        """
        async with self._lock:
            # Lazy cleanup
            await self._cleanup_expired()
            
            return telegram_charge_id in self._store
    
    async def mark_processed(self, telegram_charge_id: str) -> None:
        """
        Отметить платёж как обработанный
        
        Args:
            telegram_charge_id: ID charge от Telegram
        """
        async with self._lock:
            # Lazy cleanup
            await self._cleanup_expired()
            
            self._store[telegram_charge_id] = time.time()
            
            logger.info(f"Payment marked as processed: charge_id={telegram_charge_id}")
    
    async def _cleanup_expired(self):
        """Удалить устаревшие записи"""
        now = time.time()
        expired_keys = [
            charge_id for charge_id, processed_at in self._store.items()
            if now - processed_at > self._ttl_seconds
        ]
        
        if expired_keys:
            for key in expired_keys:
                del self._store[key]
            logger.info(f"Cleaned up {len(expired_keys)} expired payment records")
    
    async def get_stats(self) -> Dict:
        """Получить статистику (для мониторинга)"""
        async with self._lock:
            await self._cleanup_expired()
            
            return {
                "total_processed_payments": len(self._store)
            }
