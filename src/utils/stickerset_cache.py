"""
Модуль для кэширования проверок стикерсетов в галерее.

Содержит класс AsyncStickerSetCache с LRU и TTL стратегиями,
фоновой очисткой устаревших записей и метриками для мониторинга.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class AsyncStickerSetCache:
    """
    Асинхронный кэш для проверок наличия стикерсетов в галерее.
    
    Особенности:
    - LRU (Least Recently Used) через OrderedDict
    - TTL (Time To Live) для автоматического устаревания записей
    - Фоновая периодическая очистка устаревших записей
    - Метрики: hits, misses, evictions для мониторинга
    - Graceful degradation: ошибки не ломают работу бота
    - Thread-safe через asyncio.Lock
    
    Attributes:
        _cache: OrderedDict для хранения записей с LRU
        _lock: asyncio.Lock для синхронизации
        _max_size: Максимальный размер кэша
        _ttl_seconds: Время жизни записи в секундах
        _cleanup_interval: Интервал очистки в секундах
        _cleanup_task: asyncio.Task фоновой очистки
        _hits: Счётчик cache hits
        _misses: Счётчик cache misses
        _evictions: Счётчик вытесненных записей
    """
    
    def __init__(
        self,
        max_size: int = 5000,
        ttl_days: int = 7,
        cleanup_interval_hours: int = 1
    ):
        """
        Инициализация кэша.
        
        Args:
            max_size: Максимальное количество записей в кэше
            ttl_days: Время жизни записи в днях
            cleanup_interval_hours: Интервал фоновой очистки в часах
        """
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._max_size = max_size
        self._ttl_seconds = ttl_days * 86400  # Преобразуем дни в секунды
        self._cleanup_interval = cleanup_interval_hours * 3600  # Часы в секунды
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Метрики
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        
        logger.info(
            f"AsyncStickerSetCache initialized: "
            f"max_size={max_size}, ttl_days={ttl_days}, "
            f"cleanup_interval_hours={cleanup_interval_hours}"
        )
    
    async def get(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Получить запись из кэша.
        
        Args:
            url: URL стикерсета для поиска
        
        Returns:
            Dict с полями exists, set_id, cached_at или None если не найдено/устарело
        """
        async with self._lock:
            entry = self._cache.get(url)
            
            if entry is None:
                self._misses += 1
                return None
            
            # Проверяем TTL
            age = time.time() - entry['cached_at']
            if age > self._ttl_seconds:
                # Запись устарела, удаляем
                del self._cache[url]
                self._misses += 1
                logger.debug(f"Cache entry expired for {url}, age={age:.0f}s")
                return None
            
            # Перемещаем в конец для LRU (most recently used)
            self._cache.move_to_end(url)
            self._hits += 1
            
            return entry
    
    async def set(
        self,
        url: str,
        exists: bool,
        set_id: Optional[int] = None
    ) -> None:
        """
        Сохранить запись в кэш.
        
        Args:
            url: URL стикерсета
            exists: Существует ли стикерсет в галерее
            set_id: ID стикерсета в галерее (если exists=True)
        """
        async with self._lock:
            # Если запись уже есть, обновляем её
            if url in self._cache:
                del self._cache[url]
            
            # Проверяем размер кэша и удаляем самую старую запись при переполнении
            if len(self._cache) >= self._max_size:
                # FIFO: удаляем первую (самую старую) запись
                oldest_url, _ = self._cache.popitem(last=False)
                self._evictions += 1
                logger.debug(f"Cache eviction: {oldest_url} (size limit reached)")
            
            # Добавляем новую запись
            self._cache[url] = {
                'exists': exists,
                'set_id': set_id,
                'cached_at': time.time()
            }
            
            logger.debug(f"Cache set: {url}, exists={exists}, set_id={set_id}")
    
    async def invalidate(self, url: str) -> bool:
        """
        Удалить запись из кэша (инвалидация).
        
        Args:
            url: URL стикерсета для удаления
        
        Returns:
            True если запись была удалена, False если не было в кэше
        """
        async with self._lock:
            if url in self._cache:
                del self._cache[url]
                logger.debug(f"Cache invalidated: {url}")
                return True
            return False
    
    async def cleanup_expired(self) -> int:
        """
        Удалить все устаревшие записи из кэша.
        
        Returns:
            Количество удалённых записей
        """
        current_time = time.time()
        removed_count = 0
        
        async with self._lock:
            # Собираем URL-ы устаревших записей
            expired_urls = [
                url for url, entry in self._cache.items()
                if (current_time - entry['cached_at']) > self._ttl_seconds
            ]
            
            # Удаляем устаревшие записи
            for url in expired_urls:
                del self._cache[url]
                removed_count += 1
        
        if removed_count > 0:
            logger.info(f"Cache cleanup: removed {removed_count} expired entries")
        
        return removed_count
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику кэша.
        
        Returns:
            Dict с метриками: size, hits, misses, evictions, hit_rate
        """
        async with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0.0
            
            return {
                'size': len(self._cache),
                'max_size': self._max_size,
                'hits': self._hits,
                'misses': self._misses,
                'evictions': self._evictions,
                'hit_rate': round(hit_rate, 3),
                'ttl_days': self._ttl_seconds / 86400,
            }
    
    async def _cleanup_loop(self) -> None:
        """
        Фоновая задача для периодической очистки устаревших записей.
        
        Выполняется каждые cleanup_interval секунд.
        """
        logger.info("Cache cleanup loop started")
        
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval)
                
                try:
                    removed = await self.cleanup_expired()
                    
                    # Логируем статистику каждый час
                    stats = await self.get_stats()
                    logger.info(
                        f"Cache stats: size={stats['size']}/{stats['max_size']}, "
                        f"hits={stats['hits']}, misses={stats['misses']}, "
                        f"hit_rate={stats['hit_rate']:.1%}, "
                        f"evictions={stats['evictions']}, "
                        f"expired_removed={removed}"
                    )
                except Exception as e:
                    logger.error(f"Error in cleanup loop iteration: {e}", exc_info=True)
                    # Продолжаем работу несмотря на ошибку
        except asyncio.CancelledError:
            logger.info("Cache cleanup loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Fatal error in cleanup loop: {e}", exc_info=True)
    
    async def start_cleanup_task(self) -> None:
        """
        Запустить фоновую задачу очистки кэша.
        
        Должен быть вызван после инициализации бота.
        """
        if self._cleanup_task is not None:
            logger.warning("Cleanup task already running")
            return
        
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Cache cleanup task started")
    
    async def stop_cleanup_task(self) -> None:
        """
        Остановить фоновую задачу очистки кэша.
        
        Должен быть вызван при shutdown бота.
        """
        if self._cleanup_task is None:
            return
        
        self._cleanup_task.cancel()
        
        try:
            await self._cleanup_task
        except asyncio.CancelledError:
            pass
        
        self._cleanup_task = None
        logger.info("Cache cleanup task stopped")
    
    async def clear(self) -> None:
        """
        Полностью очистить кэш (для тестирования).
        """
        async with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            logger.info("Cache cleared")







