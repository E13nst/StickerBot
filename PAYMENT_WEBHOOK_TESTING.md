# Тестирование Payment Webhook System

## ✅ Статус сервера

**URL:** https://stixly-e13nst.amvera.io/

**Проверка:**
```bash
curl https://stixly-e13nst.amvera.io/api/payments/health | jq
```

**Ожидаемый результат:**
```json
{
  "status": "ok",
  "payments_enabled": true,
  "bot_instance": "initialized"
}
```

---

## 🧪 План тестирования

### 1. Проверка нового параметра `backend_webhook_url`

**Цель:** Убедиться, что новый код задеплоен и принимает параметр `backend_webhook_url`

#### Тест 1: Базовая валидация схемы

```bash
# Отправляем запрос БЕЗ авторизации чтобы проверить, что поле принимается
curl -X POST https://stixly-e13nst.amvera.io/api/payments/create-invoice \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 123456789,
    "title": "Test Package",
    "description": "Test",
    "amount_stars": 100,
    "payload": "test",
    "return_link": true,
    "backend_webhook_url": "https://webhook.site/unique-id"
  }'
```

**Ожидаемый результат:**
```json
{"detail": "Missing Authorization header"}
```
✅ Если получили эту ошибку - поле `backend_webhook_url` принимается!

❌ Если получили ошибку валидации поля - новый код еще не задеплоен.

---

### 2. Тест с валидной авторизацией

#### Шаг 1: Получить initData

**Вариант A: Из Mini App (рекомендуется)**
1. Откройте ваше Mini App в Telegram
2. Откройте консоль браузера (Inspect → Console)
3. Выполните:
```javascript
console.log(Telegram.WebApp.initData)
```
4. Скопируйте вывод

**Вариант B: Использовать скрипт**
```bash
cd /Users/andrey/PycharmProjects/StickerBot
python scripts/get_chat_id_auto.py
```

#### Шаг 2: Создать тестовый webhook endpoint

