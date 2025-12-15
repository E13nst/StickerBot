"""
Тесты для generation handlers
"""
import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from telegram.error import TelegramError

from src.bot.handlers.generation import update_message_with_image


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


@pytest.mark.asyncio
async def test_update_message_with_image_should_convert_to_webp_never_uses_photo(mock_query, mock_context):
    """Тест: при should_convert_to_webp=True никогда не используется InputMediaPhoto"""
    from telegram import InputMediaPhoto, InputMediaDocument
    
    # Arrange
    image_url = "https://example.com/image.png"
    prompt_hash = "test_hash"
    caption = "Test caption"
    
    # Мокаем успешное скачивание и конвертацию
    test_image_bytes = b"fake_image_data"
    test_webp_bytes = b"fake_webp_data"
    
    mock_wavespeed_client = mock_context.bot_data["wavespeed_client"]
    mock_wavespeed_client.download_image = AsyncMock(return_value=test_image_bytes)
    
    # Мокаем функции конвертации
    with patch("src.bot.handlers.generation.convert_to_webp_rgba") as mock_convert, \
         patch("src.bot.handlers.generation.validate_alpha_channel") as mock_validate:
        
        mock_validate.return_value = True
        mock_convert.return_value = test_webp_bytes
        
        # Мокаем успешное редактирование
        mock_query.message.edit_media = AsyncMock()
        
        # Act
        await update_message_with_image(
            query=mock_query,
            context=mock_context,
            image_url=image_url,
            prompt_hash=prompt_hash,
            caption=caption,
            should_convert_to_webp=True,
        )
        
        # Assert: проверяем, что edit_media был вызван с InputMediaDocument
        mock_query.message.edit_media.assert_called_once()
        call_args = mock_query.message.edit_media.call_args
        
        # Проверяем, что media - это InputMediaDocument, а не InputMediaPhoto
        media_arg = call_args.kwargs.get("media")
        assert isinstance(media_arg, InputMediaDocument), "Should use InputMediaDocument, not InputMediaPhoto"
        assert not isinstance(media_arg, InputMediaPhoto), "Should NOT use InputMediaPhoto"
        
        # Проверяем, что send_photo НЕ был вызван
        mock_context.bot.send_photo.assert_not_called()


