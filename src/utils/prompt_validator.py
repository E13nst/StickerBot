"""Валидация промптов для генерации"""
import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Простейший список запрещенных фраз для prompt injection
INJECTION_PHRASES = [
    "ignore previous instructions",
    "system prompt",
    "forget the system",
    "disregard the above",
]

# Простейший список запрещенных слов для NSFW (можно расширить)
NSFW_WORDS = [
    # Добавить при необходимости
]


def validate_prompt(prompt: str) -> Tuple[bool, Optional[str]]:
    """
    Валидация промпта для генерации
    
    Args:
        prompt: Промпт пользователя
        
    Returns:
        (is_valid, error_message)
    """
    if not prompt:
        return False, "Prompt cannot be empty"
    
    # Trim пробелов
    prompt = prompt.strip()
    
    if not prompt:
        return False, "Prompt cannot be empty"
    
    # Проверка длины
    MAX_LEN = 320
    if len(prompt) > MAX_LEN:
        return False, f"Prompt too long (max {MAX_LEN} characters)"
    
    # Удаление control characters (кроме \n, \t)
    # Заменяем на пробелы
    prompt_cleaned = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', ' ', prompt)
    if prompt_cleaned != prompt:
        prompt = prompt_cleaned.strip()
    
    # Проверка на prompt injection
    prompt_lower = prompt.lower()
    for phrase in INJECTION_PHRASES:
        if phrase in prompt_lower:
            logger.warning(f"Prompt injection attempt detected: {prompt[:50]}...")
            return False, "Prompt contains forbidden phrases"
    
    # Простейшая фильтрация повторов (не более 3 одинаковых слов подряд)
    words = prompt.split()
    if len(words) > 3:
        for i in range(len(words) - 3):
            if words[i] == words[i+1] == words[i+2] == words[i+3]:
                return False, "Prompt contains too many repeated words"
    
    # Опционально: проверка на NSFW слова
    if NSFW_WORDS:
        prompt_lower_words = set(prompt_lower.split())
        for word in NSFW_WORDS:
            if word in prompt_lower_words:
                logger.warning(f"NSFW word detected in prompt: {word}")
                return False, "Prompt contains inappropriate content"
    
    return True, None




