.PHONY: help install backend frontend seed test lint build up down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install backend + frontend dependencies
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

backend: ## Run the FastAPI backend (reload)
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload

frontend: ## Run the Vite dev server
	cd frontend && npm run dev

seed: ## Seed demo conversations (CALLS=50)
	cd backend && . .venv/bin/activate && python -m app.simulator --calls $(or $(CALLS),50)

test: ## Run backend tests
	cd backend && . .venv/bin/activate && pytest -q

lint: ## Lint backend (ruff) and typecheck frontend
	cd backend && . .venv/bin/activate && ruff check app tests
	cd frontend && npm run lint

build: ## Production build of the frontend
	cd frontend && npm run build

up: ## Start the full stack with Docker Compose
	docker compose up --build

down: ## Stop the stack
	docker compose down

clean: ## Remove local databases and build artifacts
	rm -rf backend/data frontend/dist
