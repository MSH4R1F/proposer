.PHONY: db-up db-down db-reset migrate test test-api test-db eval

db-up:
	docker compose up -d postgres
	@until docker compose exec -T postgres pg_isready -U proposer -d proposer >/dev/null 2>&1; do sleep 0.5; done

db-down:
	docker compose down

db-reset:
	@test "$${APP_ENV:-local}" = "local" || (echo "db-reset is local-only; refusing for APP_ENV=$${APP_ENV}" && exit 1)
	docker compose down -v
	$(MAKE) db-up
	$(MAKE) migrate

migrate:
	alembic -c alembic.ini upgrade head

test-api:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest apps/api/tests --ignore=apps/api/tests/db -p pytest_asyncio.plugin -p no:cacheprovider

test-db:
	pytest apps/api/tests/db scripts/migrations/tests -p no:cacheprovider

test: test-api test-db

eval: db-up migrate
	python scripts/eval/run_eval.py
