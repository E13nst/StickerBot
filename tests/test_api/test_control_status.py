"""
Тесты для эндпоинта /api/control/status
"""
import pytest
from unittest.mock import Mock, patch
from httpx import AsyncClient

from src.api.server import app


# Тестовый API токен
TEST_API_TOKEN = "test_token_12345"


@pytest.fixture
def api_token():
    """Фикстура для тестового API токена"""
    return TEST_API_TOKEN


@pytest.fixture
def mock_config_manager():
    """Фикстура для мока ConfigManager"""
    mock_cm = Mock()
    mock_cm.get_config.return_value = {
        'enabled': True,
        'mode': 'polling',
        'webhook_url': None
    }
    return mock_cm


@pytest.fixture
def mock_bot_task_none():
    """Фикстура для мока bot_task = None (бот не запущен)"""
    return None


@pytest.fixture
def mock_bot_task_running():
    """Фикстура для мока bot_task запущен (бот работает)"""
    mock_task = Mock()
    mock_task.done.return_value = False
    return mock_task


@pytest.fixture
def mock_bot_task_done():
    """Фикстура для мока bot_task завершен"""
    mock_task = Mock()
    mock_task.done.return_value = True
    return mock_task


@pytest.fixture
async def test_client():
    """Фикстура для создания тестового клиента FastAPI"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


# Тесты успешных сценариев

@pytest.mark.asyncio
async def test_status_success_enabled_polling(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест успешного получения статуса: бот включен, режим polling, бот не запущен"""
    # Arrange
    mock_config_manager.get_config.return_value = {
        'enabled': True,
        'mode': 'polling',
        'webhook_url': None
    }
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.get(
            "/api/control/status",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["mode"] == "polling"
    assert data["webhook_url"] is None
    assert data["bot_running"] is False


@pytest.mark.asyncio
async def test_status_success_enabled_webhook(
    test_client, mock_config_manager, mock_bot_task_running, api_token
):
    """Тест успешного получения статуса: бот включен, режим webhook, бот запущен"""
    # Arrange
    mock_config_manager.get_config.return_value = {
        'enabled': True,
        'mode': 'webhook',
        'webhook_url': 'https://example.com/webhook'
    }
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_running), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.get(
            "/api/control/status",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["mode"] == "webhook"
    assert data["webhook_url"] == "https://example.com/webhook"
    assert data["bot_running"] is True


@pytest.mark.asyncio
async def test_status_success_disabled(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест успешного получения статуса: бот выключен"""
    # Arrange
    mock_config_manager.get_config.return_value = {
        'enabled': False,
        'mode': 'polling',
        'webhook_url': None
    }
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.get(
            "/api/control/status",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["mode"] == "polling"
    assert data["bot_running"] is False


@pytest.mark.asyncio
async def test_status_with_webhook_url(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест успешного получения статуса с webhook_url"""
    # Arrange
    webhook_url = "https://mybot.example.com/webhook"
    mock_config_manager.get_config.return_value = {
        'enabled': True,
        'mode': 'webhook',
        'webhook_url': webhook_url
    }
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.get(
            "/api/control/status",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["mode"] == "webhook"
    assert data["webhook_url"] == webhook_url
    assert data["bot_running"] is False


# Тесты аутентификации

@pytest.mark.asyncio
async def test_status_unauthorized_no_token(test_client, api_token):
    """Тест запроса без токена аутентификации"""
    # Arrange & Act
    with patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        response = await test_client.get("/api/control/status")
    
    # Assert
    # FastAPI вернет 422 для отсутствующего обязательного параметра
    assert response.status_code in [401, 422]
    if response.status_code == 422:
        data = response.json()
        assert "detail" in data
    else:
        data = response.json()
        assert "detail" in data
        assert "Authorization" in data["detail"] or "токен" in data["detail"].lower() or "token" in data["detail"].lower()


@pytest.mark.asyncio
async def test_status_unauthorized_invalid_token(test_client, api_token):
    """Тест запроса с неверным токеном аутентификации"""
    # Arrange & Act
    with patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        response = await test_client.get(
            "/api/control/status",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )
    
    # Assert
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "неверный" in data["detail"].lower() or "invalid" in data["detail"].lower()


@pytest.mark.asyncio
async def test_status_unauthorized_malformed_header(test_client, api_token):
    """Тест запроса с неправильным форматом заголовка Authorization"""
    # Arrange & Act
    with patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        # Тест без префикса "Bearer "
        response1 = await test_client.get(
            "/api/control/status",
            headers={"Authorization": api_token}
        )
        
        # Тест с неправильным форматом
        response2 = await test_client.get(
            "/api/control/status",
            headers={"Authorization": f"Token {api_token}"}
        )
    
    # Assert
    assert response1.status_code == 401
    assert response2.status_code == 401
    data1 = response1.json()
    data2 = response2.json()
    assert "detail" in data1
    assert "detail" in data2


# Тесты граничных случаев

@pytest.mark.asyncio
async def test_status_missing_config_values(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест обработки отсутствующих значений в конфиге (проверка дефолтов)"""
    # Arrange
    # Конфиг с минимальными значениями (без enabled и mode)
    mock_config_manager.get_config.return_value = {
        'webhook_url': None
    }
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.get(
            "/api/control/status",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    # Проверяем, что используются дефолтные значения
    assert data["enabled"] is False  # Дефолт из кода
    assert data["mode"] == "polling"  # Дефолт из кода
    assert data["webhook_url"] is None
    assert data["bot_running"] is False


@pytest.mark.asyncio
async def test_status_bot_task_done(
    test_client, mock_config_manager, mock_bot_task_done, api_token
):
    """Тест статуса когда bot_task существует, но завершен"""
    # Arrange
    mock_config_manager.get_config.return_value = {
        'enabled': True,
        'mode': 'polling',
        'webhook_url': None
    }
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_done), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.get(
            "/api/control/status",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["mode"] == "polling"
    # bot_running должен быть False, так как task.done() возвращает True
    assert data["bot_running"] is False


@pytest.mark.asyncio
async def test_status_empty_config(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест обработки пустого конфига"""
    # Arrange
    mock_config_manager.get_config.return_value = {}
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.get(
            "/api/control/status",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    # Проверяем дефолтные значения
    assert data["enabled"] is False
    assert data["mode"] == "polling"
    assert data["webhook_url"] is None
    assert data["bot_running"] is False


@pytest.mark.asyncio
async def test_status_api_token_not_configured(test_client):
    """Тест когда API_TOKEN не настроен в переменных окружения"""
    # Arrange & Act
    with patch('src.api.routes.control.API_TOKEN', None), \
         patch('src.config.settings.API_TOKEN', None):
        response = await test_client.get(
            "/api/control/status",
            headers={"Authorization": "Bearer any_token"}
        )
    
    # Assert
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "API_TOKEN" in data["detail"] or "токен" in data["detail"].lower()

