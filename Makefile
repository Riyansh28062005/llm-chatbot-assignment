.PHONY: up down test
up:
	@test -f .env || cp .env.example .env
	docker compose up --build -d
	@echo "Frontend http://localhost:3000  Backend http://localhost:8000"
down:
	docker compose down
test:
	cd backend && pytest -q
