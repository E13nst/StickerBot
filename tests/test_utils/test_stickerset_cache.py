"""
Тесты для AsyncStickerSetCache.
"""

import pytest
import asyncio
import time
from src.utils.stickerset_cache import AsyncStickerSetCache


@pytest.mark.asyncio
async def test_cache_initialization():
    """Тест: инициализация кэша с правильными параметрами."""
    cache = AsyncStickerSetCache(
        max_size=100,
        ttl_days=1,
        cleanup_interval_hours=1
    )
    
    assert cache._max_size == 100
    assert cache._ttl_seconds == 86400  # 1 день
    assert cache._cleanup_interval == 3600  # 1 час


@pytest.mark.asyncio
async def test_cache_set_and_get():
    """Тест: сохранение и получение из кэша."""
    cache = AsyncStickerSetCache(max_size=100, ttl_days=1)
    
    url = "https://t.me/addstickers/test"
    await cache.set(url, exists=True, set_id=123)
    
    entry = await cache.get(url)
    
    assert entry is not None
    assert entry['exists'] is True
    assert entry['set_id'] == 123
    assert 'cached_at' in entry


@pytest.mark.asyncio
async def test_cache_miss():
    """Тест: cache miss для несуществующего URL."""
    cache = AsyncStickerSetCache(max_size=100, ttl_days=1)
    
    entry = await cache.get("https://t.me/addstickers/nonexistent")
    
    assert entry is None
    
    # Проверяем метрики
    stats = await cache.get_stats()
    assert stats['misses'] == 1
    assert stats['hits'] == 0


@pytest.mark.asyncio
async def test_cache_hit():
    """Тест: cache hit для существующего URL."""
    cache = AsyncStickerSetCache(max_size=100, ttl_days=1)
    
    url = "https://t.me/addstickers/test"
    await cache.set(url, exists=True, set_id=123)
    
    # Первое получение
    entry1 = await cache.get(url)
    # Второе получение
    entry2 = await cache.get(url)
    
    assert entry1 is not None
    assert entry2 is not None
    
    # Проверяем метрики
    stats = await cache.get_stats()
    assert stats['hits'] == 2
    assert stats['misses'] == 0
    assert stats['hit_rate'] == 1.0


@pytest.mark.asyncio
async def test_cache_ttl_expiration():
    """Тест: устаревание записей по TTL."""
    # Кэш с TTL = 1 секунда (для теста)
    cache = AsyncStickerSetCache(max_size=100, ttl_days=1)
    cache._ttl_seconds = 1  # Переопределяем для быстрого теста
    
    url = "https://t.me/addstickers/test"
    await cache.set(url, exists=True, set_id=123)
    
    # Сразу после добавления - запись есть
    entry = await cache.get(url)
    assert entry is not None
    
    # Ждем истечения TTL
    await asyncio.sleep(1.1)
    
    # После истечения TTL - запись пропала
    entry = await cache.get(url)
    assert entry is None


@pytest.mark.asyncio
async def test_cache_lru_eviction():
    """Тест: вытеснение старых записей при переполнении (LRU)."""
    cache = AsyncStickerSetCache(max_size=3, ttl_days=1)
    
    # Добавляем 3 записи
    await cache.set("https://t.me/addstickers/test1", exists=True, set_id=1)
    await cache.set("https://t.me/addstickers/test2", exists=True, set_id=2)
    await cache.set("https://t.me/addstickers/test3", exists=True, set_id=3)
    
    stats = await cache.get_stats()
    assert stats['size'] == 3
    assert stats['evictions'] == 0
    
    # Добавляем 4-ую запись - должна вытеснить первую
    await cache.set("https://t.me/addstickers/test4", exists=True, set_id=4)
    
    stats = await cache.get_stats()
    assert stats['size'] == 3  # Размер не превышает max_size
    assert stats['evictions'] == 1
    
    # Первая запись должна быть вытеснена
    entry1 = await cache.get("https://t.me/addstickers/test1")
    assert entry1 is None
    
    # Остальные должны быть на месте
    entry4 = await cache.get("https://t.me/addstickers/test4")
    assert entry4 is not None


