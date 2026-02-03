"""API endpoints для работы с платежами через Telegram Stars"""
import logging
import uuid
import json
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel, Field
from telegram.error import TelegramError

from src.config.settings import (
    PAYMENTS_ENABLED,
    BOT_TOKEN,
    PAYMENT_INITDATA_MAX_AGE_SECONDS,
    WEBHOOK_RATE_LIMIT
)
from src.utils.telegram_auth import validate_telegram_init_data, extract_user_id, TelegramAuthError
from src.api.middleware.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])

# Глобальная переменная для бота (устанавливается из server.py)
bot_instance = None


def set_bot_instance(instance):
    """Установить экземпляр бота"""
    global bot_instance
    bot_instance = instance
    logger.info("Bot instance set for payments router")


def validate_webhook_url(url: str) -> bool:
    """
    Валидация webhook URL
    
    Args:
        url: URL для проверки
        
    Returns:
        True если URL валидный
        
    Raises:
        HTTPException если URL невалидный
    """
    try:
        parsed = urlparse(url)
        
        # Проверка HTTPS
        if parsed.scheme != 'https':
            raise HTTPException(
                status_code=400,
                detail="backend_webhook_url must use HTTPS protocol"
            )
        
        # Проверка наличия хоста
        if not parsed.netloc:
            raise HTTPException(
                status_code=400,
                detail="backend_webhook_url must have a valid hostname"
            )
        
        # Дополнительные проверки безопасности
        # Запрет localhost/127.0.0.1 в production (опционально)
        if parsed.netloc.startswith('localhost') or parsed.netloc.startswith('127.0.0.1'):
            logger.warning(f"Webhook URL uses localhost: {url}")
        
        return True
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid backend_webhook_url format: {str(e)}"
        )


class CreateInvoiceRequest(BaseModel):
    """Запрос на создание invoice для оплаты Stars"""
    user_id: int = Field(..., description="ID пользователя Telegram")
    title: str = Field(..., min_length=1, max_length=32, description="Заголовок платежа")
    description: str = Field(..., min_length=1, max_length=255, description="Описание платежа")
    amount_stars: int = Field(..., gt=0, description="Количество Stars для списания")
    payload: str = Field(..., max_length=128, description="Произвольные данные для Mini App")
    return_link: bool = Field(False, description="Если true, возвращает invoice_link вместо отправки в чат")
    backend_webhook_url: Optional[str] = Field(None, description="URL для уведомления backend о платеже")


class CreateInvoiceResponse(BaseModel):
    """Ответ на создание invoice"""
    ok: bool
    invoice_sent: bool = False
    invoice_link: Optional[str] = None
    error: Optional[str] = None


