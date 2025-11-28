"""
Тесты для эндпоинтов /api/control/* (start, stop, mode, enable)
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from httpx import AsyncClient
import asyncio

from src.api.server import app


# Тестовый API токен
TEST_API_TOKEN = "test_token_12345"
TEST_WEBHOOK_URL = "https://example.com/webhook"


@pytest.fixture
def api_token():
    """Фикстура для тестового API токена"""
    return TEST_API_TOKEN


@pytest.fixture
def webhook_url():
    """Фикстура для тестового webhook URL"""
    return TEST_WEBHOOK_URL


@pytest.fixture
def mock_config_manager():
    """Фикстура для мока ConfigManager"""
    mock_cm = Mock()
    mock_cm.get_config.return_value = {
        'enabled': True,
        'mode': 'polling',
        'webhook_url': None
    }
    # Моки для методов изменения конфига
    mock_cm.set_mode = Mock()
    mock_cm.set_enabled = Mock()
    mock_cm.set_webhook_url = Mock()
    return mock_cm


@pytest.fixture
def mock_bot_instance():
    """Фикстура для мока экземпляра бота"""
    mock_bot = Mock()
    mock_bot.stop = AsyncMock()
    return mock_bot


@pytest.fixture
def mock_bot_task_none():
    """Фикстура для мока bot_task = None (бот не запущен)"""
    return None


def create_awaitable_mock_task():
    """Создает awaitable мок для bot_task"""
    async def cancelled_coro():
        raise asyncio.CancelledError()
    
    class AwaitableMock:
        def __init__(self):
            self._done = False
            self._cancelled = False
            self._coro = cancelled_coro()
            self.cancel = Mock()
        
        def done(self):
            return self._done
        
        def __await__(self):
            return self._coro.__await__()
    
    return AwaitableMock()


@pytest.fixture
def mock_bot_task_running():
    """Фикстура для мока bot_task запущен (бот работает)"""
    return create_awaitable_mock_task()


@pytest.fixture
async def test_client():
    """Фикстура для создания тестового клиента FastAPI"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


# ==================== Тесты для /api/control/start ====================