@pytest.mark.asyncio
async def test_update_message_with_image_should_convert_to_webp_fallback_to_photo_for_inline(mock_query, mock_context):
    """Тест: при should_convert_to_webp=True и inline_message_id, при ошибке document редактирования пробуется photo fallback"""
    from telegram import InputMediaPhoto, InputMediaDocument
    
    # Arrange
    image_url = "https://example.com/image.png"
    prompt_hash = "test_hash"
    caption = "Test caption"
    
    # Устанавливаем inline_message_id
    mock_query.inline_message_id = "inline_123"
    mock_query.message = None  # Для inline нет message
    
    test_image_bytes = b"fake_image_data"
    test_webp_bytes = b"fake_webp_data"
    
    mock_wavespeed_client = mock_context.bot_data["wavespeed_client"]
    mock_wavespeed_client.download_image = AsyncMock(return_value=test_image_bytes)
    
    # Мокаем функции конвертации
    with patch("src.bot.handlers.generation.convert_to_webp_rgba") as mock_convert, \
         patch("src.bot.handlers.generation.validate_alpha_channel") as mock_validate:
        
        mock_validate.return_value = True
        mock_convert.return_value = test_webp_bytes
        
        # Мокаем: document fail, photo success
        call_count = 0
        def mock_edit_media(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            media = kwargs.get("media")
            if call_count == 1 and isinstance(media, InputMediaDocument):
                # Первый вызов (document) - ошибка
                raise TelegramError("Document edit failed")
            elif call_count == 2 and isinstance(media, InputMediaPhoto):
                # Второй вызов (photo) - успех
                return AsyncMock()
            else:
                raise TelegramError("Unexpected call")
        
        mock_context.bot.edit_message_media = AsyncMock(side_effect=mock_edit_media)
        mock_context.bot.username = "test_bot"
        
        # Act
        await update_message_with_image(
            query=mock_query,
            context=mock_context,
            image_url=image_url,
            prompt_hash=prompt_hash,
            caption=caption,
            should_convert_to_webp=True,
        )
        
        # Assert: проверяем, что edit_message_media был вызван дважды (document, затем photo)
        assert mock_context.bot.edit_message_media.call_count == 2
        
        # Проверяем, что edit_message_text НЕ был вызван (photo fallback сработал)
        mock_context.bot.edit_message_text.assert_not_called()
        
        # Проверяем, что send_photo НЕ был вызван
        mock_context.bot.send_photo.assert_not_called()


@pytest.mark.asyncio
async def test_update_message_with_image_should_convert_to_webp_double_fail_for_inline(mock_query, mock_context):
    """Тест: при should_convert_to_webp=True и inline_message_id, при двойном фейле (document + photo) показывается текст"""
    from telegram import InputMediaPhoto, InputMediaDocument
    
    # Arrange
    image_url = "https://example.com/image.png"
    prompt_hash = "test_hash"
    caption = "Test caption"
    
    # Устанавливаем inline_message_id
    mock_query.inline_message_id = "inline_123"
    mock_query.message = None  # Для inline нет message
    
    test_image_bytes = b"fake_image_data"
    test_webp_bytes = b"fake_webp_data"
    
    mock_wavespeed_client = mock_context.bot_data["wavespeed_client"]
    mock_wavespeed_client.download_image = AsyncMock(return_value=test_image_bytes)
    
    # Мокаем функции конвертации
    with patch("src.bot.handlers.generation.convert_to_webp_rgba") as mock_convert, \
         patch("src.bot.handlers.generation.validate_alpha_channel") as mock_validate:
        
        mock_validate.return_value = True
        mock_convert.return_value = test_webp_bytes
        
        # Мокаем: document fail, photo fail
        call_count = 0
        def mock_edit_media(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise TelegramError(f"Edit failed {call_count}")
        
        mock_context.bot.edit_message_media = AsyncMock(side_effect=mock_edit_media)
        mock_context.bot.username = "test_bot"
        
        # Act
        await update_message_with_image(
            query=mock_query,
            context=mock_context,
            image_url=image_url,
            prompt_hash=prompt_hash,
            caption=caption,
            should_convert_to_webp=True,
        )
        
        # Assert: проверяем, что edit_message_media был вызван дважды (document, затем photo)
        assert mock_context.bot.edit_message_media.call_count == 2
        
        # Проверяем, что edit_message_text был вызван (last resort)
        mock_context.bot.edit_message_text.assert_called_once()
        call_args = mock_context.bot.edit_message_text.call_args
        assert "cannot preview media" in call_args.kwargs.get("text", "").lower()
        
        # Проверяем, что send_photo НЕ был вызван
        mock_context.bot.send_photo.assert_not_called()


@pytest.mark.asyncio
async def test_update_message_with_image_should_convert_to_webp_fallback_to_document_for_chat(mock_query, mock_context):
    """Тест: при should_convert_to_webp=True и chat_id, при ошибке редактирования отправляется документ, а не фото"""
    from telegram import InputMediaPhoto
    
    # Arrange
    image_url = "https://example.com/image.png"
    prompt_hash = "test_hash"
    caption = "Test caption"
    
    test_image_bytes = b"fake_image_data"
    test_webp_bytes = b"fake_webp_data"
    
    mock_wavespeed_client = mock_context.bot_data["wavespeed_client"]
    mock_wavespeed_client.download_image = AsyncMock(return_value=test_image_bytes)
    
    # Мокаем функции конвертации
    with patch("src.bot.handlers.generation.convert_to_webp_rgba") as mock_convert, \
         patch("src.bot.handlers.generation.validate_alpha_channel") as mock_validate:
        
        mock_validate.return_value = True
        mock_convert.return_value = test_webp_bytes
        
        # Мокаем ошибку редактирования
        mock_query.message.edit_media = AsyncMock(side_effect=TelegramError("Edit failed"))
        
        # Act
        await update_message_with_image(
            query=mock_query,
            context=mock_context,
            image_url=image_url,
            prompt_hash=prompt_hash,
            caption=caption,
            should_convert_to_webp=True,
        )
        
        # Assert: проверяем, что был вызван send_document, а не send_photo
        mock_context.bot.send_document.assert_called_once()
        
        # Проверяем, что send_photo НЕ был вызван
        mock_context.bot.send_photo.assert_not_called()


@pytest.mark.asyncio
async def test_update_message_with_image_no_convert_uses_photo(mock_query, mock_context):
    """Тест: при should_convert_to_webp=False используется InputMediaPhoto (обычное поведение)"""
    from telegram import InputMediaPhoto
    
    # Arrange
    image_url = "https://example.com/image.png"
    prompt_hash = "test_hash"
    caption = "Test caption"
    
    # Мокаем успешное редактирование с URL
    mock_query.message.edit_media = AsyncMock()
    
    # Act
    await update_message_with_image(
        query=mock_query,
        context=mock_context,
        image_url=image_url,
        prompt_hash=prompt_hash,
        caption=caption,
        should_convert_to_webp=False,  # Обычное поведение
    )
        
    # Assert: проверяем, что edit_media был вызван с InputMediaPhoto
    mock_query.message.edit_media.assert_called_once()
    call_args = mock_query.message.edit_media.call_args
    
    # Проверяем, что media - это InputMediaPhoto
    media_arg = call_args.kwargs.get("media")
    assert isinstance(media_arg, InputMediaPhoto), "Should use InputMediaPhoto when should_convert_to_webp=False"

