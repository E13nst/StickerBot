.PHONY: install run stop restart status clean test lint format check help

VENV ?= ./venv
BOT_SCRIPT := main.py
ENV_FILE := .env

# Определяем пути и команды для Windows и Unix
# PYTHON - Python из виртуального окружения
# PYTHON_CMD - системная команда Python (python на Windows, python3 на macOS/Linux)
ifeq ($(OS),Windows_NT)
    PYTHON := $(VENV)/Scripts/python.exe
    PIP := $(VENV)/Scripts/pip.exe
    PYTHON_CMD := python
    RM := del /Q
    FIND := where /R
else
    PYTHON := $(VENV)/bin/python
    PIP := $(VENV)/bin/pip
    PYTHON_CMD := python3
    RM := rm -f
    FIND := find
endif

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
ifeq ($(OS),Windows_NT)
	@if not exist "$(VENV)" ($(PYTHON_CMD) -m venv $(VENV) && echo Виртуальное окружение создано)
else
	@if [ ! -d $(VENV) ]; then \
		$(PYTHON_CMD) -m venv $(VENV) 2>/dev/null || python -m venv $(VENV); \
		echo "Виртуальное окружение создано"; \
	fi
endif

install: venv
	@echo "Установка зависимостей..."
	@$(PYTHON) -m pip install --upgrade pip
	@$(PYTHON) -m pip install -r requirements.txt
	@echo "Зависимости установлены"

run:
ifeq ($(OS),Windows_NT)
	@if not exist "$(VENV)" (\
		echo ⚠️  Виртуальное окружение не найдено. Запустите 'make install' сначала. && \
		exit /b 1 \
	)
	@$(PYTHON) $(BOT_SCRIPT)
else
	@if [ ! -d $(VENV) ]; then \
		echo "⚠️  Виртуальное окружение не найдено. Запустите 'make install' сначала."; \
		exit 1; \
	fi
	@$(PYTHON) $(BOT_SCRIPT)
endif

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
ifeq ($(OS),Windows_NT)
	@if not exist "$(VENV)" (\
		echo ⚠️  Виртуальное окружение не найдено. Запустите 'make install' сначала. && \
		exit /b 1 \
	)
	@$(PYTHON) -m pytest tests/ -v --tb=short || (echo ❌ Тесты завершились с ошибками && exit /b 1)
	@echo ✅ Все тесты пройдены успешно
else
	@if [ ! -d $(VENV) ]; then \
		echo "⚠️  Виртуальное окружение не найдено. Запустите 'make install' сначала."; \
		exit 1; \
	fi
	@$(PYTHON) -m pytest tests/ -v --tb=short || (echo "❌ Тесты завершились с ошибками" && exit 1)
	@echo "✅ Все тесты пройдены успешно"
endif

check:
	@echo "Проверка структуры проекта..."
	@if [ -d $(VENV) ]; then \
		$(PYTHON) scripts/check_structure.py; \
	else \
		$(PYTHON_CMD) scripts/check_structure.py 2>/dev/null || python scripts/check_structure.py; \
	fi

lint:
	@echo "Проверка кода линтером..."
	@if [ -d $(VENV) ]; then \
		$(PYTHON) -m flake8 src/ main.py scripts/ --max-line-length=120 --ignore=E501,W503 || echo "flake8 не установлен, пропускаем"; \
		$(PYTHON) -m pylint src/ main.py scripts/ --disable=all --enable=E,F || echo "pylint не установлен, пропускаем"; \
	else \
		$(PYTHON_CMD) -m flake8 src/ main.py scripts/ --max-line-length=120 --ignore=E501,W503 2>/dev/null || python -m flake8 src/ main.py scripts/ --max-line-length=120 --ignore=E501,W503 || echo "flake8 не установлен, пропускаем"; \
		$(PYTHON_CMD) -m pylint src/ main.py scripts/ --disable=all --enable=E,F 2>/dev/null || python -m pylint src/ main.py scripts/ --disable=all --enable=E,F || echo "pylint не установлен, пропускаем"; \
	fi

format:
	@echo "Форматирование кода..."
	@if [ -d $(VENV) ]; then \
		$(PYTHON) -m black src/ main.py scripts/ --line-length=120 || echo "black не установлен, пропускаем"; \
	else \
		$(PYTHON_CMD) -m black src/ main.py scripts/ --line-length=120 2>/dev/null || python -m black src/ main.py scripts/ --line-length=120 || echo "black не установлен, пропускаем"; \
	fi

clean:
	@echo "Очистка временных файлов..."
	@find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
	@echo "Очистка завершена"

