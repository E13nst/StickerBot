# Авторизация Java Backend в Python сервисе

## 📋 Обзор

Java backend взаимодействует с Python сервисом в **двух направлениях**:

1. **Входящие webhook** (Python → Java): Python сервис отправляет уведомления о платежах
2. **Исходящие API запросы** (Java → Python): Java backend может вызывать API Python сервиса

---

## 1️⃣ Входящие Webhook (Python → Java)

### Авторизация через HMAC подпись

Python сервис отправляет POST запросы на `backend_webhook_url` с HMAC-SHA256 подписью в заголовке.

### Формат запроса

**URL:** `{backend_webhook_url}` (указывается при создании invoice)

**Method:** POST

**Headers:**
```
Content-Type: application/json; charset=utf-8
X-Webhook-Signature: {hmac_sha256_hex_signature}  # 64 hex символа
User-Agent: StickerBot-WebhookNotifier/1.0
```

**Body (canonical JSON):**
```json
{"amount_stars":100,"currency":"XTR","event":"telegram_stars_payment_succeeded","invoice_payload":"{\"package_id\": \"basic_10\"}","telegram_charge_id":"1234567890","timestamp":1738500000,"user_id":141614461}
```

### Проверка подписи (Java)

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.json.JSONObject;

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
        
        // 3. Сравниваем подписи (защита от timing attacks)
        return MessageDigest.isEqual(
            receivedSignature.getBytes(StandardCharsets.UTF_8),
            expectedSignature.getBytes(StandardCharsets.UTF_8)
        );
    } catch (Exception e) {
        logger.error("Error verifying webhook signature", e);
        return false;
    }
}

private String bytesToHex(byte[] bytes) {
    StringBuilder result = new StringBuilder();
    for (byte b : bytes) {
        result.append(String.format("%02x", b));
    }
    return result.toString();
}
```

### Пример Spring Boot Controller

```java
@PostMapping("/api/payments/telegram")
public ResponseEntity<?> handleWebhook(
    @RequestBody String requestBody,
    @RequestHeader(value = "X-Webhook-Signature", required = false) String signature
) {
    // 1. Проверка подписи
    String secret = System.getenv("BACKEND_WEBHOOK_SECRET");
    if (secret != null && !secret.isEmpty()) {
        if (signature == null || !verifyWebhookSignature(signature, requestBody, secret)) {
            logger.warn("Invalid webhook signature");
            return ResponseEntity.status(401).body("Invalid signature");
        }
    }
    
    // 2. Парсим payload
    JSONObject payload = new JSONObject(requestBody);
    String event = payload.getString("event");
    
    if ("telegram_stars_payment_succeeded".equals(event)) {
        // 3. Обработка платежа
        long userId = payload.getLong("user_id");
        int amountStars = payload.getInt("amount_stars");
        String chargeId = payload.getString("telegram_charge_id");
        String invoicePayload = payload.getString("invoice_payload");
        
        // Активируем тариф, начисляем баланс и т.д.
        processPayment(userId, amountStars, chargeId, invoicePayload);
        
        // 4. Возвращаем успешный ответ (2xx)
        return ResponseEntity.ok().body("Payment processed");
    }
    
    return ResponseEntity.badRequest().body("Unknown event");
}
```

### Важные моменты

1. **Секрет:** Используйте переменную окружения `BACKEND_WEBHOOK_SECRET` (должен совпадать с Python сервисом)
2. **Canonical JSON:** Backend должен создать точно такой же canonical JSON для проверки
3. **Timing attacks:** Используйте `MessageDigest.isEqual()` вместо `String.equals()`
4. **UTF-8:** Все операции с кодировкой в UTF-8
5. **Ответ 2xx:** Backend должен вернуть HTTP 2xx для успешной обработки, иначе Python сервис будет retry

---

## 2️⃣ Исходящие API запросы (Java → Python)

### Авторизация через Bearer Token

Если Java backend хочет вызывать API Python сервиса (например, проверить статус платежа, получить информацию о invoice), используется **Bearer Token** авторизация.

### Переменная окружения

**Python сервис:**
```bash
API_TOKEN=your_api_token_here
```

**Java backend:**
```bash
PYTHON_SERVICE_API_TOKEN=your_api_token_here  # Должен совпадать с API_TOKEN
PYTHON_SERVICE_BASE_URL=https://stixly-e13nst.amvera.io
```

### Формат запроса

**Headers:**
```
Authorization: Bearer {API_TOKEN}
Content-Type: application/json
```

### Доступные endpoints

#### 1. Health Check (без авторизации)

```http
GET /api/payments/health
```

**Response:**
```json
{
  "status": "ok",
  "payments_enabled": true,
  "bot_instance": "initialized"
}
```

#### 2. Статус бота (требует авторизации)

```http
GET /api/control/status
Authorization: Bearer {API_TOKEN}
```

**Response:**
```json
{
  "enabled": true,
  "mode": "webhook",
  "webhook_url": "https://stixly-e13nst.amvera.io/webhook",
  "bot_running": true
}
```

### Пример Java клиента

```java
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;
import java.util.Collections;

