# Отчет: Отправка placeholder image вместо текста при нажатии Generate

## Проблема
При нажатии на кнопку "Generate" в inline query сообщение редактировалось на текст "⏳ Generating…", а затем пыталось замениться на изображение (InputMediaDocument). Telegram может не позволить замену типа медиа (text → document) для inline_message_id, что приводило к fallback на текст без изображения.

## Решение
Вместо редактирования на текст сразу отправляется placeholder image (512x512, прозрачный фон, текст "Generating...") как InputMediaPhoto. Это упрощает замену на финальное изображение, так как:
- Image → Image проще, чем Text → Image
- Telegram лучше обрабатывает замену одного типа медиа на другой (photo → document или photo → photo)

## Изменения

### 1. `src/utils/image_postprocess.py`
Добавлена функция `create_placeholder_image()`:
- Создает PNG изображение 512x512 с прозрачным фоном
- Рисует текст "Generating..." по центру
- Возвращает байты PNG

### 2. `src/bot/handlers/generation.py`
**В `handle_generate_callback()` и `handle_regenerate_callback()`:**
- Для `inline_message_id`: сразу отправляется placeholder image через `edit_message_media(InputMediaPhoto)`
- Для обычных сообщений: остается текст (как было)
- Fallback: если не удалось отправить placeholder, используется текст

**Логика:**
```
Нажатие Generate (inline_message_id):
├─ Попытка: edit_message_media(InputMediaPhoto(placeholder))
│  └─ Успех → ✅ Placeholder показан
│  └─ Ошибка → Fallback на edit_message_text("⏳ Generating…")
└─ Затем в run_generation_and_update_message:
   └─ Замена placeholder на финальное изображение (photo → document или photo → photo)
```

### 3. `tests/test_utils/test_image_postprocess.py`
Добавлены тесты:
- `test_create_placeholder_image()` - проверка создания placeholder
- `test_create_placeholder_image_custom_size()` - проверка кастомного размера

## Преимущества

1. **Упрощение замены медиа**: Image → Image проще, чем Text → Image
2. **Лучший UX**: Пользователь сразу видит визуальную индикацию генерации
3. **Меньше проблем с типами медиа**: Telegram лучше обрабатывает замену photo → document, чем text → document
4. **Fallback сохранен**: Если placeholder не удалось отправить, используется текст

## Ограничения

- Placeholder создается синхронно (быстро, ~4KB)
- Для обычных сообщений (не inline) остается текст (не критично)
- Если отправка placeholder не удалась, используется текст (fallback)

## Тесты

✅ Все тесты проходят:
- `test_create_placeholder_image` ✅
- `test_create_placeholder_image_custom_size` ✅
- Все существующие тесты generation ✅

## Следующие шаги

После этого изменения замена placeholder → финальное изображение должна работать лучше, так как:
- Если bg-remover успешен: placeholder (photo) → document (webp) - может работать лучше, чем text → document
- Если bg-remover не успешен: placeholder (photo) → photo (финальное) - должно работать без проблем

Это может значительно уменьшить количество случаев, когда приходится использовать fallback на текст.




