#!/usr/bin/env python3
"""
Тест canonical JSON и HMAC подписи для webhook
"""
import json
import hmac
import hashlib
from typing import Dict, Any

def canonical_json(data: Dict[str, Any]) -> str:
    """
    Сериализует данные в canonical JSON формат:
    - Ключи отсортированы в алфавитном порядке
    - Без пробелов между элементами
    - UTF-8 кодировка
    """
    sorted_data = dict(sorted(data.items()))
    canonical_json_str = json.dumps(
        sorted_data,
        ensure_ascii=False,
        separators=(',', ':'),
        sort_keys=True
    )
    return canonical_json_str

def generate_hmac_signature(canonical_json_body: str, secret: str) -> str:
    """Генерирует HMAC-SHA256 подпись"""
    signature = hmac.new(
        secret.encode('utf-8'),
        canonical_json_body.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def verify_signature(received_signature: str, canonical_json_body: str, secret: str) -> bool:
    """Проверяет HMAC подпись"""
    expected_signature = generate_hmac_signature(canonical_json_body, secret)
    return hmac.compare_digest(received_signature, expected_signature)

# Тестовые данные
test_payload = {
    "event": "telegram_stars_payment_succeeded",
    "user_id": 141614461,
    "amount_stars": 100,
    "currency": "XTR",
    "telegram_charge_id": "1234567890",
    "invoice_payload": '{"package_id": "basic_10"}',
    "timestamp": 1738500000
}

secret = "test_secret_key_12345"

print("=" * 60)
print("🧪 Тест Canonical JSON и HMAC подписи")
print("=" * 60)
print()

# 1. Canonical JSON
print("1️⃣ Canonical JSON сериализация:")
canonical = canonical_json(test_payload)
print(f"   Результат: {canonical}")
print()

# 2. Проверка детерминированности
print("2️⃣ Проверка детерминированности:")
canonical2 = canonical_json(test_payload)
print(f"   Первая сериализация: {canonical}")
print(f"   Вторая сериализация: {canonical2}")
print(f"   Совпадают: {canonical == canonical2}")
print()

# 3. Сравнение с обычным JSON
print("3️⃣ Сравнение с обычным JSON:")
normal_json = json.dumps(test_payload, ensure_ascii=False, indent=2)
print(f"   Обычный JSON (с отступами):")
print(f"   {normal_json[:100]}...")
print(f"   Canonical JSON (без пробелов):")
print(f"   {canonical}")
print(f"   Длина обычного: {len(normal_json)} символов")
print(f"   Длина canonical: {len(canonical)} символов")
print()

# 4. HMAC подпись
print("4️⃣ HMAC-SHA256 подпись:")
signature = generate_hmac_signature(canonical, secret)
print(f"   Подпись: {signature}")
print(f"   Длина: {len(signature)} символов (64 для hex SHA256)")
print()

# 5. Проверка подписи
print("5️⃣ Проверка подписи:")
is_valid = verify_signature(signature, canonical, secret)
print(f"   Подпись валидна: {is_valid}")
print()

# 6. Тест с неверной подписью
print("6️⃣ Тест с неверной подписью:")
wrong_signature = "wrong_signature_12345"
is_valid_wrong = verify_signature(wrong_signature, canonical, secret)
print(f"   Неверная подпись валидна: {is_valid_wrong} (ожидается False)")
print()

# 7. Тест с измененным payload
print("7️⃣ Тест с измененным payload:")
modified_payload = test_payload.copy()
modified_payload["amount_stars"] = 200  # Изменили сумму
modified_canonical = canonical_json(modified_payload)
modified_signature = generate_hmac_signature(modified_canonical, secret)
is_valid_modified = verify_signature(signature, modified_canonical, secret)
print(f"   Оригинальная подпись для измененного payload: {is_valid_modified} (ожидается False)")
print(f"   Новая подпись для измененного payload: {modified_signature}")
print()

# 8. Тест с Unicode
print("8️⃣ Тест с Unicode символами:")
unicode_payload = {
    "event": "telegram_stars_payment_succeeded",
    "user_id": 141614461,
    "description": "Тестовый платёж с русскими символами 🎉",
    "amount_stars": 100
}
unicode_canonical = canonical_json(unicode_payload)
unicode_signature = generate_hmac_signature(unicode_canonical, secret)
print(f"   Canonical JSON с Unicode: {unicode_canonical}")
print(f"   Подпись: {unicode_signature}")
print()

print("=" * 60)
print("✅ Все тесты завершены!")
print("=" * 60)
print()
print("📝 Пример использования на Backend (Java):")
print("""
// 1. Получить тело запроса как строку
String requestBody = getRequestBodyAsString();

// 2. Получить подпись из заголовка
String receivedSignature = request.getHeader("X-Webhook-Signature");

// 3. Создать canonical JSON из тела запроса
// (ключи отсортированы, без пробелов, UTF-8)
JSONObject json = new JSONObject(requestBody);
String canonicalJson = json.toString(); // JSONObject автоматически сортирует ключи

// 4. Вычислить ожидаемую подпись
Mac sha256 = Mac.getInstance("HmacSHA256");
SecretKeySpec secretKey = new SecretKeySpec(
    secret.getBytes(StandardCharsets.UTF_8), 
    "HmacSHA256"
);
sha256.init(secretKey);
byte[] hash = sha256.doFinal(canonicalJson.getBytes(StandardCharsets.UTF_8));
String expectedSignature = bytesToHex(hash);

// 5. Сравнить подписи (защита от timing attacks)
boolean isValid = MessageDigest.isEqual(
    receivedSignature.getBytes(),
    expectedSignature.getBytes()
);
""")
