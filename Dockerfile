ARG PYTHON_VERSION=3.9.7
ARG PYTHON_BASE=buster

FROM python:${PYTHON_VERSION} AS installer

ENV PATH=/root/.local/bin:$PATH

# Copy to tmp folder to don't pollute home dir
RUN mkdir -p /tmp/dist
COPY dist /tmp/dist

RUN ls /tmp/dist
RUN pip install --user --find-links /tmp/dist platform-operator

FROM python:${PYTHON_VERSION}-${PYTHON_BASE} AS service

LABEL org.opencontainers.image.source = "https://github.com/neuro-inc/platform-operator"

RUN apt-get update && apt-get install -y curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash -s -- -v v3.7.0

WORKDIR /app

COPY --from=installer /root/.local/ /root/.local/

ENV PATH=/root/.local/bin:$PATH

ENTRYPOINT ["kopf", "run", "-m", "platform_operator.handlers"]
