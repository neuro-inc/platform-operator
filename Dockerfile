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

RUN curl https://raw.githubusercontent.com/kubernetes/helm/master/scripts/get | bash -s -- -v v2.17.0

WORKDIR /app

COPY --from=installer /root/.local/ /root/.local/

ENV PATH=/root/.local/bin:$PATH

ENTRYPOINT ["kopf", "run", "-m", "platform_operator.handlers"]