@pytest.mark.asyncio
async def test_start_bot_success_polling(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест успешного запуска бота в режиме polling"""
    # Arrange
    mock_config_manager.get_config.return_value = {
        'enabled': True,
        'mode': 'polling',
        'webhook_url': None
    }
    
    mock_bot_class = Mock()
    mock_bot_instance = Mock()
    mock_bot_class.return_value = mock_bot_instance
    mock_bot_instance.run_polling = AsyncMock()
    
    mock_task = Mock()
    mock_task.done.return_value = False
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.bot_instance', None), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token), \
         patch('src.bot.bot.StickerBot', mock_bot_class), \
         patch('asyncio.create_task', return_value=mock_task) as mock_create_task:
        
        # Act
        response = await test_client.post(
            "/api/control/start",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert data["mode"] == "polling"
    assert "message" in data
    mock_bot_class.assert_called_once()
    mock_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_start_bot_success_webhook(
    test_client, mock_config_manager, mock_bot_task_none, api_token, webhook_url
):
    """Тест успешного запуска бота в режиме webhook"""
    # Arrange
    mock_config_manager.get_config.return_value = {
        'enabled': True,
        'mode': 'webhook',
        'webhook_url': webhook_url
    }
    
    mock_bot_class = Mock()
    mock_bot_instance = Mock()
    mock_bot_class.return_value = mock_bot_instance
    mock_bot_instance.run_webhook = AsyncMock()
    
    mock_task = Mock()
    mock_task.done.return_value = False
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.bot_instance', None), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token), \
         patch('src.api.routes.control.WEBHOOK_URL', webhook_url), \
         patch('src.config.settings.WEBHOOK_URL', webhook_url), \
         patch('src.bot.bot.StickerBot', mock_bot_class), \
         patch('asyncio.create_task', return_value=mock_task) as mock_create_task:
        
        # Act
        response = await test_client.post(
            "/api/control/start",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert data["mode"] == "webhook"
    assert "message" in data
    mock_bot_class.assert_called_once()
    mock_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_start_bot_already_running(
    test_client, mock_config_manager, mock_bot_task_running, api_token
):
    """Тест попытки запуска бота, когда он уже запущен"""
    # Arrange
    mock_config_manager.get_config.return_value = {
        'enabled': True,
        'mode': 'polling',
        'webhook_url': None
    }
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_running), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.post(
            "/api/control/start",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "уже запущен" in data["detail"].lower() or "already" in data["detail"].lower()


@pytest.mark.asyncio
async def test_start_bot_disabled(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест попытки запуска бота, когда он отключен в конфиге"""
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
        response = await test_client.post(
            "/api/control/start",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "отключен" in data["detail"].lower() or "disabled" in data["detail"].lower()


@pytest.mark.asyncio
async def test_start_bot_webhook_no_url(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест попытки запуска бота в режиме webhook без WEBHOOK_URL"""
    # Arrange
    mock_config_manager.get_config.return_value = {
        'enabled': True,
        'mode': 'webhook',
        'webhook_url': None
    }
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token), \
         patch('src.api.routes.control.WEBHOOK_URL', None), \
         patch('src.config.settings.WEBHOOK_URL', None):
        
        # Act
        response = await test_client.post(
            "/api/control/start",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "WEBHOOK_URL" in data["detail"]


@pytest.mark.asyncio
async def test_start_bot_unauthorized(test_client):
    """Тест запуска бота без авторизации"""
    # Arrange & Act
    response = await test_client.post("/api/control/start")
    
    # Assert
    assert response.status_code in [401, 422]


# ==================== Тесты для /api/control/stop ====================

@pytest.mark.asyncio
async def test_stop_bot_success(
    test_client, mock_config_manager, mock_bot_task_running, mock_bot_instance, api_token
):
    """Тест успешной остановки бота"""
    # Arrange
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_running), \
         patch('src.api.routes.control.bot_instance', mock_bot_instance), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.post(
            "/api/control/stop",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stopped"
    assert "message" in data
    mock_bot_instance.stop.assert_called_once()


@pytest.mark.asyncio
async def test_stop_bot_not_running(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест попытки остановки бота, когда он не запущен"""
    # Arrange
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.post(
            "/api/control/stop",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "не запущен" in data["detail"].lower() or "not running" in data["detail"].lower()


@pytest.mark.asyncio
async def test_stop_bot_task_done(
    test_client, mock_config_manager, mock_bot_instance, api_token
):
    """Тест попытки остановки бота, когда task уже завершен"""
    # Arrange
    mock_task_done = Mock()
    mock_task_done.done.return_value = True
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_task_done), \
         patch('src.api.routes.control.bot_instance', mock_bot_instance), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.post(
            "/api/control/stop",
            headers={"Authorization": f"Bearer {api_token}"}
        )
    
    # Assert
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_stop_bot_unauthorized(test_client):
    """Тест остановки бота без авторизации"""
    # Arrange & Act
    response = await test_client.post("/api/control/stop")
    
    # Assert
    assert response.status_code in [401, 422]


# ==================== Тесты для /api/control/mode ====================

@pytest.mark.asyncio
async def test_set_mode_polling_success(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест успешного переключения режима на polling"""
    # Arrange
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.post(
            "/api/control/mode",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"mode": "polling"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    assert data["mode"] == "polling"
    assert data["enabled"] is True
    assert "message" in data
    mock_config_manager.set_mode.assert_called_once_with("polling")
    mock_config_manager.set_enabled.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_set_mode_webhook_success(
    test_client, mock_config_manager, mock_bot_task_none, api_token, webhook_url
):
    """Тест успешного переключения режима на webhook"""
    # Arrange
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token), \
         patch('src.api.routes.control.WEBHOOK_URL', webhook_url), \
         patch('src.config.settings.WEBHOOK_URL', webhook_url):
        
        # Act
        response = await test_client.post(
            "/api/control/mode",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"mode": "webhook"}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    assert data["mode"] == "webhook"
    assert data["enabled"] is True
    assert "message" in data
    mock_config_manager.set_mode.assert_called_once_with("webhook")
    mock_config_manager.set_enabled.assert_called_once_with(True)
    mock_config_manager.set_webhook_url.assert_called_once_with(webhook_url)


@pytest.mark.asyncio
async def test_set_mode_invalid_mode(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест переключения на неверный режим"""
    # Arrange
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.post(
            "/api/control/mode",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"mode": "invalid_mode"}
        )
    
    # Assert
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "неверный" in data["detail"].lower() or "invalid" in data["detail"].lower()


@pytest.mark.asyncio
async def test_set_mode_webhook_no_url(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест переключения на webhook без WEBHOOK_URL"""
    # Arrange
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token), \
         patch('src.api.routes.control.WEBHOOK_URL', None), \
         patch('src.config.settings.WEBHOOK_URL', None):
        
        # Act
        response = await test_client.post(
            "/api/control/mode",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"mode": "webhook"}
        )
    
    # Assert
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "WEBHOOK_URL" in data["detail"]


@pytest.mark.asyncio
async def test_set_mode_stops_running_bot(
    test_client, mock_config_manager, mock_bot_instance, api_token
):
    """Тест что переключение режима останавливает запущенного бота"""
    # Arrange
    mock_task = create_awaitable_mock_task()
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_task), \
         patch('src.api.routes.control.bot_instance', mock_bot_instance), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.post(
            "/api/control/mode",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"mode": "polling"}
        )
    
    # Assert
    assert response.status_code == 200
    mock_bot_instance.stop.assert_called_once()
    mock_task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_set_mode_unauthorized(test_client):
    """Тест переключения режима без авторизации"""
    # Arrange & Act
    response = await test_client.post(
        "/api/control/mode",
        json={"mode": "polling"}
    )
    
    # Assert
    assert response.status_code in [401, 422]


@pytest.mark.asyncio
async def test_set_mode_missing_field(test_client, api_token):
    """Тест переключения режима без поля mode"""
    # Arrange & Act
    with patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        response = await test_client.post(
            "/api/control/mode",
            headers={"Authorization": f"Bearer {api_token}"},
            json={}
        )
    
    # Assert
    assert response.status_code == 422


# ==================== Тесты для /api/control/enable ====================

@pytest.mark.asyncio
async def test_enable_bot_success(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест успешного включения бота"""
    # Arrange
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.post(
            "/api/control/enable",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"enabled": True}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    assert data["enabled"] is True
    assert "message" in data
    mock_config_manager.set_enabled.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_disable_bot_success(
    test_client, mock_config_manager, mock_bot_task_none, api_token
):
    """Тест успешного выключения бота"""
    # Arrange
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_bot_task_none), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.post(
            "/api/control/enable",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"enabled": False}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    assert data["enabled"] is False
    assert "message" in data
    mock_config_manager.set_enabled.assert_called_once_with(False)


@pytest.mark.asyncio
async def test_disable_bot_stops_running(
    test_client, mock_config_manager, mock_bot_instance, api_token
):
    """Тест что выключение бота останавливает запущенного бота"""
    # Arrange
    mock_task = create_awaitable_mock_task()
    
    with patch('src.api.routes.control.get_config_manager', return_value=mock_config_manager), \
         patch('src.api.routes.control.bot_task', mock_task), \
         patch('src.api.routes.control.bot_instance', mock_bot_instance), \
         patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        
        # Act
        response = await test_client.post(
            "/api/control/enable",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"enabled": False}
        )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    mock_bot_instance.stop.assert_called_once()
    mock_task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_enable_bot_unauthorized(test_client):
    """Тест включения/выключения бота без авторизации"""
    # Arrange & Act
    response = await test_client.post(
        "/api/control/enable",
        json={"enabled": True}
    )
    
    # Assert
    assert response.status_code in [401, 422]


@pytest.mark.asyncio
async def test_enable_bot_missing_field(test_client, api_token):
    """Тест включения/выключения бота без поля enabled"""
    # Arrange & Act
    with patch('src.api.routes.control.API_TOKEN', api_token), \
         patch('src.config.settings.API_TOKEN', api_token):
        response = await test_client.post(
            "/api/control/enable",
            headers={"Authorization": f"Bearer {api_token}"},
            json={}
        )
    
    # Assert
    assert response.status_code == 422