Используйте [webhook.site](https://webhook.site/) для получения тестового URL:
1. Откройте https://webhook.site/
2. Скопируйте ваш уникальный URL (например: `https://webhook.site/abc123...`)

#### Шаг 3: Запустить тест

```bash
cd /Users/andrey/PycharmProjects/StickerBot
python test_payment_webhook.py
```

**Или вручную:**
```bash
# Замените YOUR_INIT_DATA и YOUR_WEBHOOK_URL
curl -X POST https://stixly-e13nst.amvera.io/api/payments/create-invoice \
  -H "X-Telegram-Init-Data: YOUR_INIT_DATA" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 141614461,
    "title": "Test Package",
    "description": "Тестовый пакет 100 Stars",
    "amount_stars": 100,
    "payload": "{\"package_id\": \"test_100\"}",
    "return_link": true,
    "backend_webhook_url": "YOUR_WEBHOOK_URL"
  }'
```

**Ожидаемый успешный ответ:**
```json
{
  "ok": true,
  "invoice_sent": false,
  "invoice_link": "https://t.me/$..."
}
```

---

### 3. Тесты валидации webhook URL

#### Тест 3.1: HTTP вместо HTTPS (должен быть отклонен)

```bash
curl -X POST https://stixly-e13nst.amvera.io/api/payments/create-invoice \
  -H "X-Telegram-Init-Data: YOUR_INIT_DATA" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 141614461,
    "title": "Test",
    "description": "Test",
    "amount_stars": 100,
    "payload": "test",
    "return_link": true,
    "backend_webhook_url": "http://insecure.example.com/webhook"
  }'
```

**Ожидаемая ошибка:**
```json
{
  "detail": "backend_webhook_url must use HTTPS protocol"
}
```

#### Тест 3.2: Невалидный URL (должен быть отклонен)

```bash
curl -X POST https://stixly-e13nst.amvera.io/api/payments/create-invoice \
  -H "X-Telegram-Init-Data: YOUR_INIT_DATA" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 141614461,
    "title": "Test",
    "description": "Test",
    "amount_stars": 100,
    "payload": "test",
    "return_link": true,
    "backend_webhook_url": "not-a-valid-url"
  }'
```

**Ожидаемая ошибка:**
```json
{
  "detail": "Invalid backend_webhook_url format: ..."
}
```

---

### 4. Тест полного payment flow (E2E)

#### Требования:
- Тестовый Telegram аккаунт с Stars
- Доступ к Mini App
- Webhook endpoint для получения уведомлений

#### Шаги:

1. **Создать invoice с webhook:**
```bash
curl -X POST https://stixly-e13nst.amvera.io/api/payments/create-invoice \
  -H "X-Telegram-Init-Data: YOUR_INIT_DATA" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": YOUR_USER_ID,
    "title": "Test Package 100 Stars",
    "description": "Тестовый платеж для проверки webhook",
    "amount_stars": 100,
    "payload": "{\"test_id\": \"payment_001\"}",
    "return_link": true,
    "backend_webhook_url": "https://webhook.site/YOUR_UNIQUE_ID"
  }'
```

2. **Открыть invoice_link в Telegram**
   - Скопируйте `invoice_link` из ответа
   - Откройте его в Telegram
   - Подтвердите оплату Stars

3. **Проверить webhook.site**
   - Откройте https://webhook.site/YOUR_UNIQUE_ID
   - Должны увидеть POST запрос с данными:

```json
{
  "event": "telegram_stars_payment_succeeded",
  "user_id": YOUR_USER_ID,
  "amount_stars": 100,
  "currency": "XTR",
  "telegram_charge_id": "...",
  "invoice_payload": "{\"test_id\": \"payment_001\"}",
  "timestamp": 1738500000,
  "signature": "hmac_sha256_hex_string"
}
```

4. **Проверить заголовки:**
   - `X-Webhook-Signature`: HMAC-SHA256 подпись
   - `Content-Type`: application/json
   - `User-Agent`: StickerBot-WebhookNotifier/1.0

---

## 🔍 Проверка логов на сервере

После проведения тестов проверьте логи на Amvera:

```bash
# Искать строки с:
- "Invoice stored: invoice_id="
- "Backend webhook notification queued"
- "Webhook delivered successfully"
- "Payment marked as processed: charge_id="
```

---

## 📊 Чек-лист тестирования

- [ ] Health endpoint возвращает `payments_enabled: true`
- [ ] Схема API принимает поле `backend_webhook_url`
- [ ] HTTP URL отклоняется (требуется HTTPS)
- [ ] Невалидный URL отклоняется
- [ ] Invoice создается успешно с валидным webhook URL
- [ ] Invoice создается успешно БЕЗ webhook URL (backward compatibility)
- [ ] После оплаты webhook доставляется на указанный URL
- [ ] Webhook содержит HMAC подпись в заголовке `X-Webhook-Signature`
- [ ] Payload webhook содержит все необходимые поля
- [ ] Идемпотентность: повторные webhook от Telegram игнорируются
- [ ] При ошибке backend происходит retry (3 попытки)

---

## 🐛 Troubleshooting

### Проблема: "Field required" для backend_webhook_url

**Причина:** Новый код еще не задеплоен на сервер

**Решение:** Задеплойте изменения на Amvera

### Проблема: Webhook не доставляется

**Проверьте:**
1. Логи бота на наличие ошибок
2. URL webhook доступен (попробуйте curl)
3. `BACKEND_WEBHOOK_SECRET` установлен в переменных окружения
4. Очередь webhook работает (логи "Webhook notifier started")

### Проблема: Неверная подпись на backend

**Проверьте:**
1. `BACKEND_WEBHOOK_SECRET` одинаковый на Python и Backend
2. Backend правильно вычисляет HMAC-SHA256 от тела запроса
3. Используется hex encoding для подписи

---

## 📝 Переменные окружения на Amvera

Убедитесь, что на Amvera установлены:

```bash
PAYMENTS_ENABLED=true
TELEGRAM_WEBHOOK_TOKEN=ваш_токен_от_telegram
BACKEND_WEBHOOK_SECRET=ваш_hmac_секрет_для_backend
BACKEND_WEBHOOK_RETRY_ATTEMPTS=3
BACKEND_WEBHOOK_TIMEOUT_SECONDS=10
INVOICE_TTL_HOURS=24
```

---

## ✅ Успешное тестирование

После успешного тестирования вы должны увидеть:

1. ✅ Invoice создается с `backend_webhook_url`
2. ✅ PreCheckoutQuery одобряется (в логах)
3. ✅ SuccessfulPayment обрабатывается (в логах)
4. ✅ Webhook доставляется на указанный URL
5. ✅ Backend получает уведомление с валидной подписью
6. ✅ Система работает без webhook URL (обратная совместимость)

🎉 **Система готова к production!**
