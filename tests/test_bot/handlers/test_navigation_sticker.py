"""
Регрессионные тесты навигации: стикер в ЛС -> предложение добавить в галерею.
Проверяют, что handle_sticker_for_add_pack возвращает CHOOSING_ACTION и показывает предложение,
и что add_to_gallery callback обрабатывается один раз.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram import Update, User, Chat, Message, Sticker
from telegram.ext import ContextTypes

from src.bot.handlers.add_pack_from_sticker import (
    handle_sticker_for_add_pack,
    handle_add_to_gallery,
    extract_sticker_pack_info,
    build_add_to_gallery_keyboard,
)
from src.bot.states import CHOOSING_ACTION, WAITING_STICKER_PACK_LINK


def _make_sticker(set_name="test_pack_by_bot", file_id="sticker_file_123"):
    s = MagicMock(spec=Sticker)
    s.set_name = set_name
    s.file_id = file_id
    return s


def _make_message_with_sticker(sticker=None):
    sticker = sticker or _make_sticker()
    msg = MagicMock(spec=Message)
    msg.message_id = 1
    msg.chat_id = 12345
    msg.sticker = sticker
    msg.reply_text = AsyncMock()
    return msg


@pytest.fixture
def mock_context():
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx.user_data = {}
    ctx.bot = MagicMock()
    ctx.bot.set_message_reaction = AsyncMock()
    return ctx


@pytest.fixture
def mock_gallery_service():
    s = MagicMock()
    s.is_configured = MagicMock(return_value=True)
    s.check_sticker_set = MagicMock(return_value={"exists": False, "id": None})
    # save_sticker_set вызывается через asyncio.to_thread (sync в реальном коде)
    s.save_sticker_set = MagicMock(return_value={"id": 42})
    return s


@pytest.fixture
def mock_sticker_service():
    return MagicMock()


@pytest.fixture
def mock_cache():
    c = MagicMock()
    c.get = AsyncMock(return_value=None)
    c.set = AsyncMock(return_value=None)
    return c


def test_extract_sticker_pack_info_valid_returns_dict():
    """Стикер с set_name даёт dict с set_name, link, file_id."""
    sticker = _make_sticker(set_name="my_set_by_bot", file_id="f1")
    info = extract_sticker_pack_info(sticker)
    assert info is not None
    assert info["set_name"] == "my_set_by_bot"
    assert info["link"] == "https://t.me/addstickers/my_set_by_bot"
    assert info["file_id"] == "f1"


def test_extract_sticker_pack_info_no_set_name_returns_none():
    """Стикер без set_name даёт None."""
    sticker = _make_sticker()
    sticker.set_name = None
    info = extract_sticker_pack_info(sticker)
    assert info is None


def test_extract_sticker_pack_info_none_returns_none():
    """None стикер даёт None."""
    assert extract_sticker_pack_info(None) is None


def test_build_add_to_gallery_keyboard_contains_add_button():
    """Клавиатура предложения содержит кнопку 'Добавить в галерею' с callback add_to_gallery:set_name."""
    kb = build_add_to_gallery_keyboard("my_set_by_bot")
    assert kb is not None
    inline_kb = kb.inline_keyboard
    assert len(inline_kb) >= 1
    first_row = inline_kb[0]
    assert len(first_row) >= 1
    add_btn = first_row[0]
    assert "add_to_gallery:my_set_by_bot" == add_btn.callback_data
    assert "Добавить" in add_btn.text or "галерею" in add_btn.text


@pytest.mark.asyncio
async def test_handle_sticker_for_add_pack_new_set_returns_choosing_action_and_replies(
    mock_context, mock_gallery_service, mock_sticker_service, mock_cache
):
    """Стикер из нового набора: ответ с предложением добавить в галерею, возврат CHOOSING_ACTION."""
    update = MagicMock(spec=Update)
    update.effective_message = _make_message_with_sticker(_make_sticker("new_pack_by_bot"))
    update.effective_chat = MagicMock()
    update.effective_chat.type = "private"
    update.update_id = 1

    state = await handle_sticker_for_add_pack(
        update,
        mock_context,
        mock_gallery_service,
        mock_sticker_service,
        mock_cache,
    )

    assert state == CHOOSING_ACTION
    assert mock_context.user_data.get("sticker_set_name") == "new_pack_by_bot"
    update.effective_message.reply_text.assert_called_once()
    call_args = update.effective_message.reply_text.call_args
    assert call_args is not None
    text = call_args[0][0] if call_args[0] else ""
    assert "галерею" in text or "ART" in text or "Добавить" in text


@pytest.mark.asyncio
async def test_handle_sticker_for_add_pack_no_message_returns_waiting_sticker_pack_link(
    mock_context, mock_gallery_service, mock_sticker_service, mock_cache
):
    """Вызов без message возвращает WAITING_STICKER_PACK_LINK."""
    update = MagicMock(spec=Update)
    update.effective_message = None
    update.effective_chat = MagicMock()

    state = await handle_sticker_for_add_pack(
        update,
        mock_context,
        mock_gallery_service,
        mock_sticker_service,
        mock_cache,
    )

    assert state == WAITING_STICKER_PACK_LINK


@pytest.mark.asyncio
async def test_handle_add_to_gallery_success_returns_choosing_action(mock_context, mock_gallery_service, mock_cache):
    """Callback add_to_gallery:set_name при успешном добавлении возвращает CHOOSING_ACTION."""
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 12345
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    query = MagicMock()
    query.data = "add_to_gallery:my_pack_by_bot"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update.callback_query = query

    mock_context.user_data["original_sticker_message_id"] = 10

    state = await handle_add_to_gallery(
        update,
        mock_context,
        mock_gallery_service,
        mock_cache,
    )

    assert state == CHOOSING_ACTION
    query.answer.assert_called_once()
    mock_gallery_service.save_sticker_set.assert_called_once()
