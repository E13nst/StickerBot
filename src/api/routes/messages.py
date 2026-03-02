"""API endpoint для отправки произвольного сообщения пользователю от имени бота."""
import logging
import math
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError, TimedOut

from src.api.routes.control import get_token_from_header
from src.api.middleware.rate_limit import limiter
from src.config.settings import WEBHOOK_RATE_LIMIT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/messages", tags=["messages"])

# Глобальная переменная для бота (устанавливается из server.py)
bot_instance = None

# Лимит длины текста сообщения в Telegram Bot API
TELEGRAM_MESSAGE_MAX_LENGTH = 4096


def map_telegram_send_error(error: TelegramError) -> tuple[int, dict[str, Any]]:
    """Нормализует Telegram ошибки отправки сообщения в API-ответ."""
    error_msg = str(error)
    error_lower = error_msg.lower()

    if isinstance(error, RetryAfter):
        retry_after_raw = getattr(error, "retry_after", None)
        retry_after = math.ceil(float(retry_after_raw)) if retry_after_raw is not None else None
        detail: dict[str, Any] = {
            "code": "RATE_LIMITED",
            "message": "Telegram ограничил частоту отправки. Повторите позже.",
            "retryable": True,
        }
        if retry_after is not None:
            detail["retry_after"] = retry_after
        return 429, detail

    if isinstance(error, TimedOut):
        return 503, {
            "code": "TELEGRAM_TIMEOUT",
            "message": "Telegram не ответил вовремя. Попробуйте снова.",
            "retryable": True,
        }

    if isinstance(error, Forbidden):
        if "blocked by the user" in error_lower:
            return 403, {
                "code": "BOT_BLOCKED",
                "message": "Пользователь заблокировал бота.",
                "retryable": False,
            }
        return 403, {
            "code": "NO_CHAT_ACCESS",
            "message": "У бота нет доступа к чату.",
            "retryable": False,
        }

    if isinstance(error, BadRequest):
        if "chat not found" in error_lower:
            return 400, {
                "code": "CHAT_NOT_FOUND",
                "message": "Чат не найден или недоступен для бота.",
                "retryable": False,
            }
        if "can't parse entities" in error_lower:
            return 400, {
                "code": "INVALID_PARSE_MODE",
                "message": "Некорректная разметка сообщения для выбранного parse_mode.",
                "retryable": False,
            }
        return 400, {
            "code": "TELEGRAM_BAD_REQUEST",
            "message": "Telegram отклонил запрос на отправку сообщения.",
            "retryable": False,
        }

    if isinstance(error, NetworkError):
        return 503, {
            "code": "TELEGRAM_NETWORK_ERROR",
            "message": "Временная сетевая ошибка при обращении к Telegram.",
            "retryable": True,
        }

    if "retry after" in error_lower or "too many requests" in error_lower:
        return 429, {
            "code": "RATE_LIMITED",
            "message": "Telegram ограничил частоту отправки. Повторите позже.",
            "retryable": True,
        }

    if "unavailable" in error_lower or "temporarily" in error_lower:
        return 503, {
            "code": "TELEGRAM_UNAVAILABLE",
            "message": "Telegram временно недоступен.",
            "retryable": True,
        }

    return 503, {
        "code": "TELEGRAM_API_ERROR",
        "message": "Не удалось отправить сообщение через Telegram API.",
        "retryable": True,
    }


def set_bot_instance(instance):
    """Установить экземпляр бота."""
    global bot_instance
    bot_instance = instance
    logger.info("Bot instance set for messages router")


