TAG ?= latest
DOCKER_REPO ?= neuro-docker-local-anonymous.jfrog.io
IMAGE = $(DOCKER_REPO)/platform-operator-controller:$(TAG)

setup:
	pip install setuptools wheel
	pip install -r requirements/dev.txt

format:
	isort -rc platform_operator tests setup.py
	black .

lint:
	black --check platform_operator tests setup.py
	flake8 platform_operator tests setup.py
	mypy platform_operator tests setup.py

test_unit:
	pytest -vv tests/unit

test_integration:
	pytest -vv --log-level=INFO tests/integration

docker_build:
	docker build -t $(IMAGE) .

docker_push: docker_build
ifeq ($(TAG),latest)
	$(error Docker image tag is not specified)
endif
	docker push $(IMAGE)

helm_plugin_install:
	helm plugin install https://github.com/belitre/helm-push-artifactory-plugin

helm_repo_add:
ifeq ($(ARTIFACTORY_USERNAME),)
	$(error Artifactory username is not specified)
endif
ifeq ($(ARTIFACTORY_PASSWORD),)
	$(error Artifactory password is not specified)
endif
	helm repo add neuro-local-anonymous \
		https://neuro.jfrog.io/artifactory/helm-local-anonymous \
		--username ${ARTIFACTORY_USERNAME} \
		--password ${ARTIFACTORY_PASSWORD}

helm_push:
ifeq ($(TAG),latest)
	$(error Helm package tag is not specified)
endif
	helm package --app-version=$(TAG) --version=$(TAG) deploy/platform-operator
	helm push-artifactory platform-operator-$(TAG).tgz neuro-local-anonymous
	rm platform-operator-$(TAG).tgz
