.PHONY: all test clean
all test clean:

venv:
	python -m venv venv
	. venv/bin/activate; \
	pip install pre-commit

.PHONY: setup
setup: venv
	. venv/bin/activate; \
	python -m pre_commit install
	helm plugin install https://github.com/helm-unittest/helm-unittest.git


.PHONY: lint
lint: format
	helm lint charts/platform

.PHONY: format
format:
ifdef CI_LINT_RUN
	. venv/bin/activate; \
	python -m pre_commit run --all-files --show-diff-on-failure
else
	. venv/bin/activate; \
	python -m pre_commit run --all-files
endif


.PHONY: test_unit
test_unit:
	helm unittest charts/platform
