up:
	docker compose up -d --build

down:
	docker compose down

migrate-profiles:
	docker compose exec profiles alembic upgrade head

migrate-booking:
	docker compose exec booking alembic upgrade head

test:
	cd services/profiles && python -m pytest -v
	cd services/booking && python -m pytest -v
	cd services/billing && python -m pytest -v
	cd services/analytics && python -m pytest -v
