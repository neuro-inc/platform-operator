FROM python:3.9.18-slim-bookworm AS packages

ENV PATH=/root/.local/bin:$PATH

# Copy to tmp folder to don't pollute home dir
RUN mkdir -p /tmp/dist
COPY dist /tmp/dist

RUN ls /tmp/dist
RUN pip install --user --find-links /tmp/dist platform-operator


FROM python:3.9.18-slim-bookworm AS service

LABEL org.opencontainers.image.source = "https://github.com/neuro-inc/platform-operator"

RUN apt-get update && apt-get install -y curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash -s -- -v v3.14.0

RUN mkdir /etc/platform \
    && curl -o /etc/platform/ca_staging.pem https://letsencrypt.org/certs/staging/letsencrypt-stg-root-x1.pem

WORKDIR /app

COPY --from=packages /root/.local/ /root/.local/

ENV PATH=/root/.local/bin:$PATH

ENTRYPOINT ["kopf", "run", "-m", "platform_operator.handlers"]
