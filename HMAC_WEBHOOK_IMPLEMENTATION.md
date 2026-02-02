# HMAC-SHA256 Webhook Signature Implementation

## ✅ Реализовано

### 1. Canonical JSON сериализация

**Файл:** `src/services/webhook_notifier.py`

**Метод:** `_canonical_json(data: Dict[str, Any]) -> str`

**Характеристики:**
- ✅ Ключи отсортированы в алфавитном порядке (`sort_keys=True`)
- ✅ Без пробелов между элементами (`separators=(',', ':')`)
- ✅ UTF-8 кодировка (`ensure_ascii=False`)
- ✅ Детерминированная сериализация (одинаковый input → одинаковый output)

**Пример:**
```python
payload = {
    "event": "telegram_stars_payment_succeeded",
    "user_id": 141614461,
    "amount_stars": 100
}

canonical = _canonical_json(payload)
# Результат: {"amount_stars":100,"event":"telegram_stars_payment_succeeded","user_id":141614461}
```

### 2. HMAC-SHA256 подпись

**Метод:** `_generate_hmac_signature(canonical_json_body: str) -> str`

**Алгоритм:**
1. Canonical JSON кодируется в UTF-8
2. Секрет кодируется в UTF-8
3. Вычисляется `HMAC-SHA256(secret, canonical_json_body)`
4. Возвращается hex строка (64 символа)

**Пример:**
```python
canonical_json = '{"amount_stars":100,"event":"test","user_id":123}'
secret = "my_secret_key"
signature = _generate_hmac_signature(canonical_json, secret)
# Результат: "a1b2c3d4e5f6..." (64 hex символа)
```

### 3. Заголовок X-Webhook-Signature

**Реализация:**
```python
headers = {
    "Content-Type": "application/json; charset=utf-8",
    "User-Agent": "StickerBot-WebhookNotifier/1.0",
    "X-Webhook-Signature": signature  # HMAC подпись
}
```

**Важно:**
- Подпись передается **только в заголовке**, не в теле запроса
- Заголовок добавляется только если `BACKEND_WEBHOOK_SECRET` настроен

### 4. Retry механизм

**Реализовано:**
- ✅ Exponential backoff: 1s, 2s, 4s
- ✅ Максимум 3 попытки (настраивается через `BACKEND_WEBHOOK_RETRY_ATTEMPTS`)
- ✅ Фоновая очередь для неблокирующей обработки
- ✅ Логирование всех попыток

**Логи:**
```
Webhook failed, will retry in 1s: invoice_id=..., attempt=1
Webhook failed, will retry in 2s: invoice_id=..., attempt=2
Webhook delivery failed after 3 attempts: invoice_id=...
```

### 5. Идемпотентность

**Реализовано в:** `src/utils/invoice_storage.py`

**Класс:** `PaymentIdempotencyStore`

**Механизм:**
- ✅ Хранение `telegram_payment_charge_id` с TTL 7 дней
- ✅ Проверка перед обработкой: `is_duplicate(charge_id)`
- ✅ Отметка как обработанный: `mark_processed(charge_id)`
- ✅ Потокобезопасность с async locks

**Использование:**
```python
# В handle_successful_payment
is_duplicate = await idempotency_store.is_duplicate(telegram_charge_id)
if is_duplicate:
    logger.warning("Duplicate payment detected, ignoring")
    return

await idempotency_store.mark_processed(telegram_charge_id)
```

---

## 🔍 Проверка на Backend (Java)

### Требования

1. **Canonical JSON:** Backend должен создать точно такой же canonical JSON
2. **UTF-8:** Все операции с кодировкой в UTF-8
3. **Timing attacks:** Использовать `MessageDigest.isEqual()` для сравнения

### Пример кода

