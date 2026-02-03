#!/usr/bin/env python3
"""
Тестовый скрипт для проверки payment webhook с backend_webhook_url
"""
import requests
import json
import sys

# Конфигурация
API_BASE_URL = "https://stixly-e13nst.amvera.io"
TEST_USER_ID = 123456789  # Замените на реальный user_id
TEST_BACKEND_WEBHOOK = "https://webhook.site/unique-id"  # Замените на ваш тестовый URL

def test_health():
    """Проверка health endpoint"""
    print("🔍 Проверка health endpoint...")
    response = requests.get(f"{API_BASE_URL}/api/payments/health")
    print(f"   Статус: {response.status_code}")
    print(f"   Ответ: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    return response.json()

def test_create_invoice_with_webhook(init_data: str):
    """Тест создания invoice с backend_webhook_url"""
    print("\n🔍 Тест создания invoice с backend_webhook_url...")
    
    headers = {
        "X-Telegram-Init-Data": init_data,
        "Content-Type": "application/json"
    }
    
    payload = {
        "user_id": TEST_USER_ID,
        "title": "Test Package",
        "description": "Тестовый пакет для проверки webhook",
        "amount_stars": 100,
        "payload": '{"test": "data"}',
        "return_link": True,
        "backend_webhook_url": TEST_BACKEND_WEBHOOK
    }
    
    print(f"   Отправка запроса к {API_BASE_URL}/api/payments/create-invoice")
    print(f"   Backend webhook URL: {TEST_BACKEND_WEBHOOK}")
    
    response = requests.post(
        f"{API_BASE_URL}/api/payments/create-invoice",
        headers=headers,
        json=payload
    )
    
    print(f"   Статус: {response.status_code}")
    print(f"   Ответ: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    return response

def test_create_invoice_without_webhook(init_data: str):
    """Тест создания invoice БЕЗ backend_webhook_url (обратная совместимость)"""
    print("\n🔍 Тест обратной совместимости (без backend_webhook_url)...")
    
    headers = {
        "X-Telegram-Init-Data": init_data,
        "Content-Type": "application/json"
    }
    
    payload = {
        "user_id": TEST_USER_ID,
        "title": "Test Package",
        "description": "Тестовый пакет без webhook",
        "amount_stars": 50,
        "payload": '{"test": "backward_compat"}',
        "return_link": True
        # backend_webhook_url НЕ указан
    }
    
    response = requests.post(
        f"{API_BASE_URL}/api/payments/create-invoice",
        headers=headers,
        json=payload
    )
    
    print(f"   Статус: {response.status_code}")
    print(f"   Ответ: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    return response

def test_invalid_webhook_url(init_data: str):
    """Тест с невалидным webhook URL (должен вернуть ошибку)"""
    print("\n🔍 Тест невалидного webhook URL (должен быть отклонен)...")
    
    headers = {
        "X-Telegram-Init-Data": init_data,
        "Content-Type": "application/json"
    }
    
    # Тест 1: HTTP вместо HTTPS
    payload = {
        "user_id": TEST_USER_ID,
        "title": "Test",
        "description": "Test",
        "amount_stars": 100,
        "payload": "test",
        "return_link": True,
        "backend_webhook_url": "http://insecure.example.com/webhook"  # HTTP - должен быть отклонен
    }
    
    print("   Тест 1: HTTP URL (должен быть отклонен)...")
    response = requests.post(
        f"{API_BASE_URL}/api/payments/create-invoice",
        headers=headers,
        json=payload
    )
    print(f"   Статус: {response.status_code} (ожидается 400)")
    if response.status_code != 200:
        print(f"   ✅ Правильно отклонен: {response.json().get('detail', '')}")
    else:
        print(f"   ❌ Ошибка: HTTP URL не должен приниматься!")
    
    return response

def main():
    print("=" * 60)
    print("🧪 Тестирование Payment Webhook System")
    print("=" * 60)
    
    # 1. Проверка health
    health = test_health()
    
    if not health.get("payments_enabled"):
        print("\n❌ Платежи отключены на сервере!")
        sys.exit(1)
    
    if health.get("bot_instance") != "initialized":
        print("\n❌ Бот не инициализирован!")
        sys.exit(1)
    
    print("\n✅ Сервер готов к тестированию")
    
    # 2. Запрос initData
    print("\n" + "=" * 60)
    print("⚠️  Для полноценного теста нужен валидный initData")
    print("=" * 60)
    print("\nВарианты получения initData:")
    print("1. Из Mini App: Telegram.WebApp.initData")
    print("2. Из консоли браузера в Mini App")
    print("3. Использовать скрипт scripts/get_chat_id_auto.py")
    print("\nВведите initData (или нажмите Enter для пропуска):")
    
    init_data = input().strip()
    
    if not init_data:
        print("\n⚠️  initData не предоставлен, пропускаем тесты с авторизацией")
        print("\n✅ Базовые проверки пройдены!")
        print("\nДля полного теста:")
        print("1. Откройте Mini App в Telegram")
        print("2. Получите initData из консоли браузера:")
        print("   console.log(Telegram.WebApp.initData)")
        print("3. Запустите скрипт снова с этим initData")
        return
    
    # 3. Тесты с авторизацией
    print("\n" + "=" * 60)
    print("Запуск тестов с авторизацией...")
    print("=" * 60)
    
    # Тест 1: С webhook URL
    test_create_invoice_with_webhook(init_data)
    
    # Тест 2: Без webhook URL (обратная совместимость)
    test_create_invoice_without_webhook(init_data)
    
    # Тест 3: Невалидный URL
    test_invalid_webhook_url(init_data)
    
    print("\n" + "=" * 60)
    print("✅ Тестирование завершено!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Тестирование прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
