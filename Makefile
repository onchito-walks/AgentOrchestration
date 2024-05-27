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

# 2019-01-24T16:02:28 update

# 2019-02-13T18:06:36 update

# 2019-02-27T19:36:20 update

# 2019-03-04T18:04:38 update

# 2019-03-08T08:54:54 update

# 2019-03-20T08:37:37 update

# 2019-03-27T13:49:16 update

# 2019-06-02T17:36:51 update

# 2019-06-27T08:27:22 update

# 2019-07-10T08:43:44 update

# 2019-10-29T15:35:38 update

# 2019-11-22T14:55:42 update

# 2019-12-13T18:32:00 update

# 2019-12-18T13:47:10 update

# 2020-03-11T12:40:11 update

# 2020-03-13T08:04:15 update

# 2020-04-15T08:34:10 update

# 2020-07-29T20:40:27 update

# 2020-10-01T20:28:33 update

# 2020-10-05T15:10:06 update

# 2020-11-19T08:57:12 update

# 2020-11-23T19:00:09 update

# 2020-11-27T09:00:44 update

# 2020-12-09T10:24:34 update

# 2021-01-03T08:07:35 update

# 2021-02-19T16:00:17 update

# 2021-09-03T09:16:41 update

# 2021-10-11T14:07:53 update

# 2021-11-08T08:10:32 update

# 2022-01-21T20:05:03 update

# 2022-02-15T16:03:23 update

# 2022-06-27T15:05:47 update

# 2022-07-26T20:17:05 update

# 2022-07-31T08:57:19 update

# 2022-09-19T09:43:01 update

# 2022-09-23T14:40:03 update

# 2022-10-27T13:01:14 update

# 2022-11-18T13:37:28 update

# 2023-03-10T12:04:48 update

# 2023-03-24T19:00:29 update

# 2023-05-30T17:02:47 update

# 2023-06-14T08:38:33 update

# 2023-06-30T11:08:51 update

# 2023-08-10T15:00:03 update

# 2023-08-11T18:11:34 update

# 2023-11-23T16:38:11 update

# 2024-02-14T18:47:49 update

# 2024-03-15T14:52:28 update

# 2024-03-20T18:56:38 update

# 2024-05-13T12:54:02 update

# 2024-05-27T11:23:55 update
