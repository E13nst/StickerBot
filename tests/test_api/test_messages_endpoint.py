"""
Smoke-тесты для эндпоинта POST /api/messages/send.

Ручная проверка (curl), когда бот запущен и API_TOKEN задан:

  # 401 без токена
  curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:80/api/messages/send \
    -H "Content-Type: application/json" -d '{"text":"Hi","user_id":123}'

  # 422 — ни user_id, ни chat_id
  curl -s -X POST http://localhost:80/api/messages/send \
    -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
    -d '{"text":"Hi"}'

  # 422 — оба указаны
  curl -s -X POST http://localhost:80/api/messages/send \
    -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
    -d '{"text":"Hi","user_id":1,"chat_id":2}'

  # 503 если бот не запущен; 200 + body при успехе
  curl -s -X POST http://localhost:80/api/messages/send \
    -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
    -d '{"text":"Hello","user_id":YOUR_TELEGRAM_USER_ID}'
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from httpx import AsyncClient

from src.api.server import app

TEST_API_TOKEN = "test_token_messages"


@pytest.fixture
def api_token():
    return TEST_API_TOKEN


@pytest.fixture
async def test_client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


def make_mock_bot_send_message(chat_id: int = 12345, message_id: int = 1):
    """Мок bot.send_message, возвращающий объект с chat_id и message_id."""
    async def send_message(**kwargs):
        m = Mock()
        m.chat_id = kwargs.get("chat_id", chat_id)
        m.message_id = message_id
        return m
    return AsyncMock(side_effect=send_message)


@pytest.fixture
def mock_bot_initialized():
    """Бот инициализирован, send_message возвращает успешный ответ."""
    mock_bot = Mock()
    mock_bot.application = Mock()
    mock_bot.application.bot = Mock()
    mock_bot.application.bot.send_message = make_mock_bot_send_message(chat_id=999, message_id=42)
    return mock_bot


# ==================== Авторизация (401) ====================


@pytest.mark.asyncio
async def test_send_message_401_without_auth(test_client, mock_bot_initialized):
    """Без заголовка Authorization возвращается 401."""
    with patch("src.api.routes.messages.bot_instance", mock_bot_initialized):
        response = await test_client.post(
            "/api/messages/send",
            json={"text": "Hi", "user_id": 123},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_send_message_401_wrong_token(test_client, mock_bot_initialized, api_token):
    """Неверный Bearer токен — 401."""
    with patch("src.api.routes.messages.bot_instance", mock_bot_initialized), \
         patch("src.api.routes.control.API_TOKEN", api_token), \
         patch("src.config.settings.API_TOKEN", api_token):
        response = await test_client.post(
            "/api/messages/send",
            headers={"Authorization": "Bearer wrong_token"},
            json={"text": "Hi", "user_id": 123},
        )
    assert response.status_code == 401


# ==================== Валидация target (422) ====================


@pytest.mark.asyncio
async def test_send_message_422_neither_user_id_nor_chat_id(test_client, mock_bot_initialized, api_token):
    """Не указан ни user_id, ни chat_id — 422."""
    with patch("src.api.routes.messages.bot_instance", mock_bot_initialized), \
         patch("src.api.routes.control.API_TOKEN", api_token), \
         patch("src.config.settings.API_TOKEN", api_token):
        response = await test_client.post(
            "/api/messages/send",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"text": "Hi"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_message_422_both_user_id_and_chat_id(test_client, mock_bot_initialized, api_token):
    """Указаны и user_id, и chat_id — 422."""
    with patch("src.api.routes.messages.bot_instance", mock_bot_initialized), \
         patch("src.api.routes.control.API_TOKEN", api_token), \
         patch("src.config.settings.API_TOKEN", api_token):
        response = await test_client.post(
            "/api/messages/send",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"text": "Hi", "user_id": 1, "chat_id": 2},
        )
    assert response.status_code == 422


# ==================== Бот не инициализирован (503) ====================


@pytest.mark.asyncio
async def test_send_message_503_bot_not_initialized(test_client, api_token):
    """Бот не инициализирован — 503."""
    with patch("src.api.routes.messages.bot_instance", None), \
         patch("src.api.routes.control.API_TOKEN", api_token), \
         patch("src.config.settings.API_TOKEN", api_token):
        response = await test_client.post(
            "/api/messages/send",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"text": "Hi", "user_id": 123},
        )
    assert response.status_code == 503
    assert "not initialized" in response.json().get("detail", "").lower()


# ==================== Успешная отправка ====================


@pytest.mark.asyncio
async def test_send_message_200_with_user_id(test_client, mock_bot_initialized, api_token):
    """Успешная отправка по user_id — 200, в ответе chat_id, message_id, status=sent."""
    with patch("src.api.routes.messages.bot_instance", mock_bot_initialized), \
         patch("src.api.routes.control.API_TOKEN", api_token), \
         patch("src.config.settings.API_TOKEN", api_token):
        response = await test_client.post(
            "/api/messages/send",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"text": "Hello", "user_id": 123},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "sent"
    assert data["chat_id"] == 999
    assert data["message_id"] == 42
    assert data.get("parse_mode") == "MarkdownV2"
    mock_bot_initialized.application.bot.send_message.assert_called_once()
    call_kw = mock_bot_initialized.application.bot.send_message.call_args[1]
    assert call_kw["chat_id"] == 123
    assert call_kw["text"] == "Hello"
    assert call_kw["parse_mode"] == "MarkdownV2"


@pytest.mark.asyncio
async def test_send_message_200_with_chat_id(test_client, mock_bot_initialized, api_token):
    """Успешная отправка по chat_id — 200."""
    with patch("src.api.routes.messages.bot_instance", mock_bot_initialized), \
         patch("src.api.routes.control.API_TOKEN", api_token), \
         patch("src.config.settings.API_TOKEN", api_token):
        response = await test_client.post(
            "/api/messages/send",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"text": "Group message", "chat_id": -1001234567890},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "sent"
    assert data["chat_id"] == 999
    assert data["message_id"] == 42
    call_kw = mock_bot_initialized.application.bot.send_message.call_args[1]
    assert call_kw["chat_id"] == -1001234567890
    assert call_kw["text"] == "Group message"


@pytest.mark.asyncio
async def test_send_message_200_plain_no_parse_mode(test_client, mock_bot_initialized, api_token):
    """parse_mode=plain — в Telegram не передаётся parse_mode, в ответе parse_mode null."""
    with patch("src.api.routes.messages.bot_instance", mock_bot_initialized), \
         patch("src.api.routes.control.API_TOKEN", api_token), \
         patch("src.config.settings.API_TOKEN", api_token):
        response = await test_client.post(
            "/api/messages/send",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"text": "Plain text", "user_id": 1, "parse_mode": "plain"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["parse_mode"] is None
    call_kw = mock_bot_initialized.application.bot.send_message.call_args[1]
    assert "parse_mode" not in call_kw or call_kw.get("parse_mode") is None