public class PythonServiceClient {
    private final String baseUrl;
    private final String apiToken;
    private final RestTemplate restTemplate;
    
    public PythonServiceClient(String baseUrl, String apiToken) {
        this.baseUrl = baseUrl;
        this.apiToken = apiToken;
        this.restTemplate = new RestTemplate();
    }
    
    public StatusResponse getStatus() {
        HttpHeaders headers = new HttpHeaders();
        headers.set("Authorization", "Bearer " + apiToken);
        headers.setContentType(MediaType.APPLICATION_JSON);
        
        HttpEntity<String> entity = new HttpEntity<>(headers);
        
        ResponseEntity<StatusResponse> response = restTemplate.exchange(
            baseUrl + "/api/control/status",
            HttpMethod.GET,
            entity,
            StatusResponse.class
        );
        
        return response.getBody();
    }
    
    public HealthResponse getHealth() {
        // Health endpoint не требует авторизации
        ResponseEntity<HealthResponse> response = restTemplate.getForEntity(
            baseUrl + "/api/payments/health",
            HealthResponse.class
        );
        
        return response.getBody();
    }
}
```

### Использование

```java
@Configuration
public class PythonServiceConfig {
    
    @Value("${python.service.base-url}")
    private String pythonServiceBaseUrl;
    
    @Value("${python.service.api-token}")
    private String pythonServiceApiToken;
    
    @Bean
    public PythonServiceClient pythonServiceClient() {
        return new PythonServiceClient(pythonServiceBaseUrl, pythonServiceApiToken);
    }
}

@Service
public class PaymentService {
    
    @Autowired
    private PythonServiceClient pythonServiceClient;
    
    public void checkPythonServiceHealth() {
        HealthResponse health = pythonServiceClient.getHealth();
        if (!"ok".equals(health.getStatus())) {
            logger.warn("Python service is not healthy");
        }
    }
}
```

---

## 🔐 Безопасность

### Рекомендации

1. **Секреты в env:** Никогда не храните `API_TOKEN` или `BACKEND_WEBHOOK_SECRET` в коде
2. **HTTPS only:** Все запросы должны идти через HTTPS
3. **Rate limiting:** Backend должен ограничивать количество запросов к Python API
4. **Логирование:** Не логируйте секреты или подписи в открытом виде
5. **Ротация токенов:** Периодически меняйте токены (требует синхронизации)

### Проверка подписи webhook

**Критично:** Всегда проверяйте HMAC подпись входящих webhook, даже если `BACKEND_WEBHOOK_SECRET` не задан (в этом случае Python сервис не будет отправлять подпись, но лучше явно обработать этот случай):

```java
String secret = System.getenv("BACKEND_WEBHOOK_SECRET");

