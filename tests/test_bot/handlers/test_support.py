"""
Регрессионные тесты навигации поддержки: /support и callback support_topic/exit_support.
Проверяют, что прямой /support и вход через главное меню устанавливают состояние и обрабатывают callback'и.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram import Update, User, Chat, Message, CallbackQuery, ChatLocation
from telegram.ext import ContextTypes

from src.bot.handlers.support import (
    enter_support_mode,
    handle_support_topic_selection,
    exit_support_mode,
)
from src.bot.states import CHOOSING_ACTION, CHOOSING_SUPPORT_TOPIC, SUPPORT_MODE


def _make_user(user_id=12345, first_name="Test"):
    return User(id=user_id, is_bot=False, first_name=first_name)


def _make_chat(chat_id=12345, chat_type="private"):
    return Chat(id=chat_id, type=chat_type)


def _make_message(chat=None, from_user=None, text="/support"):
    chat = chat or _make_chat()
    from_user = from_user or _make_user()
    msg = MagicMock(spec=Message)
    msg.chat = chat
    msg.from_user = from_user
    msg.text = text
    msg.reply_text = AsyncMock()
    msg.chat_id = chat.id
    return msg


def _make_callback_query(data: str, message=None, from_user=None):
    message = message or _make_message()
    from_user = from_user or _make_user()
    q = MagicMock(spec=CallbackQuery)
    q.id = "cb_1"
    q.data = data
    q.from_user = from_user
    q.message = message
    q.message.chat_id = message.chat.id
    q.message.message_id = 1
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message.delete = AsyncMock()
    q.message.reply_text = AsyncMock()
    return q


@pytest.fixture
def mock_context():
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx.user_data = {}
    ctx.bot_data = {}
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


@pytest.fixture
def update_with_message():
    """Update с сообщением (команда /support)."""
    user = _make_user()
    chat = _make_chat()
    message = _make_message(chat=chat, from_user=user)
    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.message = message
    update.callback_query = None
    update.update_id = 1
    return update


@pytest.fixture
def update_with_callback_support_topic():
    """Update с callback support_topic:bug_report."""
    user = _make_user()
    chat = _make_chat()
    message = _make_message(chat=chat, from_user=user)
    message.text = "Режим поддержки"
    q = _make_callback_query("support_topic:bug_report", message=message, from_user=user)
    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.message = None
    update.callback_query = q
    update.update_id = 2
    return update


@pytest.fixture
def update_with_callback_exit_support():
    """Update с callback exit_support."""
    user = _make_user()
    chat = _make_chat()
    message = _make_message(chat=chat, from_user=user)
    message.text = "Режим поддержки"
    q = _make_callback_query("exit_support", message=message, from_user=user)
    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.message = None
    update.callback_query = q
    update.update_id = 3
    return update


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["command", "callback"])
async def test_enter_support_mode_returns_choosing_support_topic(entry, mock_context, update_with_message, update_with_callback_support_topic):
    """Прямой /support или callback enter_support должен переводить в CHOOSING_SUPPORT_TOPIC."""
    from unittest.mock import patch
    with patch("src.bot.handlers.support.SUPPORT_ENABLED", True), patch("src.bot.handlers.support.SUPPORT_CHAT_ID", "-100123"):
        if entry == "command":
            update = update_with_message
        else:
            update = MagicMock(spec=Update)
            update.effective_user = _make_user()
            update.callback_query = _make_callback_query("enter_support")
            update.message = None
        state = await enter_support_mode(update, mock_context)
        assert state == CHOOSING_SUPPORT_TOPIC


@pytest.mark.asyncio
async def test_handle_support_topic_selection_returns_support_mode_and_sets_user_data(mock_context, update_with_callback_support_topic):
    """Выбор темы (support_topic:bug_report) переводит в SUPPORT_MODE и сохраняет тему в user_data."""
    update = update_with_callback_support_topic
    state = await handle_support_topic_selection(update, mock_context)
    assert state == SUPPORT_MODE
    assert mock_context.user_data.get("support_topic") == "bug_report"
    assert mock_context.user_data.get("support_mode") is True


@pytest.mark.asyncio
async def test_exit_support_mode_returns_choosing_action(mock_context, update_with_callback_exit_support):
    """Callback exit_support переводит обратно в CHOOSING_ACTION."""
    update = update_with_callback_exit_support
    state = await exit_support_mode(update, mock_context)
    assert state == CHOOSING_ACTION
    assert mock_context.user_data.get("support_mode") is None
    assert mock_context.user_data.get("support_topic") is None


@pytest.mark.asyncio
async def test_support_disabled_enter_returns_choosing_action(mock_context, update_with_message):
    """При выключенной поддержке enter_support_mode возвращает CHOOSING_ACTION."""
    from unittest.mock import patch
    with patch("src.bot.handlers.support.SUPPORT_ENABLED", False), patch("src.bot.handlers.support.SUPPORT_CHAT_ID", None):
        state = await enter_support_mode(update_with_message, mock_context)
        assert state == CHOOSING_ACTION
