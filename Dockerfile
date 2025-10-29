ARG PY_VERSION=3.9

FROM python:${PY_VERSION}-slim-bookworm AS builder

ENV PATH=/root/.local/bin:$PATH

WORKDIR /tmp
COPY requirements.txt /tmp/

RUN pip install --user --no-cache-dir -r requirements.txt

COPY dist /tmp/dist/
RUN pip install --user --no-cache-dir --find-links /tmp/dist platform-operator \
    && rm -rf /tmp/dist


FROM python:${PY_VERSION}-slim-bookworm AS runtime

LABEL org.opencontainers.image.source="https://github.com/neuro-inc/platform-operator"

RUN apt-get update && apt-get install -y curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash -s -- -v v3.14.0

ARG SERVICE_NAME="platform-operator"

RUN addgroup --gid 1001 $SERVICE_NAME && \
    adduser --gid 1001 --shell /bin/false --disabled-password --gecos "" --uid 1001 $SERVICE_NAME && \
    mkdir -p /var/log/$SERVICE_NAME && \
    chown $SERVICE_NAME:$SERVICE_NAME /var/log/$SERVICE_NAME

WORKDIR /home/${SERVICE_NAME}

ENV HOME=/home/${SERVICE_NAME}
ENV PYTHONUSERBASE=/home/${SERVICE_NAME}/.local
ENV PATH=/home/${SERVICE_NAME}/.local/bin:$PATH

COPY --from=builder --chown=$SERVICE_NAME /root/.local /home/${SERVICE_NAME}/.local

ENTRYPOINT ["kopf", "run", "-m", "platform_operator.handlers"]
