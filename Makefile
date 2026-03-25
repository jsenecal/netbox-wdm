NETBOX_DIR  := /opt/netbox/netbox
MANAGE      := cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py
PYTEST      := cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest
PLUGIN_PKG  := netbox_wdm

.DEFAULT_GOAL := help

.PHONY: lint format check test test-fast migrations migrate runserver superuser collectstatic sample-data sample-data-flush verify validate build clean ts-install ts-build ts-typecheck help

lint:
	uvx ruff check --fix $(PLUGIN_PKG)/

format:
	uvx ruff format $(PLUGIN_PKG)/

check:
	uvx ruff check $(PLUGIN_PKG)/
	uvx ruff format --check --exclude migrations $(PLUGIN_PKG)/

test:
	$(PYTEST) $(CURDIR)/tests/ -v

test-fast:
	$(PYTEST) $(CURDIR)/tests/ -v --no-cov

migrations:
	$(MANAGE) makemigrations $(PLUGIN_PKG)

migrate:
	$(MANAGE) migrate

runserver:
	$(MANAGE) runserver 0.0.0.0:8080

superuser:
	@cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from django.contrib.auth import get_user_model; User = get_user_model(); print('exists') if User.objects.filter(username='admin').exists() else (User.objects.create_superuser('admin', 'admin@example.com', 'admin'), print('created admin:admin'))"

sample-data:
	$(MANAGE) create_wdm_sample_data

sample-data-flush:
	$(MANAGE) create_wdm_sample_data --flush

collectstatic:
	$(MANAGE) collectstatic --no-input

verify:
	@cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from $(PLUGIN_PKG).models import *; from $(PLUGIN_PKG).forms import *; from $(PLUGIN_PKG).filters import *; print('OK')"

validate: check verify

ts-install:
	cd $(PLUGIN_PKG)/static/$(PLUGIN_PKG) && npm install

ts-build: ts-install
	cd $(PLUGIN_PKG)/static/$(PLUGIN_PKG) && npm run build

ts-typecheck:
	cd $(PLUGIN_PKG)/static/$(PLUGIN_PKG) && npm run typecheck

help:
	@grep -E '^[a-zA-Z_-]+:.*' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*"}; {printf "\033[36m%-18s\033[0m\n", $$1}'
