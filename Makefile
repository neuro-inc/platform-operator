TAG ?= latest
DOCKER_REPO ?= neuro-docker-local-anonymous.jfrog.io
IMAGE = $(DOCKER_REPO)/platform-operator-controller:$(TAG)

setup:
	pip install setuptools wheel
	pip install -r requirements/dev.txt
	pre-commit install

format:
ifdef CI_LINT_RUN
	pre-commit run --all-files --show-diff-on-failure
else
	pre-commit run --all-files
endif

lint: format
	mypy platform_operator tests setup.py

test_unit:
	pytest -vv tests/unit

test_integration:
	kubectl --context minikube apply -f deploy/platform-operator/templates/crd.yaml
	pytest -vv --log-level=INFO tests/integration

docker_build:
	docker build -t $(IMAGE) .

docker_login:
	@docker login $(DOCKER_REPO) \
		--username=$(ARTIFACTORY_USERNAME) \
		--password=$(ARTIFACTORY_PASSWORD)

docker_push: docker_build
ifeq ($(TAG),latest)
	$(error Docker image tag is not specified)
endif
	docker push $(IMAGE)

helm_install:
	curl https://raw.githubusercontent.com/kubernetes/helm/master/scripts/get \
		| bash -s -- -v v2.16.7

helm_plugin_install:
	helm plugin install https://github.com/belitre/helm-push-artifactory-plugin

helm_repo_add:
ifeq ($(ARTIFACTORY_USERNAME),)
	$(error Artifactory username is not specified)
endif
ifeq ($(ARTIFACTORY_PASSWORD),)
	$(error Artifactory password is not specified)
endif
	@helm repo add neuro \
		https://neuro.jfrog.io/artifactory/helm-virtual-public \
		--username ${ARTIFACTORY_USERNAME} \
		--password ${ARTIFACTORY_PASSWORD}
	@helm repo add neuro-local-public \
		https://neuro.jfrog.io/artifactory/helm-local-public \
		--username ${ARTIFACTORY_USERNAME} \
		--password ${ARTIFACTORY_PASSWORD}
	@helm repo add neuro-local-anonymous \
		https://neuro.jfrog.io/artifactory/helm-local-anonymous \
		--username ${ARTIFACTORY_USERNAME} \
		--password ${ARTIFACTORY_PASSWORD}

helm_push:
ifeq ($(TAG),latest)
	$(error Helm package tag is not specified)
endif
	rm -rf deploy/platform/charts
	helm dependency update deploy/platform
	helm package --app-version=$(TAG) --version=$(TAG) deploy/platform/
	helm push-artifactory platform-$(TAG).tgz neuro-local-public
	rm platform-$(TAG).tgz
	helm package --app-version=$(TAG) --version=$(TAG) deploy/platform-operator
	helm push-artifactory platform-operator-$(TAG).tgz neuro-local-anonymous
	rm platform-operator-$(TAG).tgz