```java
public boolean verifyWebhookSignature(
    String receivedSignature, 
    String requestBody, 
    String secret
) {
    try {
        // 1. Парсим и создаем canonical JSON
        JSONObject json = new JSONObject(requestBody);
        String canonicalJson = json.toString(); // Автоматически сортирует ключи
        
        // 2. Вычисляем HMAC-SHA256
        Mac sha256 = Mac.getInstance("HmacSHA256");
        SecretKeySpec secretKey = new SecretKeySpec(
            secret.getBytes(StandardCharsets.UTF_8), 
            "HmacSHA256"
        );
        sha256.init(secretKey);
        
        byte[] hash = sha256.doFinal(
            canonicalJson.getBytes(StandardCharsets.UTF_8)
        );
        String expectedSignature = bytesToHex(hash);
        
        // 3. Сравниваем (защита от timing attacks)
        return MessageDigest.isEqual(
            receivedSignature.getBytes(StandardCharsets.UTF_8),
            expectedSignature.getBytes(StandardCharsets.UTF_8)
        );
    } catch (Exception e) {
        return false;
    }
}
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Тест canonical JSON и HMAC подписи
python3 test_canonical_json.py

# Тест полного webhook flow
python3 test_payment_webhook.py
```

### Проверка детерминированности

```python
payload = {"a": 1, "b": 2, "c": 3}
canonical1 = _canonical_json(payload)
canonical2 = _canonical_json(payload)
assert canonical1 == canonical2  # Всегда True
```

### Проверка подписи

```python
canonical = _canonical_json(payload)
signature1 = _generate_hmac_signature(canonical, secret)
signature2 = _generate_hmac_signature(canonical, secret)
assert signature1 == signature2  # Всегда True

# Измененный payload → другая подпись
modified_payload = payload.copy()
modified_payload["a"] = 999
modified_canonical = _canonical_json(modified_payload)
modified_signature = _generate_hmac_signature(modified_canonical, secret)
assert signature1 != modified_signature  # Всегда True
```

---

## 📊 Формат webhook запроса

### Headers

```
Content-Type: application/json; charset=utf-8
X-Webhook-Signature: a1b2c3d4e5f6... (64 hex символа)
User-Agent: StickerBot-WebhookNotifier/1.0
```

### Body (canonical JSON)

```json
{"amount_stars":100,"currency":"XTR","event":"telegram_stars_payment_succeeded","invoice_payload":"{\"package_id\": \"basic_10\"}","telegram_charge_id":"1234567890","timestamp":1738500000,"user_id":141614461}
```

**Важно:** 
- Ключи отсортированы: `amount_stars`, `currency`, `event`, ...
- Без пробелов между элементами
- UTF-8 кодировка

---

## 🔐 Безопасность

### ✅ Реализовано

1. **HMAC-SHA256:** Криптографически стойкая подпись
2. **Canonical JSON:** Детерминированная сериализация предотвращает атаки
3. **Timing attack protection:** Использование `hmac.compare_digest()` (Python) / `MessageDigest.isEqual()` (Java)
4. **UTF-8:** Корректная обработка Unicode символов
5. **Secret в env:** Секрет хранится в переменных окружения, не в коде

### ⚠️ Рекомендации

1. **Не логируйте секрет:** Никогда не выводите `BACKEND_WEBHOOK_SECRET` в логи
2. **Ротация секрета:** Периодически меняйте секрет (требует синхронизации с backend)
3. **HTTPS only:** Webhook URL должен использовать HTTPS
4. **Rate limiting:** Backend должен ограничивать количество запросов

---

## 📝 Переменные окружения

```bash
# Обязательно для HMAC подписи
BACKEND_WEBHOOK_SECRET=your_hmac_secret_here

# Опционально (значения по умолчанию)
BACKEND_WEBHOOK_RETRY_ATTEMPTS=3
BACKEND_WEBHOOK_TIMEOUT_SECONDS=10
```

**Генерация секрета:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## ✅ Чек-лист реализации

- [x] Canonical JSON сериализация (ключи отсортированы, без пробелов)
- [x] HMAC-SHA256 подпись
- [x] Заголовок X-Webhook-Signature
- [x] UTF-8 кодировка
- [x] Retry механизм (3 попытки, exponential backoff)
- [x] Идемпотентность платежей
- [x] Фоновая очередь для неблокирующей обработки
- [x] Логирование всех операций
- [x] Документация для backend (Java пример)
- [x] Тесты canonical JSON и подписи

---

**Версия:** 1.0  
**Дата:** 2026-02-02  
**Статус:** ✅ Полностью реализовано и протестировано
