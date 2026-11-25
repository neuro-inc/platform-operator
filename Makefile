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
	@for chart in charts/*; do \
		helm lint $$chart || exit $$?; \
	done

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
	helm unittest charts/*

.PHONY: test_plugin
test_plugin:
	cd charts/platform/files/tokenfilter && go test ./...
	cd charts/platform/files/tokenfilter && GOTOOLCHAIN=go1.21.13 go run github.com/traefik/yaegi/cmd/yaegi@v0.15.1 test -v .
	cd charts/platform/files/tokenfilter && GOTOOLCHAIN=go1.23.12 go run github.com/traefik/yaegi/cmd/yaegi@v0.16.1 test -v .
