import asyncio
import logging
from fastapi import FastAPI, Request, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded

from src.api.routes.webhook import telegram_webhook, set_bot_instance as set_webhook_bot_instance
from src.api.routes.control import (
    initialize as init_control,
    get_status,
    start_bot,
    stop_bot,
    set_mode,
    set_enabled,
    set_bot_instance as set_control_bot_instance,
    set_bot_task,
    ModeRequest,
    EnableRequest,
    StatusResponse,
    get_verify_token_dependency,
    get_token_from_header,
)
from src.api.middleware.rate_limit import limiter, _rate_limit_exceeded_handler
from src.config.settings import WEBHOOK_PATH, WEBHOOK_RATE_LIMIT

logger = logging.getLogger(__name__)

security = HTTPBearer()

app = FastAPI(
    title="StickerBot Control API",
    description="API для управления ботом: переключение режимов polling/webhook, активация/деактивация",
    version="1.0.0"
)

# Настройка rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware для логирования всех входящих запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Логирует все входящие HTTP запросы"""
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Входящий запрос: {request.method} {request.url.path} от IP: {client_ip}")
    
    # Специальное логирование для webhook
    if request.url.path == WEBHOOK_PATH:
        logger.info(f"WEBHOOK запрос от IP: {client_ip}, headers: {dict(request.headers)}")
    
    try:
        response = await call_next(request)
        logger.info(f"Ответ: {request.method} {request.url.path} - {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса {request.method} {request.url.path}: {e}", exc_info=True)
        raise

# Инициализация routes
init_control(security)

# Создаем зависимость для проверки токена
verify_token = get_verify_token_dependency()


@app.post(WEBHOOK_PATH)
@limiter.limit(WEBHOOK_RATE_LIMIT)
async def webhook_endpoint(request: Request):
    """Webhook endpoint для получения обновлений от Telegram"""
    logger.info(f"Запрос дошел до webhook_endpoint: {request.method} {request.url.path}")
    return await telegram_webhook(request)


@app.get("/api/control/status", response_model=StatusResponse, tags=["control"])
async def status_endpoint(token: str = Depends(get_token_from_header)):
    """Получить текущий статус бота"""
    return await get_status(token)


@app.post("/api/control/start", tags=["control"])
async def start_endpoint(token: str = Depends(get_token_from_header)):
    """Запустить бота"""
    result = await start_bot(token)
    # Обновляем экземпляр бота в webhook
    from src.api.routes.control import bot_instance
    set_webhook_bot_instance(bot_instance)
    return result


@app.post("/api/control/stop", tags=["control"])
async def stop_endpoint(token: str = Depends(get_token_from_header)):
    """Остановить бота"""
    return await stop_bot(token)


@app.post("/api/control/mode", tags=["control"])
async def mode_endpoint(request_mode: ModeRequest, token: str = Depends(get_token_from_header)):
    """Переключить режим работы бота"""
    result = await set_mode(request_mode, token)
    # Обновляем экземпляр бота в webhook
    from src.api.routes.control import bot_instance
    set_webhook_bot_instance(bot_instance)
    return result


@app.post("/api/control/enable", tags=["control"])
async def enable_endpoint(request_enable: EnableRequest, token: str = Depends(get_token_from_header)):
    """Включить/выключить бота"""
    return await set_enabled(request_enable, token)


@app.get("/", tags=["info"])
async def root():
    """Корневой эндпоинт с информацией об API"""
    return {
        "service": "StickerBot Control API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health", tags=["info"])
async def health():
    """Проверка работоспособности сервера"""
    from src.api.routes.webhook import bot_instance as webhook_bot_instance
    return {
        "status": "ok",
        "webhook_bot_instance": "установлен" if webhook_bot_instance else "не установлен",
        "webhook_path": WEBHOOK_PATH
    }


# Настраиваем OpenAPI схему для правильного отображения авторизации в Swagger
# Должно быть после регистрации всех routes
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Добавляем security схему
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Введите ваш API токен"
        }
    }
    # Добавляем security ко всем защищенным эндпоинтам и убираем лишние параметры
    for path, path_item in openapi_schema.get("paths", {}).items():
        if path.startswith("/api/control"):
            for method in path_item:
                if method in ["get", "post", "put", "delete", "patch"]:
                    method_item = path_item[method]
                    # Добавляем security
                    if "security" not in method_item:
                        method_item["security"] = [{"Bearer": []}]
                    # Убираем лишние параметры (scheme, credentials, Authorization)
                    # так как они должны быть только в security схеме
                    if "parameters" in method_item:
                        method_item["parameters"] = [
                            p for p in method_item["parameters"]
                            if p.get("name") not in ["scheme", "credentials", "Authorization"]
                        ]
                        # Если параметров не осталось, удаляем ключ
                        if not method_item["parameters"]:
                            del method_item["parameters"]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi


async def run_api_server():
    """Запуск API сервера"""
    import uvicorn
    from src.config.settings import API_PORT
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=API_PORT,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