@router.post("/create-invoice", response_model=CreateInvoiceResponse)
@limiter.limit(WEBHOOK_RATE_LIMIT)
async def create_invoice(
    request: Request,
    invoice_request: CreateInvoiceRequest,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """
    Создает invoice для оплаты через Telegram Stars.
    
    Вызывается из Mini App когда пользователь хочет совершить покупку.
    
    Headers:
        X-Telegram-Init-Data: данные из Telegram.WebApp.initData
    
    Returns:
        CreateInvoiceResponse с результатом операции
    """
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(
        f"create_invoice called: user_id={invoice_request.user_id}, "
        f"amount={invoice_request.amount_stars}, "
        f"from IP={client_ip}"
    )
    
    # Проверка что платежи включены
    if not PAYMENTS_ENABLED:
        logger.warning(f"Payment attempt but PAYMENTS_ENABLED=false, IP={client_ip}")
        raise HTTPException(
            status_code=503,
            detail="Payments are currently disabled"
        )
    
    # Проверка что бот инициализирован
    if not bot_instance or not bot_instance.application:
        logger.error(f"Payment attempt but bot not initialized, IP={client_ip}")
        raise HTTPException(
            status_code=503,
            detail="Bot not initialized"
        )
    
    # Валидация X-Telegram-Init-Data header
    if not x_telegram_init_data:
        logger.warning(f"create_invoice called without X-Telegram-Init-Data header, IP={client_ip}")
        raise HTTPException(
            status_code=401,
            detail="Missing X-Telegram-Init-Data header"
        )
    
    # Валидация initData
    try:
        validated_data = validate_telegram_init_data(
            init_data=x_telegram_init_data,
            bot_token=BOT_TOKEN,
            max_age_seconds=PAYMENT_INITDATA_MAX_AGE_SECONDS
        )
        
        logger.info(f"initData validated successfully for payment request")
        
    except TelegramAuthError as e:
        logger.warning(f"initData validation failed: {e}, IP={client_ip}")
        raise HTTPException(
            status_code=401,
            detail=f"Invalid initData: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error validating initData: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal error validating authorization"
        )
    
    # Проверка соответствия user_id
    validated_user_id = extract_user_id(validated_data)
    if validated_user_id is None:
        logger.error(f"Could not extract user_id from validated initData")
        raise HTTPException(
            status_code=401,
            detail="Invalid user data in initData"
        )
    
    if validated_user_id != invoice_request.user_id:
        logger.warning(
            f"user_id mismatch: initData={validated_user_id}, "
            f"request={invoice_request.user_id}, IP={client_ip}"
        )
        raise HTTPException(
            status_code=403,
            detail="user_id in request does not match authenticated user"
        )
    
    # Валидация backend_webhook_url если предоставлен
    if invoice_request.backend_webhook_url:
        validate_webhook_url(invoice_request.backend_webhook_url)
        logger.info(f"Backend webhook URL validated: {invoice_request.backend_webhook_url[:50]}...")
    
    # Генерируем уникальный invoice_id
    invoice_id = str(uuid.uuid4())
    
    # Создаём комбинированный payload: {invoice_id: ..., original_payload: ...}
    combined_payload = json.dumps({
        "invoice_id": invoice_id,
        "original_payload": invoice_request.payload
    }, ensure_ascii=False)
    
    # Сохраняем invoice в хранилище перед созданием в Telegram
    try:
        invoice_store = bot_instance.application.bot_data.get("invoice_store")
        if invoice_store:
            await invoice_store.create_invoice(
                invoice_id=invoice_id,
                user_id=invoice_request.user_id,
                amount_stars=invoice_request.amount_stars,
                currency="XTR",
                backend_webhook_url=invoice_request.backend_webhook_url,
                payload=invoice_request.payload
            )
            logger.info(f"Invoice stored: invoice_id={invoice_id}")
        else:
            logger.warning("InvoiceStore not available, invoice not stored")
    except Exception as storage_error:
        logger.error(f"Failed to store invoice: {storage_error}", exc_info=True)
        # Продолжаем даже если хранение не удалось (graceful degradation)
    
    # Создаем invoice
    try:
        if invoice_request.return_link:
            # Создаем invoice link для открытия в Mini App
            logger.info(
                f"Creating invoice link: user_id={invoice_request.user_id}, "
                f"title='{invoice_request.title}', "
                f"amount={invoice_request.amount_stars} Stars"
            )
            
            invoice_link = await bot_instance.application.bot.create_invoice_link(
                title=invoice_request.title,
                description=invoice_request.description,
                payload=combined_payload,
                provider_token="",  # Для Telegram Stars provider_token должен быть пустым
                currency="XTR",  # XTR = Telegram Stars
                prices=[{
                    "label": invoice_request.title,
                    "amount": invoice_request.amount_stars
                }]
            )
            
            logger.info(
                f"Invoice link created successfully: user_id={invoice_request.user_id}, "
                f"amount={invoice_request.amount_stars} Stars, "
                f"link={invoice_link[:50]}..."
            )
            
            return CreateInvoiceResponse(
                ok=True,
                invoice_sent=False,
                invoice_link=invoice_link
            )
        else:
            # Отправляем invoice в чат (старое поведение)
            logger.info(
                f"Sending invoice to chat: user_id={invoice_request.user_id}, "
                f"title='{invoice_request.title}', "
                f"amount={invoice_request.amount_stars} Stars"
            )
            
            await bot_instance.application.bot.send_invoice(
                chat_id=invoice_request.user_id,
                title=invoice_request.title,
                description=invoice_request.description,
                payload=combined_payload,
                provider_token="",  # Для Telegram Stars provider_token должен быть пустым
                currency="XTR",  # XTR = Telegram Stars
                prices=[{
                    "label": invoice_request.title,
                    "amount": invoice_request.amount_stars
                }]
            )
            
            logger.info(
                f"Invoice sent to chat successfully: user_id={invoice_request.user_id}, "
                f"amount={invoice_request.amount_stars} Stars"
            )
            
            return CreateInvoiceResponse(
                ok=True,
                invoice_sent=True
            )
        
    except TelegramError as e:
        error_msg = str(e)
        logger.error(
            f"Telegram error sending invoice: {error_msg}, "
            f"user_id={invoice_request.user_id}",
            exc_info=True
        )
        
        # Возвращаем ошибку клиенту
        return CreateInvoiceResponse(
            ok=False,
            invoice_sent=False,
            error=f"Failed to send invoice: {error_msg}"
        )
        
    except Exception as e:
        logger.error(
            f"Unexpected error creating invoice: {e}, "
            f"user_id={invoice_request.user_id}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error creating invoice"
        )


@router.get("/health", tags=["payments"])
async def payments_health():
    """Проверка работоспособности payments API"""
    return {
        "status": "ok",
        "payments_enabled": PAYMENTS_ENABLED,
        "bot_instance": "initialized" if bot_instance else "not initialized"
    }
