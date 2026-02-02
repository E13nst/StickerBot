# Интеграция Telegram Stars Payments в Mini App

## 📋 Оглавление

1. [Обзор](#обзор)
2. [Архитектура](#архитектура)
3. [Backend API](#backend-api)
4. [Frontend Mini App](#frontend-mini-app)
5. [Тестирование](#тестирование)
6. [Безопасность](#безопасность)
7. [Troubleshooting](#troubleshooting)

---

## Обзор

Этот документ описывает интеграцию платежей через **Telegram Stars** в Telegram Mini App. Реализованы два способа проведения платежей:

### Способ 1: Invoice в чате (по умолчанию)
- Bot API отправляет invoice в чат с пользователем
- Пользователь открывает чат и подтверждает оплату
- Подходит для простых сценариев

### Способ 2: Invoice в Mini App (рекомендуется) ⭐
- Bot API возвращает `invoice_link`
- Mini App открывает форму оплаты через `Telegram.WebApp.openInvoice()`
- Пользователь остается в приложении
- Получаете мгновенный callback о результате
- **Лучший UX для Mini App!**

---

## Архитектура

```mermaid
sequenceDiagram
    participant MiniApp
    participant BotAPI as Bot API
    participant TG as Telegram
    participant User
    
    Note over MiniApp,User: Способ 2: Invoice в Mini App (return_link=true)
    
    MiniApp->>BotAPI: POST /api/payments/create-invoice<br/>{return_link: true}
    BotAPI->>BotAPI: Валидация initData
    BotAPI->>TG: create_invoice_link()
    TG->>BotAPI: invoice_link
    BotAPI->>MiniApp: {invoice_link: "..."}
    MiniApp->>MiniApp: Telegram.WebApp.openInvoice(link)
    MiniApp->>User: Показ формы оплаты внутри App
    User->>TG: Подтверждение оплаты
    TG->>BotAPI: PreCheckoutQuery (webhook)
    BotAPI->>TG: answer(ok=True)
    TG->>TG: Списание Stars
    TG->>BotAPI: SuccessfulPayment (webhook)
    TG->>MiniApp: Callback: status='paid'
    MiniApp->>MiniApp: Обновление UI
    BotAPI->>User: Уведомление в чат
```

---

## Backend API

### Endpoint: `POST /api/payments/create-invoice`

#### Request

```json
{
  "user_id": 141614461,
  "title": "Пакет генераций",
  "description": "Пакет на 10 генераций стикеров",
  "amount_stars": 100,
  "payload": "{\"package_id\": \"basic_10\"}",
  "return_link": true  // 👈 Ключевой параметр!
}
```

**Headers:**
```
Content-Type: application/json
Authorization: tma <initData>
```

#### Response

**Для `return_link: true`:**
```json
{
  "ok": true,
  "invoice_sent": false,
  "invoice_link": "https://t.me/$abcdef1234567890ABCDEF..."
}
```

**Для `return_link: false` (по умолчанию):**
```json
{
  "ok": true,
  "invoice_sent": true,
  "invoice_link": null
}
```

#### Параметры запроса

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `user_id` | int | Да | ID пользователя Telegram |
| `title` | string | Да | Заголовок платежа (1-32 символа) |
| `description` | string | Да | Описание платежа (1-255 символов) |
| `amount_stars` | int | Да | Количество Stars (> 0) |
| `payload` | string | Да | Данные для идентификации платежа (макс. 128 символов) |
| `return_link` | bool | Нет | `true` - вернуть ссылку, `false` - отправить в чат |

---

## Frontend Mini App

### Установка Telegram WebApp SDK

Подключите SDK в вашем HTML:

```html
<script src="https://telegram.org/js/telegram-web-app.js"></script>
```

### Пример интеграции (JavaScript/TypeScript)

#### 1. Базовая функция создания платежа

```javascript
/**
 * Создает invoice и открывает форму оплаты в Mini App
 * @param {string} packageId - ID пакета
 * @param {number} amountStars - Количество Stars
 * @param {string} title - Название платежа
 * @param {string} description - Описание
 * @returns {Promise<string>} - Статус оплаты: 'paid', 'cancelled', 'failed', 'pending'
 */
async function createAndPayInvoice(packageId, amountStars, title, description) {
  const initData = Telegram.WebApp.initData;
  const userId = Telegram.WebApp.initDataUnsafe.user.id;
  
  if (!initData) {
    throw new Error('Telegram WebApp не инициализирован');
  }
  
  try {
    // 1. Создаем invoice через Bot API
    const response = await fetch('https://your-bot-api.com/api/payments/create-invoice', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `tma ${initData}`
      },
      body: JSON.stringify({
        user_id: userId,
        title: title,
        description: description,
        amount_stars: amountStars,
        payload: JSON.stringify({ 
          package_id: packageId,
          timestamp: Date.now()
        }),
        return_link: true  // 👈 Важно!
      })
    });
    
    const data = await response.json();
    
    if (!data.ok || !data.invoice_link) {
      throw new Error(data.error || 'Не удалось создать invoice');
    }
    
    // 2. Открываем форму оплаты в Mini App
    return new Promise((resolve) => {
      Telegram.WebApp.openInvoice(data.invoice_link, (status) => {
        console.log('Payment status:', status);
        resolve(status);
      });
    });
    
  } catch (error) {
    console.error('Payment error:', error);
    throw error;
  }
}
```

#### 2. Использование в React

```jsx
import { useState } from 'react';

function PaymentButton({ packageId, price, title, description }) {
  const [isProcessing, setIsProcessing] = useState(false);
  
  const handlePayment = async () => {
    setIsProcessing(true);
    
    try {
      const status = await createAndPayInvoice(
        packageId,
        price,
        title,
        description
      );
      
      switch (status) {
        case 'paid':
          // ✅ Оплата успешна
          Telegram.WebApp.showAlert('Оплата прошла успешно! 🎉');
          // Обновляем UI, активируем пакет
          onPaymentSuccess(packageId);
          break;
          
        case 'cancelled':
          // ❌ Пользователь отменил
          Telegram.WebApp.showAlert('Оплата отменена');
          break;
          
        case 'failed':
          // ⚠️ Ошибка
          Telegram.WebApp.showAlert('Ошибка оплаты. Попробуйте снова.');
          break;
          
        case 'pending':
          // ⏳ В обработке (редко)
          Telegram.WebApp.showAlert('Платеж обрабатывается...');
          break;
      }
      
    } catch (error) {
      Telegram.WebApp.showAlert('Ошибка: ' + error.message);
    } finally {
      setIsProcessing(false);
    }
  };
  
  return (
    <button 
      onClick={handlePayment}
      disabled={isProcessing}
      className="payment-button"
    >
      {isProcessing ? 'Обработка...' : `Купить за ${price} ⭐`}
    </button>
  );
}
```

#### 3. Обработка результата платежа

```javascript
async function onPaymentSuccess(packageId) {
  // 1. Обновить локальное состояние
  updateUserBalance(packageId);
  
  // 2. Синхронизировать с бэкендом (опционально)
  await fetch('https://your-backend.com/api/activate-package', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `tma ${Telegram.WebApp.initData}`
    },
    body: JSON.stringify({
      package_id: packageId,
      user_id: Telegram.WebApp.initDataUnsafe.user.id
    })
  });
  
  // 3. Показать анимацию успеха
  showSuccessAnimation();
  
  // 4. Обновить UI
  refreshPackagesList();
}
```

---

## Тестирование

### 1. Тестирование через curl

```bash
# Создание invoice с return_link
curl -X POST http://localhost:80/api/payments/create-invoice \
  -H "Content-Type: application/json" \
  -H "Authorization: tma user=%7B%22id%22%3A141614461...%7D&hash=..." \
  -d '{
    "user_id": 141614461,
    "title": "Тест",
    "description": "Тестовый платеж",
    "amount_stars": 1,
    "payload": "test",
    "return_link": true
  }'

# Ожидаемый ответ:
# {
#   "ok": true,
#   "invoice_sent": false,
#   "invoice_link": "https://t.me/$..."
# }
```

### 2. Тестирование в Mini App

1. Добавьте тестовую кнопку в ваш Mini App:
```html
<button onclick="testPayment()">Тест платежа (1 Star)</button>

<script>
async function testPayment() {
  const status = await createAndPayInvoice(
    'test_package',
    1,  // 1 Star для теста
    'Тестовый платеж',
    'Тест интеграции Stars'
  );
  console.log('Test payment status:', status);
}
</script>
```

2. Откройте Mini App в Telegram
3. Нажмите кнопку теста
4. Должна открыться форма оплаты **внутри приложения**
5. Подтвердите оплату

### 3. Мониторинг логов

```bash
# На сервере бота
tail -f logs/bot.log | grep -i payment

# Вы увидите:
# - "Creating invoice link: user_id=..."
# - "Invoice link created successfully: ..."
# - "PreCheckoutQuery received: ..."
# - "SuccessfulPayment received: ..."
```

---

## Безопасность

### 1. Валидация initData

Backend **обязательно** валидирует `initData` через HMAC-SHA256:

```python
# Автоматически в Bot API
validated_data = validate_telegram_init_data(
    init_data=init_data,
    bot_token=BOT_TOKEN,
    max_age_seconds=3600  # 1 час
)
```

### 2. Проверка user_id

API проверяет соответствие `user_id` из `initData` и `user_id` в запросе:

```python
if validated_user_id != invoice_request.user_id:
    raise HTTPException(403, "user_id mismatch")
```

### 3. Rate Limiting

Автоматическое ограничение запросов:
- 100 запросов/минуту по умолчанию
- Настраивается через `WEBHOOK_RATE_LIMIT` в `.env`

### 4. Payload для идентификации

Используйте `payload` для идентификации платежа:

```javascript
payload: JSON.stringify({
  package_id: 'premium_10',
  user_id: userId,
  timestamp: Date.now(),
  nonce: Math.random().toString(36)
})
```

В `handle_successful_payment` можете извлечь эти данные:

```python
payload_data = json.loads(payment.invoice_payload)
package_id = payload_data.get('package_id')
# Активируйте пакет для пользователя
```

---

## Troubleshooting

### Проблема: "initData is too old"

**Причина:** initData устарел (> 1 часа)

**Решение:** 
- Обновите страницу Mini App
- Или увеличьте `PAYMENT_INITDATA_MAX_AGE_SECONDS` в `.env`

### Проблема: "Payments are currently disabled"

**Причина:** `PAYMENTS_ENABLED=false` в `.env`

**Решение:**
```bash
# В .env
PAYMENTS_ENABLED=true
```

### Проблема: "Missing Authorization header"

**Причина:** Не передан `initData` в заголовке

**Решение:**
```javascript
headers: {
  'Authorization': `tma ${Telegram.WebApp.initData}`
}
```

### Проблема: "Invoice не открывается в Mini App"

**Причина:** Не передан `return_link: true`

**Решение:**
```json
{
  "return_link": true  // Добавить в request
}
```

### Проблема: "User ID mismatch"

**Причина:** `user_id` в запросе не совпадает с `user_id` из `initData`

**Решение:**
```javascript
const userId = Telegram.WebApp.initDataUnsafe.user.id;
// Используйте этот userId в запросе
```

---

## Конфигурация

### Backend (.env)

```bash
# Платежи
PAYMENTS_ENABLED=true
PAYMENT_INITDATA_MAX_AGE_SECONDS=3600

# Rate limiting
WEBHOOK_RATE_LIMIT=100/minute

# API
API_PORT=80
```

### Frontend (config.js)

```javascript
const CONFIG = {
  botApiUrl: 'https://your-bot-api.com',
  
  packages: [
    {
      id: 'basic_10',
      name: 'Базовый',
      stars: 50,
      generations: 10
    },
    {
      id: 'premium_50',
      name: 'Премиум',
      stars: 200,
      generations: 50
    }
  ]
};
```

---

## Дополнительные ресурсы

- [Telegram Bot API - Payments](https://core.telegram.org/bots/api#payments)
- [Telegram Stars Documentation](https://core.telegram.org/bots/payments#telegram-stars)
- [Telegram WebApp Documentation](https://core.telegram.org/bots/webapps)
- [openInvoice Method](https://core.telegram.org/bots/webapps#initializing-mini-apps)

---

## Поддержка

Если возникли вопросы:
1. Проверьте логи: `tail -f logs/bot.log | grep payment`
2. Проверьте Network tab в DevTools Mini App
3. Убедитесь, что `PAYMENTS_ENABLED=true`
4. Проверьте, что `initData` актуален

---

**Версия документа:** 1.0  
**Дата:** 2026-02-02
