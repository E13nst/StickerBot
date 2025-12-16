"""
Тесты для generation handlers
"""
import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from telegram.error import TelegramError
from telegram import StickerSet, Sticker

from src.bot.handlers.generation import update_message_with_image, save_sticker_to_user_set, save_sticker_to_user_set


@pytest.fixture
def mock_query():
    """Фикстура для мока query"""
    query = MagicMock()
    query.inline_message_id = None
    query.message = MagicMock()
    query.message.chat = MagicMock()
    query.message.chat.id = 12345
    query.message.edit_media = AsyncMock()
    query.message.edit_text = AsyncMock()
    return query


@pytest.fixture
def mock_context():
    """Фикстура для мока context"""
    context = MagicMock()
    context.bot_data = {
        "wavespeed_client": MagicMock(),
    }
    context.bot = MagicMock()
    context.bot.edit_message_media = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.send_document = AsyncMock()
    context.bot.send_photo = AsyncMock()
    return context


# Старые тесты для конвертации в WebP удалены, так как эта функциональность была удалена из кода


# Новые тесты для функциональности сохранения в стикерсет и отправки нового сообщения

@pytest.mark.asyncio
async def test_save_sticker_to_user_set_creates_new_set(mock_context):
    """Тест: создание нового стикерсета при сохранении стикера"""
    from telegram import StickerSet, Sticker
    
    # Arrange
    user_id = 12345
    user_username = "testuser"
    bot_username = "testbot"
    png_bytes = b"fake_png_data"
    
    mock_sticker_service = MagicMock()
    mock_sticker_service.is_sticker_set_available = Mock(return_value=True)  # Стикерсет не существует
    mock_sticker_service.create_new_sticker_set = Mock(return_value={"ok": True})
    
    mock_sticker_set = MagicMock(spec=StickerSet)
    mock_sticker = MagicMock(spec=Sticker)
    mock_sticker.file_id = "CAACAgIAAxUAAWlBOzKD_test_file_id"
    mock_sticker_set.stickers = [mock_sticker]
    
    mock_context.bot.get_sticker_set = AsyncMock(return_value=mock_sticker_set)
    
    # Act
    result = await save_sticker_to_user_set(
        user_id=user_id,
        user_username=user_username,
        bot_username=bot_username,
        png_bytes=png_bytes,
        sticker_service=mock_sticker_service,
        context=mock_context,
    )
    
    # Assert
    assert result == "CAACAgIAAxUAAWlBOzKD_test_file_id"
    mock_sticker_service.is_sticker_set_available.assert_called_once_with("testuser_by_testbot")
    mock_sticker_service.create_new_sticker_set.assert_called_once()
    mock_sticker_service.add_sticker_to_set.assert_not_called()
    mock_context.bot.get_sticker_set.assert_called_once_with("testuser_by_testbot")


@pytest.mark.asyncio
async def test_save_sticker_to_user_set_adds_to_existing(mock_context):
    """Тест: добавление стикера в существующий стикерсет"""
    from telegram import StickerSet, Sticker
    
    # Arrange
    user_id = 12345
    user_username = "testuser"
    bot_username = "testbot"
    png_bytes = b"fake_png_data"
    
    mock_sticker_service = MagicMock()
    mock_sticker_service.is_sticker_set_available = Mock(return_value=False)  # Стикерсет существует
    mock_sticker_service.add_sticker_to_set = Mock(return_value=True)
    
    mock_sticker_set = MagicMock(spec=StickerSet)
    mock_sticker1 = MagicMock(spec=Sticker)
    mock_sticker1.file_id = "old_file_id"
    mock_sticker2 = MagicMock(spec=Sticker)
    mock_sticker2.file_id = "new_file_id"
    mock_sticker_set.stickers = [mock_sticker1, mock_sticker2]
    
    mock_context.bot.get_sticker_set = AsyncMock(return_value=mock_sticker_set)
    
    # Act
    result = await save_sticker_to_user_set(
        user_id=user_id,
        user_username=user_username,
        bot_username=bot_username,
        png_bytes=png_bytes,
        sticker_service=mock_sticker_service,
        context=mock_context,
    )
    
    # Assert
    assert result == "new_file_id"  # Последний стикер (только что добавленный)
    mock_sticker_service.is_sticker_set_available.assert_called_once_with("testuser_by_testbot")
    mock_sticker_service.add_sticker_to_set.assert_called_once()
    mock_sticker_service.create_new_sticker_set.assert_not_called()


@pytest.mark.asyncio
async def test_save_sticker_to_user_set_fallback_username(mock_context):
    """Тест: использование fallback username при отсутствии username пользователя"""
    from telegram import StickerSet, Sticker
    
    # Arrange
    user_id = 12345
    user_username = None  # Нет username
    bot_username = "testbot"
    png_bytes = b"fake_png_data"
    
    mock_sticker_service = MagicMock()
    mock_sticker_service.is_sticker_set_available = Mock(return_value=True)
    mock_sticker_service.create_new_sticker_set = Mock(return_value={"ok": True})
    
    mock_sticker_set = MagicMock(spec=StickerSet)
    mock_sticker = MagicMock(spec=Sticker)
    mock_sticker.file_id = "test_file_id"
    mock_sticker_set.stickers = [mock_sticker]
    
    mock_context.bot.get_sticker_set = AsyncMock(return_value=mock_sticker_set)
    
    # Act
    result = await save_sticker_to_user_set(
        user_id=user_id,
        user_username=user_username,
        bot_username=bot_username,
        png_bytes=png_bytes,
        sticker_service=mock_sticker_service,
        context=mock_context,
    )
    
    # Assert
    assert result == "test_file_id"
    # Проверяем, что использовался fallback: user_{user_id}
    mock_sticker_service.is_sticker_set_available.assert_called_once_with("user_12345_by_testbot")
    mock_sticker_service.create_new_sticker_set.assert_called_once()
    call_args = mock_sticker_service.create_new_sticker_set.call_args
    assert call_args.kwargs["name"] == "user_12345_by_testbot"


