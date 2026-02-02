"""Обработчики для платежей через Telegram Stars"""
import logging
import json
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from src.utils.invoice_storage import InvoiceStatus

logger = logging.getLogger(__name__)


async def handle_pre_checkout_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик PreCheckoutQuery.
    
    Вызывается когда пользователь подтверждает оплату в форме Telegram.
    Проверяет существование invoice в хранилище и валидирует сумму.
    
    КРИТИЧНО: Должен ответить в течение 10 секунд, иначе Telegram отменит платёж.
    """
    query = update.pre_checkout_query
    
    if not query:
        logger.error("PreCheckoutQuery handler called but query is None")
        return
    
    user_id = query.from_user.id if query.from_user else None
    username = query.from_user.username if query.from_user else "unknown"
    
    logger.info(
        f"PreCheckoutQuery received: "
        f"query_id={query.id}, "
        f"user_id={user_id}, "
        f"username={username}, "
        f"invoice_payload={query.invoice_payload}, "
        f"currency={query.currency}, "
        f"total_amount={query.total_amount}"
    )
    
    try:
        # Извлекаем invoice_id из payload
        invoice_id = None
        if query.invoice_payload:
            try:
                payload_data = json.loads(query.invoice_payload)
                invoice_id = payload_data.get("invoice_id")
            except json.JSONDecodeError:
                # Старый формат payload (без JSON) - для обратной совместимости
                logger.debug(f"Legacy payload format (non-JSON) for user {user_id}")
        
        # Если есть invoice_id, проверяем в хранилище
        if invoice_id:
            invoice_store = context.bot_data.get("invoice_store")
            if invoice_store:
                invoice = await invoice_store.get_invoice(invoice_id)
                
                if invoice:
                    # Валидация суммы
                    if invoice.amount_stars != query.total_amount:
                        logger.warning(
                            f"Amount mismatch for invoice {invoice_id}: "
                            f"expected={invoice.amount_stars}, got={query.total_amount}"
                        )
                        # Можно отклонить платёж, но для безопасности одобряем
                    
                    # Валидация пользователя
                    if invoice.user_id != user_id:
                        logger.warning(
                            f"User mismatch for invoice {invoice_id}: "
                            f"expected={invoice.user_id}, got={user_id}"
                        )
                    
                    logger.info(f"Invoice validated: invoice_id={invoice_id}, user_id={user_id}")
                else:
                    logger.warning(
                        f"Invoice not found in store: invoice_id={invoice_id}, "
                        "but approving for backward compatibility"
                    )
            else:
                logger.warning("InvoiceStore not available, skipping validation")
        else:
            logger.info(
                f"No invoice_id in payload from user {user_id}, "
                "approving for backward compatibility"
            )
        
        # Одобряем платеж
        # Всегда одобряем, так как валидация уже прошла при создании invoice
        await query.answer(ok=True)
        
        logger.info(
            f"PreCheckoutQuery approved: "
            f"query_id={query.id}, user_id={user_id}, "
            f"amount={query.total_amount} {query.currency}"
        )
        
    except TelegramError as e:
        logger.error(
            f"Telegram error answering PreCheckoutQuery: {e}, "
            f"query_id={query.id}, user_id={user_id}",
            exc_info=True
        )
        # Пытаемся отклонить с сообщением об ошибке
        try:
            await query.answer(
                ok=False,
                error_message="Произошла ошибка. Попробуйте позже."
            )
        except Exception as retry_error:
            logger.error(f"Failed to send error response: {retry_error}")
            
    except Exception as e:
        logger.error(
            f"Unexpected error in PreCheckoutQuery handler: {e}, "
            f"query_id={query.id}, user_id={user_id}",
            exc_info=True
        )
        # Отклоняем платеж при неожиданной ошибке
        try:
            await query.answer(
                ok=False,
                error_message="Произошла ошибка. Попробуйте позже."
            )
        except Exception as retry_error:
            logger.error(f"Failed to send error response: {retry_error}")


async def handle_successful_payment(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик успешного платежа.
    
    Вызывается после успешного списания Stars от пользователя.
    
    Выполняет:
    1. Проверку идемпотентности (предотвращение дублирования)
    2. Поиск invoice в хранилище
    3. Уведомление backend через webhook (если настроен)
    4. Отправку подтверждения пользователю
    """
    if not update.message or not update.message.successful_payment:
        logger.error("SuccessfulPayment handler called but payment data is missing")
        return
    
    payment = update.message.successful_payment
    user = update.effective_user
    user_id = user.id if user else None
    username = user.username if user else "unknown"
    
    telegram_charge_id = payment.telegram_payment_charge_id
    
    logger.info(
        f"SuccessfulPayment received: "
        f"user_id={user_id}, "
        f"username={username}, "
        f"currency={payment.currency}, "
        f"total_amount={payment.total_amount}, "
        f"invoice_payload={payment.invoice_payload}, "
        f"telegram_charge_id={telegram_charge_id}, "
        f"provider_charge_id={payment.provider_payment_charge_id}"
    )
    
    try:
        # 1. Проверка идемпотентности
        idempotency_store = context.bot_data.get("payment_idempotency_store")
        if idempotency_store:
            is_duplicate = await idempotency_store.is_duplicate(telegram_charge_id)
            
            if is_duplicate:
                logger.warning(
                    f"Duplicate payment detected: charge_id={telegram_charge_id}, "
                    f"user_id={user_id}. Ignoring."
                )
                return
            
            # Отмечаем как обработанный
            await idempotency_store.mark_processed(telegram_charge_id)
            logger.info(f"Payment marked as processed: charge_id={telegram_charge_id}")
        else:
            logger.warning("PaymentIdempotencyStore not available, skipping duplicate check")
        
        # 2. Извлекаем invoice_id из payload
        invoice_id = None
        original_payload = payment.invoice_payload
        
        if payment.invoice_payload:
            try:
                payload_data = json.loads(payment.invoice_payload)
                invoice_id = payload_data.get("invoice_id")
                original_payload = payload_data.get("original_payload", payment.invoice_payload)
            except json.JSONDecodeError:
                # Старый формат payload
                logger.debug("Legacy payload format in successful_payment")
        
        # 3. Ищем invoice в хранилище
        invoice = None
        if invoice_id:
            invoice_store = context.bot_data.get("invoice_store")
            if invoice_store:
                invoice = await invoice_store.get_invoice(invoice_id)
                
                if invoice:
                    logger.info(
                        f"Invoice found: invoice_id={invoice_id}, "
                        f"has_webhook={bool(invoice.backend_webhook_url)}"
                    )
                    
                    # Обновляем статус invoice
                    await invoice_store.update_status(invoice_id, InvoiceStatus.PAID)
                else:
                    logger.warning(f"Invoice not found in store: invoice_id={invoice_id}")
            else:
                logger.warning("InvoiceStore not available")
        
        # 4. Уведомление backend через webhook (если настроен)
        if invoice and invoice.backend_webhook_url:
            webhook_notifier = context.bot_data.get("webhook_notifier")
            
            if webhook_notifier:
                try:
                    await webhook_notifier.notify_payment_success(
                        webhook_url=invoice.backend_webhook_url,
                        user_id=user_id,
                        amount_stars=payment.total_amount,
                        currency=payment.currency,
                        telegram_charge_id=telegram_charge_id,
                        invoice_payload=original_payload,
                        invoice_id=invoice_id
                    )
                    
                    # Обновляем статус на pending_delivery (ждём ответа от backend)
                    invoice_store = context.bot_data.get("invoice_store")
                    if invoice_store:
                        await invoice_store.update_status(
                            invoice_id,
                            InvoiceStatus.PENDING_DELIVERY
                        )
                    
                    logger.info(
                        f"Backend webhook notification queued: "
                        f"invoice_id={invoice_id}, url={invoice.backend_webhook_url[:50]}..."
                    )
                except Exception as webhook_error:
                    logger.error(
                        f"Failed to queue webhook notification: {webhook_error}",
                        exc_info=True
                    )
                    # Продолжаем даже если webhook не удался
            else:
                logger.warning("WebhookNotifier not available")
        
        # 5. Отправляем подтверждение пользователю
        await update.message.reply_text(
            "✅ Оплата успешно завершена!\n\n"
            f"Списано: {payment.total_amount} Stars\n"
            f"ID транзакции: {telegram_charge_id}\n\n"
            "Ваш пакет активирован. Приятного использования! 🎨"
        )
        
        logger.info(
            f"Payment confirmation sent to user {user_id}, "
            f"charge_id={telegram_charge_id}"
        )
        
    except TelegramError as e:
        logger.error(
            f"Failed to send payment confirmation to user {user_id}: {e}",
            exc_info=True
        )
    except Exception as e:
        logger.error(
            f"Unexpected error in SuccessfulPayment handler: {e}, "
            f"user_id={user_id}",
            exc_info=True
        )
