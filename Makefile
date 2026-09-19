# Punjaber — learn conversational Punjabi.
# Everything runs in Docker; you need nothing installed but Docker and make.

COMPOSE ?= docker compose
DEV_COMPOSE = $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
PORT ?= 8000

.DEFAULT_GOAL := help
.PHONY: help start up build dev down stop restart logs test lint shell open clean reset-data audio-clear recordings-backup recordings-restore status

help: ## Show this help
	@echo "Punjaber"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Start here:  make start   then open http://localhost:$(PORT)"

start: ## Build if needed, start the app, and print the URL
	@$(COMPOSE) up -d --build
	@echo ""
	@echo "  Punjaber is running at http://localhost:$(PORT)"
	@echo "  Stop it with: make down"

up: ## Start the app in the background (no rebuild)
	$(COMPOSE) up -d

build: ## Build the Docker image
	$(COMPOSE) build

dev: ## Run in the foreground with live reload on code changes
	$(DEV_COMPOSE) up --build

down: ## Stop and remove the container
	$(COMPOSE) down

stop: ## Stop the container but keep it around
	$(COMPOSE) stop

restart: ## Restart the container
	$(COMPOSE) restart

logs: ## Follow the container logs
	$(COMPOSE) logs -f

status: ## Show container status and a health check
	@$(COMPOSE) ps
	@echo ""
	@$(COMPOSE) exec -T punjaber python -c "import urllib.request,json;print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health')))" \
		|| echo "  (not running — try: make start)"

test: ## Run the test suite inside the image
	$(COMPOSE) run --rm --no-deps punjaber python -m pytest -q

shell: ## Open a shell in the running container
	$(COMPOSE) exec punjaber /bin/bash

open: ## Open the app in your browser
	@python -c "import webbrowser;webbrowser.open('http://localhost:$(PORT)')" 2>/dev/null \
		|| echo "Open http://localhost:$(PORT)"

reset-data: ## Delete all saved progress (asks first)
	@printf "Delete ./data/punjaber.db and all progress? [y/N] " && read answer && [ "$$answer" = "y" ]
	rm -f data/punjaber.db data/punjaber.db-wal data/punjaber.db-shm
	@echo "Progress cleared."

recordings-backup: ## Zip your recordings to ./backups (they are irreplaceable)
	@mkdir -p backups
	@test -d data/recordings || { echo "No recordings yet."; exit 0; }
	tar -czf backups/recordings-$$(date +%Y%m%d-%H%M%S).tar.gz -C data recordings
	@ls -1t backups/recordings-*.tar.gz | head -1 | sed 's/^/  Saved /'

recordings-restore: ## Restore recordings from the newest backup in ./backups
	@test -n "$$(ls -1t backups/recordings-*.tar.gz 2>/dev/null | head -1)" \
		|| { echo "No backup found in ./backups"; exit 1; }
	tar -xzf $$(ls -1t backups/recordings-*.tar.gz | head -1) -C data
	@echo "Restored. Restart with: make restart"

audio-clear: ## Delete cached pronunciation clips (they re-render on demand)
	rm -rf data/audio
	@echo "Audio cache cleared."

clean: ## Stop everything and remove the image
	-$(COMPOSE) down --rmi local --volumes --remove-orphans
