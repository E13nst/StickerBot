"""
Тесты для WaveSpeedClient
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx
from httpx import Response

from src.managers.wavespeed_client import WaveSpeedClient


@pytest.fixture
def api_key():
    """Фикстура для тестового API ключа"""
    return "test_api_key_12345"


@pytest.fixture
def client(api_key):
    """Фикстура для создания клиента"""
    return WaveSpeedClient(api_key)


@pytest.fixture
def mock_httpx_client():
    """Фикстура для мока httpx.AsyncClient"""
    mock_client = AsyncMock()
    return mock_client


# ==================== Тесты для submit_flux_schnell ====================

@pytest.mark.asyncio
async def test_submit_flux_schnell_new_format_success(client, mock_httpx_client):
    """Тест успешной отправки запроса с новым форматом ответа (с вложенным data)"""
    # Arrange
    new_format_response = {
        "code": 200,
        "message": "success",
        "data": {
            "id": "24d877a42de446a3ab3f0339564dfdd4",
            "model": "wavespeed-ai/flux-schnell",
            "outputs": [],
            "urls": {
                "get": "https://api.wavespeed.ai/api/v3/predictions/24d877a42de446a3ab3f0339564dfdd4/result"
            },
            "status": "created",
        }
    }
    
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = new_format_response
    mock_response.raise_for_status = Mock()
    mock_httpx_client.post = AsyncMock(return_value=mock_response)
    
    client._client = mock_httpx_client
    
    # Act
    request_id = await client.submit_flux_schnell("test prompt")
    
    # Assert
    assert request_id == "24d877a42de446a3ab3f0339564dfdd4"
    mock_httpx_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_submit_flux_schnell_old_format_success(client, mock_httpx_client):
    """Тест успешной отправки запроса со старым форматом ответа (обратная совместимость)"""
    # Arrange
    old_format_response = {
        "id": "old_format_id_12345",
        "status": "created",
    }
    
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = old_format_response
    mock_response.raise_for_status = Mock()
    mock_httpx_client.post = AsyncMock(return_value=mock_response)
    
    client._client = mock_httpx_client
    
    # Act
    request_id = await client.submit_flux_schnell("test prompt")
    
    # Assert
    assert request_id == "old_format_id_12345"
    mock_httpx_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_submit_flux_schnell_request_id_fallback(client, mock_httpx_client):
    """Тест извлечения requestId как fallback для id"""
    # Arrange
    response_with_request_id = {
        "code": 200,
        "message": "success",
        "data": {
            "requestId": "fallback_request_id_67890",
            "status": "created",
        }
    }
    
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = response_with_request_id
    mock_response.raise_for_status = Mock()
    mock_httpx_client.post = AsyncMock(return_value=mock_response)
    
    client._client = mock_httpx_client
    
    # Act
    request_id = await client.submit_flux_schnell("test prompt")
    
    # Assert
    assert request_id == "fallback_request_id_67890"


@pytest.mark.asyncio
async def test_submit_flux_schnell_no_id_error(client, mock_httpx_client):
    """Тест ошибки при отсутствии id в ответе"""
    # Arrange
    invalid_response = {
        "code": 200,
        "message": "success",
        "data": {
            "status": "created",
            # нет id или requestId
        }
    }
    
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = invalid_response
    mock_response.raise_for_status = Mock()
    mock_httpx_client.post = AsyncMock(return_value=mock_response)
    
    client._client = mock_httpx_client
    
    # Act & Assert
    with pytest.raises(ValueError, match="Invalid response from WaveSpeed API"):
        await client.submit_flux_schnell("test prompt")


@pytest.mark.asyncio
async def test_submit_flux_schnell_retry_on_500(client, mock_httpx_client):
    """Тест ретрая при ошибке 500"""
    # Arrange
    error_response = Mock(spec=Response)
    error_response.status_code = 500
    http_error = httpx.HTTPStatusError("Server Error", request=Mock(), response=error_response)
    
    success_response = Mock(spec=Response)
    success_response.json.return_value = {
        "code": 200,
        "data": {"id": "retry_success_id"}
    }
    success_response.raise_for_status = Mock()
    
    mock_httpx_client.post = AsyncMock(side_effect=[http_error, success_response])
    
    client._client = mock_httpx_client
    
    # Act
    with patch('asyncio.sleep', new_callable=AsyncMock):
        request_id = await client.submit_flux_schnell("test prompt")
    
    # Assert
    assert request_id == "retry_success_id"
    assert mock_httpx_client.post.call_count == 2


@pytest.mark.asyncio
async def test_submit_flux_schnell_retry_on_network_error(client, mock_httpx_client):
    """Тест ретрая при сетевой ошибке"""
    # Arrange
    network_error = httpx.RequestError("Network error")
    
    success_response = Mock(spec=Response)
    success_response.json.return_value = {
        "code": 200,
        "data": {"id": "network_retry_success_id"}
    }
    success_response.raise_for_status = Mock()
    
    mock_httpx_client.post = AsyncMock(side_effect=[network_error, success_response])
    
    client._client = mock_httpx_client
    
    # Act
    with patch('asyncio.sleep', new_callable=AsyncMock):
        request_id = await client.submit_flux_schnell("test prompt")
    
    # Assert
    assert request_id == "network_retry_success_id"
    assert mock_httpx_client.post.call_count == 2


# ==================== Тесты для submit_background_remover ====================

@pytest.mark.asyncio
async def test_submit_background_remover_new_format_success(client, mock_httpx_client):
    """Тест успешной отправки запроса на удаление фона с новым форматом ответа"""
    # Arrange
    new_format_response = {
        "code": 200,
        "message": "success",
        "data": {
            "id": "bg_remover_id_12345",
            "status": "created",
        }
    }
    
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = new_format_response
    mock_response.raise_for_status = Mock()
    mock_httpx_client.post = AsyncMock(return_value=mock_response)
    
    client._client = mock_httpx_client
    
    # Act
    request_id = await client.submit_background_remover("https://example.com/image.png")
    
    # Assert
    assert request_id == "bg_remover_id_12345"
    mock_httpx_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_submit_background_remover_old_format_success(client, mock_httpx_client):
    """Тест успешной отправки запроса на удаление фона со старым форматом ответа"""
    # Arrange
    old_format_response = {
        "id": "old_bg_remover_id",
        "status": "created",
    }
    
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = old_format_response
    mock_response.raise_for_status = Mock()
    mock_httpx_client.post = AsyncMock(return_value=mock_response)
    
    client._client = mock_httpx_client
    
    # Act
    request_id = await client.submit_background_remover("https://example.com/image.png")
    
    # Assert
    assert request_id == "old_bg_remover_id"


# ==================== Тесты для get_prediction_result ====================

@pytest.mark.asyncio
async def test_get_prediction_result_success_with_image(client, mock_httpx_client):
    """Тест успешного получения результата с изображением"""
    # Arrange
    result_response = {
        "status": "completed",
        "outputs": [
            "https://example.com/generated_image_1.png",
            "https://example.com/generated_image_2.png"
        ],
        "executionTime": 5.2,
        "id": "result_id_12345"
    }
    
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = result_response
    mock_response.raise_for_status = Mock()
    mock_httpx_client.get = AsyncMock(return_value=mock_response)
    
    client._client = mock_httpx_client
    
    # Act
    result = await client.get_prediction_result("result_id_12345")
    
    # Assert
    assert result is not None
    assert result["status"] == "completed"
    assert len(result["outputs"]) == 2
    assert "https://example.com/generated_image_1.png" in result["outputs"]
    assert "https://example.com/generated_image_2.png" in result["outputs"]
    assert result["executionTime"] == 5.2
    mock_httpx_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_prediction_result_pending_status(client, mock_httpx_client):
    """Тест получения результата со статусом pending"""
    # Arrange
    result_response = {
        "status": "pending",
        "outputs": [],
        "executionTime": 0,
    }
    
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = result_response
    mock_response.raise_for_status = Mock()
    mock_httpx_client.get = AsyncMock(return_value=mock_response)
    
    client._client = mock_httpx_client
    
    # Act
    result = await client.get_prediction_result("result_id_12345")
    
    # Assert
    assert result is not None
    assert result["status"] == "pending"
    assert result["outputs"] == []


@pytest.mark.asyncio
async def test_get_prediction_result_failed_status(client, mock_httpx_client):
    """Тест получения результата со статусом failed"""
    # Arrange
    result_response = {
        "status": "failed",
        "error": "Generation failed",
        "outputs": [],
    }
    
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = result_response
    mock_response.raise_for_status = Mock()
    mock_httpx_client.get = AsyncMock(return_value=mock_response)
    
    client._client = mock_httpx_client
    
    # Act
    result = await client.get_prediction_result("result_id_12345")
    
    # Assert
    assert result is not None
    assert result["status"] == "failed"
    assert result["error"] == "Generation failed"


@pytest.mark.asyncio
async def test_get_prediction_result_not_found(client, mock_httpx_client):
    """Тест обработки 404 ошибки (результат не найден)"""
    # Arrange
    error_response = Mock(spec=Response)
    error_response.status_code = 404
    http_error = httpx.HTTPStatusError("Not Found", request=Mock(), response=error_response)
    
    mock_httpx_client.get = AsyncMock(side_effect=http_error)
    
    client._client = mock_httpx_client
    
    # Act
    result = await client.get_prediction_result("nonexistent_id")
    
    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_get_prediction_result_network_error(client, mock_httpx_client):
    """Тест обработки сетевой ошибки при получении результата"""
    # Arrange
    network_error = httpx.RequestError("Network error")
    
    mock_httpx_client.get = AsyncMock(side_effect=network_error)
    
    client._client = mock_httpx_client
    
    # Act
    result = await client.get_prediction_result("result_id_12345")
    
    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_get_prediction_result_with_image_urls(client, mock_httpx_client):
    """Тест что результат содержит URL изображений"""
    # Arrange
    result_response = {
        "status": "completed",
        "outputs": [
            "https://cdn.wavespeed.ai/predictions/abc123/image1.png",
            "https://cdn.wavespeed.ai/predictions/abc123/image2.png"
        ],
        "executionTime": 3.5,
    }
    
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = result_response
    mock_response.raise_for_status = Mock()
    mock_httpx_client.get = AsyncMock(return_value=mock_response)
    
    client._client = mock_httpx_client
    
    # Act
    result = await client.get_prediction_result("result_id_12345")
    
    # Assert
    assert result is not None
    assert result["status"] == "completed"
    assert "outputs" in result
    assert isinstance(result["outputs"], list)
    assert len(result["outputs"]) > 0
    # Проверяем, что все outputs - это строки (URL)
    for output in result["outputs"]:
        assert isinstance(output, str)
        assert output.startswith("http")


@pytest.mark.asyncio
async def test_get_prediction_result_empty_outputs(client, mock_httpx_client):
    """Тест результата с пустым списком outputs"""
    # Arrange
    result_response = {
        "status": "processing",
        "outputs": [],
        "executionTime": 1.0,
    }
    
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = result_response
    mock_response.raise_for_status = Mock()
    mock_httpx_client.get = AsyncMock(return_value=mock_response)
    
    client._client = mock_httpx_client
    
    # Act
    result = await client.get_prediction_result("result_id_12345")
    
    # Assert
    assert result is not None
    assert result["status"] == "processing"
    assert result["outputs"] == []


# ==================== Тесты для инициализации ====================

def test_client_init_with_empty_api_key():
    """Тест инициализации клиента с пустым API ключом"""
    with pytest.raises(ValueError, match="WAVESPEED_API_KEY is required"):
        WaveSpeedClient("")


def test_client_init_with_none_api_key():
    """Тест инициализации клиента с None API ключом"""
    with pytest.raises(ValueError, match="WAVESPEED_API_KEY is required"):
        WaveSpeedClient(None)


@pytest.mark.asyncio
async def test_client_close(client, mock_httpx_client):
    """Тест закрытия клиента"""
    client._client = mock_httpx_client
    mock_httpx_client.aclose = AsyncMock()
    
    await client.close()
    
    mock_httpx_client.aclose.assert_called_once()

