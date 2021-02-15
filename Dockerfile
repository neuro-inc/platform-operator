FROM python:3.9-buster

RUN curl https://raw.githubusercontent.com/kubernetes/helm/master/scripts/get | bash -s -- -v v2.17.0

WORKDIR /neuromation

# installing dependencies ONLY
COPY setup.py ./
RUN \
    pip install -U pip && \
    pip install -e . && \
    pip uninstall -y platform_operator

COPY platform_operator/ platform_operator/
RUN pip install -e .

ENTRYPOINT ["kopf", "run", "-m", "platform_operator.handlers"]
