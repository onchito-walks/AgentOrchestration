.PHONY: install test lint clean build run

install:
	uv sync

test:
	pytest --cov=src tests/ -v

lint:
	flake8 src/ tests/
	mypy src/ --ignore-missing-imports

clean:
	rm -rf build/ dist/ *.egg-info/ __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build:
	uv build

run:
	uvicorn src.api.server:create_app --reload --host 0.0.0.0 --port 8000

docker-build:
	docker compose -f infra/docker-compose.yml build

docker-up:
	docker compose -f infra/docker-compose.yml up -d

docker-down:
	docker compose -f infra/docker-compose.yml down

# 2019-01-15T19:25:56 update
