.PHONY: install lint test unit integration e2e cov frontend ci docker
install:
	pip install -r requirements-dev.txt && cd frontend && npm ci
lint:
	ruff check app scripts tests
unit:
	pytest tests/unit -m unit
integration:
	pytest tests/integration -m integration
e2e: frontend
	pytest tests/e2e -m e2e
cov:
	pytest tests/unit tests/integration --cov --cov-report=term-missing --cov-report=xml
frontend:
	cd frontend && npm run build
ci: lint cov frontend e2e
docker:
	docker build -t reverse-chatbot .