@pytest.mark.asyncio
async def test_update_message_with_image_sends_sticker_for_inline(mock_query, mock_context):
    """Тест: для inline сообщений отправляется новое сообщение со стикером в личный чат"""
    # Arrange
    image_url = "https://example.com/image.png"
    prompt_hash = "test_hash"
    
    mock_query.inline_message_id = "inline_123"
    mock_query.from_user = MagicMock()
    mock_query.from_user.id = 12345
    mock_query.from_user.username = "testuser"
    
    mock_context.bot.username = "testbot"
    mock_context.bot.send_sticker = AsyncMock()
    
    mock_sticker_service = MagicMock()
    mock_context.bot_data["sticker_service"] = mock_sticker_service
    
    mock_wavespeed_client = mock_context.bot_data["wavespeed_client"]
    mock_wavespeed_client.download_image = AsyncMock(return_value=b"fake_png_data")
    
    # Мокаем save_sticker_to_user_set
    with patch("src.bot.handlers.generation.save_sticker_to_user_set") as mock_save:
        mock_save.return_value = "CAACAgIAAxUAAWlBOzKD_test_file_id"
        
        # Act
        await update_message_with_image(
            query=mock_query,
            context=mock_context,
            image_url=image_url,
            prompt_hash=prompt_hash,
        )
        
        # Assert
        mock_save.assert_called_once()
        mock_context.bot.send_sticker.assert_called_once()
        call_args = mock_context.bot.send_sticker.call_args
        assert call_args.kwargs["chat_id"] == 12345
        assert call_args.kwargs["sticker"] == "CAACAgIAAxUAAWlBOzKD_test_file_id"
        # Проверяем, что edit_message_media НЕ был вызван
        mock_context.bot.edit_message_media.assert_not_called()


@pytest.mark.asyncio
async def test_update_message_with_image_deletes_and_sends_sticker_for_regular(mock_query, mock_context):
    """Тест: для обычных сообщений удаляется старое и отправляется новое со стикером"""
    # Arrange
    image_url = "https://example.com/image.png"
    prompt_hash = "test_hash"
    
    mock_query.inline_message_id = None
    mock_query.from_user = MagicMock()
    mock_query.from_user.id = 12345
    mock_query.from_user.username = "testuser"
    mock_query.message.chat.id = 67890
    mock_query.message.delete = AsyncMock()
    
    mock_context.bot.username = "testbot"
    mock_context.bot.send_sticker = AsyncMock()
    
    mock_sticker_service = MagicMock()
    mock_context.bot_data["sticker_service"] = mock_sticker_service
    
    mock_wavespeed_client = mock_context.bot_data["wavespeed_client"]
    mock_wavespeed_client.download_image = AsyncMock(return_value=b"fake_png_data")
    
    # Мокаем save_sticker_to_user_set
    with patch("src.bot.handlers.generation.save_sticker_to_user_set") as mock_save:
        mock_save.return_value = "CAACAgIAAxUAAWlBOzKD_test_file_id"
        
        # Act
        await update_message_with_image(
            query=mock_query,
            context=mock_context,
            image_url=image_url,
            prompt_hash=prompt_hash,
        )
        
        # Assert
        mock_save.assert_called_once()
        mock_query.message.delete.assert_called_once()
        mock_context.bot.send_sticker.assert_called_once()
        call_args = mock_context.bot.send_sticker.call_args
        assert call_args.kwargs["chat_id"] == 67890
        assert call_args.kwargs["sticker"] == "CAACAgIAAxUAAWlBOzKD_test_file_id"


@pytest.mark.asyncio
async def test_update_message_with_image_fallback_when_sticker_save_fails(mock_query, mock_context):
    """Тест: при ошибке сохранения стикера используется fallback логика"""
    # Arrange
    image_url = "https://example.com/image.png"
    prompt_hash = "test_hash"
    
    mock_query.inline_message_id = None
    mock_query.from_user = MagicMock()
    mock_query.from_user.id = 12345
    mock_query.message.edit_media = AsyncMock()
    
    mock_sticker_service = MagicMock()
    mock_context.bot_data["sticker_service"] = mock_sticker_service
    
    mock_wavespeed_client = mock_context.bot_data["wavespeed_client"]
    mock_wavespeed_client.download_image = AsyncMock(return_value=b"fake_png_data")
    
    # Мокаем save_sticker_to_user_set с ошибкой
    with patch("src.bot.handlers.generation.save_sticker_to_user_set") as mock_save:
        mock_save.return_value = None  # Ошибка сохранения
        
        # Act
        await update_message_with_image(
            query=mock_query,
            context=mock_context,
            image_url=image_url,
            prompt_hash=prompt_hash,
        )
        
        # Assert
        mock_save.assert_called_once()
        # Проверяем, что использовалась fallback логика (edit_media с фото)
        mock_query.message.edit_media.assert_called_once()
        call_args = mock_query.message.edit_media.call_args
        from telegram import InputMediaPhoto
        assert isinstance(call_args.kwargs["media"], InputMediaPhoto)

