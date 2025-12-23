"""
Тесты для inline handlers
"""
import pytest
from unittest.mock import MagicMock
from telegram import InlineQueryResultArticle, InlineQueryResultCachedSticker

from src.bot.handlers.inline import build_generate_result


@pytest.fixture
def mock_prompt_store():
    """Фикстура для мока prompt_store"""
    store = MagicMock()
    store.store_prompt = MagicMock(return_value="test_hash")
    return store


def test_build_generate_result_with_placeholder_file_id_returns_sticker(mock_prompt_store):
    """Тест: build_generate_result возвращает InlineQueryResultCachedSticker когда placeholder_file_id задан"""
    # Arrange
    raw_query = "test prompt"
    generation_enabled = True
    placeholder_file_id = "test_file_id_123"
    
    # Act
    result = build_generate_result(
        raw_query=raw_query,
        prompt_store=mock_prompt_store,
        generation_enabled=generation_enabled,
        placeholder_file_id=placeholder_file_id
    )
    
    # Assert
    assert result is not None
    assert isinstance(result, InlineQueryResultCachedSticker), "Should return InlineQueryResultCachedSticker"
    assert not isinstance(result, InlineQueryResultArticle), "Should NOT return InlineQueryResultArticle"
    assert result.sticker_file_id == placeholder_file_id
    assert result.reply_markup is not None


def test_build_generate_result_without_placeholder_file_id_returns_article(mock_prompt_store):
    """Тест: build_generate_result возвращает InlineQueryResultArticle когда placeholder_file_id не задан"""
    # Arrange
    raw_query = "test prompt"
    generation_enabled = True
    placeholder_file_id = None
    
    # Act
    result = build_generate_result(
        raw_query=raw_query,
        prompt_store=mock_prompt_store,
        generation_enabled=generation_enabled,
        placeholder_file_id=placeholder_file_id
    )
    
    # Assert
    assert result is not None
    assert isinstance(result, InlineQueryResultArticle), "Should return InlineQueryResultArticle"
    assert not isinstance(result, InlineQueryResultCachedSticker), "Should NOT return InlineQueryResultCachedSticker"


def test_build_generate_result_with_empty_placeholder_file_id_returns_article(mock_prompt_store):
    """Тест: build_generate_result возвращает InlineQueryResultArticle когда placeholder_file_id пустой"""
    # Arrange
    raw_query = "test prompt"
    generation_enabled = True
    placeholder_file_id = ""
    
    # Act
    result = build_generate_result(
        raw_query=raw_query,
        prompt_store=mock_prompt_store,
        generation_enabled=generation_enabled,
        placeholder_file_id=placeholder_file_id
    )
    
    # Assert
    assert result is not None
    assert isinstance(result, InlineQueryResultArticle), "Should return InlineQueryResultArticle when placeholder_file_id is empty"




