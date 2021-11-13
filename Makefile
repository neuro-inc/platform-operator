GITHUB_OWNER ?= neuro-inc

IMAGE_TAG ?= latest

IMAGE_NAME      = platform-operator-controller
IMAGE_REPO_BASE = ghcr.io/$(GITHUB_OWNER)
IMAGE_REPO      = $(IMAGE_REPO_BASE)/$(IMAGE_NAME)

HELM_ENV           ?= dev
HELM_CHART         ?= platform-operator
HELM_CHART_VERSION ?= 1.0.0
HELM_APP_VERSION   ?= 1.0.0

WAIT_FOR_IT_URL = https://raw.githubusercontent.com/eficode/wait-for/master/wait-for
WAIT_FOR_IT = curl -s $(WAIT_FOR_IT_URL) | bash -s --

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
	pytest -vv tests/unit

test_integration:
	docker-compose -f tests/integration/docker/docker-compose.yaml pull -q
	docker-compose -f tests/integration/docker/docker-compose.yaml up -d
	@$(WAIT_FOR_IT) 0.0.0.0:8500 -- echo "consul is up"
	kubectl --context minikube apply -f charts/platform-operator/crds
	@pytest -vv --log-level=INFO tests/integration; \
	exit_code=$$?; \
	docker-compose -f tests/integration/docker/docker-compose.yaml down -v; \
	exit $$exit_code

docker_build:
	rm -rf build dist
	pip install -U build
	python -m build
	docker build \
		--build-arg PYTHON_BASE=slim-buster \
		-t $(IMAGE_NAME):latest .

helm_create_chart:
	export IMAGE_REPO=$(IMAGE_REPO); \
	export IMAGE_TAG=$(IMAGE_TAG); \
	export IMAGE_REPO_BASE=$(IMAGE_REPO_BASE); \
	export CHART_VERSION=$(HELM_CHART_VERSION); \
	export APP_VERSION=$(HELM_APP_VERSION); \
	VALUES=$$(cat charts/$(HELM_CHART)/values.yaml | envsubst); \
	echo "$$VALUES" > charts/$(HELM_CHART)/values.yaml; \
	CHART=$$(cat charts/$(HELM_CHART)/Chart.yaml | envsubst); \
	echo "$$CHART" > charts/$(HELM_CHART)/Chart.yaml
