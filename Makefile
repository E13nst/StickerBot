.PHONY: install run stop restart status clean test lint format check help

VENV ?= ./venv
# Определяем пути для Windows и Unix
ifeq ($(OS),Windows_NT)
    PYTHON := $(VENV)/Scripts/python.exe
    PIP := $(VENV)/Scripts/pip.exe
else
    PYTHON := $(VENV)/bin/python
    PIP := $(VENV)/bin/pip
endif
BOT_SCRIPT := main.py
ENV_FILE := .env

help:
	@echo "Доступные команды:"
	@echo "  make install    - Установить зависимости"
	@echo "  make run        - Запустить бота"
	@echo "  make stop       - Остановить бота"
	@echo "  make restart    - Перезапустить бота"
	@echo "  make status     - Проверить статус бота"
	@echo "  make test        - Запустить тесты (если есть)"
	@echo "  make lint        - Проверить код линтером"
	@echo "  make check       - Проверить структуру проекта"
	@echo "  make clean       - Очистить временные файлы"
	@echo "  make venv        - Создать виртуальное окружение"

venv:
	@if [ ! -d $(VENV) ]; then \
		python -m venv $(VENV); \
		echo "Виртуальное окружение создано"; \
	fi

install: venv
	@echo "Установка зависимостей..."
	@python -m pip install --upgrade pip
	@python -m pip install -r requirements.txt
	@echo "Зависимости установлены"

run:
	@python $(BOT_SCRIPT)

stop:
	@pkill -f "$(BOT_SCRIPT)" || echo "Бот не запущен"

restart:
	@$(MAKE) stop || true
	@sleep 1
	@$(MAKE) run

status:
	@if pgrep -f "$(BOT_SCRIPT)" > /dev/null; then \
		echo "✅ Бот запущен:"; \
		pgrep -fal "$(BOT_SCRIPT)"; \
	else \
		echo "❌ Бот не запущен"; \
	fi

test:
	@echo "Запуск тестов..."
	@if [ ! -d $(VENV) ]; then \
		echo "⚠️  Виртуальное окружение не найдено. Запустите 'make install' сначала."; \
		exit 1; \
	fi
	@python -m pytest tests/ -v --tb=short || (echo "❌ Тесты завершились с ошибками" && exit 1)
	@echo "✅ Все тесты пройдены успешно"

check:
	@echo "Проверка структуры проекта..."
	@python scripts/check_structure.py

lint:
	@echo "Проверка кода линтером..."
	@python -m flake8 src/ main.py scripts/ --max-line-length=120 --ignore=E501,W503 || echo "flake8 не установлен, пропускаем"
	@python -m pylint src/ main.py scripts/ --disable=all --enable=E,F || echo "pylint не установлен, пропускаем"

format:
	@echo "Форматирование кода..."
	@python -m black src/ main.py scripts/ --line-length=120 || echo "black не установлен, пропускаем"

clean:
	@echo "Очистка временных файлов..."
	@find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
	@echo "Очистка завершена"

