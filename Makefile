.PHONY: all test clean
all test clean:

.PHONY: venv
venv:
	poetry lock
	poetry install --with dev;

.PHONY: build
build: venv poetry-plugins

.PHONY: poetry-plugins
poetry-plugins:
	poetry self add "poetry-dynamic-versioning[plugin]"; \
    poetry self add "poetry-plugin-export";

.PHONY: setup
setup: venv
	poetry run pre-commit install;


.PHONY: lint
lint: format
	poetry run mypy platform_operator tests

format:
ifdef CI_LINT_RUN
	pre-commit run --all-files --show-diff-on-failure
else
	pre-commit run --all-files
endif

.PHONY: test_unit
test_unit:
	poetry run pytest -vv --cov-config=pyproject.toml --cov-report xml:.coverage.unit.xml tests/unit


.PHONY: test_integration
test_integration:
	kubectl --context minikube apply -f charts/platform-operator/crds
	poetry run pytest -vv --log-level=INFO --cov-config=pyproject.toml --cov-report xml:.coverage.integration.xml tests/integration

.PHONY: clean-dist
clean-dist:
	rm -rf dist

IMAGE_NAME = platform-operator-controller

.PHONY: docker_build
docker_build: dist
	docker build \
		--build-arg PY_VERSION=$$(cat .python-version) \
		-t $(IMAGE_NAME):latest .

.python-version:
	@echo "Error: .python-version file is missing!" && exit 1

.PHONY: dist
dist: build
	rm -rf build dist; \
	poetry export -f requirements.txt --without-hashes -o requirements.txt; \
	poetry build -f wheel;