@pytest.mark.asyncio
async def test_cache_update_existing():
    """Тест: обновление существующей записи."""
    cache = AsyncStickerSetCache(max_size=100, ttl_days=1)
    
    url = "https://t.me/addstickers/test"
    
    # Первое сохранение
    await cache.set(url, exists=False, set_id=None)
    entry1 = await cache.get(url)
    assert entry1['exists'] is False
    assert entry1['set_id'] is None
    
    # Обновление
    await cache.set(url, exists=True, set_id=123)
    entry2 = await cache.get(url)
    assert entry2['exists'] is True
    assert entry2['set_id'] == 123


@pytest.mark.asyncio
async def test_cache_invalidate():
    """Тест: инвалидация записи."""
    cache = AsyncStickerSetCache(max_size=100, ttl_days=1)
    
    url = "https://t.me/addstickers/test"
    await cache.set(url, exists=True, set_id=123)
    
    # Запись есть
    entry = await cache.get(url)
    assert entry is not None
    
    # Инвалидируем
    result = await cache.invalidate(url)
    assert result is True
    
    # Запись удалена
    entry = await cache.get(url)
    assert entry is None
    
    # Попытка инвалидировать несуществующую запись
    result = await cache.invalidate(url)
    assert result is False


@pytest.mark.asyncio
async def test_cache_cleanup_expired():
    """Тест: ручная очистка устаревших записей."""
    cache = AsyncStickerSetCache(max_size=100, ttl_days=1)
    cache._ttl_seconds = 1  # Переопределяем для быстрого теста
    
    # Добавляем 3 записи
    await cache.set("https://t.me/addstickers/test1", exists=True, set_id=1)
    await cache.set("https://t.me/addstickers/test2", exists=True, set_id=2)
    await asyncio.sleep(1.1)  # Ждем истечения TTL
    await cache.set("https://t.me/addstickers/test3", exists=True, set_id=3)
    
    # Первые две устарели, третья нет
    removed = await cache.cleanup_expired()
    assert removed == 2
    
    stats = await cache.get_stats()
    assert stats['size'] == 1


@pytest.mark.asyncio
async def test_cache_clear():
    """Тест: полная очистка кэша."""
    cache = AsyncStickerSetCache(max_size=100, ttl_days=1)
    
    # Добавляем записи
    await cache.set("https://t.me/addstickers/test1", exists=True, set_id=1)
    await cache.set("https://t.me/addstickers/test2", exists=True, set_id=2)
    
    stats = await cache.get_stats()
    assert stats['size'] == 2
    
    # Очищаем
    await cache.clear()
    
    stats = await cache.get_stats()
    assert stats['size'] == 0
    assert stats['hits'] == 0
    assert stats['misses'] == 0
    assert stats['evictions'] == 0


@pytest.mark.asyncio
async def test_cache_stats():
    """Тест: статистика кэша."""
    cache = AsyncStickerSetCache(max_size=100, ttl_days=7)
    
    # Начальная статистика
    stats = await cache.get_stats()
    assert stats['size'] == 0
    assert stats['max_size'] == 100
    assert stats['hits'] == 0
    assert stats['misses'] == 0
    assert stats['evictions'] == 0
    assert stats['hit_rate'] == 0.0
    assert stats['ttl_days'] == 7
    
    # Добавляем записи и делаем запросы
    await cache.set("https://t.me/addstickers/test1", exists=True, set_id=1)
    await cache.get("https://t.me/addstickers/test1")  # hit
    await cache.get("https://t.me/addstickers/nonexistent")  # miss
    
    stats = await cache.get_stats()
    assert stats['size'] == 1
    assert stats['hits'] == 1
    assert stats['misses'] == 1
    assert stats['hit_rate'] == 0.5


@pytest.mark.asyncio
async def test_cache_concurrent_access():
    """Тест: конкурентный доступ к кэшу."""
    cache = AsyncStickerSetCache(max_size=100, ttl_days=1)
    
    async def set_and_get(index):
        url = f"https://t.me/addstickers/test{index}"
        await cache.set(url, exists=True, set_id=index)
        entry = await cache.get(url)
        assert entry is not None
        assert entry['set_id'] == index
    
    # Запускаем 10 конкурентных операций
    await asyncio.gather(*[set_and_get(i) for i in range(10)])
    
    stats = await cache.get_stats()
    assert stats['size'] == 10
    assert stats['hits'] == 10