class SendMessageRequest(BaseModel):
    """Запрос на отправку сообщения пользователю."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=TELEGRAM_MESSAGE_MAX_LENGTH,
        description="Текст сообщения (1–4096 символов). Поддерживается MarkdownV2/HTML при соответствующем parse_mode.",
    )
    user_id: Optional[int] = Field(
        None,
        description="Telegram user ID — сообщение уйдёт в личный чат. Укажите ровно один из user_id или chat_id.",
        json_schema_extra={"format": "int64"},
    )
    chat_id: Optional[int] = Field(
        None,
        description="Telegram chat ID — для групп/каналов, где бот состоит. Укажите ровно один из user_id или chat_id.",
        json_schema_extra={"format": "int64"},
    )
    parse_mode: Literal["MarkdownV2", "HTML", "plain"] = Field(
        "MarkdownV2",
        description="Режим форматирования: MarkdownV2 (по умолчанию), HTML или plain (без разметки).",
    )
    disable_web_page_preview: bool = Field(
        False,
        description="Отключить предпросмотр ссылок в сообщении.",
    )

    @model_validator(mode="after")
    def exactly_one_target(self):
        has_user = self.user_id is not None
        has_chat = self.chat_id is not None
        if has_user and has_chat:
            raise ValueError("Укажите ровно один из user_id или chat_id")
        if not has_user and not has_chat:
            raise ValueError("Укажите user_id или chat_id")
        return self


class SendMessageResponse(BaseModel):
    """Ответ после успешной отправки сообщения."""

    status: Literal["sent"] = "sent"
    chat_id: int = Field(..., description="ID чата, в который отправлено сообщение", json_schema_extra={"format": "int64"})
    message_id: int = Field(..., description="ID отправленного сообщения в чате", json_schema_extra={"format": "int64"})
    parse_mode: Optional[str] = Field(
        None,
        description="Использованный режим разметки (null для plain)",
    )


@router.post("/send", response_model=SendMessageResponse)
@limiter.limit(WEBHOOK_RATE_LIMIT)
async def send_message(
    request: Request,
    body: SendMessageRequest,
    token: str = Depends(get_token_from_header),
):
    """
    Отправить произвольное текстовое сообщение указанному пользователю или в чат от имени бота.

    Требуется заголовок `Authorization: Bearer <API_TOKEN>`.

    - **user_id** — отправка в личный чат с пользователем.
    - **chat_id** — отправка в группу/канал (бот должен состоять в чате).
    - **parse_mode**: MarkdownV2 (рекомендуется), HTML или plain.

    При ошибке Telegram API:
    - 403 — если бот заблокирован пользователем или у бота нет доступа к чату.
    - 502/503 — прочие ошибки Telegram API.
    """
    if not bot_instance or not getattr(bot_instance, "application", None):
        logger.warning("send_message called but bot not initialized")
        raise HTTPException(
            status_code=503,
            detail="Bot not initialized",
        )

    target_chat_id = body.chat_id if body.chat_id is not None else body.user_id
    parse_mode_value: Optional[str] = None if body.parse_mode == "plain" else body.parse_mode

    logger.info(
        "Sending message: target_chat_id=%s, parse_mode=%s, text_length=%d",
        target_chat_id,
        body.parse_mode,
        len(body.text),
    )

    try:
        send_kwargs = {
            "chat_id": target_chat_id,
            "text": body.text,
            "disable_web_page_preview": body.disable_web_page_preview,
        }
        if parse_mode_value:
            send_kwargs["parse_mode"] = parse_mode_value

        message = await bot_instance.application.bot.send_message(**send_kwargs)
    except TelegramError as e:
        status, detail = map_telegram_send_error(e)
        log_message = "Telegram error sending message: %s, target_chat_id=%s, code=%s, status=%s"
        log_args = (e, target_chat_id, detail.get("code"), status)
        if status in (400, 403, 429):
            logger.warning(log_message, *log_args, exc_info=True)
        else:
            logger.error(log_message, *log_args, exc_info=True)
        raise HTTPException(
            status_code=status,
            detail=detail,
        )
    except Exception as e:
        logger.error(
            "Unexpected error sending message: %s, target_chat_id=%s",
            e,
            target_chat_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error sending message",
        )

    logger.info(
        "Message sent: chat_id=%s, message_id=%s",
        message.chat_id,
        message.message_id,
    )

    return SendMessageResponse(
        status="sent",
        chat_id=message.chat_id,
        message_id=message.message_id,
        parse_mode=parse_mode_value,
    )
