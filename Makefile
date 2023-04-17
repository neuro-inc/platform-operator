setup:
	pip install -U pip
	pip install -e .[dev]
	pre-commit install

format:
ifdef CI_LINT_RUN
	pre-commit run --all-files --show-diff-on-failure
else
	pre-commit run --all-files
endif

lint: format
	mypy platform_operator tests

test_unit:
	pytest -vv --cov=platform_operator --cov-report xml:.coverage-unit.xml tests/unit

test_integration:
	kubectl --context minikube apply -f charts/platform-operator/crds
	pytest -vv --log-level=INFO --cov=platform_operator --cov-report xml:.coverage-integration.xml tests/integration
docker_build:
	rm -rf build dist
	pip install -U build
	python -m build
	docker build -t platform-operator-controller:latest .
