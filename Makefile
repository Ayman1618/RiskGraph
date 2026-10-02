.PHONY: help up down restart status build test lint format stream batch dq graph-sync seed-db clean

help:
	@echo "RiskGraph — Real-Time Fraud & Identity Platform"
	@echo "Available commands:"
	@echo "  make up          - Start all services with Docker Compose"
	@echo "  make down        - Stop and tear down all Docker Compose services"
	@echo "  make restart     - Restart all containers"
	@echo "  make status      - Check health and connectivity of local platform services"
	@echo "  make test        - Run test suite with pytest and code coverage"
	@echo "  make stream      - Generate real-time synthetic transaction stream"
	@echo "  make batch       - Run Lakehouse PySpark Batch ETL (Bronze -> Silver -> Gold)"
	@echo "  make dq          - Run automated Data Quality validation checks"
	@echo "  make graph-sync  - Synchronize identity entities into Neo4j graph"
	@echo "  make lint        - Run linters (flake8, black, isort)"
	@echo "  make clean       - Remove cache, temporary checkpoints, and test artifacts"

up:
	docker compose up -d

down:
	docker compose down

restart: down up

status:
	python cli.py status

build:
	docker compose build

test:
	pytest --cov=src tests/

lint:
	flake8 src/ tests/ dags/ cli.py --max-line-length=120 || true
	black --check src/ tests/ dags/ cli.py
	isort --check-only src/ tests/ dags/ cli.py

format:
	black src/ tests/ dags/ cli.py
	isort src/ tests/ dags/ cli.py

stream:
	python cli.py generate-stream --rate 5 --count 100

stream-kafka:
	python cli.py generate-stream --rate 10 --kafka

dq:
	python cli.py run-dq-suite --sample-size 500

evaluate:
	python cli.py evaluate-tx --amount 8500 --emulator

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov /tmp/riskgraph