if (secret != null && !secret.isEmpty()) {
    // Секрет настроен - проверяем подпись
    if (signature == null) {
        return ResponseEntity.status(401).body("Signature required");
    }
    
    if (!verifyWebhookSignature(signature, requestBody, secret)) {
        return ResponseEntity.status(401).body("Invalid signature");
    }
} else {
    // Секрет не настроен - предупреждение
    logger.warn("BACKEND_WEBHOOK_SECRET not configured, accepting webhook without signature verification");
}
```

---

## 📝 Переменные окружения

### Python сервис

```bash
# Для входящих webhook от Telegram
TELEGRAM_WEBHOOK_TOKEN=your_telegram_webhook_token

# Для исходящих webhook к Java backend
BACKEND_WEBHOOK_SECRET=your_backend_hmac_secret

# Для API авторизации (если Java backend вызывает API)
API_TOKEN=your_api_token
```

### Java backend

```bash
# Для проверки входящих webhook от Python
BACKEND_WEBHOOK_SECRET=your_backend_hmac_secret  # Должен совпадать с Python

# Для вызова API Python сервиса
PYTHON_SERVICE_API_TOKEN=your_api_token  # Должен совпадать с API_TOKEN
PYTHON_SERVICE_BASE_URL=https://stixly-e13nst.amvera.io
```

---

## 🧪 Тестирование

### Тест проверки подписи

```java
@Test
public void testWebhookSignatureVerification() {
    String secret = "test_secret";
    String payload = "{\"event\":\"test\",\"user_id\":123}";
    
    // Генерируем подпись (как это делает Python)
    String signature = generateHMAC(payload, secret);
    
    // Проверяем подпись
    boolean isValid = verifyWebhookSignature(signature, payload, secret);
    assertTrue(isValid);
    
    // Проверяем с неверной подписью
    boolean isInvalid = verifyWebhookSignature("wrong_signature", payload, secret);
    assertFalse(isInvalid);
}
```

### Тест API клиента

```java
@Test
public void testPythonServiceClient() {
    PythonServiceClient client = new PythonServiceClient(
        "https://stixly-e13nst.amvera.io",
        "test_api_token"
    );
    
    HealthResponse health = client.getHealth();
    assertEquals("ok", health.getStatus());
}
```

---

## 📊 Схема взаимодействия

```
┌─────────────────┐                    ┌─────────────────┐
│  Python Service │                    │  Java Backend   │
└─────────────────┘                    └─────────────────┘
         │                                       │
         │  1. POST /api/payments/telegram      │
         │     X-Webhook-Signature: {HMAC}      │
         │──────────────────────────────────────>│
         │                                       │
         │                                       │ 2. Проверка HMAC
         │                                       │    подписи
         │                                       │
         │                                       │ 3. Обработка платежа
         │                                       │
         │  4. HTTP 200 OK                       │
         │<──────────────────────────────────────│
         │                                       │
         │                                       │
         │  5. GET /api/control/status           │
         │     Authorization: Bearer {token}    │
         │<──────────────────────────────────────│
         │                                       │
         │  6. HTTP 200 OK + JSON                │
         │──────────────────────────────────────>│
         │                                       │
```

---

## ✅ Чек-лист интеграции

- [ ] `BACKEND_WEBHOOK_SECRET` установлен в обоих сервисах (одинаковое значение)
- [ ] Java backend проверяет HMAC подпись входящих webhook
- [ ] Java backend возвращает HTTP 2xx при успешной обработке
- [ ] Java backend обрабатывает ошибки и логирует их
- [ ] `API_TOKEN` установлен в Python сервисе (если нужен доступ к API)
- [ ] Java backend использует `Authorization: Bearer {token}` для API запросов
- [ ] Все запросы идут через HTTPS
- [ ] Секреты хранятся в переменных окружения, не в коде

---

**Версия:** 1.0  
**Дата:** 2026-02-02
