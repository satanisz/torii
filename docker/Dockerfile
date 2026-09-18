# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12
ARG PROFILE=vanilla
ARG UV_VERSION=0.11.32
ARG CODE_SERVER_VERSION=4.131.0

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM codercom/code-server:${CODE_SERVER_VERSION} AS code-server

FROM python:${PYTHON_VERSION}-slim-trixie AS python-environment

ARG PROFILE

ENV DEBIAN_FRONTEND=noninteractive \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

COPY --from=uv /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        gfortran \
        git \
        libffi-dev \
        libhdf5-dev \
        libopenblas-dev \
        libssl-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY docker/requirements/ /tmp/requirements/
COPY docker/constraints/ /tmp/constraints/

RUN set -eux; \
    sed -i 's/\r$//' /tmp/requirements/*.txt /tmp/constraints/*.txt; \
    test -f "/tmp/requirements/${PROFILE}.txt"; \
    uv venv "${VIRTUAL_ENV}"; \
    grep -E '^(torch|torchvision|torchaudio)([<>=!~].*)?$' "/tmp/requirements/${PROFILE}.txt" > /tmp/pytorch-requested.txt || true; \
    grep -Ev '^(torch|torchvision|torchaudio)([<>=!~].*)?$' "/tmp/requirements/${PROFILE}.txt" > /tmp/general.txt; \
    sed -i -E 's/^xgboost([<>=!~].*)?$/xgboost-cpu\1/' /tmp/general.txt; \
    if test -s /tmp/pytorch-requested.txt; then \
        if grep -q '^torchaudio' /tmp/pytorch-requested.txt; then \
            cp /tmp/constraints/pytorch-full-cpu.txt /tmp/pytorch-cpu.txt; \
        else \
            cp /tmp/constraints/pytorch-core-cpu.txt /tmp/pytorch-cpu.txt; \
        fi; \
        uv pip install --python "${VIRTUAL_ENV}/bin/python" \
            --index https://download.pytorch.org/whl/cpu \
            --index-strategy first-index \
            --requirements /tmp/pytorch-cpu.txt; \
    fi; \
    uv pip install --python "${VIRTUAL_ENV}/bin/python" \
        --constraint /tmp/constraints/python-compatibility.txt \
        --requirements /tmp/general.txt; \
    mkdir -p /opt/datahub-mlflow-venv; \
    if test -f "/tmp/requirements/${PROFILE}-datahub-mlflow.txt"; then \
        uv venv /opt/datahub-mlflow-venv; \
        uv pip install --python /opt/datahub-mlflow-venv/bin/python \
            --requirements "/tmp/requirements/${PROFILE}-datahub-mlflow.txt"; \
        uv pip check --python /opt/datahub-mlflow-venv/bin/python; \
    fi; \
    uv pip check --python "${VIRTUAL_ENV}/bin/python"; \
    if grep -q '^tables\([<>=!~].*\)\?$' /tmp/general.txt; then \
        "${VIRTUAL_ENV}/bin/python" -c "import tables"; \
    fi; \
    if test -s /tmp/pytorch-requested.txt; then \
        "${VIRTUAL_ENV}/bin/python" -c "import torch; assert torch.version.cuda is None, torch.version.cuda"; \
        if grep -q '^torchaudio' /tmp/pytorch-requested.txt; then \
            "${VIRTUAL_ENV}/bin/python" -c "import torchaudio, torch; assert torchaudio.__version__.split('+')[0] == torch.__version__.split('+')[0]"; \
        fi; \
        if uv pip list --python "${VIRTUAL_ENV}/bin/python" --format freeze | grep -qi '^nvidia-'; then \
            echo "Unexpected NVIDIA package in a CPU-only profile" >&2; \
            exit 1; \
        fi; \
    fi

FROM python:${PYTHON_VERSION}-slim-trixie AS runtime

ARG PYTHON_VERSION
ARG PROFILE
ARG USER_ID=1001
ARG GROUP_ID=1001

ENV DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/home/torii \
    WORKSPACE_DIR=/workspace \
    WORKSPACE_IDE=jupyter \
    WORKSPACE_AUTH_MODE=auto \
    TORII_PROFILE=${PROFILE} \
    TORII_PYTHON=${PYTHON_VERSION} \
    AUTOML_PROFILE=${PROFILE} \
    AUTOML_PYTHON=${PYTHON_VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        openssh-client \
        procps \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${GROUP_ID}" torii \
    && useradd --uid "${USER_ID}" --gid torii --create-home --shell /bin/bash torii \
    && printf '%s\n' \
        'export VIRTUAL_ENV=/opt/venv' \
        'export PATH="/opt/venv/bin:${PATH}"' \
        > /etc/profile.d/torii-venv.sh \
    && mkdir -p /workspace /opt/torii/scaffold \
    && chown -R torii:torii /workspace /opt/torii /home/torii

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=python-environment --chown=torii:torii /opt/venv /opt/venv
COPY --from=python-environment --chown=torii:torii /opt/datahub-mlflow-venv /opt/datahub-mlflow-venv
COPY --from=code-server /usr/bin/code-server /usr/bin/code-server
COPY --from=code-server /usr/lib/code-server /usr/lib/code-server
COPY --chown=torii:torii scaffold/ /opt/torii/scaffold/
COPY --chmod=0755 docker/scripts/initialize-workspace.sh /usr/local/bin/initialize-workspace
COPY --chmod=0755 docker/scripts/workspace-entrypoint.sh /usr/local/bin/workspace-entrypoint

LABEL org.opencontainers.image.title="Torii workspace" \
      org.opencontainers.image.description="Local-first Python ML workspace with JupyterLab, code-server and a safe project scaffold" \
      io.torii.python="${PYTHON_VERSION}" \
      io.torii.profile="${PROFILE}"

USER torii
WORKDIR /workspace

EXPOSE 8888 8080

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/workspace-entrypoint"]
