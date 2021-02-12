ARTIFACTORY_DOCKER_REPO ?= neuro-docker-local-anonymous.jfrog.io

TAG ?= latest

IMAGE_NAME = platform-operator-controller
IMAGE = $(IMAGE_NAME):$(TAG)

ARTIFACTORY_IMAGE_REPO = $(ARTIFACTORY_DOCKER_REPO)/$(IMAGE_NAME)
ARTIFACTORY_IMAGE = $(ARTIFACTORY_IMAGE_REPO):$(TAG)

PLATFORM_HELM_CHART = platform
HELM_CHART = platform-operator

WAIT_FOR_IT_URL = https://raw.githubusercontent.com/eficode/wait-for/master/wait-for
WAIT_FOR_IT = curl -s $(WAIT_FOR_IT_URL) | bash -s --

setup:
	pip install -U pip
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
	docker-compose -f tests/integration/docker/docker-compose.yaml pull -q
	docker-compose -f tests/integration/docker/docker-compose.yaml up -d
	@$(WAIT_FOR_IT) 0.0.0.0:8500 -- echo "consul is up"
	kubectl --context minikube apply -f deploy/platform-operator/templates/crd.yaml
	@pytest -vv --log-level=INFO tests/integration; \
	exit_code=$$?; \
	docker-compose -f tests/integration/docker/docker-compose.yaml down -v; \
	exit $$exit_code

docker_build:
	docker build -t $(IMAGE) .

artifactory_docker_push: docker_build
	docker tag $(IMAGE) $(ARTIFACTORY_IMAGE)
	docker push $(ARTIFACTORY_IMAGE)

helm_install:
	curl https://raw.githubusercontent.com/kubernetes/helm/master/scripts/get | bash -s -- -v $(HELM_VERSION)
	helm init --client-only
	helm plugin install https://github.com/belitre/helm-push-artifactory-plugin

helm_repo_add:
	@helm repo add neuro https://neuro.jfrog.io/artifactory/helm-virtual-public \
		--username ${ARTIFACTORY_USERNAME} \
		--password ${ARTIFACTORY_PASSWORD}
	@helm repo add neuro-local-public https://neuro.jfrog.io/artifactory/helm-local-public \
		--username ${ARTIFACTORY_USERNAME} \
		--password ${ARTIFACTORY_PASSWORD}
	@helm repo add neuro-local-anonymous https://neuro.jfrog.io/artifactory/helm-local-anonymous \
		--username ${ARTIFACTORY_USERNAME} \
		--password ${ARTIFACTORY_PASSWORD}

_helm_fetch:
	rm -rf temp_deploy

	mkdir -p temp_deploy/$(PLATFORM_HELM_CHART)
	cp -Rf deploy/$(PLATFORM_HELM_CHART) temp_deploy/
	find temp_deploy/$(PLATFORM_HELM_CHART) -type f -name 'values*' -delete
	helm dependency update temp_deploy/$(PLATFORM_HELM_CHART)

	mkdir -p temp_deploy/$(HELM_CHART)
	cp -Rf deploy/$(HELM_CHART) temp_deploy/
	find temp_deploy/$(HELM_CHART) -type f -name 'values*' -delete

_helm_expand_vars:
	export IMAGE_REPO=$(ARTIFACTORY_IMAGE_REPO); \
	export IMAGE_TAG=$(TAG); \
	export DOCKER_SERVER=$(ARTIFACTORY_DOCKER_REPO); \
	cat deploy/$(PLATFORM_HELM_CHART)/values-template.yaml | envsubst > temp_deploy/$(PLATFORM_HELM_CHART)/values.yaml; \
	cat deploy/$(HELM_CHART)/values-template.yaml | envsubst > temp_deploy/$(HELM_CHART)/values.yaml

artifactory_helm_push: _helm_fetch _helm_expand_vars
	helm package --version=$(TAG) --app-version=$(TAG) temp_deploy/$(PLATFORM_HELM_CHART)
	helm push-artifactory $(PLATFORM_HELM_CHART)-$(TAG).tgz neuro-local-public
	rm $(PLATFORM_HELM_CHART)-$(TAG).tgz

	helm package --version=$(TAG) --app-version=$(TAG) temp_deploy/$(HELM_CHART)
	helm push-artifactory $(HELM_CHART)-$(TAG).tgz neuro-local-anonymous
	rm $(HELM_CHART)-$(TAG).tgz
