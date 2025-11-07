.PHONY: install run stop restart status clean

VENV ?= ./venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
BOT_SCRIPT := bot.py

install:
	$(PIP) install -r requirements.txt

run:
	$(PYTHON) $(BOT_SCRIPT)

stop:
	pkill -f "$(BOT_SCRIPT)" || true

restart:
	$(MAKE) stop || true
	$(MAKE) run

status:
	pgrep -fal "$(BOT_SCRIPT)" || echo "bot.py is not running"

clean:
	rm -rf __pycache__

