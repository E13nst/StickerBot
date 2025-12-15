"""In-memory storage для промптов и rate limiting (конкурентность)"""
import asyncio
import hashlib
import base64
import time
import logging
from typing import Optional, Dict, Tuple
from collections import defaultdict
from math import ceil

logger = logging.getLogger(__name__)

# Salt для хеширования промптов (можно вынести в env)
PROMPT_HASH_SALT = b"stixly_prompt_salt_v1"


class PromptStore:
    """In-memory storage для промптов с TTL"""
    
    def __init__(self, ttl_seconds: int = 3600):
        """
        Args:
            ttl_seconds: Время жизни промпта в секундах (по умолчанию 1 час)
        """
        self._store: Dict[str, Tuple[str, float]] = {}  # {hash: (prompt, created_at)}
        self._ttl = ttl_seconds
    
    def store_prompt(self, prompt: str) -> str:
        """
        Сохранить промпт и вернуть hash
        
        Args:
            prompt: Промпт пользователя
            
        Returns:
            prompt_hash (12-16 символов base64url)
        """
        # Lazy cleanup перед сохранением
        self._cleanup_expired()
        
        # Генерируем hash
        prompt_bytes = prompt.encode('utf-8')
        hash_obj = hashlib.sha256(PROMPT_HASH_SALT + prompt_bytes)
        hash_bytes = hash_obj.digest()[:12]  # Берем первые 12 байт
        prompt_hash = base64.urlsafe_b64encode(hash_bytes).decode('ascii').rstrip('=')
        
        # Сохраняем
        self._store[prompt_hash] = (prompt, time.time())
        
        return prompt_hash
    
    def get_prompt(self, prompt_hash: str) -> Optional[str]:
        """
        Получить промпт по hash
        
        Args:
            prompt_hash: Hash промпта
            
        Returns:
            Промпт или None если не найден/истек
        """
        # Lazy cleanup перед получением
        self._cleanup_expired()
        
        if prompt_hash not in self._store:
            return None
        
        prompt, created_at = self._store[prompt_hash]
        
        # Проверка TTL
        if time.time() - created_at > self._ttl:
            del self._store[prompt_hash]
            return None
        
        return prompt
    
    def _cleanup_expired(self):
        """Удалить просроченные записи"""
        now = time.time()
        expired_keys = [
            key for key, (_, created_at) in self._store.items()
            if now - created_at > self._ttl
        ]
        for key in expired_keys:
            del self._store[key]


class RateLimiter:
    """Rate limiter для конкурентности и cooldown (не для квот)"""
    
    def __init__(self):
        self._active: Dict[int, bool] = defaultdict(bool)
        self._last_ts: Dict[int, float] = defaultdict(float)
        # Per-user locks для атомарности
        self._locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock_cleanup_interval = 300  # Очистка locks каждые 5 минут
        self._last_cleanup = time.time()
    
    async def try_start(
        self, user_id: int, now: float, cooldown_seconds: float
    ) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Атомарная проверка и резервация слота
        
        Args:
            user_id: ID пользователя
            now: Текущее время (timestamp)
            cooldown_seconds: Cooldown в секундах
            
        Returns:
            (ok, message, retry_after_seconds)
        """
        # Lazy cleanup locks
        if now - self._last_cleanup > self._lock_cleanup_interval:
            self._cleanup_locks()
            self._last_cleanup = now
        
        lock = self._locks[user_id]
        async with lock:
            # Проверка активной генерации
            if self._active[user_id]:
                return False, "Already generating…", None
            
            # Проверка cooldown
            last_ts = self._last_ts[user_id]
            if last_ts > 0:
                elapsed = now - last_ts
                if elapsed < cooldown_seconds:
                    retry_after = cooldown_seconds - elapsed
                    return False, f"Please wait {ceil(retry_after)}s.", retry_after
            
            # Резервируем слот
            self._active[user_id] = True
            self._last_ts[user_id] = now
            
            return True, None, None
    
    async def finish(self, user_id: int):
        """Освободить слот"""
        async with self._locks[user_id]:
            self._active[user_id] = False
    
    def _cleanup_locks(self):
        """Очистить locks для неактивных пользователей"""
        # Удаляем locks для пользователей, которые не активны и не использовались недавно
        now = time.time()
        inactive_users = [
            uid for uid, active in self._active.items()
            if not active and (now - self._last_ts.get(uid, 0) > 3600)
        ]
        for uid in inactive_users:
            self._locks.pop(uid, None)
            self._active.pop(uid, None)
            self._last_ts.pop(uid, None)

