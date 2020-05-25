FROM python:3.8.3

RUN curl https://raw.githubusercontent.com/kubernetes/helm/master/scripts/get | bash -s -- -v v2.16.7

WORKDIR /neuromation

# installing dependencies ONLY
COPY setup.py ./
RUN \
    pip install -e . && \
    pip uninstall -y platform_operator

COPY platform_operator/ platform_operator/
RUN pip install -e .

CMD kopf run \
    --standalone \
    --namespace "$NP_PLATFORM_NAMESPACE" \
    --liveness=http://0.0.0.0:8080/healthz \
    -m platform_operator.handlers