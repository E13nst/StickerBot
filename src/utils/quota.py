"""Управление квотами (FREE/PREMIUM) с атомарными операциями"""
import asyncio
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple, Optional, Deque
from collections import deque, defaultdict

logger = logging.getLogger(__name__)


class Plan(Enum):
    """План пользователя"""
    FREE = "free"
    PREMIUM = "premium"


@dataclass
class QuotaConfig:
    """Конфигурация квот для плана"""
    daily_limit: int
    max_per_10min: int
    cooldown_seconds: float
    max_active: int = 1


class UserPlanResolver:
    """Определение плана пользователя (заменяемый источник)"""
    
    def __init__(self, premium_user_ids: set[int]):
        """
        Args:
            premium_user_ids: Whitelist премиум пользователей
        """
        self._premium_user_ids = premium_user_ids
    
    def get_plan(self, user_id: int) -> Plan:
        """
        Получить план пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Plan (FREE или PREMIUM)
        """
        return Plan.PREMIUM if user_id in self._premium_user_ids else Plan.FREE


class DailyQuotaStore:
    """In-memory storage для суточных квот с атомарными операциями"""
    
    def __init__(self):
        self._store: Dict[Tuple[int, str], int] = {}  # {(user_id, day_key): count}
        # Per-user locks для атомарности
        self._locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock_cleanup_interval = 300
        self._last_cleanup = time.time()
    
    @staticmethod
    def _get_day_key(timestamp: float) -> str:
        """Получить day_key в UTC (YYYY-MM-DD)"""
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    
    async def try_consume(
        self, user_id: int, day_key: str, limit: int
    ) -> Tuple[bool, int]:
        """
        Атомарная проверка и инкремент суточной квоты
        
        Args:
            user_id: ID пользователя
            day_key: Ключ дня (YYYY-MM-DD)
            limit: Лимит на день
            
        Returns:
            (ok, count) - ok=True если можно, count - текущее значение
        """
        # Lazy cleanup locks
        now = time.time()
        if now - self._last_cleanup > self._lock_cleanup_interval:
            self._cleanup_locks()
            self._last_cleanup = now
        
        lock = self._locks[user_id]
        async with lock:
            key = (user_id, day_key)
            count = self._store.get(key, 0)
            
            if count >= limit:
                return False, count
            
            # Инкрементируем
            self._store[key] = count + 1
            
            # Lazy cleanup старых ключей (старше 3 дней)
            self._cleanup_old_keys(day_key)
            
            return True, count + 1
    
    def get_count(self, user_id: int, day_key: str) -> int:
        """Получить количество (без lock, для чтения)"""
        return self._store.get((user_id, day_key), 0)
    
    def _cleanup_old_keys(self, current_day_key: str):
        """Удалить ключи старше 3 дней"""
        try:
            current_dt = datetime.strptime(current_day_key, "%Y-%m-%d")
            cutoff_dt = current_dt.replace(day=current_dt.day - 3)
            cutoff_key = cutoff_dt.strftime("%Y-%m-%d")
            
            keys_to_remove = [
                key for key in self._store.keys()
                if len(key) == 2 and key[1] < cutoff_key
            ]
            for key in keys_to_remove:
                self._store.pop(key, None)
        except Exception as e:
            logger.warning(f"Error cleaning up old daily quota keys: {e}")
    
    def _cleanup_locks(self):
        """Очистить locks для неактивных пользователей"""
        # Удаляем locks для пользователей без активных записей
        active_user_ids = {key[0] for key in self._store.keys() if len(key) == 2}
        inactive_user_ids = set(self._locks.keys()) - active_user_ids
        for uid in inactive_user_ids:
            self._locks.pop(uid, None)


