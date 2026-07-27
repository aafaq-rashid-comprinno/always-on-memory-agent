.PHONY: run dashboard docker-up docker-down clean lint test help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

run: ## Run the agent locally
	PYTHONPATH=. python -m src.main

dashboard: ## Run the Streamlit dashboard
	streamlit run dashboard.py

docker-up: ## Start all services with Docker Compose
	docker compose up --build -d

docker-down: ## Stop all Docker services
	docker compose down

docker-logs: ## Tail Docker logs
	docker compose logs -f

clean: ## Remove database and processed files
	rm -f data/memory.db
	rm -f inbox/*

lint: ## Run linter
	ruff check src/ dashboard.py

format: ## Auto-format code
	ruff format src/ dashboard.py

test: ## Run tests
	PYTHONPATH=. pytest tests/ -v

install: ## Install dependencies
	pip install -r requirements.txt

install-dev: ## Install dev dependencies
	pip install -e ".[dev]"