class RollingWindowStore:
    """In-memory storage для rolling window (per 10 min) с атомарными операциями"""
    
    def __init__(self):
        self._store: Dict[int, Deque[float]] = defaultdict(deque)
        # Per-user locks для атомарности
        self._locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock_cleanup_interval = 300
        self._last_cleanup = time.time()
    
    async def try_consume(
        self, user_id: int, now: float, limit: int, window_seconds: int = 600
    ) -> Tuple[bool, Optional[float]]:
        """
        Атомарная проверка и добавление в rolling window
        
        Args:
            user_id: ID пользователя
            now: Текущее время (timestamp)
            limit: Лимит за окно
            window_seconds: Размер окна в секундах (по умолчанию 600 = 10 минут)
            
        Returns:
            (ok, retry_after_seconds) - ok=True если можно, retry_after - когда можно повторить
        """
        # Lazy cleanup locks
        if now - self._last_cleanup > self._lock_cleanup_interval:
            self._cleanup_locks()
            self._last_cleanup = now
        
        lock = self._locks[user_id]
        async with lock:
            timestamps = self._store[user_id]
            
            # Prune старые timestamps
            cutoff = now - window_seconds
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()
            
            # Проверка лимита
            if len(timestamps) >= limit:
                if timestamps:
                    oldest = timestamps[0]
                    retry_after = max(0, (oldest + window_seconds) - now)
                    return False, retry_after
                else:
                    return False, window_seconds
            
            # Добавляем timestamp
            timestamps.append(now)
            return True, None
    
    def count_recent(self, user_id: int, now: float, window_seconds: int = 600) -> int:
        """Получить количество (без lock, для чтения)"""
        timestamps = self._store.get(user_id, deque())
        cutoff = now - window_seconds
        return sum(1 for ts in timestamps if ts >= cutoff)
    
    def _cleanup_locks(self):
        """Очистить locks для неактивных пользователей"""
        # Удаляем locks для пользователей без активных записей
        active_user_ids = set(self._store.keys())
        inactive_user_ids = set(self._locks.keys()) - active_user_ids
        for uid in inactive_user_ids:
            self._locks.pop(uid, None)
            self._store.pop(uid, None)


class QuotaManager:
    """Менеджер квот (объединяет все проверки)"""
    
    def __init__(
        self,
        rate_limiter,
        daily_store: DailyQuotaStore,
        rolling_store: RollingWindowStore,
        resolver: UserPlanResolver,
        configs: Dict[Plan, QuotaConfig],
    ):
        """
        Args:
            rate_limiter: RateLimiter для конкурентности
            daily_store: DailyQuotaStore для суточных квот
            rolling_store: RollingWindowStore для rolling window
            resolver: UserPlanResolver для определения плана
            configs: Словарь конфигураций по планам
        """
        self._rate_limiter = rate_limiter
        self._daily_store = daily_store
        self._rolling_store = rolling_store
        self._resolver = resolver
        self._configs = configs
    
    async def try_consume(
        self, user_id: int, now: float
    ) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Почти атомарная проверка и резервация квот
        
        Args:
            user_id: ID пользователя
            now: Текущее время (timestamp)
            
        Returns:
            (ok, message, retry_after_seconds)
        """
        # Определяем план
        plan = self._resolver.get_plan(user_id)
        cfg = self._configs[plan]
        
        # 1. Резервируем concurrency/cooldown
        ok, message, retry_after = await self._rate_limiter.try_start(
            user_id, now, cfg.cooldown_seconds
        )
        if not ok:
            return False, message, retry_after
        
        # 2. Проверяем rolling window (если включен)
        if cfg.max_per_10min > 0:
            ok, retry_after = await self._rolling_store.try_consume(
                user_id, now, cfg.max_per_10min, window_seconds=600
            )
            if not ok:
                # Откатываем reservation
                await self._rate_limiter.finish(user_id)
                retry_after_ceil = int(retry_after) if retry_after else 0
                return False, f"Too many requests. Try again in {retry_after_ceil}s.", retry_after
        
        # 3. Проверяем daily quota
        day_key = DailyQuotaStore._get_day_key(now)
        ok, count = await self._daily_store.try_consume(
            user_id, day_key, cfg.daily_limit
        )
        if not ok:
            # Откатываем reservation
            await self._rate_limiter.finish(user_id)
            if plan == Plan.FREE:
                return False, "Daily free limit reached. Upgrade to Premium for more generations.", None
            else:
                return False, "Premium daily limit reached. Try again tomorrow.", None
        
        # Все проверки пройдены
        return True, None, None
    
    async def finish(self, user_id: int):
        """Освободить слот (проксирует RateLimiter.finish)"""
        await self._rate_limiter.finish(user_id)

